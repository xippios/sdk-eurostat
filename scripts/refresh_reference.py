"""Refresh the packaged reference data from upstream (``/refresh-reference-data``).

Eurostat's lists are packaged as tables, not as enums: the Catalogue API's table of
contents (TOC) and the twelve codelists in ``params.CODELISTS``, each too large for an
enum (the design round of 2026-10-27), written with ``PackagedList.write`` to
``reference/<name>.json`` (conventions §3, ADR-0022):

- ``toc.json``: the TOC, downloaded whole to a temporary file through
  ``api.catalogue.get_toc_xml`` (core's ``download``, which streams the body to disk; 23 MB
  on 2026-10-27), then read from that file a megabyte at a time with the standard
  library's ``xml.etree.ElementTree`` pull parser (``TocParser``), each element cleared
  once read: every ``leaf``, datasets and tables alike, with its code, type, English
  title, the English titles of the folders above it joined with ``" > "`` (``path``),
  ``lastUpdate``, ``lastModified``, ``dataStart``, ``dataEnd`` and ``values`` as printed.
  This script is the only code that parses XML (D44; ADR-0020 decision 3).
- ``<codelist>.json``: one codelist each, the latest version in JSON-stat through
  ``api.sdmx.code_list_query`` with English labels (Johannes, 2026-10-27, D1 and D2), its
  codes and labels in upstream's order.
- ``lists.json``: not a packaged list but a derived index, plain JSON with keys of its
  own (``params.ListIndex``): ``fetched``, when the run's last answer arrived, and
  ``lists``, one record per packaged list with what upstream gives each as its release
  (the TOC's ``creationDate``, a codelist's ``version`` and ``LAST_UPDATED``), since a
  packaged file holds its four keys and a ``note`` and nothing else (ADR-0022,
  amendment 8; gap, row 111). It names no upstream operation: it is derived from the
  thirteen answers.

Each packaged file's ``fetched`` is the time its answer arrived, UTC to the second. The
provenance table of ``reference/README.md`` is rewritten from the packaged files. Run
from the repository root, without a key (the API takes none)::

    uv run python scripts/refresh_reference.py

Thirteen keyless requests: the TOC and twelve codelists, paced by the package client.
``--samples`` also cuts the parser tests' samples from the same answers, without a
request of its own: a folder of the TOC with two of its leaves and the folders above it
under ``tests/fixtures/files/toc/``, and the STATINFO codelist whole under
``tests/fixtures/files/codelist/``, their provenance in ``tests/fixtures/files/README.md``
(ADR-0020 decision 6, conventions §10). The TOC's cut parses the whole file again with
``ElementTree.parse``, about 200 MB at its peak: fine for a one-off run, not for the
plain refresh, which reads the file a megabyte at a time.

Value lists and lists of integer ids would become enums: a value list in ``LISTS`` a
``StrEnum``, a list of ids and names in ``ID_LISTS``, through ``id_name_pairs``, an
``IntEnum`` (conventions §3), rendered into ``enums.py`` with one
``xippios.core.reference.render_enums`` call, ASCII-only, and formatted with
``ruff format`` and ``ruff check --fix``, to be committed as formatted (ADR-0008,
amendment 2026-10-27). Eurostat's lists are neither, so both mappings stay empty and
``enums.py`` is an empty module. ``--render-only`` regenerates it from the packaged
files alone, without a request: after a core release changes the renderer (conventions
§15, item 6), it changes ``enums.py`` and nothing else.
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections.abc import Callable, Coroutine, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NamedTuple

from xippios.core import Downloaded, PackagedList, UpstreamModel, sync
from xippios.core.reference import id_name_pairs, render_enums

from xippios.eurostat import api, params
from xippios.eurostat._client import BASE_URL
from xippios.eurostat.models import Codelist, Dataset
from xippios.eurostat.params import ListInfo

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = ROOT / "src/xippios/eurostat"
REFERENCE = PACKAGE_DIR / "reference"
ENUMS = PACKAGE_DIR / "enums.py"
GENERATOR = "scripts/refresh_reference.py"
SAMPLES = ROOT / "tests/fixtures/files"

LISTS: dict[str, Callable[[], Coroutine[Any, Any, list[str]]]] = {}
"""Value lists, one ``StrEnum`` each: Eurostat's packaged lists are tables, none is one."""

