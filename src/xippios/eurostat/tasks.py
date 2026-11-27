"""Task functions, the public API: the adapters serve ``__all__`` (conventions §2).

``/add-endpoint`` adds them.

``get_data`` answers one Statistics API request (``api.statistics.get_data``) as the
JSON-stat cube it returns. A ``DS-`` dataset, Comext trade or Prodcom production
(``"DS-059358"``), is requested on Eurostat's Comext base,
``https://ec.europa.eu/eurostat/api/comext/dissemination``, by upstream's rule
(``_client.url_for``), every other on the main base; the tasks are the same on both, and
so are their answers' shapes. Release metadata: ``meta.published_at`` is the cube's
``updated``, the dataset's last update with its zone; ``meta.vintage`` is the same
member as upstream printed it (``"2026-10-05T23:00:00+0200"``), Eurostat's only release
identifier for a dataset (``docs/upstream/user-guide/api-introduction.md``: "there is no
versioning or documentation of past versions of the data"; sdk-core ADR-0041 decision
2). An ``updated`` without a zone, never seen, goes into ``published_at`` as printed with
``published_at_naive`` set, no zone invented (sdk-core ADR-0041 decision 2).
``meta.endpoint`` is the operation's name, ``"getData"``; ``meta.request`` holds what
was sent, a parameter left ``None`` omitted; ``meta.total`` stays ``None``: the answer
counts no records for the request (its ``OBS_COUNT`` annotation counts the whole
dataset's, sdk-core ADR-0034). The cube's ``updated`` is the dataset's last update,
``extension`` carries Eurostat's annotations as sent, and in Python
``result.data.observations()`` reads the cells out one by one with their codes and labels.
Eurostat estimates a query it has not cached in cells: from 500,000 it answers
asynchronously, which the package refuses with ``InvalidRequestError`` and does not poll,
and over 5,000,000 it refuses the query, which is core's ``QueryTooLarge``
(``docs/upstream/user-guide/api-detailed-guidelines/asynchronous-api.md``).

``get_data`` checks before its request the codes of each filter whose dimension one
packaged codelist of the dataset's base feeds (``CHECKED_FILTERS``), by core's check of a
packaged list, and names them in ``meta.names``; a cube without a cell, a code the dataset
does not use or a period not yet released, raises ``NotFoundError`` (conventions §5;
sdk-core ADR-0061, decision 6). Every refusal before a request says ``Nothing was sent.``
after its first sentence, and a refusal of an answer names the request that was sent
(conventions §5). No task sends more than one request, so none states a ceiling of its
own.

The list tasks, ``list_datasets`` and ``list_codes``, answer from the packaged lists
(``params``) without a request, by sdk-core ADR-0041 decision 1: ``meta.retrieved_at``
is the list's ``fetched``, ``meta.endpoint`` the operation it was fetched from
(``catalogue/toc/xml``, ``sdmx/2.1/codelist/ESTAT/<ID>``, or for a codelist of the
Comext base its full URL), ``meta.total`` ``None``. Their release metadata (decision D4
of https://github.com/xippios/sdk-eurostat/pull/6) comes from ``reference/lists.json``:
for the table of contents
``meta.vintage`` is its ``creationDate`` as printed (``"20261126T2200"``) and
``meta.published_at`` the same time without a zone, ``published_at_naive`` set (sdk-core ADR-0041
decision 2); for a codelist ``meta.vintage`` is its version (``"29.0"``) and
``meta.published_at`` its ``LAST_UPDATED`` annotation with the zone Eurostat prints, or
``None`` for a codelist without one (CXT_EU_FLUX).

``download_dataset`` is the bulk task, named in ``BULK_TASKS`` and so Python-only: the
adapters skip it, no tool or route returns a file path (sdk-core ADR-0040 decision 4). It
streams one SDMX 2.1 data query (``api.sdmx.data_query``) as gzip-compressed SDMX-CSV to
the file the caller names and returns ``Result[Downloaded]``; ``parse.parse_sdmx_csv``
reads the file. Its release metadata comes from the file's first row, read through the
parser: ``meta.vintage`` is ``LAST UPDATE`` as printed
(``"05/10/26 23:00:00"``) and ``meta.published_at`` the same time without a zone,
``published_at_naive`` set (sdk-core ADR-0041 decision 2); ``meta.endpoint`` is ``"dataQuery"``.
"""

