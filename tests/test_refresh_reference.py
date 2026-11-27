"""``scripts/refresh_reference.py``'s declaration on its samples, and the packaged files.

The script declares the nineteen lists in one ``Lists`` and hands it to core's ``run``,
which fetches and writes the files and the provenance rows, and no ``enums.py``, since no
list declares an enum (sdk-core ADR-0062): core tests that frame, and these tests hold
what the script declares and what it writes beside the lists, ``lists.json`` and the
samples. The samples under ``tests/fixtures/files/`` were cut by the script's
``--samples`` cutter from upstream's answers (``tests/fixtures/files/README.md`` names
each one's release, URL, sha256 and fetch time): a folder of the table of contents with
two of its leaves, one of them a dataset with a pre-defined table under it; from a later
download, a folder with a pre-defined table that prints no number of values; and the
STATINFO codelist whole. The tests assert the readers' shape, never values or sizes
(conventions §10). Nothing here sends a request: the refresh's two operations,
``getTocXml`` and ``codeListQuery``, are served by ``respx`` with those samples, and the
live smoke tests in ``tests/test_live.py`` read upstream's current answers with the same
fetches. The tests that run the script's ``main`` run core's frame on a copy of the
package's ``reference/`` folder, so that the repository's files stay as committed; the
Comext base's codelists are checked on the committed files.
"""

import importlib.util
import json
import re
import shutil
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

import httpx
import pytest
import respx
from xippios.core import PackagedList, XippiosError, parse, sync
from xippios.core.testing import mcp_call, sent_urls

