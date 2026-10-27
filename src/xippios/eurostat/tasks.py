"""Task-shaped functions for Eurostat dissemination API.

The public API (ADR-0001, layer 2). A task composes endpoint wrappers from ``api/``,
resolves pagination and reference lookups, and returns ``Result[T]`` with full
``ResultMeta``. Write the async version, derive the sync one with ``xippios.core.sync``,
and list the sync name in ``__all__``: the MCP server and the HTTP router register
exactly what is named there.

Docstrings are read by agents: one sentence first, then ``Args:`` with examples of
valid values for every parameter. ``/add-endpoint`` walks through the whole recipe.

``get_data`` answers one Statistics API request (``api.statistics.getData``) as the
JSON-stat cube it returns. Release metadata: ``meta.published_at`` is the cube's
``updated``, the dataset's last update with its zone; ``meta.vintage`` is the same
member as upstream printed it (``"2026-10-05T23:00:00+0200"``), Eurostat's only release
identifier for a dataset (``docs/upstream/user-guide/api-introduction.md``: "there is no
versioning or documentation of past versions of the data"; ADR-0022 decision 2). An
``updated`` without a zone, never seen, goes into ``published_at`` as printed with
``published_at_naive`` set, no zone invented (ADR-0022 rule 2). ``meta.endpoint`` is the
operation's name, ``"getData"``; ``meta.request`` holds what was sent, a parameter left
``None`` omitted; ``meta.total`` stays ``None``: the answer counts no records for the
request (its ``OBS_COUNT`` annotation counts the whole dataset's, ADR-0012).

The slices, ``get_series``, ``get_latest_period`` and ``get_cross_section``, each send one
``get_data`` request (``sinceTimePeriod`` and ``untilTimePeriod``, ``lastTimePeriod=1``,
``time=<period>``) and return the cube's observations as a list, with ``get_data``'s
``meta``: ``meta.request`` names what was sent, in ``get_data``'s terms. Nothing here
compares datasets or sources (ADR-0003).

The list tasks, ``list_datasets`` and ``list_codes``, answer from the packaged lists
(``params``) without a request, by ADR-0022 rule 1: ``meta.retrieved_at`` is the list's
``fetched``, ``meta.endpoint`` the operation it was fetched from (``catalogue/toc/xml``,
``sdmx/2.1/codelist/ESTAT/<ID>``), ``meta.total`` ``None``. Their release metadata
(Johannes, 2026-10-27, D4) comes from ``reference/lists.json``: for the table of contents
``meta.vintage`` is its ``creationDate`` as printed (``"20261027T1000"``) and
``meta.published_at`` the same time without a zone, ``published_at_naive`` set (ADR-0022
rule 2); for a codelist ``meta.vintage`` is its version (``"28.0"``) and
``meta.published_at`` its ``LAST_UPDATED`` annotation with the zone Eurostat prints.
"""

import math
from collections.abc import Mapping, Sequence
from datetime import datetime
from enum import StrEnum
from typing import Any

from xippios.core import (
    InvalidRequestError,
    Result,
    ResultCap,
    ResultMeta,
    UnknownCode,
    closest,
    matches,
    sync,
)

from xippios.eurostat import api, params
from xippios.eurostat._client import SOURCE
from xippios.eurostat.api.statistics import ENDPOINT
from xippios.eurostat.models import Code, Cube, Dataset, GeoLevel, Lang, Observation

__all__ = [
    "get_cross_section",
    "get_data",
    "get_latest_period",
    "get_series",
    "list_codes",
    "list_datasets",
]