import os
from collections.abc import Mapping, Sequence
from contextlib import closing
from datetime import datetime
from enum import StrEnum
from functools import cache
from pathlib import Path
from typing import Any

from xippios.core import (
    Downloaded,
    InvalidRequestError,
    NotFoundError,
    PackagedCodes,
    PackagedList,
    Result,
    ResultCap,
    ResultMeta,
    matches,
    sync,
)

from xippios.eurostat import api, params
from xippios.eurostat._client import BASE_URL, COMEXT_BASE_URL, COMEXT_PREFIX, SOURCE
from xippios.eurostat.api.statistics import ENDPOINT
from xippios.eurostat.models import Code, Cube, Dataset, GeoLevel, Lang
from xippios.eurostat.parse import parse_sdmx_csv
from xippios.eurostat.parse.sdmx_csv import last_update_as_printed

__all__ = [
    "download_dataset",
    "get_data",
    "list_codes",
    "list_datasets",
]

MCP_INSTRUCTIONS = (
    "Eurostat dissemination API via xippios. "
    "Tools are read-only. "
    "Where list tools (eurostat_list_*) exist, call them first to find valid values, "
    "then query."
)
"""The server's instructions, which core's ``ToolSet.from_tasks`` reads from this module
(sdk-core ADR-0063, decision 7)."""

NOTHING_SENT = "Nothing was sent."
"""The sentence after the first of every refusal before a request (conventions §5)."""

BULK_TASKS: frozenset[str] = frozenset({"download_dataset"})
"""Tasks the adapters skip (sdk-core ADR-0040 decision 4): ``download_dataset``, which
writes a file and is Python-only. Core's ``build_server`` and ``router_from_tasks`` read
it from this module and leave its names out, so ``mcp.py`` and ``http.py`` pass
``__all__`` whole."""

RESERVED_PARAMETERS = frozenset(
    {"format", "lang", "sincetimeperiod", "untiltimeperiod", "lasttimeperiod", "geolevel"}
)
"""The Statistics API's own parameters, lower-cased: not dimension filters. ``format`` is
fixed to ``JSON``; the others are ``get_data``'s own arguments."""

TIME_FILTERS = frozenset({"time", "time_period"})
"""The filters that address the TIME_PERIOD dimension, lower-cased: "Both "time" and
"time_period" parameters are accepted in the URL to address the TIME_PERIOD dimension"
(api-statistics.md, "The Time parameter")."""

MCP_CAPS: Mapping[str, ResultCap] = {
    "list_datasets": ResultCap(
        paged=True,
        note=(
            "pass search, a word of the title or a part of the code (milk, apro_mk), "
            "to see the rest"
        ),
    ),
    "list_codes": ResultCap(
        max_rows=1000,
        paged=True,
        note="pass search, a part of the code or of the label (AT, austria), to see the rest",
    ),
}
"""MCP result caps of their own, by task function name (conventions §8, sdk-core ADR-0038).

``get_data`` returns a cube, not a list, and keeps the default cap. The list tasks' caps
add the note that names ``search``. ``list_datasets`` keeps the family's 200 rows or
64 KB: no agent needs the whole table of contents at once (over 10,000 leaves, about 400
bytes each as compact JSON, so the bytes cut it at about 150), and a search narrows it to
what it looks for. ``list_codes`` takes up to 1,000 rows within the family's 64 KB
(sdk-core ADR-0038 decision 4): a code of the main base's codelists is about 45 to 70
bytes, so a codelist comes whole up to the byte bound, eleven of the twelve packaged on
2026-11-20 (UNIT's 773 codes are 57,670 bytes), and CXT_INDICATORS too; GEO's thousands,
the two PRODCOM product lists, whose labels are long, and CXT_NC's tens of thousands are
cut with the note (CXT_PRODCOM2_TOTAL's 822 codes at 652 rows on 2026-10-28).

Both caps are paged, ``ResultCap(paged=True)``, so their tools take ``offset`` and a cut
answer's note names the offset to continue with: the next page runs the task again and
sends nothing, since both tasks read packaged tables (sdk-core ADR-0047, as amended).
"""


GET_DATA_ARGUMENTS = (
    "format is always JSON, and lang, since_time_period, until_time_period, "
    "last_time_period and geo_level are arguments of get_data"
)
"""Where ``get_data`` sets the API's own parameters, for the refusal of one as a filter."""


