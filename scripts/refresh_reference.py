"""Refresh the packaged reference data from upstream (``/refresh-reference-data``).

The script declares Eurostat's nineteen packaged lists in one ``Lists`` and hands it to
core's ``run`` (sdk-core ADR-0062), which fetches every list through the declared fetch,
then writes each to ``reference/<name>.json`` with ``PackagedList.write`` and the
provenance rows of ``reference/README.md``, and no ``enums.py``, since no list declares an
enum: Eurostat's lists are tables, each too large for one
(https://github.com/xippios/sdk-eurostat/pull/6). The frame sends each request once
through the package's client, ``RetryPolicy(max_attempts=1)`` for the run, so a 5xx or a
429 spends no second request of upstream's fair use; it fetches every list before it
writes the first file, so a run that fails writes nothing and is run again, and it prints
the requests it sent, a failed run's too, and the quota left, which Eurostat reports in no
header. ``--only <list> [<list> ...]`` fetches the lists named by their files
(``statinfo``, ``cxt_prodcom2_sold``, ``toc``) alone and keeps every other list's file and
row; ``--render-only`` writes the rows from the packaged files without a request.

The lists (conventions §3, sdk-core ADR-0041):

- ``toc.json``: the Catalogue API's table of contents, downloaded whole to a temporary
  file through ``api.catalogue.get_toc_xml`` (core's ``download``, which streams the body
  to disk), then read from that file a megabyte at a time with the standard library's
  ``xml.etree.ElementTree`` pull parser (``TocParser``), each element cleared once read:
  every ``leaf``, datasets and tables alike, with its code, type, English title, the
  English titles of the folders above it joined with ``" > "`` (``path``), ``lastUpdate``
  and ``lastModified``, printed day first and read into dates, which ``toc.json`` holds as
  ISO dates (``Dataset``, ``dump_upstream``), and ``dataStart``, ``dataEnd`` and ``values``
  as printed. This script is the only code that parses XML, so the package parses none at
  run time (decision D1 of
  https://github.com/xippios/sdk-eurostat/pull/6; sdk-core ADR-0020 decision 3).
- ``<codelist>.json``: one codelist each, the latest version in JSON-stat through
  ``api.sdmx.code_list_query`` with English labels (decisions D1 and D2 of
  https://github.com/xippios/sdk-eurostat/pull/6), its codes and labels in upstream's
  order, requested on the base ``params.CODELISTS`` names for it: twelve on the main
  base, six on the Comext base, the codelists of the Prodcom datasets' ``product`` and
  ``indicators`` and of the trade datasets' ``product``, ``reporter`` and ``partner``, and
  ``flow`` (https://github.com/xippios/sdk-eurostat/pull/13 and
  https://github.com/xippios/sdk-eurostat/pull/14). Its ``param`` is the dimension
  ``params.CODELISTS`` names (``geo``, ``product``), and its ``endpoint`` the path it was
  fetched from on the main base (``sdmx/2.1/codelist/ESTAT/GEO``) and the full URL on the
  Comext base (``codelist_endpoint``).

Each fetch builds its finished ``PackagedList``, its ``fetched`` the time its answer
arrived, and keeps what upstream gives the list as its release for the index. The
declaration's ``after``, which the frame calls once the lists are written, writes beside
them:

- ``lists.json``: not a packaged list but a derived index, plain JSON with keys of its
  own (``params.ListIndex``): ``fetched``, the latest ``fetched`` among the packaged
  lists, and ``lists``, one record per packaged list with what upstream gives each as
  its release (the TOC's ``creationDate``, a codelist's ``version`` and
  ``LAST_UPDATED``), since a packaged file holds its four keys and a ``note`` and
  nothing else (sdk-core ADR-0041, decision 5; https://github.com/xippios/sdk-core/issues/81).
  It names no upstream operation: it is derived from the nineteen answers. After a run
  with ``--only`` the records of the lists it fetched are replaced and every other is
  kept as committed, and the index's ``fetched`` becomes the latest ``fetched`` among all
  the packaged lists, the previous index's or this run's, whichever is later.
- With ``--samples``, the parser tests' samples, cut from the same answers without a
  request of their own: each folder of the TOC that ``TOC_SAMPLES`` names, with the leaves
  it names and the folders above it, under ``tests/fixtures/files/toc/``, and the STATINFO
  codelist's answer whole under ``tests/fixtures/files/codelist/``, their provenance in
  ``tests/fixtures/files/README.md`` (sdk-core ADR-0020 decision 6, conventions §10). The
  samples are cut while their answers are at hand and written with the index, so a run
  that fails writes none. Each TOC cut parses the whole file again with
  ``ElementTree.parse``, about 200 MB at its peak: fine for a one-off run, not for the
  plain refresh, which reads the file a megabyte at a time. ``--samples`` takes no other
  option, since it cuts from a run of every list.

Run from the repository root, without a key (the API takes none)::

    uv run python scripts/refresh_reference.py

Nineteen keyless requests, the TOC and eighteen codelists, each sent once and paced by the
package's client.
"""