BULK_TASKS: frozenset[str] = frozenset()
"""Tasks the adapters skip (ADR-0019 decision 4): none yet. Written by hand until
template v0.3.0 renders it (D33)."""

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
    "get_series": ResultCap(
        max_rows=200,
        note=(
            "rows run in cube order, which runs oldest period first in every recorded "
            "cube: pass since, the period after the last row shown, to see the later ones"
        ),
    ),
    "get_latest_period": ResultCap(
        max_rows=200,
        note=(
            "pin more dimensions in filters, one code each (geo, unit, a product), to see the rest"
        ),
    ),
    "get_cross_section": ResultCap(
        max_rows=200,
        note=(
            "pin more dimensions in filters, one code each (a product, a unit), or give "
            "geo a list of codes, to see the rest"
        ),
    ),
    "list_datasets": ResultCap(
        note=(
            "pass search, a word of the title or a part of the code (milk, apro_mk), "
            "to see the rest"
        ),
    ),
    "list_codes": ResultCap(
        max_rows=1000,
        note="pass search, a part of the code or of the label (AT, austria), to see the rest",
    ),
}
"""MCP result caps of their own, by task function name (conventions §8, ADR-0016).

The slices serve lists of observations, 234 to 453 bytes each as compact JSON (UTF-8,
as ``cap_result`` counts them) in the seven recorded slice answers, so the family's
64 KB holds about 145 to 280 rows and the 200 rows stay the family's too: every
recorded series (9 and 5 rows) and cross-section (36 rows, one series over every geo
code; 151 rows, five series over every geo code) comes whole, and the latest period of
a whole ef_m_farmleg table for one country (1,810 rows) is cut. What each cap adds is
its note, naming the task's own way to see the rest. ``get_data`` returns a cube, not a
list, and keeps the default cap.

The list tasks' caps add the note that names ``search``. ``list_datasets`` keeps the
family's 200 rows or 64 KB: no agent needs the whole table of contents at once (over
10,000 leaves, about 400 bytes each as compact JSON, so the bytes cut it at about 150),
and a search narrows it to what it looks for. ``list_codes`` takes up to 1,000 rows within
the family's 64 KB (ADR-0016 decision 4): a code is about 45 to 70 bytes, so a codelist
comes whole up to the byte bound, eleven of the twelve packaged on 2026-10-27 (UNIT's 773
codes are 57,670 bytes), and GEO's thousands are cut with the note.
"""


GET_DATA_ARGUMENTS = (
    "format is always JSON, and lang, since_time_period, until_time_period, "
    "last_time_period and geo_level are arguments of get_data"
)
"""Where ``get_data`` sets the API's own parameters, for the refusal of one as a filter."""


def _filters(
    filters: Mapping[str, str | Sequence[str]] | None,
    *,
    arguments: str = GET_DATA_ARGUMENTS,
    time_rule: str | None = None,
) -> dict[str, str | list[str]]:
    """The filters as sent: one code or a list of codes per dimension; refusals first.

    Args:
        filters: The caller's filters.
        arguments: What the refusal of one of the API's own parameters says about where
            the task sets it.
        time_rule: For a task that selects periods itself: a ``time`` or ``time_period``
            filter is refused with this text. ``None`` lets it through.

    Raises:
        InvalidRequestError: A filter names one of the API's own parameters, or the time
            dimension where ``time_rule`` is given, or gives an empty list of codes,
            which would send no filter for that dimension.
    """
    sent: dict[str, str | list[str]] = {}
    for code, values in (filters or {}).items():
        if code.lower() in RESERVED_PARAMETERS:
            raise InvalidRequestError(
                f"filters[{code!r}]: {code} is a parameter of the Statistics API, not a "
                f"dimension; {arguments}",
                source=SOURCE,
            )
        if time_rule is not None and code.lower() in TIME_FILTERS:
            raise InvalidRequestError(f"filters[{code!r}]: {time_rule}", source=SOURCE)
        listed = values if isinstance(values, str) else list(values)
        if not listed:
            raise InvalidRequestError(
                f"filters[{code!r}] lists no code: give one code or several, or leave "
                "the dimension out to get all of its codes",
                source=SOURCE,
            )
        sent[code] = listed
    return sent


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
            f"{name}={value!r} is not one of {allowed}", source=SOURCE
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
    since with until, passes. Refused before any request (ADR-0007).

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
            "until_time_period",
            source=SOURCE,
        )