UNKNOWN_FILTER_CODE = (
    "Eurostat answers a code that matches nothing with an empty cube, so the package refuses "
    "a code that the one packaged codelist of its dimension lacks; list_codes (over MCP, the "
    "tool eurostat_list_codes) lists its codes."
)
"""Why ``get_data`` refuses a filter's code before its request: the reason of its
``UnknownCode``."""


def _fed_by_one_codelist(base_url: str) -> dict[str, str]:
    """Each dimension that exactly one packaged codelist of ``base_url`` feeds, to its id."""
    fed: dict[str, list[str]] = {}
    for codelist, origin in params.CODELISTS.items():
        if origin.base_url == base_url:
            fed.setdefault(origin.param, []).append(codelist)
    return {param: codelists[0] for param, codelists in fed.items() if len(codelists) == 1}


CHECKED_FILTERS: Mapping[str, Mapping[str, str]] = {
    base_url: _fed_by_one_codelist(base_url) for base_url in (BASE_URL, COMEXT_BASE_URL)
}
"""The filters ``get_data`` checks before its request, by the base that serves the dataset:
each dimension that exactly one packaged codelist of that base feeds, the codelist's
``param``, to the codelist (conventions §5; the maintainer's decision of 2026-11-27 on
https://github.com/xippios/sdk-eurostat/issues/82). On the main base the twelve codelists,
one for each dimension; on the Comext base ``reporter``, ``flow`` and ``indicators``.
``product``, which CXT_PRODCOM2_SOLD, CXT_PRODCOM2_TOTAL and CXT_NC feed, and ``partner``,
the ``param`` of no packaged list, are sent unchecked, and so is a key of one base on a
dataset of the other, whose codes may be another coding system's, as ``freq`` of a ``DS-``
dataset takes CXT_FREQ, which is not packaged ("A code sent under a coding system the
packaged list does not hold goes unchecked", conventions §5)."""


@cache
def _codelist_codes(codelist: str) -> PackagedCodes:
    """The codes of the packaged ``codelist``, by id, for core's check of a filter.

    Compared without case, since the Statistics API takes a filter so ("DIMENSION_CODE and
    VALUE are case-insensitive", api-statistics.md), and so sent as the caller gave them
    (conventions §5); a refusal names the codelist by its id, which ``list_codes`` takes.
    """
    return params.packaged(codelist.lower()).codes(
        "code", "label", fold_case=True, list_name=codelist, source=SOURCE
    )


def _filters(
    filters: Mapping[str, str | Sequence[str]] | None, checked: Mapping[str, str]
) -> dict[str, str | list[str]]:
    """The filters as sent: one code or a list of codes per dimension; refusals first.

    A key that ``checked`` names, compared without case, has its codes checked against
    the codelist it maps to, by core's check of a packaged list; the keys are read in the
    caller's order, and the first problem found is refused (sdk-core ADR-0061, decision 7).

    Raises:
        InvalidRequestError: A filter names one of the API's own parameters, or gives an
            empty list of codes, which would send no filter for that dimension.
        UnknownCode: A checked filter's code that its codelist lacks.
    """
    sent: dict[str, str | list[str]] = {}
    for code, values in (filters or {}).items():
        if code.lower() in RESERVED_PARAMETERS:
            raise InvalidRequestError(
                f"filters[{code!r}]: {code} is a parameter of the Statistics API, not a "
                f"dimension; {GET_DATA_ARGUMENTS}. {NOTHING_SENT}",
                source=SOURCE,
            )
        listed = values if isinstance(values, str) else list(values)
        if not listed:
            raise InvalidRequestError(
                f"filters[{code!r}] lists no code: give one code or several, or leave "
                f"the dimension out to get all of its codes. {NOTHING_SENT}",
                source=SOURCE,
            )
        codelist = checked.get(code.lower())
        if codelist is not None:
            _codelist_codes(codelist).check(code, listed, reason=UNKNOWN_FILTER_CODE)
        sent[code] = listed
    return sent