ID_LISTS: dict[
    str, tuple[str, str, Callable[[], Coroutine[Any, Any, Sequence[UpstreamModel]]]]
] = {}
"""Lists of integer ids and names, one ``IntEnum`` each (conventions §3): none either."""

NAVTREE = "urn:eu.europa.ec.eurostat.navtree"
"""The namespace of the TOC's XML (``TableOfContent.xsd``)."""

XSI = "http://www.w3.org/2001/XMLSchema-instance"

PATH_SEPARATOR = " > "
"""What joins the folder titles of a leaf's ``path``."""

TOC_PARAM = "datasetCode"
"""What a TOC leaf's code feeds: the Statistics API's ``datasetCode`` (``getData``)."""

LANG = "en"
"""The codelists' language: English labels, as the TOC's English titles."""

SAMPLE_FOLDER = "apro_mk"
"""The TOC folder the sample keeps: "Milk and milk products"."""

SAMPLE_LEAVES = ("apro_mk_cola", "apro_mk_farm")
"""The leaves of ``SAMPLE_FOLDER`` the sample keeps: a dataset without tables under it
and one with a pre-defined table under it."""

SAMPLE_CODELIST = "STATINFO"
"""The codelist the sample keeps whole: 18 KB on 2026-10-27."""

SAMPLE_KINDS = ("toc", "codelist")
"""The sample kinds this script cuts; the README rows of any other kind are kept as they
are (``sdmx-csv/``, the bodies of the recorded ``dataQuery`` exchanges)."""


def _tag(name: str) -> str:
    return f"{{{NAVTREE}}}{name}"


TREE, BRANCH, LEAF, TITLE, CODE = map(_tag, ("tree", "branch", "leaf", "title", "code"))


def _text(element: ET.Element, name: str) -> str | None:
    """The text of ``element``'s child ``name``, ``None`` when it is absent or empty."""
    text = element.findtext(_tag(name))
    return text if text else None


def _english_title(element: ET.Element) -> str | None:
    return next(
        (title.text for title in element.findall(TITLE) if title.get("language") == "en"), None
    )


class Toc(NamedTuple):
    """The table of contents as read: its ``creationDate`` and its leaves in tree order."""

    creation_date: str | None
    leaves: list[Dataset]


@dataclass
class _Node:
    """A branch or leaf the reader is inside: its English title, its place if a leaf."""

    slot: int | None
    title: str | None = None