async def get_data_async(
    dataset: str,
    filters: Mapping[str, str | Sequence[str]] | None = None,
    *,
    lang: Lang = Lang.EN,
    since_time_period: str | None = None,
    until_time_period: str | None = None,
    last_time_period: int | None = None,
    geo_level: GeoLevel | None = None,
) -> Result[Cube]:
    """Get one Eurostat dataset, or a slice of it, as a JSON-stat 2.0 cube.

    One request to the Statistics API. The cube lists the dataset's dimensions in order
    (``id``, ``size``), each dimension's codes with their positions and labels
    (``dimension``), and the cells that hold a value or a status (``value``,
    ``status``), keyed by cell index: row-major over ``size``, the last dimension
    varying fastest. ``updated`` is the dataset's last update; ``extension`` carries
    Eurostat's annotations as sent. In Python, ``result.data.observations()`` reads the
    cells out one by one with their codes and labels. Keep slices small (a country or
    two, a few periods): the whole slice comes back at once. A filter code that matches
    nothing gives an empty cube (size 0 on that dimension, no values), not an error. An
    unknown dataset, or Eurostat's "No results found", raises ``NotFoundError``. More
    than one time parameter (a ``time`` filter, since, until, last), other than
    ``since_time_period`` with ``until_time_period``, is refused before any request with
    ``InvalidRequestError``. A query Eurostat refuses (an unknown dimension, ``geo``
    with ``geo_level``) raises ``InvalidRequestError`` with Eurostat's message, and so
    does one it judges too large, naming how to narrow it, or one it would answer
    asynchronously: send the same request again later, or narrow it.

    Args:
        dataset: The dataset's online data code, e.g. ``"apro_mk_cola"`` (cows' milk
            collection and dairy products, annual), ``"apro_cpnh1"`` (crop production)
            or ``"ef_m_farmleg"`` (farm indicators by legal status).
        filters: Dimension code to one code or a list of codes, each sent as
            ``DIMENSION_CODE=VALUE``; any dimension of the dataset, codes as in the
            cube's ``dimension``, case-insensitive, e.g. ``{"geo": "AT", "time":
            ["2022", "2023"]}`` or ``{"geo": "AT", "milkitem": "PRD"}``; ``time`` (or
            ``time_period``) filters periods and is a time parameter. ``None`` asks for
            every code of every dimension.
        lang: Language of the labels: ``"EN"`` (the default), ``"FR"`` or ``"DE"``.
        since_time_period: The first time period, included, e.g. ``"2022"``; combines
            with ``until_time_period`` and with no other time parameter.
        until_time_period: The last time period, included, e.g. ``"2023"``; combines
            with ``since_time_period`` and with no other time parameter.
        last_time_period: The number of most recent time periods, e.g. ``2``; alone,
            without another time parameter.
        geo_level: Selects geo codes by level instead of a ``geo`` filter:
            ``"aggregate"``, ``"country"``, ``"nuts1"``, ``"nuts2"``, ``"nuts3"`` or
            ``"city"``; never together with ``filters["geo"]``.
    """
    sent = _filters(filters)
    _check_time_parameters(sent, since_time_period, until_time_period, last_time_period)
    lang = _member(Lang, lang, "lang")
    if geo_level is not None:
        geo_level = _member(GeoLevel, geo_level, "geo_level")
    answer = await api.statistics.getData(
        dataset,
        lang=lang,
        filters=sent,
        since_time_period=since_time_period,
        until_time_period=until_time_period,
        last_time_period=last_time_period,
        geo_level=geo_level,
    )
    request: dict[str, Any] = {
        "dataset": dataset,
        "filters": sent or None,
        "lang": lang.value,
        "since_time_period": since_time_period,
        "until_time_period": until_time_period,
        "last_time_period": last_time_period,
        "geo_level": None if geo_level is None else geo_level.value,
    }
    updated = answer.cube.updated
    meta = ResultMeta(
        source=SOURCE,
        endpoint=ENDPOINT,
        retrieved_at=answer.retrieved_at,
        published_at=updated,
        published_at_naive=updated is not None and updated.tzinfo is None,
        vintage=answer.updated,
        request=request,
    )
    return Result(data=answer.cube, meta=meta)


get_data = sync(get_data_async)


SHOWN_CODES = 20
"""The most codes of one dimension that ``get_series``'s refusal lists; it says how many
more there are."""


def _time_dimension(cube: Cube) -> str | None:
    """The code of the cube's time dimension (``time``), or ``None`` if it has none."""
    return next((name for name in cube.id if name.lower() in TIME_FILTERS), None)


def _one_series(dataset: str, cube: Cube) -> None:
    """Refuse a cube that spans more than one series.

    A cube spans more than one series when a dimension other than time has more than one
    code.

    Raises:
        InvalidRequestError: Naming each such dimension with its codes (the first
            ``SHOWN_CODES`` and how many more), for the caller to pin one in ``filters``.
    """
    time = _time_dimension(cube)
    spread = [
        (name, size)
        for name, size in zip(cube.id, cube.size, strict=True)
        if name != time and size > 1
    ]
    if not spread:
        return
    named = []
    for name, size in spread:
        index = cube.dimension[name].category.index
        codes = sorted(index, key=index.__getitem__)
        more = f" and {size - SHOWN_CODES} more" if size > SHOWN_CODES else ""
        named.append(f"{name} ({size} codes: {', '.join(codes[:SHOWN_CODES])}{more})")
    series = math.prod(size for _, size in spread)
    raise InvalidRequestError(
        f"the answer for {dataset} spans up to {series} series, not one: pin each of these "
        f"dimensions to one code in filters: {'; '.join(named)}",
        source=SOURCE,
    )