import functools
import hashlib
import importlib.util
import json
import re
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple

import httpx
from xippios.core import AsyncClient, Downloaded, PackagedList
from xippios.core.refresh import Listed, Lists, run

from xippios.eurostat import api, params
from xippios.eurostat._client import BASE_URL, client
from xippios.eurostat.models import Codelist, Dataset
from xippios.eurostat.params import ListInfo

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = "scripts/refresh_reference.py"
SAMPLES = ROOT / "tests/fixtures/files"

SAMPLES_OPTION = "--samples"
"""The script's own option, read before the frame's command line."""

NAVTREE = "urn:eu.europa.ec.eurostat.navtree"
"""The namespace of the TOC's XML (``TableOfContent.xsd``)."""

XSI = "http://www.w3.org/2001/XMLSchema-instance"

PATH_SEPARATOR = " > "
"""What joins the folder titles of a leaf's ``path``."""

TOC_PARAM = "datasetCode"
"""What a TOC leaf's code feeds: the Statistics API's ``datasetCode`` (``getData``)."""

LANG = "en"
"""The codelists' language: English labels, as the TOC's English titles."""

TOC_SAMPLES: dict[str, tuple[str, ...]] = {
    "apro_mk": ("apro_mk_cola", "apro_mk_farm"),
    "ai": ("tai13",),
}
"""The TOC folders the samples keep, ``toc/<folder>.xml`` each, with the leaves each keeps.

"Milk and milk products" with a dataset without tables under it and one with a
pre-defined table under it; "Agri-environmental indicators" with a pre-defined table
whose number of values the TOC printed empty
(https://github.com/xippios/sdk-eurostat/issues/72).
"""

SAMPLE_CODELIST = "STATINFO"
"""The codelist the sample keeps whole, its answer as decoded."""

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


def codelist_endpoint(resource_id: str) -> str:
    """A packaged codelist's ``endpoint``: its path on the main base, else its full URL.

    ``sdmx/2.1/codelist/ESTAT/GEO`` for a codelist of the main base, as packaged since
    0.1.0; ``https://ec.europa.eu/eurostat/api/comext/dissemination/sdmx/2.1/codelist/``
    ``ESTAT/CXT_PRODCOM2_SOLD`` for one of the Comext base, whose path alone would name
    the main base's operation (conventions §4, sdk-core ADR-0041 decision 1, as
    https://github.com/xippios/sdk-eurostat/pull/13 decided).

    Raises:
        KeyError: ``params.CODELISTS`` does not name the codelist.
    """
    path = api.sdmx.codelist_path(params.AGENCY, resource_id)
    base_url = params.CODELISTS[resource_id].base_url
    return path if base_url == BASE_URL else f"{base_url}/{path}"


