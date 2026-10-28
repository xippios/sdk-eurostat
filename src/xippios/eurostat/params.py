"""The packaged reference lists, read from ``reference/`` without a call (conventions §3).

``/refresh-reference-data`` writes them; ``PackagedList.load(PACKAGE, name)`` reads one.

The table of contents and eighteen codelists ship inside the package under ``reference/``
so that ``list_datasets``, ``list_codes``, ``list_products``, ``list_cn8`` and ``list_hs``
need no request, and the production and trade tasks check their codes before sending,
with an index of their release identifiers beside them; ``scripts/refresh_reference.py``
writes the twenty JSON files, never by hand (ADR-0022). The nineteen lists are
packaged-list files that
``PackagedList.load`` reads (``{"param", "endpoint", "fetched", "records"}`` and an
optional ``note``); the index is plain JSON:

- ``toc.json``: every leaf of the Catalogue API's table of contents
  (``catalogue/toc/xml``), datasets and tables, as ``models.Dataset`` records; ``param``
  ``datasetCode``, what a leaf's code feeds.
- ``<codelist>.json``, the codelist's id lower-cased (``geo.json``,
  ``cxt_prodcom2_sold.json``): the codes of one SDMX codelist as ``models.Code`` records;
  ``param`` the dimension code the Statistics API takes, ``CODELISTS``'s (``geo``,
  ``product``). The twelve codelists of the main base keep the path they were fetched
  from as ``endpoint`` (``sdmx/2.1/codelist/ESTAT/GEO``); the six of the Comext base
  the full URL (``https://ec.europa.eu/eurostat/api/comext/dissemination/sdmx/2.1/``
  ``codelist/ESTAT/CXT_PRODCOM2_SOLD``), since the path alone would name the main base's
  operation (ADR-0022 rule 1; Johannes, 2026-10-28; gap, row 172).
- ``lists.json``: not a packaged list but the package's derived index, plain JSON read
  with ``load_json`` (``ListIndex``): the latest ``fetched`` among the packaged lists
  and one ``ListInfo`` record per packaged list, with the release identifiers upstream
  gives each, which a packaged-list file has no key for (ADR-0022, amendment 8; gap, row
  111): the TOC's ``creationDate``, a codelist's ``version`` and ``LAST_UPDATED``. It is
  derived from the nineteen answers the packaged lists come from and names no upstream
  operation. The list tasks read their ``vintage`` and ``published_at`` from it, and
  ``list_codes`` the codelists it knows.

No enum is generated from them (too large for one, the design round of 2026-10-27);
``enums.py`` holds none. ``reference/README.md`` carries the provenance of every file.
"""

import functools
from collections.abc import Mapping
from typing import NamedTuple

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from xippios.core import PackagedList, UpstreamModel, load_json, parse

from xippios.eurostat._client import BASE_URL, COMEXT_BASE_URL, SOURCE
from xippios.eurostat.models import Code, Dataset