async def get_series_async(
    dataset: str,
    filters: Mapping[str, str | Sequence[str]],
    *,
    since: str | None = None,
    until: str | None = None,
    lang: Lang = Lang.EN,
) -> Result[list[Observation]]:
    """Get one time series of a Eurostat dataset as observations, in its time dimension's order.

    One request to the Statistics API. ``filters`` pins every dimension but time to one
    code, so that the answer is one series; ``since`` and ``until`` bound its periods, which
    come in the order of the dataset's time dimension (oldest first in apro_mk_cola and
    ef_m_farmleg). Each observation carries its code and label on every dimension, its value
    and its status (``"|C"`` confidential, say). A dimension left out of ``filters`` is fine
    when the dataset has one code there (``freq`` ``"A"`` in an annual dataset). An answer
    that spans more than one series, a dimension other than time with more than one code,
    raises ``InvalidRequestError`` naming each such dimension and its codes: pin one and ask
    again (the request is spent, since only the answer shows it). A code that matches
    nothing gives an empty list. A ``time`` filter is refused before any request: ``since``
    and ``until`` select the periods. An unknown dataset raises ``NotFoundError``; a query
    Eurostat refuses or judges too large, ``InvalidRequestError`` with its message.

    Args:
        dataset: The dataset's online data code, e.g. ``"apro_mk_cola"`` (cows' milk
            collection and dairy products, annual) or ``"ef_m_farmleg"`` (farm
            indicators by legal status).
        filters: Every dimension but time, each to one code, codes as in
            ``get_data``'s cube, case-insensitive, e.g. ``{"milkitem": "PRD",
            "dairyprod": "D1110D", "unit": "THS_T", "geo": "AT"}`` for apro_mk_cola or
            ``{"statinfo": "TOTAL", "leg_form": "PER_NTL", "farmtype": "FT1",
            "so_eur": "TOTAL", "uaarea": "TOTAL", "unit": "HLD", "geo": "AT"}`` for
            ef_m_farmleg.
        since: The first period, included, as the dataset's time dimension prints it,
            e.g. ``"2015"`` (annual) or ``"2026-08"`` (monthly, as in apro_ec_poulm);
            ``None`` starts at the dataset's first period. Eurostat's ``sinceTimePeriod``.
        until: The last period, included, e.g. ``"2023"`` or ``"2026-09"``; ``None`` runs
            to the latest. Eurostat's ``untilTimePeriod``.
        lang: Language of the labels: ``"EN"`` (the default), ``"FR"`` or ``"DE"``.
    """
    sent = _filters(
        filters,
        arguments=(
            "format is always JSON, lang is an argument of get_series and since and until "
            "select its periods; get_data takes the other time parameters and geo_level"
        ),
        time_rule=(
            "get_series selects periods with since and until; filters pins every dimension but time"
        ),
    )
    answer = await get_data_async(
        dataset, sent, lang=lang, since_time_period=since, until_time_period=until
    )
    cube = answer.data
    observations = list(cube.observations())
    if not observations:
        return Result(data=[], meta=answer.meta)
    _one_series(dataset, cube)
    # One series: every other dimension has one code, so a cell's index is its period's
    # position in the time dimension, and cube order is the time category's index order.
    return Result(data=observations, meta=answer.meta)


get_series = sync(get_series_async)