def codelist_list(codelist: Codelist, fetched: datetime) -> PackagedList:
    """A packaged codelist: its codes and labels, in upstream's order.

    ``param`` is the dimension code the Statistics API takes, as ``params.CODELISTS``
    names it (``geo``, ``product``), and ``endpoint`` is ``codelist_endpoint``'s.
    """
    resource_id = codelist.extension.id
    return PackagedList(
        param=params.CODELISTS[resource_id].param,
        endpoint=codelist_endpoint(resource_id),
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


def _utc(moment: datetime) -> str:
    return f"{moment.astimezone(UTC):%Y-%m-%dT%H:%M:%SZ}"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    for chunk in _chunks(path):
        digest.update(chunk)
    return digest.hexdigest()


class Sample(NamedTuple):
    """One parser-test sample, cut and not yet written, and its provenance row."""

    path: Path
    text: str
    row: str


def cut_toc_sample(
    source: Path, downloaded: Downloaded, toc: Toc, dest: Path, folder: str, leaves: Sequence[str]
) -> Sample:
    """Cut the TOC's ``folder`` with its ``leaves`` and the folders above it out of the TOC.

    The elements kept are upstream's as parsed, written again by ``ElementTree`` under
    upstream's prefixes and indented by two spaces; every other branch and leaf is left
    out. A comment after the declaration carries the provenance (sdk-core ADR-0020 decision 6).
    """
    ET.register_namespace("nt", NAVTREE)
    ET.register_namespace("xsi", XSI)
    root = ET.parse(source).getroot()
    parents = {child: parent for parent in root.iter() for child in parent}
    branch = next(branch for branch in root.iter(BRANCH) if branch.findtext(CODE) == folder)
    children = branch.find(_tag("children"))
    if children is None:
        raise ValueError(f"the folder {folder} has no children")
    for leaf in list(children):
        if leaf.findtext(CODE) not in leaves:
            children.remove(leaf)
    kept = branch
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
        f"{folder} with its leaves {', '.join(leaves)} and the folders above "
        "it, every other branch and leaf left out."
    )
    if "--" in comment:
        raise ValueError("an XML comment cannot hold two hyphens in a row")
    tree = ET.tostring(root, encoding="unicode")
    text = f'<?xml version="1.0" encoding="UTF-8"?>\n<!-- {comment} -->\n{tree}\n'
    row = (
        f"| `{dest.relative_to(SAMPLES)}` | `{toc.creation_date}` (creationDate) | {url} | "
        f"{size} | `{sha256}` | {_utc(downloaded.retrieved_at)} | the folder `{folder}` "
        f"with the leaves {', '.join(f'`{code}`' for code in leaves)} and the folders "
        "above it, written again by ElementTree |"
    )
    return Sample(dest, text, row)


def codelist_sample(body: bytes, codelist: Codelist, retrieved_at: datetime, dest: Path) -> Sample:
    """A codelist's answer whole, as compact JSON, with its provenance row.

    The answer as decoded, written again with ``ensure_ascii=False`` and no spaces, which
    gave back every codelist answer probed byte for byte when the sample was first cut;
    the row's sha256 and size are the file's.
    """
    text = json.dumps(json.loads(body), ensure_ascii=False, separators=(",", ":"))
    encoded = text.encode("utf-8")
    extension = codelist.extension
    base_url = params.CODELISTS[extension.id].base_url
    url = (
        f"{base_url}/{api.sdmx.codelist_path(params.AGENCY, extension.id)}?format=JSON&lang={LANG}"
    )
    row = (
        f"| `{dest.relative_to(SAMPLES)}` | `{extension.version}` (version) | {url} | "
        f"{len(encoded)} | `{hashlib.sha256(encoded).hexdigest()}` | {_utc(retrieved_at)} | "
        "the whole answer, decoded and written again as compact JSON |"
    )
    return Sample(dest, text, row)