__all__ = [
    "AGENCY",
    "CODELISTS",
    "INDEX",
    "PACKAGE",
    "PACKAGED_LISTS",
    "PRODCOM_INDICATORS",
    "PRODCOM_SOLD",
    "PRODCOM_TOTAL",
    "TOC",
    "TRADE_COUNTRIES",
    "TRADE_FLOWS",
    "TRADE_PRODUCTS",
    "CodelistOrigin",
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


class CodelistOrigin(NamedTuple):
    """Where a packaged codelist is fetched and which dimension it feeds.

    Attributes:
        base_url: The base that serves it: ``_client.BASE_URL``, or
            ``_client.COMEXT_BASE_URL`` for a codelist of the Comext and Prodcom
            datasets, e.g. ``"https://ec.europa.eu/eurostat/api/comext/dissemination"``.
        param: The dimension code the Statistics API takes for its codes, the packaged
            file's ``param``, e.g. ``"geo"`` or ``"product"``. A codelist that feeds two
            dimensions names the first in the data structure's order: CXT_FREE_ISO's
            ``param`` is ``"reporter"``, and the trade datasets name it for ``partner``
            too (``TRADE_COUNTRIES``).
    """

    base_url: str
    param: str


PRODCOM_SOLD = "CXT_PRODCOM2_SOLD"
"""The products of DS-059358 (Prodcom, sold production, exports and imports): its
``product`` dimension's codelist (the data structure DS-059358 2.7)."""

PRODCOM_TOTAL = "CXT_PRODCOM2_TOTAL"
"""The products of DS-059359 (Prodcom, total production): its ``product`` dimension's
codelist (the data structure DS-059359 2.7, read 2026-10-28)."""

PRODCOM_INDICATORS = "CXT_INDICATORS"
"""The indicators of DS-059358 and DS-059359: their ``indicators`` dimension's codelist,
which Comext's trade datasets share."""

TRADE_PRODUCTS = "CXT_NC"
"""The products of Comext's trade datasets DS-045409 (EU trade since 1988 by HS2-4-6 and
CN8) and DS-059341 (International trade of EU and non-EU countries since 2002 by
HS2-4-6): their ``product`` dimension's codelist, the Combined Nomenclature's eight-digit
codes with the HS chapters, headings and subheadings above them (the data structures
DS-045409 6.6 and DS-059341 3.7, read 2026-10-28)."""

TRADE_COUNTRIES = "CXT_FREE_ISO"
"""The reporters and partners of Comext's trade datasets DS-045409 and DS-059341: the
codelist of their ``reporter`` and ``partner`` dimensions, countries and aggregates
(``EU27_2020_EXTRA``); the production tasks check a Prodcom reporter against it too
(Johannes, 2026-10-28)."""

TRADE_FLOWS = "CXT_EU_FLUX"
"""The flows of Comext's trade datasets DS-045409 and DS-059341: their ``flow``
dimension's codelist."""

CODELISTS: Mapping[str, CodelistOrigin] = {
    "FREQ": CodelistOrigin(BASE_URL, "freq"),
    "GEO": CodelistOrigin(BASE_URL, "geo"),
    "UNIT": CodelistOrigin(BASE_URL, "unit"),
    "CROPS": CodelistOrigin(BASE_URL, "crops"),
    "STRUCPRO": CodelistOrigin(BASE_URL, "strucpro"),
    "MILKITEM": CodelistOrigin(BASE_URL, "milkitem"),
    "DAIRYPROD": CodelistOrigin(BASE_URL, "dairyprod"),
    "STATINFO": CodelistOrigin(BASE_URL, "statinfo"),
    "LEG_FORM": CodelistOrigin(BASE_URL, "leg_form"),
    "FARMTYPE": CodelistOrigin(BASE_URL, "farmtype"),
    "SO_EUR": CodelistOrigin(BASE_URL, "so_eur"),
    "UAAREA": CodelistOrigin(BASE_URL, "uaarea"),
    PRODCOM_SOLD: CodelistOrigin(COMEXT_BASE_URL, "product"),
    PRODCOM_TOTAL: CodelistOrigin(COMEXT_BASE_URL, "product"),
    PRODCOM_INDICATORS: CodelistOrigin(COMEXT_BASE_URL, "indicators"),
    TRADE_PRODUCTS: CodelistOrigin(COMEXT_BASE_URL, "product"),
    TRADE_COUNTRIES: CodelistOrigin(COMEXT_BASE_URL, "reporter"),
    TRADE_FLOWS: CodelistOrigin(COMEXT_BASE_URL, "flow"),
}
"""The packaged codelists, by upstream's id, each with its base and its dimension.

Twelve on the main base, the codelists the dimensions of apro_cpnh1, apro_mk_cola and
ef_m_farmleg name in their data structures (Johannes, 2026-10-27, D2), each feeding the
dimension whose code is its id lower-cased; six on the Comext base, the codelists the
Prodcom datasets DS-059358 and DS-059359 name for ``product`` and ``indicators`` and the
codelists the trade datasets DS-045409 and DS-059341 name for ``product``, ``reporter``
and ``partner``, and ``flow`` (Johannes, 2026-10-28). The packaged file of each is its id
lower-cased."""

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
        name: The packaged file, without ``.json``, e.g. ``"geo"``,
            ``"cxt_prodcom2_sold"`` or ``"toc"``.
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
        fetched: The latest ``fetched`` among the packaged lists, timezone-aware UTC,
            e.g. 2026-10-27 19:55:36 UTC: when the last answer of the refresh runs that
            wrote them arrived, a run with ``--only`` refreshing some of them.
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