class TocParser:
    """Reads the TOC's XML incrementally: ``feed`` it bytes in pieces, then ``close`` it.

    The refresh feeds it the downloaded file a megabyte at a time; the live smoke test
    feeds it a stream. ``creation_date`` is known once the root element has started, and
    ``completed`` counts the leaves read so far, so a reader of a stream can stop early. Every
    ``leaf`` becomes one ``Dataset``, wherever it sits: under a folder, or under a
    dataset, as a pre-defined table can. Its ``path`` joins the English titles of every
    branch and leaf above it, top first. Each element is cleared once read, so the tree
    is never held whole.

    Attributes:
        creation_date: The root's ``creationDate`` as printed, e.g. ``"20261027T1000"``;
            ``None`` before the root has started or when it carries none.
        completed: The leaves read so far.
    """

    def __init__(self) -> None:
        self.creation_date: str | None = None
        self.completed = 0
        self._parser: ET.XMLPullParser[ET.Element] = ET.XMLPullParser(events=("start", "end"))
        self._stack: list[_Node] = []
        self._leaves: list[Dataset | None] = []
        self._rooted = False

    def feed(self, chunk: bytes) -> None:
        """Read ``chunk``, the next bytes of the XML.

        Raises:
            ValueError: The document is not the TOC: its root is not the navigation
                tree's ``tree``.
            xml.etree.ElementTree.ParseError: The bytes are not well-formed XML.
            pydantic.ValidationError: A leaf lacks what a ``Dataset`` needs.
        """
        self._parser.feed(chunk)
        self._read()

    def close(self) -> Toc:
        """End the document and return what was read.

        Raises:
            xml.etree.ElementTree.ParseError: The document ends before it is complete.
        """
        self._parser.close()
        self._read()
        leaves = [leaf for leaf in self._leaves if leaf is not None]
        return Toc(creation_date=self.creation_date, leaves=leaves)

    def leaves(self) -> list[Dataset]:
        """The leaves read completely so far, in tree order."""
        return [leaf for leaf in self._leaves if leaf is not None]

    def _read(self) -> None:
        for event in self._parser.read_events():
            element = event[-1]
            if not isinstance(element, ET.Element):
                continue
            if event[0] == "start":
                self._start(element)
            else:
                self._end(element)

    def _start(self, element: ET.Element) -> None:
        if not self._rooted:
            if element.tag != TREE:
                raise ValueError(f"not the table of contents: the root is {element.tag!r}")
            self._rooted = True
            self.creation_date = element.get("creationDate")
        if element.tag == BRANCH:
            self._stack.append(_Node(slot=None))
        elif element.tag == LEAF:
            self._stack.append(_Node(slot=len(self._leaves)))
            self._leaves.append(None)

    def _end(self, element: ET.Element) -> None:
        if element.tag == TITLE and element.get("language") == "en" and self._stack:
            node = self._stack[-1]
            if node.title is None:
                node.title = element.text
        elif element.tag in (BRANCH, LEAF):
            node = self._stack.pop()
            if node.slot is not None:
                self._leaves[node.slot] = self._dataset(element, node)
                self.completed += 1
            element.clear()

    def _dataset(self, element: ET.Element, node: _Node) -> Dataset:
        path = PATH_SEPARATOR.join(above.title for above in self._stack if above.title)
        return Dataset.model_validate(
            {
                "code": _text(element, "code"),
                "type": element.get("type"),
                "title": node.title,
                "path": path,
                "lastUpdate": _text(element, "lastUpdate"),
                "lastModified": _text(element, "lastModified"),
                "dataStart": _text(element, "dataStart"),
                "dataEnd": _text(element, "dataEnd"),
                "values": _text(element, "values"),
            }
        )


CHUNK = 1 << 20


def _chunks(path: Path) -> Iterable[bytes]:
    with path.open("rb") as file:
        while chunk := file.read(CHUNK):
            yield chunk


def read_toc(path: Path) -> Toc:
    """The table of contents in ``path``, read a megabyte at a time."""
    parser = TocParser()
    for chunk in _chunks(path):
        parser.feed(chunk)
    return parser.close()


def toc_list(toc: Toc, fetched: datetime) -> PackagedList:
    """The packaged TOC: every leaf under upstream's field names, in tree order."""
    return PackagedList(
        param=TOC_PARAM,
        endpoint=api.catalogue.PATH,
        fetched=fetched,
        records=[leaf.dump_upstream() for leaf in toc.leaves],
    )


def toc_info(toc: Toc) -> ListInfo:
    """The TOC's record in ``lists.json``."""
    return ListInfo(
        name=params.TOC, kind="toc", creation_date=toc.creation_date, count=len(toc.leaves)
    )


def codelist_list(codelist: Codelist, fetched: datetime) -> PackagedList:
    """A packaged codelist: its codes and labels, in upstream's order.

    ``param`` is the dimension code the Statistics API takes, the id lower-cased.
    """
    resource_id = codelist.extension.id
    return PackagedList(
        param=resource_id.lower(),
        endpoint=api.sdmx.codelist_path(params.AGENCY, resource_id),
        fetched=fetched,
        records=[code.dump_upstream() for code in codelist.codes()],
    )


def codelist_info(codelist: Codelist) -> ListInfo:
    """A codelist's record in ``lists.json``: its id, name, version and LAST_UPDATED."""
    resource_id = codelist.extension.id
    return ListInfo(
        name=resource_id.lower(),
        kind="codelist",
        id=resource_id,
        label=codelist.label,
        version=codelist.extension.version,
        last_updated=codelist.annotation("LAST_UPDATED"),
        count=len(codelist.codes()),
    )


async def fetch_toc(dest: Path) -> Downloaded:
    """Stream the TOC's XML to ``dest`` through ``api.catalogue.get_toc_xml``: one request."""
    return await api.catalogue.get_toc_xml(dest)


async def fetch_codelist(resource_id: str) -> api.sdmx.CodelistAnswer:
    """One codelist, the latest version with English labels: one request."""
    return await api.sdmx.code_list_query(params.AGENCY, resource_id, lang=LANG)