async def get_latest_period_async(
    dataset: str,
    filters: Mapping[str, str | Sequence[str]] | None = None,
    *,
    lang: Lang = Lang.EN,
) -> Result[list[Observation]]:
    """Get the observations of a Eurostat dataset's most recent period, for the filters.

    One request to the Statistics API with ``lastTimePeriod=1``, Eurostat's "most recent
    data": the latest position of the time dimension, one period for the whole answer, not
    each series' own latest; a series without a cell in that period is absent. Any number of
    series, in cube order (the dimensions in the dataset's order, the last varying fastest),
    each observation with its code and label on every dimension, its value and its status.
    Keep the slice small with ``filters`` (a country, a product): it comes back whole. A
    code that matches nothing gives an empty list. A ``time`` filter is refused before any
    request: the task asks for the latest period itself (``get_cross_section`` takes one
    period). An unknown dataset raises ``NotFoundError``; a query Eurostat refuses or judges
    too large, ``InvalidRequestError`` with its message.

    Args:
        dataset: The dataset's online data code, e.g. ``"apro_mk_cola"`` (cows' milk
            collection and dairy products, annual) or ``"apro_cpnh1"`` (crop
            production).
        filters: Dimension code to one code or a list of codes, any dimension but time,
            codes as in ``get_data``'s cube, case-insensitive, e.g. ``{"milkitem":
            "PRD", "dairyprod": "D1110D", "unit": "THS_T", "geo": "AT"}`` for
            apro_mk_cola or ``{"crops": "C1110", "geo": ["AT", "DE"]}`` for apro_cpnh1;
            ``None`` asks for every code of every dimension.
        lang: Language of the labels: ``"EN"`` (the default), ``"FR"`` or ``"DE"``.
    """
    sent = _filters(
        filters,
        arguments=(
            "format is always JSON and lang is an argument of get_latest_period, which "
            "asks for the latest period itself; get_data takes the other time parameters "
            "and geo_level"
        ),
        time_rule=(
            "get_latest_period asks for the latest period itself; leave time out of "
            "filters, or ask get_cross_section for one period"
        ),
    )
    answer = await get_data_async(dataset, sent, lang=lang, last_time_period=1)
    return Result(data=list(answer.data.observations()), meta=answer.meta)


get_latest_period = sync(get_latest_period_async)


async def get_cross_section_async(
    dataset: str,
    period: str,
    filters: Mapping[str, str | Sequence[str]] | None = None,
    *,
    lang: Lang = Lang.EN,
) -> Result[list[Observation]]:
    """Get the observations of one period of a Eurostat dataset, for the filters.

    One request to the Statistics API with ``time=<period>``. Any number of series, in
    cube order (the dimensions in the dataset's order, the last varying fastest), each
    observation with its code and label on every dimension, its value and its status:
    leave ``geo`` out of ``filters`` for every geo code the dataset holds, European
    aggregates (``"EU27_2020"``) and countries alike. Keep the slice small with
    ``filters`` (one product, one unit): it comes back whole. A code that matches nothing
    gives an empty list. A ``time`` filter, and an empty ``period``, are refused before any
    request: ``period`` is the one period. An unknown dataset raises ``NotFoundError``; a
    query Eurostat refuses or judges too large, ``InvalidRequestError`` with its message.

    Args:
        dataset: The dataset's online data code, e.g. ``"apro_mk_cola"`` (cows' milk
            collection and dairy products, annual) or ``"apro_cpnh1"`` (crop
            production).
        period: The period, as the dataset's time dimension prints it, e.g. ``"2023"``
            (annual) or ``"2026-08"`` (monthly, as in apro_ec_poulm).
        filters: Dimension code to one code or a list of codes, any dimension but time,
            codes as in ``get_data``'s cube, case-insensitive, e.g. ``{"milkitem":
            "PRD", "dairyprod": "D1110D", "unit": "THS_T"}`` for apro_mk_cola or
            ``{"crops": "C1110", "strucpro": "HPRD_THS_T"}`` for apro_cpnh1; ``None``
            asks for every code of every dimension.
        lang: Language of the labels: ``"EN"`` (the default), ``"FR"`` or ``"DE"``.
    """
    sent = _filters(
        filters,
        arguments=(
            "format is always JSON, lang is an argument of get_cross_section and period "
            "selects its period; get_data takes the other time parameters and geo_level"
        ),
        time_rule="get_cross_section takes its one period as period; leave time out of filters",
    )
    if not period.strip():
        raise InvalidRequestError(
            f"period={period!r}: give one period as the dataset's time dimension prints it, "
            'e.g. "2023" or "2026-08"',
            source=SOURCE,
        )
    answer = await get_data_async(dataset, {**sent, "time": period}, lang=lang)
    return Result(data=list(answer.data.observations()), meta=answer.meta)


get_cross_section = sync(get_cross_section_async)


def _release_time(text: str | None, form: str | None = None) -> datetime | None:
    """A release time as printed, parsed: ``form`` for ``strptime``, else ISO 8601.

    ``None`` when there is no text.
    """
    if text is None:
        return None
    return datetime.strptime(text, form) if form else datetime.fromisoformat(text)


CREATION_DATE = "%Y%m%dT%H%M"
"""How the TOC prints its ``creationDate``: ``"20261027T1000"``, no zone."""