def _names(
    sent: Mapping[str, str | list[str]], checked: Mapping[str, str]
) -> dict[str, dict[str, str]]:
    """``meta.names``: each checked filter's codes as the caller gave them, to their labels.

    The labels of the packaged codelist, runs of white space collapsed as a refusal shows
    them (sdk-core ADR-0067, decision 2); a filter that is not checked names no code.
    """
    names: dict[str, dict[str, str]] = {}
    for key, values in sent.items():
        codelist = checked.get(key.lower())
        if codelist is not None:
            codes = _codelist_codes(codelist)
            listed = [values] if isinstance(values, str) else values
            names[key] = {code: " ".join(str(codes.name_of(code)).split()) for code in listed}
    return names


NO_DATA = (
    "A code that the dataset does not use, or a period that Eurostat has not released, "
    "answers so, and the cube of a call without that filter lists the codes of each dimension."
)
"""What closes the refusal of a cube without a cell, after the call it names."""


def _no_data(request: Mapping[str, Any]) -> NotFoundError:
    """The refusal of a cube without a cell, naming the call as sent but its ``lang``.

    Raised after the request, so it says that the request was sent (conventions §5).
    """
    call = ", ".join(
        f"{name}={value!r}"
        for name, value in request.items()
        if name != "lang" and value is not None
    )
    return NotFoundError(
        f"Eurostat holds no data for get_data({call}): the request was sent, and its cube "
        f"has no cell with a value or a status. {NO_DATA}",
        source=SOURCE,
    )


def _member[E: StrEnum](enum: type[E], value: str, name: str) -> E:
    """``value`` as a member of ``enum``; a plain string is accepted, an unknown one refused.

    Raises:
        InvalidRequestError: ``value`` is none of the enumeration's values.
    """
    try:
        return enum(value)
    except ValueError:
        allowed = ", ".join(repr(member.value) for member in enum)
        raise InvalidRequestError(
            f"{name}={value!r} is not one of {allowed}. {NOTHING_SENT}", source=SOURCE
        ) from None


def _check_time_parameters(
    sent: Mapping[str, str | list[str]],
    since_time_period: str | None,
    until_time_period: str | None,
    last_time_period: int | None,
) -> None:
    """Refuse a combination of time parameters the Statistics API does not accept.

    "Using more than one Time parameter in the same query is not accepted. The only
    exception is using both sinceTimePeriod and untilTimePeriod." (api-statistics.md,
    "The Time parameter"). The Time parameters are a ``time`` or ``time_period`` filter,
    ``sinceTimePeriod``, ``untilTimePeriod`` and ``lastTimePeriod``; one alone, or exactly
    since with until, passes. Refused before any request (sdk-core ADR-0007).

    Raises:
        InvalidRequestError: Two or more of them, other than since with until; the
            message names the parameters given and the one exception.
    """
    given = [f"filters[{code!r}]" for code in sent if code.lower() in TIME_FILTERS]
    given += [
        name
        for name, value in (
            ("since_time_period", since_time_period),
            ("until_time_period", until_time_period),
            ("last_time_period", last_time_period),
        )
        if value is not None
    ]
    if len(given) > 1 and given != ["since_time_period", "until_time_period"]:
        raise InvalidRequestError(
            f"{', '.join(given)}: the Statistics API does not accept more than one time "
            "parameter in a query; the one exception is since_time_period with "
            f"until_time_period. {NOTHING_SENT}",
            source=SOURCE,
        )