def _utc(moment: datetime) -> str:
    return f"{moment.astimezone(UTC):%Y-%m-%dT%H:%M:%SZ}"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    for chunk in _chunks(path):
        digest.update(chunk)
    return digest.hexdigest()


class Sample(NamedTuple):
    """One parser-test sample and its provenance row."""

    path: Path
    row: str


def cut_toc_sample(source: Path, downloaded: Downloaded, toc: Toc, dest: Path) -> Sample:
    """Cut ``SAMPLE_FOLDER`` with ``SAMPLE_LEAVES`` and the folders above it out of the TOC.

    The elements kept are upstream's as parsed, written again by ``ElementTree`` under
    upstream's prefixes and indented by two spaces; every other branch and leaf is left
    out. A comment after the declaration carries the provenance (ADR-0020 decision 6).
    """
    ET.register_namespace("nt", NAVTREE)
    ET.register_namespace("xsi", XSI)
    root = ET.parse(source).getroot()
    parents = {child: parent for parent in root.iter() for child in parent}
    folder = next(branch for branch in root.iter(BRANCH) if branch.findtext(CODE) == SAMPLE_FOLDER)
    children = folder.find(_tag("children"))
    if children is None:
        raise ValueError(f"the folder {SAMPLE_FOLDER} has no children")
    for leaf in list(children):
        if leaf.findtext(CODE) not in SAMPLE_LEAVES:
            children.remove(leaf)
    kept = folder
    while kept is not root:
        parent = parents[kept]
        for sibling in list(parent):
            if sibling.tag in (BRANCH, LEAF) and sibling is not kept:
                parent.remove(sibling)
        kept = parent
    ET.indent(root, space="  ")
    sha256, size = _sha256(source), source.stat().st_size
    url = f"{BASE_URL}/{api.catalogue.PATH}"
    comment = (
        f"Cut by {GENERATOR} with its samples option from {url}, creationDate "
        f"{toc.creation_date}, "
        f"{size} bytes, sha256 {sha256}, fetched {_utc(downloaded.retrieved_at)}: the folder "
        f"{SAMPLE_FOLDER} with its leaves {', '.join(SAMPLE_LEAVES)} and the folders above "
        "it, every other branch and leaf left out."
    )
    if "--" in comment:
        raise ValueError("an XML comment cannot hold two hyphens in a row")
    text = ET.tostring(root, encoding="unicode")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        f'<?xml version="1.0" encoding="UTF-8"?>\n<!-- {comment} -->\n{text}\n', encoding="utf-8"
    )
    row = (
        f"| `{dest.relative_to(SAMPLES)}` | `{toc.creation_date}` (creationDate) | {url} | "
        f"{size} | `{sha256}` | {_utc(downloaded.retrieved_at)} | the folder `{SAMPLE_FOLDER}` "
        f"with the leaves {', '.join(f'`{code}`' for code in SAMPLE_LEAVES)} and the folders "
        "above it, written again by ElementTree |"
    )
    return Sample(dest, row)


def write_codelist_sample(answer: api.sdmx.CodelistAnswer, dest: Path) -> Sample:
    """Write a codelist answer whole, as compact JSON, with its provenance row.

    The answer as decoded, written again with ``ensure_ascii=False`` and no spaces, which
    gave back every codelist answer probed on 2026-10-27 byte for byte; the row's sha256
    and size are the file's.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(answer.payload, ensure_ascii=False, separators=(",", ":"))
    dest.write_text(text, encoding="utf-8")
    extension = answer.codelist.extension
    url = (
        f"{BASE_URL}/{api.sdmx.codelist_path(params.AGENCY, extension.id)}?format=JSON&lang={LANG}"
    )
    row = (
        f"| `{dest.relative_to(SAMPLES)}` | `{extension.version}` (version) | {url} | "
        f"{dest.stat().st_size} | `{_sha256(dest)}` | {_utc(answer.retrieved_at)} | the "
        "whole answer, decoded and written again as compact JSON |"
    )
    return Sample(dest, row)


SAMPLES_README = """# Parser-test samples

