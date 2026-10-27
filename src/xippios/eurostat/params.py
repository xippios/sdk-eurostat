"""Packaged lists for Eurostat dissemination API (conventions §3, ADR-0022).

The table of contents and twelve codelists ship inside the package under ``reference/``
so that ``list_datasets`` and ``list_codes`` need no request;
``scripts/refresh_reference.py`` writes them, never by hand, each a packaged-list file
that ``PackagedList.load`` reads (``{"param", "endpoint", "fetched", "records"}`` and an
optional ``note``):

- ``toc.json``: every leaf of the Catalogue API's table of contents
  (``catalogue/toc/xml``), datasets and tables, as ``models.Dataset`` records; ``param``
  ``datasetCode``, what a leaf's code feeds.
- ``<codelist>.json``, the codelist's id lower-cased (``geo.json``): the codes of one
  SDMX codelist (``sdmx/2.1/codelist/ESTAT/<ID>``) as ``models.Code`` records; ``param``
  the dimension code the Statistics API takes (``geo``).
- ``lists.json``: not a packaged list but the package's derived index, plain JSON read
  with ``load_json`` (``ListIndex``): when the run's last answer arrived and one
  ``ListInfo`` record per packaged list, with the release identifiers upstream gives
  each, which a packaged-list file has no key for (ADR-0022, amendment 8; gap, row 111):
  the TOC's ``creationDate``, a codelist's ``version`` and ``LAST_UPDATED``. It is
  derived from the thirteen answers the packaged lists come from and names no upstream
  operation. The list tasks read their ``vintage`` and ``published_at`` from it, and
  ``list_codes`` the codelists it knows.

No enum is generated from them (too large for one, the design round of 2026-10-27);
``enums.py`` holds none. ``reference/README.md`` carries the provenance of every file.
"""

import functools

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from xippios.core import PackagedList, UpstreamModel, load_json, parse

from xippios.eurostat._client import SOURCE
from xippios.eurostat.models import Code, Dataset

__all__ = [
    "AGENCY",
    "CODELISTS",
    "INDEX",
    "PACKAGE",
    "PACKAGED_LISTS",
    "TOC",
    "ListIndex",
    "ListInfo",
    "codes",
    "datasets",
    "index",
    "list_info",
    "packaged",
]

PACKAGE = "xippios.eurostat"

AGENCY = "ESTAT"
"""The agency that maintains the packaged codelists."""

CODELISTS: tuple[str, ...] = (
    "FREQ",
    "GEO",
    "UNIT",
    "CROPS",
    "STRUCPRO",
    "MILKITEM",
    "DAIRYPROD",
    "STATINFO",
    "LEG_FORM",
    "FARMTYPE",
    "SO_EUR",
    "UAAREA",
)
"""The packaged codelists, by upstream's id: the codelists the dimensions of apro_cpnh1,
apro_mk_cola and ef_m_farmleg name in their data structures (Johannes, 2026-10-27, D2).
For each, the dimension's code is the id lower-cased."""

TOC = "toc"
"""The packaged table of contents, ``reference/toc.json``."""

INDEX = "lists"
"""The index of the packaged lists, ``reference/lists.json``; not a packaged list."""

PACKAGED_LISTS: tuple[str, ...] = (TOC, *(codelist.lower() for codelist in CODELISTS))
"""The packaged-list files under ``reference/``, without ``.json``; ``lists.json``, the
index, is not one."""


class ListInfo(UpstreamModel):
    """One packaged list's record in ``reference/lists.json``.

    The package's own record, not an upstream object: ``name``, ``kind`` and ``count``
    are the package's; the other fields hold upstream's identifiers under upstream's
    names, as printed.

    Attributes:
        name: The packaged file, without ``.json``, e.g. ``"geo"`` or ``"toc"``.
        kind: ``"toc"`` or ``"codelist"``.
        id: The codelist's id, e.g. ``"GEO"`` (``extension.id``); ``None`` for the TOC.
        label: The codelist's name, e.g. ``"Geopolitical entity (reporting)"``;
            ``None`` for the TOC.
        version: The codelist's version, e.g. ``"28.0"`` (``extension.version``);
            ``None`` for the TOC.
        last_updated: The codelist's ``LAST_UPDATED`` annotation as printed, e.g.
            ``"2026-03-25T23:00:00+0100"``; ``None`` for the TOC.
        creation_date: The TOC's ``creationDate`` as printed, e.g. ``"20261027T1000"``;
            ``None`` for a codelist.
        count: The records the packaged file holds, e.g. ``4292``.
    """

    name: str
    kind: str
    id: str | None = None
    label: str | None = None
    version: str | None = None
    last_updated: str | None = Field(default=None, validation_alias="LAST_UPDATED")
    creation_date: str | None = Field(default=None, validation_alias="creationDate")
    count: int


class ListIndex(BaseModel):
    """``reference/lists.json``: the package's derived index of its packaged lists.

    Plain JSON with keys of its own, not a packaged list: it is derived from the answers
    the packaged lists come from and names no upstream operation.

    Attributes:
        fetched: When the refresh run's last answer arrived, timezone-aware UTC, e.g.
            2026-10-27 19:55:36 UTC.
        lists: One record per packaged list, the TOC first.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    fetched: AwareDatetime
    lists: list[ListInfo]


@functools.cache
def index() -> ListIndex:
    """``reference/lists.json``, read once per process with ``load_json``.

    Raises:
        ValidationError: The file is not the index ``ListIndex`` describes.
    """
    return parse(
        ListIndex, load_json(PACKAGE, f"{INDEX}.json"), source=SOURCE, endpoint=f"{INDEX}.json"
    )


@functools.cache
def packaged(name: str) -> PackagedList:
    """The packaged list ``reference/<name>.json``, read once per process.

    Raises:
        FileNotFoundError: The package ships no such file.
        ValidationError: The file is not a packaged list.
    """
    return PackagedList.load(PACKAGE, name)


@functools.cache
def list_info() -> dict[str, ListInfo]:
    """``reference/lists.json``'s records by ``name``, read once per process."""
    return {info.name: info for info in index().lists}


@functools.cache
def _datasets() -> tuple[Dataset, ...]:
    return tuple(packaged(TOC).parse(Dataset, source=SOURCE))


def datasets() -> list[Dataset]:
    """The packaged table of contents' leaves, in the tree's order; a new list each call."""
    return list(_datasets())


@functools.cache
def _codes(name: str) -> tuple[Code, ...]:
    return tuple(packaged(name).parse(Code, source=SOURCE))


def codes(name: str) -> list[Code]:
    """The codes of the packaged codelist ``name`` (``"geo"``), in upstream's order.

    A new list each call.

    Raises:
        FileNotFoundError: The package ships no such codelist.
    """
    return list(_codes(name))
