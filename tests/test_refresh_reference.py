"""``scripts/refresh_reference.py`` on its samples, and the packaged files it wrote.

The samples under ``tests/fixtures/files/`` were cut by the script's ``--samples`` run
from the answers it packaged (``tests/fixtures/files/README.md`` names each one's
release, URL, sha256 and fetch time): a folder of the table of contents with two of its
leaves, one of them a dataset with a pre-defined table under it, and the STATINFO
codelist whole. The tests assert the readers' shape, never values or sizes (conventions
§10). Nothing here sends a request: the refresh's two operations, ``getTocXml`` and
``codeListQuery``, are replayed with ``respx`` serving those samples as the answers, and
the live smoke tests in ``tests/test_live.py`` read upstream's current answers with the
same functions.
"""

import importlib.util
import json
import re
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

import httpx
import pytest
import respx
from xippios.core import PackagedList, parse
from xippios.core.testing import sent_urls

from xippios.eurostat import params
from xippios.eurostat._client import BASE_URL
from xippios.eurostat.models import Code, Codelist, Dataset, LeafType

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "refresh_reference.py"
SAMPLES = ROOT / "tests" / "fixtures" / "files"
TOC_SAMPLE = SAMPLES / "toc" / "apro_mk.xml"
CODELIST_SAMPLE = SAMPLES / "codelist" / "statinfo.json"
REFERENCE = ROOT / "src" / "xippios" / "eurostat" / "reference"
FETCHED = datetime(2026, 10, 27, 12, 0, 0, tzinfo=UTC)


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("refresh_reference", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


script = load_script()


def statinfo() -> tuple[dict[str, Any], Codelist]:
    payload: dict[str, Any] = json.loads(CODELIST_SAMPLE.read_text(encoding="utf-8"))
    return payload, parse(Codelist, payload, source="eurostat", endpoint="codeListQuery")


def test_read_toc_reads_every_leaf_with_its_folders() -> None:
    toc = script.read_toc(TOC_SAMPLE)
    assert re.fullmatch(r"\d{8}T\d{4}", toc.creation_date)
    leaves: list[Dataset] = toc.leaves
    assert leaves
    assert all(isinstance(leaf, Dataset) for leaf in leaves)
    assert all(leaf.code and leaf.title and leaf.path for leaf in leaves)
    assert all(re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", leaf.last_update) for leaf in leaves)
    folders = {leaf.path for leaf in leaves if leaf.type == LeafType.DATASET}
    assert len(folders) == 1, "the sample's datasets sit in one folder"
    (folder,) = folders
    assert folder.count(script.PATH_SEPARATOR) >= 1, "the folders above it, top first"


def test_read_toc_reads_a_table_under_a_dataset_after_it() -> None:
    """A pre-defined table filed under a dataset: its path ends with the dataset's title,
    and it follows the dataset, in the tree's order."""
    leaves: list[Dataset] = script.read_toc(TOC_SAMPLE).leaves
    tables = [index for index, leaf in enumerate(leaves) if leaf.type == LeafType.TABLE]
    assert tables, "the sample keeps a table under a dataset"
    for index in tables:
        table = leaves[index]
        above = next(
            leaf
            for leaf in reversed(leaves[:index])
            if leaf.type == LeafType.DATASET
            and table.path == f"{leaf.path}{script.PATH_SEPARATOR}{leaf.title}"
        )
        assert above.code != table.code


def test_toc_parser_reads_a_stream_in_pieces() -> None:
    data = TOC_SAMPLE.read_bytes()
    root_tag_end = data.index(b">", data.index(b"<nt:tree")) + 1
    parser = script.TocParser()
    parser.feed(data[:root_tag_end])
    assert parser.creation_date == script.read_toc(TOC_SAMPLE).creation_date
    assert parser.completed == 0
    for start in range(root_tag_end, len(data), 97):
        parser.feed(data[start : start + 97])
    toc = parser.close()
    assert toc == script.read_toc(TOC_SAMPLE)
    assert parser.completed == len(toc.leaves)


def test_toc_parser_refuses_another_document() -> None:
    parser = script.TocParser()
    with pytest.raises(ValueError, match="not the table of contents"):
        parser.feed(b"<html><body/></html>")


def test_toc_list_is_a_packaged_list_of_the_leaves(tmp_path: Path) -> None:
    toc = script.read_toc(TOC_SAMPLE)
    script.toc_list(toc, FETCHED).write(tmp_path / "toc.json")
    written = json.loads((tmp_path / "toc.json").read_text(encoding="utf-8"))
    assert list(written) == ["param", "endpoint", "fetched", "records"]
    assert written["param"] == "datasetCode"
    assert written["endpoint"] == "catalogue/toc/xml"
    assert written["fetched"] == "2026-10-27T12:00:00Z"
    assert set(written["records"][0]) == {
        "code",
        "type",
        "title",
        "path",
        "lastUpdate",
        "lastModified",
        "dataStart",
        "dataEnd",
        "values",
    }
    packaged = PackagedList.model_validate(written)
    assert packaged.parse(Dataset, source="eurostat") == toc.leaves
    info = script.toc_info(toc)
    assert info.kind == "toc"
    assert info.creation_date == toc.creation_date
    assert info.count == len(toc.leaves)


def test_codelist_list_keeps_upstream_order_and_labels() -> None:
    payload, codelist = statinfo()
    packaged = script.codelist_list(codelist, FETCHED)
    assert packaged.param == "statinfo"
    assert packaged.endpoint == "sdmx/2.1/codelist/ESTAT/STATINFO"
    assert packaged.fetched == FETCHED
    assert [record["code"] for record in packaged.records] == payload["category"]["index"]
    assert all(
        record["label"] == payload["category"]["label"][record["code"]]
        for record in packaged.records
    )
    assert packaged.parse(Code, source="eurostat") == codelist.codes()


def test_codelist_info_reads_the_release_identifiers() -> None:
    payload, codelist = statinfo()
    info = script.codelist_info(codelist)
    assert info.name == "statinfo"
    assert info.kind == "codelist"
    assert info.id == payload["extension"]["id"] == "STATINFO"
    assert info.label == payload["label"]
    assert info.version == payload["extension"]["version"]
    assert info.last_updated is not None
    assert datetime.fromisoformat(info.last_updated).utcoffset() is not None
    assert info.count == len(payload["category"]["index"])
    assert info.dump_upstream()["LAST_UPDATED"] == info.last_updated


def test_samples_are_listed_with_their_provenance() -> None:
    readme = (SAMPLES / "README.md").read_text(encoding="utf-8")
    for sample in (TOC_SAMPLE, CODELIST_SAMPLE):
        assert f"| `{sample.relative_to(SAMPLES)}` |" in readme
        assert sample.stat().st_size < 256 * 1024
    assert (
        TOC_SAMPLE.read_text(encoding="utf-8")
        .splitlines()[1]
        .startswith("<!-- Cut by scripts/refresh_reference.py")
    )


def test_every_packaged_list_is_indexed() -> None:
    """``lists.json`` is plain JSON with keys of its own, no packaged list: it names no
    upstream operation; every packaged list has one record in it."""
    raw = json.loads((REFERENCE / "lists.json").read_text(encoding="utf-8"))
    assert list(raw) == ["fetched", "lists"]
    index = params.index()
    assert index.fetched == datetime.fromisoformat(raw["fetched"])
    infos = params.list_info()
    assert list(infos) == list(params.PACKAGED_LISTS)
    for name, info in infos.items():
        packaged = PackagedList.load(params.PACKAGE, name)
        assert len(packaged.records) == info.count
        assert packaged.fetched <= index.fetched + timedelta(seconds=5)
    assert {info.id for info in infos.values() if info.kind == "codelist"} == set(params.CODELISTS)
    stems = sorted(path.stem for path in REFERENCE.glob("*.json"))
    assert stems == sorted([params.INDEX, *params.PACKAGED_LISTS])
    readme = (REFERENCE / "README.md").read_text(encoding="utf-8")
    assert "| `lists.json` |" not in readme, "a derived index has no origin row"
    assert all(f"| `{name}.json` |" in readme for name in params.PACKAGED_LISTS)


def test_render_only_reproduces_the_committed_enums(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No list is an enum: ``--render-only`` renders the empty module that is committed."""
    target = tmp_path / "enums.py"
    monkeypatch.setattr(script, "ENUMS", target)
    script.main(["--render-only"])
    committed = (ROOT / "src" / "xippios" / "eurostat" / "enums.py").read_text(encoding="utf-8")
    assert target.read_text(encoding="utf-8") == committed
    assert script.LISTS == {}
    assert script.ID_LISTS == {}


def test_refresh_writes_every_file_from_replayed_answers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, respx_mock: respx.MockRouter
) -> None:
    """The whole refresh, offline: ``getTocXml`` downloads the TOC sample and
    ``codeListQuery`` answers the STATINFO sample, served by ``respx`` (no request), into
    a reference directory of the test's own, the codelists cut to STATINFO."""
    toc_route = respx_mock.get(f"{BASE_URL}/catalogue/toc/xml").mock(
        return_value=httpx.Response(
            200,
            content=TOC_SAMPLE.read_bytes(),
            headers={"Content-Type": "application/xml;charset=UTF-8"},
        )
    )
    codelist_route = respx_mock.get(f"{BASE_URL}/sdmx/2.1/codelist/ESTAT/STATINFO").mock(
        return_value=httpx.Response(
            200, content=CODELIST_SAMPLE.read_bytes(), headers={"Content-Type": "application/json"}
        )
    )
    reference = tmp_path / "reference"
    reference.mkdir()
    shutil.copy(REFERENCE / "README.md", reference / "README.md")
    monkeypatch.setattr(script, "REFERENCE", reference)
    monkeypatch.setattr(script, "ENUMS", tmp_path / "enums.py")
    monkeypatch.setattr(params, "CODELISTS", ("STATINFO",))
    script.main([])

    assert sent_urls(toc_route) == [f"{BASE_URL}/catalogue/toc/xml"]
    assert sent_urls(codelist_route) == [
        f"{BASE_URL}/sdmx/2.1/codelist/ESTAT/STATINFO?format=JSON&lang=en"
    ]
    expected = script.read_toc(TOC_SAMPLE)
    toc = PackagedList.model_validate_json((reference / "toc.json").read_text(encoding="utf-8"))
    assert toc.param == "datasetCode"
    assert toc.endpoint == "catalogue/toc/xml"
    assert toc.parse(Dataset, source="eurostat") == expected.leaves
    payload, codelist = statinfo()
    codes = PackagedList.model_validate_json(
        (reference / "statinfo.json").read_text(encoding="utf-8")
    )
    assert codes.endpoint == "sdmx/2.1/codelist/ESTAT/STATINFO"
    assert codes.parse(Code, source="eurostat") == codelist.codes()
    index = json.loads((reference / "lists.json").read_text(encoding="utf-8"))
    assert list(index) == ["fetched", "lists"]
    assert [entry["name"] for entry in index["lists"]] == ["toc", "statinfo"]
    assert index["lists"][0]["creationDate"] == expected.creation_date
    assert index["lists"][1]["version"] == payload["extension"]["version"]
    assert datetime.fromisoformat(index["fetched"]) >= codes.fetched
    readme = (reference / "README.md").read_text(encoding="utf-8")
    assert "| `toc.json` | `catalogue/toc/xml` |" in readme
    assert "| `statinfo.json` | `sdmx/2.1/codelist/ESTAT/STATINFO` |" in readme
    assert "| `lists.json` |" not in readme
    assert (tmp_path / "enums.py").read_text(encoding="utf-8").startswith('"""Enums of the')