class Gathered:
    """What one run's fetches gather beside the lists, for the declaration's ``after``.

    Attributes:
        samples: Whether the run cuts the parser tests' samples (``--samples``).
        infos: Each fetched list's record in ``lists.json``, by the list's name.
        pending: The samples to cut once every list is fetched, in the order of their
            fetches, which ``after`` cuts and writes.
        answered: The body of the sampled codelist's answer as it came from the wire,
            which ``SampledAnswer`` keeps in a ``--samples`` run.
    """

    def __init__(self) -> None:
        self.samples = False
        self.infos: dict[str, ListInfo] = {}
        self.pending: list[Callable[[], Sample]] = []
        self.answered: bytes | None = None
        self._work: tempfile.TemporaryDirectory[str] | None = None

    def start(self, *, samples: bool) -> None:
        """Forget what an earlier run gathered, its kept TOC removed with it."""
        if self._work is not None:
            self._work.cleanup()
        self._work = tempfile.TemporaryDirectory(prefix="xippios-eurostat-") if samples else None
        self.samples = samples
        self.infos = {}
        self.pending = []
        self.answered = None

    def kept(self) -> Path | None:
        """The directory that keeps the TOC for its samples until the run ends, if any."""
        return None if self._work is None else Path(self._work.name)


RUN = Gathered()
"""What the current run's fetches gather: the fetches take no argument, as the frame calls
them, so they hand what the index and the samples need here."""


class SampledAnswer:
    """The client's ``observe`` hook in a ``--samples`` run: keeps the sampled codelist's body.

    Core calls the hook with every response from the wire, its body read, and a cache hit
    never (``ClientConfig.observe``); it calls the hook the client had first, and keeps the
    body of the 200 answer to ``SAMPLE_CODELIST``'s request in ``RUN.answered``, so the
    sample is the same answer as the packaged list, without a request of its own.
    """

    def __init__(self, observe: Callable[[httpx.Response], None] | None) -> None:
        self._observe = observe
        self._path = f"/{api.sdmx.codelist_path(params.AGENCY, SAMPLE_CODELIST)}"

    def __call__(self, response: httpx.Response) -> None:
        """Call the hook the client had, then keep the sampled answer's body."""
        if self._observe is not None:
            self._observe(response)
        if response.status_code == 200 and response.request.url.path.endswith(self._path):
            RUN.answered = response.content


@contextmanager
def sampling(target: AsyncClient) -> Iterator[None]:
    """``target`` for a ``--samples`` run: ``SampledAnswer`` observes it, then it is restored."""
    configured = target.config
    target.config = replace(configured, observe=SampledAnswer(configured.observe))
    try:
        yield
    finally:
        target.config = configured


async def fetch_toc() -> PackagedList:
    """The packaged TOC through ``api.catalogue.get_toc_xml``: one request.

    The XML is streamed to a temporary file and read from it; a ``--samples`` run keeps the
    file until the run ends, its samples of ``TOC_SAMPLES`` cut from it once every list is
    fetched.
    """
    kept = RUN.kept()
    with tempfile.TemporaryDirectory(prefix="xippios-eurostat-toc-") as work:
        downloaded = await api.catalogue.get_toc_xml((kept or Path(work)) / "toc.xml")
        toc = read_toc(downloaded.path)
    if kept is not None:
        for folder, leaves in TOC_SAMPLES.items():
            dest = SAMPLES / "toc" / f"{folder}.xml"
            RUN.pending.append(
                functools.partial(
                    cut_toc_sample, downloaded.path, downloaded, toc, dest, folder, leaves
                )
            )
    RUN.infos[params.TOC] = toc_info(toc)
    return toc_list(toc, downloaded.retrieved_at)