async def get_data_async(
    dataset_code: str,
    *,
    filters: Mapping[str, str | Sequence[str]] | None = None,
    lang: Lang = Lang.EN,
    since_time_period: str | None = None,
    until_time_period: str | None = None,
    last_time_period: int | None = None,
    geo_level: GeoLevel | None = None,
) -> Result[Cube]:
    """Get one Eurostat dataset, or a slice of it, as a JSON-stat 2.0 cube.

    One request to the Statistics API, on Eurostat's Comext base for a ``DS-`` dataset
    (Comext trade, Prodcom production) and on the main base for any other. The cube lists
    the dataset's dimensions in order (``id``, ``size``), each dimension's codes with their
    positions and labels (``dimension``), and the cells that hold a value or a status
    (``value``, ``status``), keyed by cell index: row-major over ``size``, the last
    dimension varying fastest. A value is a number, or the text Eurostat prints where a
    Prodcom indicator is a unit or a flag (``"KG"``, ``":E"``). Keep slices small: the
    whole slice comes back at once. A filter's code that its codelist lacks is refused
    before sending. An unknown dataset, and a cube without a cell, raise ``NotFoundError``.
    A query Eurostat refuses or would answer asynchronously raises ``InvalidRequestError``,
    and one over its limit ``QueryTooLarge``, each naming how to narrow it.

    Args:
        dataset_code: The dataset's online data code, upstream's ``datasetCode``, e.g.
            ``"apro_mk_cola"`` (cows' milk collection and dairy products, annual),
            ``"apro_cpnh1"`` (crop production), ``"ef_m_farmleg"`` (farm indicators by
            legal status) or ``"DS-059358"`` (Prodcom: sold production, exports and
            imports, on the Comext base).
        filters: Dimension code to one code or a list of codes, each sent as
            ``DIMENSION_CODE=VALUE``; any dimension of the dataset, codes as in the
            cube's ``dimension``, case-insensitive, e.g. ``{"geo": "AT", "time":
            ["2022", "2023"]}``, ``{"geo": "AT", "milkitem": "PRD"}`` or, for
            DS-059358, ``{"reporter": "AT", "product": "10411200"}`` (fish and marine
            oils, NACE 10.41); ``time`` (or ``time_period``) filters periods and is a
            time parameter. ``None`` asks for every code of every dimension. The codes of
            a dimension that one packaged codelist of the dataset's base feeds are checked
            against it before sending, ``geo``, ``unit`` or ``milkitem`` on the main base,
            ``reporter``, ``flow`` or ``indicators`` on the Comext base, as
            ``list_codes`` lists them; ``product``, which three codelists feed, and
            ``partner`` are sent unchecked. A code that the dataset does not use answers a
            cube without a cell, ``NotFoundError``, and so may a period not yet released.
        lang: Language of the labels: ``"EN"`` (the default), ``"FR"`` or ``"DE"``.
        since_time_period: The first time period, included, e.g. ``"2022"``; combines
            with ``until_time_period`` and with no other time parameter, any other
            combination refused before sending.
        until_time_period: The last time period, included, e.g. ``"2023"``; combines
            with ``since_time_period`` and with no other time parameter.
        last_time_period: The number of most recent time periods, e.g. ``2``; alone,
            without another time parameter.
        geo_level: Selects geo codes by level instead of a ``geo`` filter:
            ``"aggregate"``, ``"country"``, ``"nuts1"``, ``"nuts2"``, ``"nuts3"`` or
            ``"city"``; never together with ``filters["geo"]``, which Eurostat refuses.
    """
    checked = CHECKED_FILTERS[
        COMEXT_BASE_URL if dataset_code.startswith(COMEXT_PREFIX) else BASE_URL
    ]
    sent = _filters(filters, checked)
    _check_time_parameters(sent, since_time_period, until_time_period, last_time_period)
    lang = _member(Lang, lang, "lang")
    if geo_level is not None:
        geo_level = _member(GeoLevel, geo_level, "geo_level")
    answer = await api.statistics.get_data(
        dataset_code,
        lang=lang,
        filters=sent,
        since_time_period=since_time_period,
        until_time_period=until_time_period,
        last_time_period=last_time_period,
        geo_level=geo_level,
    )
    request: dict[str, Any] = {
        "dataset_code": dataset_code,
        "filters": sent or None,
        "lang": lang.value,
        "since_time_period": since_time_period,
        "until_time_period": until_time_period,
        "last_time_period": last_time_period,
        "geo_level": None if geo_level is None else geo_level.value,
    }
    cube = answer.payload.cube
    if next(cube.observations(), None) is None:
        raise _no_data(request)
    updated = cube.updated
    meta = ResultMeta(
        source=SOURCE,
        endpoint=ENDPOINT,
        retrieved_at=answer.retrieved_at,
        published_at=updated,
        published_at_naive=updated is not None and updated.tzinfo is None,
        vintage=answer.payload.updated,
        request=request,
        names=_names(sent, checked),
    )
    return Result(data=cube, meta=meta)


get_data = sync(get_data_async)


def _release_time(text: str | None, form: str | None = None) -> datetime | None:
    """A release time as printed, parsed: ``form`` for ``strptime``, else ISO 8601.

    ``None`` when there is no text.
    """
    if text is None:
        return None
    return datetime.strptime(text, form) if form else datetime.fromisoformat(text)