from xippios.eurostat import params
from xippios.eurostat._client import BASE_URL, COMEXT_BASE_URL, client
from xippios.eurostat.mcp import server
from xippios.eurostat.models import Code, Codelist, Dataset, LeafType

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "refresh_reference.py"
SAMPLES = ROOT / "tests" / "fixtures" / "files"
TOC_SAMPLE = SAMPLES / "toc" / "apro_mk.xml"
TOC_SAMPLE_WITHOUT_VALUES = SAMPLES / "toc" / "ai.xml"
CODELIST_SAMPLE = SAMPLES / "codelist" / "statinfo.json"
REFERENCE = ROOT / "src" / "xippios" / "eurostat" / "reference"
FETCHED = datetime(2026, 10, 27, 12, 0, 0, tzinfo=UTC)
HEADER = "| File | Origin | Fetched |"
TOC_URL = f"{BASE_URL}/catalogue/toc/xml"
STATINFO_URL = f"{BASE_URL}/sdmx/2.1/codelist/ESTAT/STATINFO"
FREQ_URL = f"{BASE_URL}/sdmx/2.1/codelist/ESTAT/FREQ"


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("refresh_reference", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


script = load_script()
LISTED = {listed.name: listed for listed in script.LISTS.lists}


def statinfo() -> tuple[dict[str, Any], Codelist]:
    payload: dict[str, Any] = json.loads(CODELIST_SAMPLE.read_text(encoding="utf-8"))
    return payload, parse(Codelist, payload, source="eurostat", endpoint="codeListQuery")


def serve_toc(respx_mock: respx.MockRouter) -> respx.Route:
    """``getTocXml`` answered with the TOC sample.

    NOT RECORDED as served: the sample under ``tests/fixtures/files/toc/``, cut from a
    whole answer of the operation, served in memory at the operation's own URL, where
    upstream answers alike with the whole tree (conventions §10, kind 3).
    """
    return respx_mock.get(TOC_URL).mock(
        return_value=httpx.Response(
            200,
            content=TOC_SAMPLE.read_bytes(),
            headers={"Content-Type": "application/xml;charset=UTF-8"},
        )
    )


def serve_statinfo(respx_mock: respx.MockRouter, url: str = STATINFO_URL) -> respx.Route:
    """``codeListQuery`` answered with the STATINFO sample at ``url``.

    NOT RECORDED as served: the sample under ``tests/fixtures/files/codelist/``, the whole
    answer of the operation as decoded, served in memory at its own URL or at the Comext
    base's, where the test asserts only what was sent and what is written from it
    (conventions §10, kind 3).
    """
    return respx_mock.get(url).mock(
        return_value=httpx.Response(
            200, content=CODELIST_SAMPLE.read_bytes(), headers={"Content-Type": "application/json"}
        )
    )


def serve_unavailable(respx_mock: respx.MockRouter, url: str) -> respx.Route:
    """``url`` answered with a bare 503.

    NOT RECORDED: a body of no shape upstream sends, to show that the script leaves a
    server error to core's client and the frame, which send it once (conventions §10,
    kind 5).
    """
    return respx_mock.get(url).mock(return_value=httpx.Response(503, text="Service Unavailable"))


@pytest.fixture
def copied_package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """The package's ``reference/`` folder in a package of the test's own.

    Core's frame writes into the package's directory as imported, which must lie in the
    directory the script runs in, so the declaration is pointed at a copy under
    ``tmp_path`` and the run runs there: the repository's files stay as committed. The
    samples go to a folder of the test's own as well.

    Returns:
        The copy's ``reference/`` folder.
    """
    package = tmp_path / "copied_eurostat"
    shutil.copytree(REFERENCE, package / "reference")
    (package / "__init__.py").write_text("", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(script, "LISTS", replace(script.LISTS, package=package.name))
    monkeypatch.setattr(script, "SAMPLES", tmp_path / "files")
    yield package / "reference"
    script.RUN.start(samples=False)


def readme_rows(reference: Path) -> dict[str, str]:
    """The provenance table's rows by their file, under the frame's one header."""
    text = (reference / "README.md").read_text(encoding="utf-8")
    rows = text.partition(f"{HEADER}\n| --- | --- | --- |\n")[2]
    return {line.split("`")[1]: line for line in rows.splitlines() if line.startswith("| `")}


def files_of(reference: Path) -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in sorted(reference.iterdir())}


def test_the_lists_are_the_packaged_lists_in_one_declaration() -> None:
    """One ``Lists`` of nineteen ``Listed``, the TOC first and the codelists in
    ``params.CODELISTS``' order, each a finished table of its endpoint and dimension."""
    lists = script.LISTS
    assert lists.package == params.PACKAGE
    assert tuple(lists.packaged) == params.PACKAGED_LISTS
    assert [listed.name for listed in lists.lists] == list(params.PACKAGED_LISTS)
    assert len(lists.lists) == 19
    assert lists.client is client
    assert lists.quota_header is None, "Eurostat reports its quota in no header"
    toc = LISTED[params.TOC]
    assert (toc.endpoint, toc.param) == ("catalogue/toc/xml", "datasetCode")
    for resource_id, origin in params.CODELISTS.items():
        listed = LISTED[resource_id.lower()]
        assert listed.endpoint == script.codelist_endpoint(resource_id)
        assert listed.param == origin.param
    assert all(listed.enum is None for listed in lists.lists), "tables, no enum"
    assert all(listed.origin is None for listed in lists.lists), "the endpoint is the origin"


def test_the_committed_provenance_rows_are_the_declared_lists() -> None:
    """The rows core's frame writes: each list's endpoint and its file's fetch time, in the
    declared order, under the frame's one header."""
    readme = (REFERENCE / "README.md").read_text(encoding="utf-8")
    rows = [line for line in readme.splitlines() if line.startswith("| `")]
    assert rows == [
        f"| `{listed.name}.json` | `{params.packaged(listed.name).endpoint}` | "
        f"{params.packaged(listed.name).fetched:%Y-%m-%dT%H:%M:%SZ} |"
        for listed in script.LISTS.lists
    ]
    assert f"{HEADER}\n| --- | --- | --- |\n" in readme


def test_the_readme_example_shows_the_first_packaged_geo_record() -> None:
    """The README's example prints GEO's first record as the refresh packaged it, so a
    refresh that changes the record fails here until the example follows."""
    readme = (REFERENCE / "README.md").read_text(encoding="utf-8")
    shown = re.search(r"^geo\.records\[0\]  # (\{.*\})$", readme, re.MULTILINE)
    assert shown is not None, "the example of GEO's first record"
    geo = PackagedList.load(params.PACKAGE, "geo")
    assert json.loads(shown.group(1)) == geo.records[0]


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


def test_read_toc_reads_a_leaf_that_prints_no_number_of_values() -> None:
    """A leaf whose ``values`` element is empty, as upstream printed a pre-defined table,
    reads with ``values`` ``None`` and its other fields as printed
    (https://github.com/xippios/sdk-eurostat/issues/72)."""
    values = script._tag("values")
    printed = [
        leaf.findtext(script.CODE)
        for leaf in ET.parse(TOC_SAMPLE_WITHOUT_VALUES).getroot().iter(script.LEAF)
        if leaf.find(values) is not None and not leaf.findtext(values)
    ]
    assert printed, "the sample keeps a leaf whose values element is empty"
    leaves: list[Dataset] = script.read_toc(TOC_SAMPLE_WITHOUT_VALUES).leaves
    without = [leaf for leaf in leaves if leaf.values is None]
    assert [leaf.code for leaf in without] == printed
    for leaf in without:
        assert leaf.title
        assert leaf.path
        assert re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", leaf.last_update)
        assert re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", leaf.last_modified)


def test_toc_list_writes_an_absent_number_of_values_as_null(tmp_path: Path) -> None:
    """The packaged table keeps the leaf: ``values`` is written as ``null`` under its
    upstream name and read back as ``None``."""
    toc = script.read_toc(TOC_SAMPLE_WITHOUT_VALUES)
    script.toc_list(toc, FETCHED).write(tmp_path / "toc.json")
    written = json.loads((tmp_path / "toc.json").read_text(encoding="utf-8"))
    nulls = [record for record in written["records"] if record["values"] is None]
    assert [record["code"] for record in nulls] == [
        leaf.code for leaf in toc.leaves if leaf.values is None
    ]
    assert nulls, "the sample's leaf without a number of values is packaged"
    packaged = PackagedList.model_validate(written)
    assert packaged.parse(Dataset, source="eurostat") == toc.leaves


@pytest.mark.anyio
async def test_list_datasets_tool_serves_an_absent_number_of_values_as_null(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``eurostat_list_datasets`` serves the leaf with every field, ``values`` ``null``.

    The table is the one the script packages from the sample, in place of the package's
    own, so the test holds whatever leaves a refresh packages."""
    toc = script.read_toc(TOC_SAMPLE_WITHOUT_VALUES)
    script.toc_list(toc, FETCHED).write(tmp_path / "toc.json")
    packaged = PackagedList.model_validate_json((tmp_path / "toc.json").read_text(encoding="utf-8"))
    leaves = packaged.parse(Dataset, source="eurostat")
    monkeypatch.setattr(params, "datasets", lambda: list(leaves))
    payload = await mcp_call(server, "eurostat_list_datasets", {})
    assert "note" not in payload
    served = [leaf for leaf in payload["data"] if leaf["values"] is None]
    assert [leaf["code"] for leaf in served] == [
        leaf.code for leaf in leaves if leaf.values is None
    ]
    assert served
    assert all(set(leaf) == set(Dataset.model_fields) for leaf in served)


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


def test_the_codelist_fetch_packages_the_answer_and_keeps_its_record(
    respx_mock: respx.MockRouter,
) -> None:
    """STATINFO's declared fetch: one request, the finished list of its codes, and its
    record for ``lists.json`` kept for the declaration's ``after``."""
    route = serve_statinfo(respx_mock)
    script.RUN.start(samples=False)
    packaged = sync(LISTED["statinfo"].fetch)()
    assert sent_urls(route) == [f"{STATINFO_URL}?format=JSON&lang=en"]
    _, codelist = statinfo()
    assert isinstance(packaged, PackagedList)
    assert (packaged.endpoint, packaged.param) == ("sdmx/2.1/codelist/ESTAT/STATINFO", "statinfo")
    assert packaged.parse(Code, source="eurostat") == codelist.codes()
    assert script.RUN.infos == {"statinfo": script.codelist_info(codelist)}
    assert script.RUN.pending == [], "no sample outside a --samples run"
    script.RUN.start(samples=False)


def test_a_codelist_is_fetched_on_its_base_with_its_dimension(
    monkeypatch: pytest.MonkeyPatch, respx_mock: respx.MockRouter
) -> None:
    """The fetch asks ``params.CODELISTS`` for a codelist's base and dimension: with
    STATINFO's origin moved to the Comext base and another dimension, the request goes to
    the Comext base and the list records its full URL and that dimension."""
    url = f"{COMEXT_BASE_URL}/sdmx/2.1/codelist/ESTAT/STATINFO"
    route = serve_statinfo(respx_mock, url)
    moved = params.CodelistOrigin(COMEXT_BASE_URL, "indicators")
    monkeypatch.setattr(params, "CODELISTS", {"STATINFO": moved})
    script.RUN.start(samples=False)
    written = sync(script.fetch_codelist)("STATINFO")
    script.RUN.start(samples=False)
    assert sent_urls(route) == [f"{url}?format=JSON&lang=en"]
    assert written.endpoint == url
    assert written.param == "indicators"


def test_samples_are_listed_with_their_provenance() -> None:
    readme = (SAMPLES / "README.md").read_text(encoding="utf-8")
    for sample in (TOC_SAMPLE, TOC_SAMPLE_WITHOUT_VALUES, CODELIST_SAMPLE):
        assert f"| `{sample.relative_to(SAMPLES)}` |" in readme
        assert sample.stat().st_size < 256 * 1024
    for sample in (TOC_SAMPLE, TOC_SAMPLE_WITHOUT_VALUES):
        assert (
            sample.read_text(encoding="utf-8")
            .splitlines()[1]
            .startswith("<!-- Cut by scripts/refresh_reference.py")
        )


def test_samples_option_cuts_every_toc_sample() -> None:
    """Each sample under ``toc/`` is one that ``--samples`` cuts, so a run with it writes
    its row again and never leaves a sample without one."""
    cut = {f"{folder}.xml" for folder in script.TOC_SAMPLES}
    assert cut == {path.name for path in (SAMPLES / "toc").iterdir()}


def test_samples_readme_keeps_the_rows_the_script_does_not_cut(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--samples`` writes its samples and rewrites the rows of the kinds it cuts
    (``toc/``, ``codelist/``) and keeps the others, the ``sdmx-csv/`` bodies of the recorded
    ``dataQuery`` exchanges; the committed README is what the script writes."""
    committed = (SAMPLES / "README.md").read_text(encoding="utf-8")
    assert committed.startswith(script.SAMPLES_README)
    rows = [line for line in committed.splitlines() if line.startswith("| `")]
    kept = [line for line in rows if line.startswith("| `sdmx-csv/")]
    assert len(kept) == len(list((SAMPLES / "sdmx-csv").iterdir())), "one row per sample"
    (tmp_path / "README.md").write_text(committed, encoding="utf-8")
    monkeypatch.setattr(script, "SAMPLES", tmp_path)
    toc_row = "| `toc/apro_mk.xml` | a new run's row |"
    sample = script.Sample(tmp_path / "toc" / "apro_mk.xml", "<tree/>\n", toc_row)
    script.write_samples([sample])
    written = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert written == script.SAMPLES_README + "".join(f"{line}\n" for line in [toc_row, *kept])
    assert sample.path.read_text(encoding="utf-8") == "<tree/>\n"


def test_a_samples_run_keeps_the_codelist_answer_as_decoded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, respx_mock: respx.MockRouter
) -> None:
    """In a ``--samples`` run the client keeps the sampled codelist's body as it came, so the
    sample is the answer whole, written again as compact JSON, from the same request; the
    client's configuration is back after the run."""
    route = serve_statinfo(respx_mock)
    monkeypatch.setattr(script, "SAMPLES", tmp_path)
    configured = client.config
    script.RUN.start(samples=True)
    try:
        with script.sampling(client):
            sync(script.fetch_codelist)("STATINFO")
        (cut,) = script.RUN.pending
        sample = cut()
    finally:
        script.RUN.start(samples=False)
    assert client.config is configured
    assert route.call_count == 1, "the sample costs no request of its own"
    payload, _ = statinfo()
    assert sample.path == tmp_path / "codelist" / "statinfo.json"
    assert json.loads(sample.text) == payload
    assert sample.text == CODELIST_SAMPLE.read_text(encoding="utf-8"), "as it was cut"
    assert sample.row.startswith(
        f"| `codelist/statinfo.json` | `{payload['extension']['version']}` (version) | "
        f"{STATINFO_URL}?format=JSON&lang=en | {CODELIST_SAMPLE.stat().st_size} | "
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


@pytest.mark.parametrize("option", ["--render-only", "--render"])
def test_render_only_writes_the_committed_rows_and_no_enums(
    copied_package: Path, option: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """``--render`` is ``--render-only`` as the frame's parser reads an abbreviation: the frame
    writes the provenance rows from the packaged files, sends nothing, writes no ``enums.py``
    and calls no ``after``, so every file stays as committed."""
    before = files_of(copied_package)
    assert script.main([option]) == 0
    out = capsys.readouterr().out
    assert "requests sent" not in out, "the frame fetched nothing"
    assert "enums.py: left alone, no list declares an enum" in out
    assert files_of(copied_package) == before
    assert not (copied_package.parent / "enums.py").exists()


def test_only_two_lists_writes_their_files_their_records_and_their_rows(
    copied_package: Path, respx_mock: respx.MockRouter
) -> None:
    """``--only toc statinfo``, offline: ``getTocXml`` downloads the TOC sample and
    ``codeListQuery`` answers the STATINFO sample. The frame writes both files and their
    rows, and the script's ``after`` their records in ``lists.json``, every other file,
    record and row kept as committed, and the index's ``fetched`` the latest of all."""
    toc_route = serve_toc(respx_mock)
    codelist_route = serve_statinfo(respx_mock)
    before = files_of(copied_package)
    index_before = json.loads(before["lists.json"])
    rows_before = readme_rows(copied_package)
    assert script.main(["--only", "toc", "statinfo"]) == 0

    assert sent_urls(toc_route) == [TOC_URL]
    assert sent_urls(codelist_route) == [f"{STATINFO_URL}?format=JSON&lang=en"]
    after = files_of(copied_package)
    changed = sorted(name for name in after if after[name] != before.get(name))
    assert changed == ["README.md", "lists.json", "statinfo.json", "toc.json"]
    expected = script.read_toc(TOC_SAMPLE)
    toc = PackagedList.model_validate_json(after["toc.json"])
    assert (toc.param, toc.endpoint) == ("datasetCode", "catalogue/toc/xml")
    assert toc.parse(Dataset, source="eurostat") == expected.leaves
    _, codelist = statinfo()
    codes = PackagedList.model_validate_json(after["statinfo.json"])
    assert codes.endpoint == "sdmx/2.1/codelist/ESTAT/STATINFO"
    assert codes.parse(Code, source="eurostat") == codelist.codes()
    index = json.loads(after["lists.json"])
    assert [entry["name"] for entry in index["lists"]] == list(params.PACKAGED_LISTS)
    for old, new in zip(index_before["lists"], index["lists"], strict=True):
        if old["name"] == "toc":
            assert new == script.toc_info(expected).dump_upstream()
        elif old["name"] == "statinfo":
            assert new == script.codelist_info(codelist).dump_upstream()
        else:
            assert new == old, f"{old['name']} kept as committed"
    latest = max(datetime.fromisoformat(index_before["fetched"]), toc.fetched, codes.fetched)
    assert datetime.fromisoformat(index["fetched"]) == latest
    rows = readme_rows(copied_package)
    assert list(rows) == list(rows_before)
    for name, row in rows.items():
        if name == "toc.json":
            assert row == f"| `toc.json` | `catalogue/toc/xml` | {toc.fetched:%Y-%m-%dT%H:%M:%SZ} |"
        elif name == "statinfo.json":
            assert row == (
                "| `statinfo.json` | `sdmx/2.1/codelist/ESTAT/STATINFO` | "
                f"{codes.fetched:%Y-%m-%dT%H:%M:%SZ} |"
            )
        else:
            assert row == rows_before[name], f"{name} kept as committed"


def test_a_failed_fetch_writes_nothing_and_reports_the_requests_sent(
    copied_package: Path, respx_mock: respx.MockRouter, capsys: pytest.CaptureFixture[str]
) -> None:
    """A 5xx spends no second request of upstream's fair use: the frame sends each request
    once, writes nothing when one fails, the index neither, and prints the requests it
    sent; the client's own configuration is back after the run."""
    route = serve_unavailable(respx_mock, STATINFO_URL)
    before = files_of(copied_package)
    configured = client.config
    with pytest.raises(XippiosError):
        script.main(["--only", "statinfo"])
    assert route.call_count == 1, "one attempt, no retry"
    assert files_of(copied_package) == before
    assert "requests sent: 1; quota left: not reported" in capsys.readouterr().out
    assert client.config is configured


def test_a_failed_samples_run_writes_no_sample(
    copied_package: Path, tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    """``--samples`` cuts the TOC's samples while its answer is at hand and writes them
    after the last list: the TOC arrives, the first codelist after it fails, and no sample,
    no README of the samples and no packaged file is written."""
    serve_toc(respx_mock)
    serve_unavailable(respx_mock, FREQ_URL)
    before = files_of(copied_package)
    with pytest.raises(XippiosError):
        script.main(["--samples"])
    assert not (tmp_path / "files").exists(), "no sample written before the last fetch"
    assert files_of(copied_package) == before
    assert script.RUN.pending == [], "the run's samples forgotten after it"
    assert script.RUN.kept() is None, "the kept TOC removed after the run"


@pytest.mark.parametrize(
    "argv", [["--samples", "--only", "statinfo"], ["--render-only", "--samples"]]
)
def test_samples_takes_no_other_option(
    copied_package: Path, respx_mock: respx.MockRouter, argv: list[str]
) -> None:
    before = files_of(copied_package)
    with pytest.raises(SystemExit, match=r"--samples cuts the samples from a run of every list"):
        script.main(argv)
    assert not respx_mock.calls
    assert files_of(copied_package) == before


def test_only_refuses_an_unknown_name_before_any_request(
    copied_package: Path, respx_mock: respx.MockRouter
) -> None:
    """``--only`` takes a list's file name, as the frame's declaration names the lists:
    a codelist's id as upstream writes it is no such name."""
    before = files_of(copied_package)
    with pytest.raises(SystemExit, match=r"--only: no list nace_r2, GEO in toc, freq, geo"):
        script.main(["--only", "nace_r2", "GEO", "geo"])
    assert not respx_mock.calls
    assert files_of(copied_package) == before


def test_the_trade_codelists_follow_the_prodcom_lists_in_the_index() -> None:
    """The three lists of the trade datasets were added with ``--only``: the index and the
    README list them after the Prodcom lists, in ``params.CODELISTS``' order."""
    names = [info.name for info in params.index().lists]
    assert names[-6:] == [
        "cxt_prodcom2_sold",
        "cxt_prodcom2_total",
        "cxt_indicators",
        "cxt_nc",
        "cxt_free_iso",
        "cxt_eu_flux",
    ]
    assert list(readme_rows(REFERENCE))[-3:] == [
        "cxt_nc.json",
        "cxt_free_iso.json",
        "cxt_eu_flux.json",
    ]


def test_codelist_endpoint_is_the_path_on_the_main_base_and_the_url_on_comext() -> None:
    assert script.codelist_endpoint("GEO") == "sdmx/2.1/codelist/ESTAT/GEO"
    assert script.codelist_endpoint("CXT_PRODCOM2_SOLD") == (
        "https://ec.europa.eu/eurostat/api/comext/dissemination/sdmx/2.1/codelist/ESTAT/"
        "CXT_PRODCOM2_SOLD"
    )


@pytest.mark.parametrize(
    ("resource_id", "param"),
    [
        ("CXT_PRODCOM2_SOLD", "product"),
        ("CXT_PRODCOM2_TOTAL", "product"),
        ("CXT_INDICATORS", "indicators"),
        ("CXT_NC", "product"),
        ("CXT_FREE_ISO", "reporter"),
        ("CXT_EU_FLUX", "flow"),
    ],
)
def test_comext_codelists_are_packaged_with_their_url_and_dimension(
    resource_id: str, param: str
) -> None:
    """The six Comext codelists' files: ``endpoint`` the full URL on the Comext base,
    ``param`` the dimension the Statistics API takes, the first in the data structure's
    order for CXT_FREE_ISO, which feeds ``partner`` too
    (https://github.com/xippios/sdk-eurostat/pull/14)."""
    assert params.CODELISTS[resource_id] == params.CodelistOrigin(COMEXT_BASE_URL, param)
    packaged = PackagedList.load(params.PACKAGE, resource_id.lower())
    assert packaged.endpoint == f"{COMEXT_BASE_URL}/sdmx/2.1/codelist/ESTAT/{resource_id}"
    assert packaged.param == param
    readme = (REFERENCE / "README.md").read_text(encoding="utf-8")
    assert f"| `{resource_id.lower()}.json` | `{packaged.endpoint}` |" in readme
    assert params.list_info()[resource_id.lower()].id == resource_id