async def fetch_codelist(resource_id: str) -> PackagedList:
    """One packaged codelist, the latest version with English labels, on its base.

    One request through ``api.sdmx.code_list_query``; in a ``--samples`` run the sampled
    codelist's answer is cut whole from the body ``SampledAnswer`` kept.

    Raises:
        SystemExit: Upstream answered another codelist, or the sampled codelist's answer
            came from the client's cache, which keeps no body for the sample; nothing is
            written then.
    """
    answer = await api.sdmx.code_list_query(
        params.AGENCY, resource_id, lang=LANG, base_url=params.CODELISTS[resource_id].base_url
    )
    codelist = answer.payload
    if codelist.extension.id != resource_id:
        raise SystemExit(f"asked for {resource_id}, got {codelist.extension.id}")
    RUN.infos[resource_id.lower()] = codelist_info(codelist)
    if RUN.samples and resource_id == SAMPLE_CODELIST:
        if RUN.answered is None:
            raise SystemExit(
                f"{resource_id}'s answer came from the client's cache, which keeps no body for "
                "the sample: run the script again in a process of its own. Nothing was written."
            )
        dest = SAMPLES / "codelist" / f"{resource_id.lower()}.json"
        sample = codelist_sample(RUN.answered, codelist, answer.retrieved_at, dest)
        RUN.pending.append(lambda: sample)
    return codelist_list(codelist, answer.retrieved_at)


def _codelist(resource_id: str) -> Listed:
    """The declaration of one packaged codelist, its file the id lower-cased."""

    async def fetch() -> PackagedList:
        return await fetch_codelist(resource_id)

    return Listed(
        resource_id.lower(),
        fetch=fetch,
        endpoint=codelist_endpoint(resource_id),
        param=params.CODELISTS[resource_id].param,
    )


LISTS = Lists(
    package=params.PACKAGE,
    lists=(
        Listed(params.TOC, fetch=fetch_toc, endpoint=api.catalogue.PATH, param=TOC_PARAM),
        *(_codelist(resource_id) for resource_id in params.CODELISTS),
    ),
    packaged=params.PACKAGED_LISTS,
    client=client,
    quota_header=None,
)
"""The nineteen packaged lists, the TOC and the codelists in ``params.CODELISTS``' order, each
a table and no enum. Eurostat reports its quota in no header: the user guide states a
fair-use rule without a number (``asynchronous-api.md``) and no such header."""