CREATION_DATE = "%Y%m%dT%H%M"
"""How the TOC prints its ``creationDate``: ``"20261027T1000"``, no zone."""


async def list_datasets_async(*, search: str | None = None) -> Result[list[Dataset]]:
    """Find Eurostat datasets and tables by code or title in the table of contents.

    Answers from the package's copy of Eurostat's table of contents (``catalogue/toc/xml``),
    without a request: every dataset and pre-defined table of the navigation tree, over
    10,000 leaves, one per listing in the tree (a code filed under two folders appears
    twice). Each has its ``code``, its ``type`` (``"dataset"`` or ``"table"``), its English
    ``title``, the folders above it (``path``, joined with ``" > "``), its last data update
    and structure change as dates, which Eurostat prints day first (``"02.10.2026"``), its
    first and last period and its number of values, each ``None`` where Eurostat prints
    none. A dataset's ``code`` is what ``get_data`` takes as ``dataset_code``.
    ``meta.vintage`` is the table of contents' ``creationDate`` as printed
    (``"20261126T2200"``), and ``meta.retrieved_at`` is when the package's copy was
    fetched: a dataset Eurostat added since is missing until the package is refreshed.

    Args:
        search: Text to look for in the code or the English title, ignoring case, e.g.
            ``"milk"``, ``"apro_mk"`` or ``"crop production"``; give one, since the whole
            list is far more than one answer shows. ``None`` lists every leaf.
    """
    toc = params.packaged(params.TOC)
    created = params.list_info()[params.TOC].creation_date
    found = [leaf for leaf in params.datasets() if matches(search, leaf.code, leaf.title)]
    meta = toc.meta(
        SOURCE,
        request={"search": search},
        vintage=created,
        published_at=_release_time(created, CREATION_DATE),
        published_at_naive=created is not None,
    )
    return Result(data=found, meta=meta)


list_datasets = sync(list_datasets_async)


UNPACKAGED_CODELIST = (
    "The package carries the codelists of the dimensions of apro_cpnh1, apro_mk_cola and "
    "ef_m_farmleg, of the product and indicators dimensions of the Prodcom datasets "
    "DS-059358 and DS-059359, and of the product, reporter and partner, and flow dimensions "
    "of the Comext trade datasets DS-045409 and DS-059341, only; for any other dataset, "
    "the cube of get_data (over MCP, the tool eurostat_get_data) lists the codes it "
    "answers with on each dimension, with their labels."
)
"""Why ``list_codes`` refuses a codelist the package does not carry."""


@cache
def _codelists() -> PackagedCodes:
    """The packaged codelists by id and label, as core's check reads them (conventions §5).

    One record per codelist of ``reference/lists.json``, its id as ``codeListQuery``
    answered it, compared without case, as ``list_codes`` takes a codelist's name.
    """
    listed = PackagedList(
        param="codelist",
        endpoint=api.sdmx.CODELIST_ENDPOINT,
        fetched=params.index().fetched,
        records=[
            {"id": info.id, "label": info.label}
            for info in params.list_info().values()
            if info.kind == "codelist"
        ],
    )
    return listed.codes("id", "label", fold_case=True, source=SOURCE)


def _codelist_answer(
    info: params.ListInfo,
    search: str | None,
    request: Mapping[str, Any],
) -> Result[list[Code]]:
    """The codes of the packaged codelist ``info`` names that ``search`` keeps, with meta.

    sdk-core ADR-0041 decision 1: the packaged file's ``meta``, its version as ``vintage``
    and its ``LAST_UPDATED`` as ``published_at``, with the zone Eurostat prints; ``None``
    when the codelist carries no ``LAST_UPDATED`` (CXT_EU_FLUX).
    """
    packaged = params.packaged(info.name)
    found = [entry for entry in params.codes(info.name) if matches(search, entry.code, entry.label)]
    published = _release_time(info.last_updated)
    meta = packaged.meta(
        SOURCE,
        request=request,
        vintage=info.version,
        published_at=published,
        published_at_naive=published is not None and published.tzinfo is None,
    )
    return Result(data=found, meta=meta)