Small real samples of the answers the package and its refresh script read, under
`<kind>/<case>.*`, never written by hand (ADR-0020 decision 6, conventions §10): `toc/`
and `codelist/` cut by `scripts/refresh_reference.py --samples` from the answers of its
run, which rewrites their rows and keeps the others; `sdmx-csv/` the response bodies of
the recorded `tests/fixtures/data_query/` exchanges, byte for byte, which
`tests/test_parse.py` checks. One row per file: the release (upstream's identifier of
it), the URL, the bytes and sha256 of the full answer, and when it was fetched. The
parser tests in `tests/test_refresh_reference.py` and `tests/test_parse.py` read them;
they assert shape, never values or sizes.

| File | Release | URL | Bytes | sha256 | Fetched | What |
| --- | --- | --- | --- | --- | --- | --- |
"""

SAMPLE_ROW = re.compile(r"^\| `(?P<kind>[^/`]+)/[^`]*` \|")
"""A sample's row in the README, its kind the first part of its path."""


def write_samples_readme(samples: Sequence[Sample]) -> None:
    """Write ``tests/fixtures/files/README.md``: one row per sample of this run.

    The rows of the samples this script does not cut (a kind outside ``SAMPLE_KINDS``)
    are kept as they are, after this run's.
    """
    path = SAMPLES / "README.md"
    kept = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            row = SAMPLE_ROW.match(line)
            if row is not None and row["kind"] not in SAMPLE_KINDS:
                kept.append(line)
    rows = "".join(f"{line}\n" for line in [*(sample.row for sample in samples), *kept])
    path.write_text(SAMPLES_README + rows, encoding="utf-8")


README_TABLE = "| File | Origin | Fetched |\n| --- | --- | --- |\n"


def write_reference_readme(written: Mapping[str, PackagedList]) -> None:
    """Rewrite the provenance table at the end of ``reference/README.md``.

    One row per packaged list; ``lists.json``, the derived index, has no origin and no
    row, and the README's text says so.
    """
    path = REFERENCE / "README.md"
    text = path.read_text(encoding="utf-8")
    head, found, _ = text.partition(README_TABLE)
    if not found:
        raise SystemExit(f"{path.name} has no provenance table to rewrite")
    rows = "".join(
        f"| `{name}.json` | `{packaged.endpoint}` | {_utc(packaged.fetched)} |\n"
        for name, packaged in written.items()
    )
    path.write_text(head + README_TABLE + rows, encoding="utf-8")


def write_index(infos: Sequence[ListInfo], fetched: datetime) -> None:
    """Write ``reference/lists.json``, the derived index, as plain JSON (``params.ListIndex``).

    ``fetched`` is written to the second, as ISO 8601 UTC with ``Z``; the records under
    upstream's names where they are upstream's (``LAST_UPDATED``, ``creationDate``).
    """
    index = params.ListIndex(fetched=fetched.replace(microsecond=0), lists=list(infos))
    payload = {
        "fetched": _utc(index.fetched),
        "lists": [info.dump_upstream() for info in index.lists],
    }
    path = REFERENCE / f"{params.INDEX}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{path.name}: {len(index.lists)} lists")  # noqa: T201


def write(name: str, packaged: PackagedList) -> None:
    """Write ``reference/<name>.json`` with ``PackagedList.write``."""
    path = REFERENCE / f"{name}.json"
    packaged.write(path)
    print(f"{path.name}: {len(packaged.records)} records")  # noqa: T201


def read(name: str) -> dict[str, Any]:
    """The packaged ``reference/<name>.json``, as ``write`` wrote it."""
    path = REFERENCE / f"{name}.json"
    if not path.is_file():
        raise SystemExit(f"{path.name} is not packaged yet: run the script without --render-only")
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return payload


def render(
    lists: Mapping[str, Sequence[str] | Sequence[tuple[int, str]]],
    fetched: Mapping[str, str],
) -> None:
    """Write ``enums.py`` with one ``render_enums`` call, then format it with ruff.

    A value list renders a ``StrEnum``, a list of ``(id, name)`` pairs an ``IntEnum``, each
    class docstring naming its list's date in ``fetched``. ``ruff format`` and
    ``ruff check --fix`` then choose the quotes, wrap what fits and sort ``__all__``; the
    module is committed as formatted (ADR-0008, amendment 2026-10-27).
    """
    ENUMS.write_text(render_enums(lists, fetched=fetched, generator=GENERATOR), encoding="utf-8")
    for command in (["format"], ["check", "--fix"]):
        subprocess.run([sys.executable, "-m", "ruff", *command, str(ENUMS)], check=True, cwd=ROOT)