async def list_datasets_async(search: str | None = None) -> Result[list[Dataset]]:
    """Find Eurostat datasets and tables by code or title in the table of contents.

    Answers from the package's copy of Eurostat's table of contents (``catalogue/toc/xml``),
    without a request: every dataset and pre-defined table of the navigation tree, over
    10,000 leaves, one per place in the tree (a code filed under two folders appears
    twice). Each has its ``code``, its ``type`` (``"dataset"`` or ``"table"``), its
    English ``title``, the folders above it (``path``, their titles joined with
    ``" > "``), its last data update and structure change as Eurostat prints them, day
    first (``"02.10.2026"``), its first and last period and its number of values.
    ``search`` keeps the leaves whose code or title contains the text, ignoring case:
    give one, since the whole list is far more than one answer shows. A dataset's
    ``code`` is what ``get_data`` and the slices take as ``dataset``. ``meta.vintage`` is
    the table of contents' ``creationDate`` as printed (``"20261027T1000"``) and
    ``meta.published_at`` the same time, which Eurostat prints without a zone
    (``meta.published_at_naive``); ``meta.retrieved_at`` is when the package's copy was
    fetched. A dataset Eurostat added since is missing until the package is refreshed.

    Args:
        search: Text to look for in the code or the English title, ignoring case, e.g.
            ``"milk"``, ``"apro_mk"`` or ``"crop production"``; ``None`` lists every
            leaf.
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
    "ef_m_farmleg only; for any other dataset, get_data's cube lists the codes it answers "
    "with on each dimension, with their labels."
)
"""Why ``list_codes`` refuses a codelist the package does not carry."""


async def list_codes_async(codelist: str, search: str | None = None) -> Result[list[Code]]:
    """List the codes of one Eurostat codelist, the values a dimension filter takes.

    Answers from the package's copies of twelve SDMX codelists
    (``sdmx/2.1/codelist/ESTAT/<ID>``, English labels), without a request: FREQ, GEO,
    UNIT, CROPS, STRUCPRO, MILKITEM, DAIRYPROD, STATINFO, LEG_FORM, FARMTYPE, SO_EUR and
    UAAREA, the codelists of the dimensions of apro_cpnh1, apro_mk_cola and
    ef_m_farmleg, each named as its dimension is in upper case. A codelist holds every
    code Eurostat defines in it, more than any one dataset uses: GEO has thousands. A
    dimension's filter takes its codes, e.g. ``get_data("apro_mk_cola", {"geo": "AT"})``.
    ``search`` keeps the codes whose code or label contains the text, ignoring case.
    A codelist the package does not carry raises ``UnknownCode`` naming the closest it
    does. ``meta.vintage`` is the codelist's version (``"28.0"``) and
    ``meta.published_at`` its last update, with Eurostat's zone; ``meta.retrieved_at``
    is when the package's copy was fetched. A code Eurostat added since is missing until
    the package is refreshed.

    Args:
        codelist: The codelist, case-insensitive: ``"geo"``, ``"unit"``, ``"freq"``,
            ``"crops"``, ``"strucpro"``, ``"milkitem"``, ``"dairyprod"``,
            ``"statinfo"``, ``"leg_form"``, ``"farmtype"``, ``"so_eur"`` or
            ``"uaarea"``.
        search: Text to look for in the code or the English label, ignoring case, e.g.
            ``"austria"``, ``"AT"`` or ``"wheat"``; ``None`` lists every code.
    """
    known = {
        info.id: info
        for info in params.list_info().values()
        if info.kind == "codelist" and info.id is not None
    }
    info = known.get(codelist.strip().upper())
    if info is None or info.id is None:
        raise UnknownCode(
            "codelist",
            codelist,
            list_name="codelist",
            fetched=params.packaged(params.INDEX).fetched,
            closest=closest(codelist, {code: entry.label or code for code, entry in known.items()}),
            reason=UNPACKAGED_CODELIST,
            source=SOURCE,
        )
    packaged = params.packaged(info.name)
    found = [entry for entry in params.codes(info.name) if matches(search, entry.code, entry.label)]
    published = _release_time(info.last_updated)
    meta = packaged.meta(
        SOURCE,
        request={"codelist": info.id, "search": search},
        vintage=info.version,
        published_at=published,
        published_at_naive=published is not None and published.tzinfo is None,
    )
    return Result(data=found, meta=meta)


list_codes = sync(list_codes_async)