async def list_codes_async(codelist: str, *, search: str | None = None) -> Result[list[Code]]:
    """List the codes of one Eurostat codelist, the values a dimension filter takes.

    Answers from the package's copies of eighteen SDMX codelists
    (``sdmx/2.1/codelist/ESTAT/<ID>``, English labels), without a request: twelve of
    Eurostat's main base, the codelists of the dimensions of apro_cpnh1, apro_mk_cola and
    ef_m_farmleg, each named as its dimension is, and six of the Comext base, the codes of
    the Prodcom datasets DS-059358 and DS-059359 and of the trade datasets DS-045409 and
    DS-059341. A codelist holds every code Eurostat defines in it, more than any one
    dataset uses: GEO has thousands. A dimension's filter takes its codes, e.g.
    ``get_data("apro_mk_cola", filters={"geo": "AT"})``. A codelist the package does not
    carry raises ``UnknownCode`` naming the closest it does. ``meta.vintage`` is the codelist's
    version (``"29.0"``) and ``meta.published_at`` its last update, or ``None`` where it
    names none; a code Eurostat added since is missing until the package is refreshed.

    Args:
        codelist: The codelist, case-insensitive: of the main base ``"freq"``,
            ``"geo"``, ``"unit"``, ``"crops"``, ``"strucpro"``, ``"milkitem"``,
            ``"dairyprod"``, ``"statinfo"``, ``"leg_form"``, ``"farmtype"``,
            ``"so_eur"`` or ``"uaarea"``; of the Comext base ``"cxt_prodcom2_sold"``,
            the ``product`` codes of DS-059358 (sold production, exports and imports),
            ``"cxt_prodcom2_total"``, those of DS-059359 (total production),
            ``"cxt_indicators"``, the ``indicators`` codes of both, ``"cxt_nc"``, the
            ``product`` codes of DS-045409 and DS-059341, ``"cxt_free_iso"``, their
            ``reporter`` and ``partner`` codes and the Prodcom datasets' reporters, or
            ``"cxt_eu_flux"``, their ``flow`` codes.
        search: Text to look for in the code or the English label, ignoring case, e.g.
            ``"austria"``, ``"AT"``, ``"wheat"`` or ``"fertilisers"``; ``None`` lists
            every code.
    """
    name = _codelists().check("codelist", codelist.strip(), reason=UNPACKAGED_CODELIST)
    info = next(
        info
        for info in params.list_info().values()
        if info.kind == "codelist" and info.id is not None and info.id == name.upper()
    )
    return _codelist_answer(info, search, {"codelist": info.id, "search": search})


list_codes = sync(list_codes_async)


DOT_SEGMENTS = frozenset({".", ".."})
"""Keys a URL resolves away as a path segment before sending."""


async def _download(
    flow_ref: str,
    target: Path,
    request: Mapping[str, Any],
    *,
    key: str,
    start_period: str | None,
    end_period: str | None,
    last_n_observations: int | None = None,
) -> Result[Downloaded]:
    """Stream one SDMX-CSV data query, gzip-compressed, to ``target``, with its meta.

    The release is read from the file's first row through the parser: ``LAST UPDATE`` as
    printed as ``vintage`` and the naive time the row reads it into as ``published_at``
    (sdk-core ADR-0041 decision 2); ``request`` is ``meta.request`` as given.

    Raises:
        ValidationError: The file's header or first row is not SDMX-CSV as the parser
            reads it, a ``LAST UPDATE`` printed in another form among them; the file stays
            at ``target``.
    """
    downloaded = await api.sdmx.data_query(
        flow_ref,
        target,
        key=key,
        start_period=start_period,
        end_period=end_period,
        last_n_observations=last_n_observations,
        compressed=True,
    )
    with closing(parse_sdmx_csv(downloaded.path)) as rows:
        first = next(rows, None)
    published = None if first is None else first.last_update
    vintage = None if first is None else last_update_as_printed(downloaded.path)
    meta = ResultMeta(
        source=SOURCE,
        endpoint=api.sdmx.DATA_ENDPOINT,
        retrieved_at=downloaded.retrieved_at,
        published_at=published,
        published_at_naive=published is not None,
        vintage=vintage,
        request=dict(request),
    )
    return Result(data=downloaded, meta=meta)