class Fetched(NamedTuple):
    """What one run fetched: the packaged lists, their records in ``lists.json``, samples."""

    written: dict[str, PackagedList]
    infos: list[ListInfo]
    samples: list[Sample]


async def fetch_all(work: Path, *, samples: bool) -> Fetched:
    """Fetch the TOC and every codelist, one request each, and build their files.

    The TOC goes to ``work`` while it is read; nothing else touches the disk here but the
    samples, when asked for.
    """
    written: dict[str, PackagedList] = {}
    infos: list[ListInfo] = []
    cut: list[Sample] = []
    downloaded = await fetch_toc(work / "toc.xml")
    toc = read_toc(downloaded.path)
    written[params.TOC] = toc_list(toc, downloaded.retrieved_at)
    infos.append(toc_info(toc))
    if samples:
        dest = SAMPLES / "toc" / f"{SAMPLE_FOLDER}.xml"
        cut.append(cut_toc_sample(downloaded.path, downloaded, toc, dest))
    for resource_id in params.CODELISTS:
        answer = await fetch_codelist(resource_id)
        if answer.codelist.extension.id != resource_id:
            raise SystemExit(f"asked for {resource_id}, got {answer.codelist.extension.id}")
        written[resource_id.lower()] = codelist_list(answer.codelist, answer.retrieved_at)
        infos.append(codelist_info(answer.codelist))
        if samples and resource_id == SAMPLE_CODELIST:
            dest = SAMPLES / "codelist" / f"{resource_id.lower()}.json"
            cut.append(write_codelist_sample(answer, dest))
    return Fetched(written, infos, cut)


def refresh(*, samples: bool = False) -> None:
    """Fetch every list, write its file, ``lists.json`` and the README, render ``enums.py``."""
    REFERENCE.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as work:
        fetched = sync(fetch_all)(Path(work), samples=samples)
    for name, packaged in fetched.written.items():
        write(name, packaged)
    write_index(fetched.infos, max(packaged.fetched for packaged in fetched.written.values()))
    write_reference_readme(fetched.written)
    if fetched.samples:
        write_samples_readme(fetched.samples)
        for sample in fetched.samples:
            print(f"{sample.path.relative_to(ROOT)}: {sample.path.stat().st_size} bytes")  # noqa: T201
    render_only()


def render_only() -> None:
    """Regenerate ``enums.py`` from the packaged files, without a request.

    Each list keeps the date its file records, so lists fetched on different days render
    with their own dates. With ``LISTS`` and ``ID_LISTS`` empty, the module has no enum.
    """
    lists: dict[str, Sequence[str] | Sequence[tuple[int, str]]] = {}
    fetched: dict[str, str] = {}
    for name in LISTS:
        payload = read(name)
        lists[name] = [next(iter(record.values())) for record in payload["records"]]
        fetched[name] = str(payload["fetched"])[:10]
    for name, (id_field, name_field, _) in ID_LISTS.items():
        payload = read(name)
        lists[name] = id_name_pairs(payload["records"], id_field=id_field, name_field=name_field)
        fetched[name] = str(payload["fetched"])[:10]
    render(lists, fetched)
    print(f"{ENUMS.name}: {len(lists)} enums, from the packaged files")  # noqa: T201


def main(argv: Sequence[str] | None = None) -> None:
    """Refresh from upstream, or with ``--render-only`` regenerate ``enums.py`` alone."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    choice = parser.add_mutually_exclusive_group()
    choice.add_argument(
        "--render-only",
        action="store_true",
        help="regenerate enums.py from the packaged reference/*.json, without a request",
    )
    choice.add_argument(
        "--samples",
        action="store_true",
        help="also cut the parser tests' samples under tests/fixtures/files/ from this run",
    )
    args = parser.parse_args(argv)
    if shared := sorted(LISTS.keys() & ID_LISTS.keys()):
        raise SystemExit(f"a list is named in both LISTS and ID_LISTS: {shared}")
    if args.render_only:
        render_only()
    else:
        refresh(samples=args.samples)


if __name__ == "__main__":
    main()