SAMPLES_README = """# Parser-test samples

Small real samples of the answers the package and its refresh script read, under
`<kind>/<case>.*`, never written by hand (sdk-core ADR-0020 decision 6, conventions §10): `toc/`
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


def write_samples(samples: Sequence[Sample]) -> None:
    """Write each sample and ``tests/fixtures/files/README.md``: one row per sample.

    The rows of the samples this script does not cut (a kind outside ``SAMPLE_KINDS``)
    are kept as they are, after this run's.
    """
    for sample in samples:
        sample.path.parent.mkdir(parents=True, exist_ok=True)
        sample.path.write_text(sample.text, encoding="utf-8")
    path = SAMPLES / "README.md"
    kept = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            row = SAMPLE_ROW.match(line)
            if row is not None and row["kind"] not in SAMPLE_KINDS:
                kept.append(line)
    rows = "".join(f"{line}\n" for line in [*(sample.row for sample in samples), *kept])
    path.write_text(SAMPLES_README + rows, encoding="utf-8")


def reference_directory(package: str) -> Path:
    """The ``reference/`` directory of ``package`` as imported, where the frame writes.

    Raises:
        SystemExit: The package is not importable as one directory.
    """
    spec = importlib.util.find_spec(package)
    locations = list(spec.submodule_search_locations or []) if spec is not None else []
    if len(locations) != 1:
        raise SystemExit(f"{package} is not importable as one package directory")
    return Path(locations[0]) / "reference"


def read_index(reference: Path) -> params.ListIndex:
    """The committed ``reference/lists.json``, for a run with ``--only`` to merge into.

    Raises:
        SystemExit: The index is missing; a run without ``--only`` writes it whole.
    """
    path = reference / f"{params.INDEX}.json"
    if not path.is_file():
        raise SystemExit(f"{path.name} is not written yet: run the script without --only")
    return params.ListIndex.model_validate_json(path.read_text(encoding="utf-8"))


def merge_index(
    previous: params.ListIndex, infos: Sequence[ListInfo], written: Mapping[str, PackagedList]
) -> tuple[list[ListInfo], datetime]:
    """The records and ``fetched`` of the index after a run with ``--only``.

    One record per packaged list, in the index's order: this run's for the lists it
    fetched, the previous record for every other, and none for a list neither has. The
    index's ``fetched`` is the latest ``fetched`` among all the packaged lists: the
    previous index's, the latest of the lists it recorded, or the latest of this run's,
    whichever is later, since a list's ``fetched`` only moves forward.
    """
    fresh = {info.name: info for info in infos}
    before = {info.name: info for info in previous.lists}
    merged = [
        fresh[name] if name in fresh else before[name]
        for name in params.PACKAGED_LISTS
        if name in fresh or name in before
    ]
    latest = max([previous.fetched, *(packaged.fetched for packaged in written.values())])
    return merged, latest


def write_index(reference: Path, infos: Sequence[ListInfo], fetched: datetime) -> None:
    """Write ``reference/lists.json``, the derived index, as plain JSON (``params.ListIndex``).

    ``fetched`` is written to the second, as ISO 8601 UTC with ``Z``; the records under
    upstream's names where they are upstream's (``LAST_UPDATED``, ``creationDate``).
    """
    index = params.ListIndex(fetched=fetched.replace(microsecond=0), lists=list(infos))
    payload = {
        "fetched": _utc(index.fetched),
        "lists": [info.dump_upstream() for info in index.lists],
    }
    path = reference / f"{params.INDEX}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{path.name}: {len(index.lists)} lists")  # noqa: T201


def write_beside(package: str, written: Mapping[str, PackagedList]) -> None:
    """The declaration's ``after``: ``lists.json``, then the samples a ``--samples`` run cut.

    A run of every list writes the index whole, its ``fetched`` the latest of the lists'; a
    run with ``--only`` merges its lists' records into the committed index (``merge_index``).

    Raises:
        SystemExit: A fetched list left no record for the index, or a run with ``--only``
            finds no committed index to merge into.
    """
    reference = reference_directory(package)
    if missing := [name for name in written if name not in RUN.infos]:
        raise SystemExit(f"no record for lists.json of {', '.join(missing)}")
    infos = [RUN.infos[name] for name in params.PACKAGED_LISTS if name in written]
    if set(written) == set(params.PACKAGED_LISTS):
        write_index(reference, infos, max(packaged.fetched for packaged in written.values()))
    else:
        write_index(reference, *merge_index(read_index(reference), infos, written))
    if RUN.pending:
        samples = [cut() for cut in RUN.pending]
        write_samples(samples)
        for sample in samples:
            print(f"{sample.path.relative_to(SAMPLES)}: {len(sample.text.encode())} bytes")  # noqa: T201


def main(argv: Sequence[str] | None = None) -> int:
    """Run core's frame on ``LISTS``, writing the index and any samples in its ``after``.

    ``--samples``, the script's own option, is read first and handed on to no parser: it
    takes no other option, so the run fetches every list, and the client keeps the sampled
    codelist's answer for the sample while the run lasts.

    Raises:
        SystemExit: ``--samples`` beside another option, before any request.
    """
    given = list(sys.argv[1:] if argv is None else argv)
    samples = SAMPLES_OPTION in given
    if samples:
        given = [arg for arg in given if arg != SAMPLES_OPTION]
        if given:
            raise SystemExit(
                f"{SAMPLES_OPTION} cuts the samples from a run of every list, so it takes no "
                f"other option: {' '.join(given)}. Nothing was fetched or written."
            )
    declaration = LISTS
    RUN.start(samples=samples)
    after = functools.partial(write_beside, declaration.package)
    try:
        with sampling(declaration.client) if samples else nullcontext():
            return run(replace(declaration, after=after), given)
    finally:
        RUN.start(samples=False)


if __name__ == "__main__":
    raise SystemExit(main())