async def download_dataset_async(
    flow_ref: str,
    key: str = "",
    *,
    start_period: str | None = None,
    end_period: str | None = None,
    last_n_observations: int | None = None,
    dest: str | os.PathLike[str],
) -> Result[Downloaded]:
    """Download a Eurostat dataset, or a slice of it, as a gzip-compressed SDMX-CSV file.

    Python only, no MCP tool or HTTP route (a bulk task). One request to the SDMX 2.1 API
    (``sdmx/2.1/data/{flowRef}/{key}?format=SDMX-CSV&compressed=true``), on Eurostat's
    Comext base for a ``DS-`` dataset (Comext trade, Prodcom production, e.g.
    ``"DS-059358"``) and on the main base for any other, streamed to ``dest``, never held
    in memory or cached; the file holds the answer as Eurostat sends
    it, gzip-compressed whatever ``dest``'s name, and ``parse_sdmx_csv(result.data.path)``
    from ``xippios.eurostat.parse`` reads it row by row. ``result.data`` is core's
    ``Downloaded``: the path, its size, the content type and Eurostat's file name
    (``"estat_apro_mk_cola_filtered_en.csv.gz"``). ``meta.vintage`` is the first row's
    ``LAST UPDATE`` as printed (``"05/10/26 23:00:00"``, day first) and
    ``meta.published_at`` the same time, which Eurostat prints without a zone
    (``meta.published_at_naive``); both are ``None`` when the file holds no row. ``key``
    is Eurostat's own: the dataset's dimensions but time, in structure order,
    dot-separated, empty for every code of a dimension, ``+`` between codes, as the
    dataset's SDMX-CSV columns before ``TIME_PERIOD`` or ``get_data``'s cube (``id``,
    without its last, ``time``) list them; it is sent as given, never looked up. A
    Comext trade dataset is not served whole, only filtered (the user guide's Comext
    page; Prodcom's datasets are the exception). A query Eurostat would answer
    asynchronously raises ``InvalidRequestError``, and one it refuses as too large
    ``QueryTooLarge`` (the user guide names 500,000 and 5,000,000 cells for a query it has
    not cached), each naming how to narrow it, and ``dest`` is left untouched; a
    file that is not SDMX-CSV raises ``ValidationError`` and stays at ``dest``. ``dest``
    must name a file in a directory that exists: a directory, or a missing one, is
    refused before any request.

    Args:
        flow_ref: The dataset's online data code, upstream's ``flowRef``, e.g.
            ``"apro_mk_cola"`` (cows' milk collection and dairy products, annual),
            ``"ef_m_farmleg"`` (farm indicators by legal status) or ``"DS-059358"``
            (Prodcom: sold production, exports and imports).
        key: Eurostat's series key, e.g. ``"A...THS_T.AT"`` for apro_mk_cola (freq A,
            every milkitem and dairyprod, unit THS_T, geo AT), ``"A.PRD.D1110D.THS_T.AT+DE"``
            (two geo codes) or ``"A.AT.10411200."`` for DS-059358 (freq A, reporter AT,
            product 10411200, every indicator); ``""``, the default, downloads every code
            of every dimension, the whole dataset.
        start_period: The first period, included, as the dataset prints it, e.g.
            ``"2022"`` or ``"2026-08"``; Eurostat's ``startPeriod``. ``None`` starts at the
            first.
        end_period: The last period, included, e.g. ``"2023"``; Eurostat's
            ``endPeriod``. ``None`` runs to the latest.
        last_n_observations: The most recent observations of each series, e.g. ``2``;
            Eurostat's ``lastNObservations``. ``None`` keeps them all.
        dest: The file to write, e.g. ``"apro_mk_cola.csv.gz"`` or
            ``Path("data") / "ef_m_farmleg.csv.gz"``, in a directory that exists; a file
            there is replaced once the download is complete.
    """
    if key in DOT_SEGMENTS:
        raise InvalidRequestError(
            f"key={key!r} wildcards every dimension, which a URL cannot carry as a path "
            f'segment: pass key="" for every code of every dimension. {NOTHING_SENT}',
            source=SOURCE,
        )
    request = {
        "flow_ref": flow_ref,
        "key": key,
        "start_period": start_period,
        "end_period": end_period,
        "last_n_observations": last_n_observations,
        "format": api.sdmx.DATA_FORMAT,
        "compressed": True,
    }
    return await _download(
        flow_ref,
        Path(dest),
        request,
        key=key,
        start_period=start_period,
        end_period=end_period,
        last_n_observations=last_n_observations,
    )


download_dataset = sync(download_dataset_async)
