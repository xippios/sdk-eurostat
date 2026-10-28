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

The production tasks, ``get_sold_production`` and ``get_total_production``, read
Prodcom's two datasets on the Comext base, DS-059358 (sold production, exports and
imports) and DS-059359 (total production): each sends one ``get_data`` request, as the
slices do, with a ``product`` filter, ``reporter`` and ``indicators`` filters where
given and ``sinceTimePeriod`` and ``untilTimePeriod``, and returns the cube's
observations in cube order with ``get_data``'s ``meta``. The product is checked against
the dataset's packaged product list first (CXT_PRODCOM2_SOLD, CXT_PRODCOM2_TOTAL), and
each indicator against CXT_INDICATORS, so a code a list lacks raises ``UnknownCode``
without a request (conventions §5); a reporter is sent as given, since no list of
reporters is packaged, and one the dataset lacks gives an empty list, as an unknown
code gives ``get_data`` an empty cube.

The list tasks, ``list_datasets``, ``list_codes`` and ``list_products``, answer from the
packaged lists (``params``) without a request, by ADR-0022 rule 1: ``meta.retrieved_at``
is the list's ``fetched``, ``meta.endpoint`` the operation it was fetched from
(``catalogue/toc/xml``, ``sdmx/2.1/codelist/ESTAT/<ID>``, or for a codelist of the
Comext base its full URL), ``meta.total`` ``None``. Their release metadata (Johannes,
2026-10-27, D4) comes from ``reference/lists.json``: for the table of contents
``meta.vintage`` is its ``creationDate`` as printed (``"20261027T1000"``) and
``meta.published_at`` the same time without a zone, ``published_at_naive`` set (ADR-0022
rule 2); for a codelist ``meta.vintage`` is its version (``"28.0"``) and
``meta.published_at`` its ``LAST_UPDATED`` annotation with the zone Eurostat prints.

``download_dataset`` is the bulk task, named in ``BULK_TASKS`` and so Python-only: the
adapters skip it, no tool or route returns a file path (ADR-0019 decision 4). It streams
one SDMX 2.1 data query (``api.sdmx.data_query``) as gzip-compressed SDMX-CSV to the file
the caller names and returns ``Result[Downloaded]``; ``parse.parse_sdmx_csv`` reads the
file. Its release metadata comes from the file's first row, read through the parser:
``meta.vintage`` is ``LAST UPDATE`` as printed (``"05/10/26 23:00:00"``) and
``meta.published_at`` the same time without a zone, ``published_at_naive`` set
(ADR-0022 rule 2); ``meta.endpoint`` is ``"dataQuery"``.
"""

import functools
import math
import os
from collections.abc import Mapping, Sequence
from contextlib import closing
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Any

from xippios.core import (
    Downloaded,
    InvalidRequestError,
    Result,
    ResultCap,
    ResultMeta,
    UnknownCode,
    ValidationError,
    closest,
    matches,
    sync,
)

from xippios.eurostat import api, params
from xippios.eurostat._client import SOURCE
from xippios.eurostat.api.statistics import ENDPOINT
from xippios.eurostat.models import Code, Cube, Dataset, GeoLevel, Lang, Observation
from xippios.eurostat.parse import parse_sdmx_csv

__all__ = [
    "download_dataset",
    "get_cross_section",
    "get_data",
    "get_latest_period",
    "get_series",
    "get_sold_production",
    "get_total_production",
    "list_codes",
    "list_datasets",
    "list_products",
]

BULK_TASKS: frozenset[str] = frozenset({"download_dataset"})
"""Tasks the adapters skip (ADR-0019 decision 4): ``download_dataset``, which writes a
file and is Python-only. Core's ``build_server`` and ``router_from_tasks`` read it from
this module and leave its names out, so ``mcp.py`` and ``http.py`` pass ``__all__`` whole."""

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
    "list_products": ResultCap(
        max_rows=1000,
        note=(
            "pass search, a part of the code or of the label (1041, soya, oilcake), to see the rest"
        ),
    ),
    "get_sold_production": ResultCap(
        max_rows=200,
        note=(
            "rows run reporter by reporter and indicator by indicator, oldest year first: "
            "ask for fewer reporters or indicators (PRODVAL, PRODQNT, QNTUNIT), or a later "
            "since, to see the rest"
        ),
    ),
    "get_total_production": ResultCap(
        max_rows=200,
        note=(
            "rows run reporter by reporter and indicator by indicator, oldest year first: "
            "ask for fewer reporters or indicators (APRODQNT, QNTUNIT), or a later since, "
            "to see the rest"
        ),
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

The production tasks serve the same observations, 258 to 346 bytes each as compact JSON
in the two recorded Prodcom answers, a product's label in every one, so the family's
64 KB holds about 190 to 250 rows and they keep the family's 200 rows too: one product
for one reporter over two years is 22 rows (DS-059358, 23 indicators) or 4 (DS-059359,
4 indicators), and every reporter over every year is cut, with a note naming
``reporters``, ``indicators`` and ``since``.

The list tasks' caps add the note that names ``search``. ``list_datasets`` keeps the
family's 200 rows or 64 KB: no agent needs the whole table of contents at once (over
10,000 leaves, about 400 bytes each as compact JSON, so the bytes cut it at about 150),
and a search narrows it to what it looks for. ``list_codes`` takes up to 1,000 rows within
the family's 64 KB (ADR-0016 decision 4): a code is about 45 to 70 bytes, so a codelist
comes whole up to the byte bound, eleven of the twelve of the main base packaged on
2026-10-27 (UNIT's 773 codes are 57,670 bytes) and CXT_INDICATORS, and GEO's thousands
and the PRODCOM lists' hundreds of long labels are cut with the note. ``list_products``
takes the same cap, so a search for a NACE class (``"1041"``, 42 products of oils and
fats) or a word comes whole.
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

    One request to the Statistics API; a ``DS-`` dataset (Comext trade, Prodcom
    production, e.g. ``"DS-059358"``) is requested on Eurostat's Comext base, any other
    on the main base. The cube lists the dataset's dimensions in order (``id``,
    ``size``), each dimension's codes with their positions and labels (``dimension``),
    and the cells that hold a value or a status (``value``, ``status``), keyed by cell
    index: row-major over ``size``, the last dimension varying fastest. A value is a
    number, or the text Eurostat prints where a Prodcom indicator is a unit or a flag
    (``"KG"``, ``":E"``). ``updated`` is the dataset's last update; ``extension`` carries
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
            collection and dairy products, annual), ``"apro_cpnh1"`` (crop production),
            ``"ef_m_farmleg"`` (farm indicators by legal status) or ``"DS-059358"``
            (Prodcom: sold production, exports and imports, on the Comext base).
        filters: Dimension code to one code or a list of codes, each sent as
            ``DIMENSION_CODE=VALUE``; any dimension of the dataset, codes as in the
            cube's ``dimension``, case-insensitive, e.g. ``{"geo": "AT", "time":
            ["2022", "2023"]}``, ``{"geo": "AT", "milkitem": "PRD"}`` or, for
            DS-059358, ``{"reporter": "AT", "product": "10411200"}`` (fish and marine
            oils, NACE 10.41); ``time`` (or
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
    answer = await api.statistics.get_data(
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
    Eurostat refuses or judges too large, ``InvalidRequestError`` with its message. A
    ``DS-`` dataset (Comext, Prodcom) is requested on Eurostat's Comext base.

    Args:
        dataset: The dataset's online data code, e.g. ``"apro_mk_cola"`` (cows' milk
            collection and dairy products, annual), ``"ef_m_farmleg"`` (farm
            indicators by legal status) or ``"DS-059358"`` (Prodcom: sold production,
            exports and imports).
        filters: Every dimension but time, each to one code, codes as in
            ``get_data``'s cube, case-insensitive, e.g. ``{"milkitem": "PRD",
            "dairyprod": "D1110D", "unit": "THS_T", "geo": "AT"}`` for apro_mk_cola or
            ``{"statinfo": "TOTAL", "leg_form": "PER_NTL", "farmtype": "FT1",
            "so_eur": "TOTAL", "uaarea": "TOTAL", "unit": "HLD", "geo": "AT"}`` for
            ef_m_farmleg or ``{"reporter": "AT", "product": "10411200", "indicators":
            "EXPVAL"}`` for DS-059358.
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
    too large, ``InvalidRequestError`` with its message. A ``DS-`` dataset (Comext,
    Prodcom) is requested on Eurostat's Comext base.

    Args:
        dataset: The dataset's online data code, e.g. ``"apro_mk_cola"`` (cows' milk
            collection and dairy products, annual), ``"apro_cpnh1"`` (crop
            production) or ``"DS-059358"`` (Prodcom: sold production, exports and
            imports).
        filters: Dimension code to one code or a list of codes, any dimension but time,
            codes as in ``get_data``'s cube, case-insensitive, e.g. ``{"milkitem":
            "PRD", "dairyprod": "D1110D", "unit": "THS_T", "geo": "AT"}`` for
            apro_mk_cola, ``{"crops": "C1110", "geo": ["AT", "DE"]}`` for apro_cpnh1 or
            ``{"reporter": "AT", "product": "10411200"}`` for DS-059358; ``None`` asks
            for every code of every dimension.
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
    A ``DS-`` dataset (Comext, Prodcom) is requested on Eurostat's Comext base.

    Args:
        dataset: The dataset's online data code, e.g. ``"apro_mk_cola"`` (cows' milk
            collection and dairy products, annual), ``"apro_cpnh1"`` (crop
            production) or ``"DS-059358"`` (Prodcom: sold production, exports and
            imports).
        period: The period, as the dataset's time dimension prints it, e.g. ``"2023"``
            (annual) or ``"2026-08"`` (monthly, as in apro_ec_poulm).
        filters: Dimension code to one code or a list of codes, any dimension but time,
            codes as in ``get_data``'s cube, case-insensitive, e.g. ``{"milkitem":
            "PRD", "dairyprod": "D1110D", "unit": "THS_T"}`` for apro_mk_cola or
            ``{"crops": "C1110", "strucpro": "HPRD_THS_T"}`` for apro_cpnh1 or
            ``{"product": "10411200", "indicators": "PRODVAL"}`` for DS-059358; ``None``
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
    10,000 leaves, one per listing in the tree, as the TOC lists them (a code filed under
    two folders appears twice). Each has its ``code``, its ``type`` (``"dataset"`` or
    ``"table"``), its English ``title``, the folders above it (``path``, their titles
    joined with ``" > "``), its last data update and structure change as Eurostat prints
    them, day first (``"02.10.2026"``), its first and last period and its number of
    values.
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
    "ef_m_farmleg, and of the product and indicators dimensions of the Prodcom datasets "
    "DS-059358 and DS-059359, only; for any other dataset, get_data's cube lists the codes "
    "it answers with on each dimension, with their labels."
)
"""Why ``list_codes`` refuses a codelist the package does not carry."""


def _codelist_answer(
    info: params.ListInfo, search: str | None, request: Mapping[str, Any]
) -> Result[list[Code]]:
    """The codes of the packaged codelist ``info`` names that ``search`` keeps, with meta.

    ADR-0022 rule 1: the packaged file's ``meta``, its version as ``vintage`` and its
    ``LAST_UPDATED`` as ``published_at``, with the zone Eurostat prints.
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


async def list_codes_async(codelist: str, search: str | None = None) -> Result[list[Code]]:
    """List the codes of one Eurostat codelist, the values a dimension filter takes.

    Answers from the package's copies of fifteen SDMX codelists
    (``sdmx/2.1/codelist/ESTAT/<ID>``, English labels), without a request. Twelve come
    from Eurostat's main base: FREQ, GEO, UNIT, CROPS, STRUCPRO, MILKITEM, DAIRYPROD,
    STATINFO, LEG_FORM, FARMTYPE, SO_EUR and UAAREA, the codelists of the dimensions of
    apro_cpnh1, apro_mk_cola and ef_m_farmleg, each named as its dimension is in upper
    case. Three come from the Comext base, the codelists of the Prodcom datasets:
    CXT_PRODCOM2_SOLD, the ``product`` codes of DS-059358 (sold production, exports and
    imports; ``list_products`` serves it too), CXT_PRODCOM2_TOTAL, the ``product`` codes of
    DS-059359 (total production), and CXT_INDICATORS, the ``indicators`` codes of both,
    which Comext's trade datasets share. A codelist holds every code Eurostat defines in
    it, more than any one dataset uses: GEO has thousands. A dimension's filter takes its
    codes, e.g. ``get_data("apro_mk_cola", {"geo": "AT"})``. ``search`` keeps the codes
    whose code or label contains the text, ignoring case. A codelist the package does not
    carry raises ``UnknownCode`` naming the closest it does. ``meta.vintage`` is the
    codelist's version (``"28.0"``) and ``meta.published_at`` its last update, with
    Eurostat's zone; ``meta.retrieved_at`` is when the package's copy was fetched. A code
    Eurostat added since is missing until the package is refreshed.

    Args:
        codelist: The codelist, case-insensitive: ``"geo"``, ``"unit"``, ``"freq"``,
            ``"crops"``, ``"strucpro"``, ``"milkitem"``, ``"dairyprod"``,
            ``"statinfo"``, ``"leg_form"``, ``"farmtype"``, ``"so_eur"``, ``"uaarea"``,
            ``"cxt_prodcom2_sold"``, ``"cxt_prodcom2_total"`` or ``"cxt_indicators"``.
        search: Text to look for in the code or the English label, ignoring case, e.g.
            ``"austria"``, ``"AT"``, ``"wheat"`` or ``"fertilisers"``; ``None`` lists
            every code.
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
            fetched=params.index().fetched,
            closest=closest(codelist, {code: entry.label or code for code, entry in known.items()}),
            reason=UNPACKAGED_CODELIST,
            source=SOURCE,
        )
    return _codelist_answer(info, search, {"codelist": info.id, "search": search})


list_codes = sync(list_codes_async)


async def list_products_async(search: str | None = None) -> Result[list[Code]]:
    """List the PRODCOM product codes and labels that get_sold_production takes.

    Answers from the package's copy of the Comext codelist CXT_PRODCOM2_SOLD (English
    labels), without a request: the ``product`` codes of Prodcom's DS-059358 (sold
    production, exports and imports), thousands of manufactured goods, food and
    agricultural inputs among them. A product is an eight-digit code that starts with its
    NACE class: ``1041`` for vegetable and animal oils and fats, ``2015`` for
    fertilisers. A few codes carry a letter (``101200Z1``, ``2410T110``) and stand for
    several products together, as their labels say. The list keeps the codes of earlier
    PRODCOM years beside the current ones, so one label can stand under two codes (crude
    sunflower-seed and safflower oil is ``10412300`` and ``10412400``). For agriculture:
    crude oils such as ``10412100`` (crude soya-bean oil) and refined ones such as
    ``10415400`` (refined sunflower-seed and safflower oil) under ``1041``; the
    oil-cakes ``10414130`` (soya-bean), ``10414150`` (sunflower seed) and ``10414170``
    (rape or colza seed); ethanol, ``20147400`` (undenatured, of at least 80 % vol) and
    ``20147500`` (denatured); biodiesel, ``20595800``; sugar under ``1081`` (``10811230``,
    refined white cane or beet sugar); animal feed under ``1091`` (``10911035``, for
    cattle); meat under ``1011`` and ``1012`` (``10111140``, beef and veal carcases);
    dairy under ``1051`` (``10513030``, butter); beverages under ``11`` (``11051000``,
    beer); fertilisers under ``2015`` (``20153130``, urea). DS-059359 (total production,
    ``get_total_production``) takes the codes of CXT_PRODCOM2_TOTAL, a few hundred of
    these, chiefly chemicals, fertilisers and metals:
    ``list_codes("cxt_prodcom2_total")`` lists them. ``search`` keeps the products whose
    code or label contains the text, ignoring case. ``meta.vintage`` is the codelist's
    version (``"6.0"``) and ``meta.published_at`` its last update, with Eurostat's zone;
    ``meta.endpoint`` is the codelist's URL on the Comext base and ``meta.retrieved_at``
    when the package's copy was fetched.

    Args:
        search: Text to look for in the code or the English label, ignoring case, e.g.
            ``"soya"``, ``"oilcake"``, ``"1041"`` (a NACE class), ``"ethyl alcohol"`` or
            ``"fertilisers"``; ``None`` lists every product.
    """
    info = params.list_info()[params.PRODCOM_SOLD.lower()]
    return _codelist_answer(info, search, {"search": search})


list_products = sync(list_products_async)


SOLD_PRODUCTION = "DS-059358"
"""Prodcom's sold production, exports and imports, annual, on the Comext base."""

TOTAL_PRODUCTION = "DS-059359"
"""Prodcom's total production, annual, on the Comext base."""

UNKNOWN_PRODUCT = (
    "A product the dataset lacks would give an empty cube, so the package checks the "
    "product against its copy of the dataset's product list before sending."
)
"""Why a production task refuses a product its packaged list lacks (conventions §5)."""

UNKNOWN_INDICATOR = (
    "An indicator the dataset lacks would give an empty cube, so the package checks each "
    "indicator against its copy of CXT_INDICATORS before sending; "
    'list_codes("cxt_indicators") lists them.'
)
"""Why a production task refuses an indicator CXT_INDICATORS lacks (conventions §5)."""


@functools.cache
def _labels(name: str) -> Mapping[str, str]:
    """The packaged codelist ``name``'s codes to their labels, the code where it has none."""
    return MappingProxyType({code.code: code.label or code.code for code in params.codes(name)})


def _check_code(param: str, value: str, codelist: str, reason: str) -> None:
    """Refuse ``value`` when the packaged codelist ``codelist`` lacks it (conventions §5).

    Raises:
        UnknownCode: Naming the list, its fetch date and the closest codes.
    """
    labels = _labels(codelist.lower())
    if value not in labels:
        raise UnknownCode(
            param,
            value,
            list_name=codelist,
            fetched=params.packaged(codelist.lower()).fetched,
            closest=closest(value, labels),
            reason=reason,
            source=SOURCE,
        )


def _listed(name: str, values: Sequence[str], every: str) -> list[str]:
    """The codes of a list parameter as sent: one code or several, never none.

    A plain string is one code, not a sequence of letters.

    Raises:
        InvalidRequestError: The list holds no code, which would send no filter.
    """
    listed = [values] if isinstance(values, str) else list(values)
    if not listed:
        raise InvalidRequestError(
            f"{name} lists no code: give one code or several, or leave {name} out for {every}",
            source=SOURCE,
        )
    return listed


async def _production(
    dataset: str,
    products: str,
    product: str,
    reporters: Sequence[str] | None,
    since: str | None,
    until: str | None,
    indicators: Sequence[str] | None,
) -> Result[list[Observation]]:
    """One Prodcom dataset's observations for one product: one ``get_data`` request.

    ``products`` is the id of the dataset's product codelist. Every code is checked
    before the request; the filters go out in the order reporter, product, indicators.
    """
    _check_code(
        "product",
        product,
        products,
        f"{UNKNOWN_PRODUCT} "
        + (
            "list_products lists them."
            if products == params.PRODCOM_SOLD
            else f'list_codes("{products.lower()}") lists them.'
        ),
    )
    filters: dict[str, str | list[str]] = {}
    if reporters is not None:
        filters["reporter"] = _listed("reporters", reporters, "every reporter")
    filters["product"] = product
    if indicators is not None:
        filters["indicators"] = _listed("indicators", indicators, "every indicator")
        for code in filters["indicators"]:
            _check_code("indicator", code, params.PRODCOM_INDICATORS, UNKNOWN_INDICATOR)
    answer = await get_data_async(
        dataset, filters, since_time_period=since, until_time_period=until
    )
    return Result(data=list(answer.data.observations()), meta=answer.meta)


async def get_sold_production_async(
    product: str,
    reporters: Sequence[str] | None = None,
    since: str | None = None,
    until: str | None = None,
    indicators: Sequence[str] | None = None,
) -> Result[list[Observation]]:
    """Get Prodcom's sold production, exports and imports of one product, by country and year.

    One request to the Statistics API on Eurostat's Comext base for Prodcom's annual
    dataset DS-059358. Each observation carries its code and label on every dimension
    (``freq``, ``reporter``, ``product``, ``indicators``, ``time``), its value and its
    status, in cube order: reporter by reporter, indicator by indicator, oldest year
    first. The indicators are the measures, PRODVAL (sold production value, euro),
    PRODQNT (sold production quantity) in QNTUNIT (its unit, e.g. ``"KG"``), EXPVAL and
    EXPQNT (exports, value in euro and quantity) and IMPVAL and IMPQNT (imports), and
    beside them each measure's flag and rounding base (PVALFLAG, PVALBASE, PQNTFLAG,
    PQNTBASE), production on own account (OWNPRODVAL, OWNPRODQNT, with OWNVALFLAG,
    OWNVALBASE, OWNQNTFLAG, OWNQNTBASE) and sub-contracted production (SCPRODVAL,
    SCPRODQNT, with SCVALFLAG, SCVALBASE, SCQNTFLAG, SCQNTBASE). A value is a number, or
    the text Eurostat prints for a unit or a flag (``"KG"``, ``":E"``). ``product`` is
    checked against the package's copy of the dataset's product list
    (CXT_PRODCOM2_SOLD, which ``list_products`` lists), and each indicator against
    CXT_INDICATORS, before any request: a code they lack raises ``UnknownCode`` naming
    the closest. A reporter is sent as given, and one the dataset lacks gives an empty
    list. ``meta`` is ``get_data``'s: ``meta.request`` holds the dataset and the filters
    sent, ``meta.published_at`` the dataset's last update with Eurostat's zone and
    ``meta.vintage`` the same time as printed. A query Eurostat refuses or judges too
    large raises ``InvalidRequestError`` with its message.

    Args:
        product: One PRODCOM product code, e.g. ``"10412100"`` (crude soya-bean oil),
            ``"10414130"`` (soya-bean oilcake), ``"20147400"`` (undenatured ethyl
            alcohol of at least 80 % vol), ``"20595800"`` (biodiesel) or ``"10411200"``
            (fish and marine oils); ``list_products`` lists them.
        reporters: Reporting countries, as the cube's ``reporter`` codes, e.g.
            ``["AT"]`` or ``["DE", "FR"]``; ``None`` asks for every reporter.
        since: The first year, included, e.g. ``"2022"``; ``None`` starts at the
            dataset's first. Eurostat's ``sinceTimePeriod``.
        until: The last year, included, e.g. ``"2023"``; ``None`` runs to the latest.
            Eurostat's ``untilTimePeriod``.
        indicators: Indicator codes, e.g. ``["PRODVAL", "PRODQNT", "QNTUNIT"]`` or
            ``["EXPVAL", "IMPVAL"]``; ``None`` asks for every indicator the dataset
            serves.
    """
    return await _production(
        SOLD_PRODUCTION, params.PRODCOM_SOLD, product, reporters, since, until, indicators
    )


get_sold_production = sync(get_sold_production_async)


async def get_total_production_async(
    product: str,
    reporters: Sequence[str] | None = None,
    since: str | None = None,
    until: str | None = None,
    indicators: Sequence[str] | None = None,
) -> Result[list[Observation]]:
    """Get Prodcom's total production of one product, by country and year.

    One request to the Statistics API on Eurostat's Comext base for Prodcom's annual
    dataset DS-059359, which covers a few hundred products, chiefly chemicals,
    fertilisers and metals. Each observation carries its code and label on every
    dimension (``freq``, ``reporter``, ``product``, ``indicators``, ``time``), its value
    and its status, in cube order: reporter by reporter, indicator by indicator, oldest
    year first. The indicators are APRODQNT (actual production quantity) in QNTUNIT (its
    unit, e.g. ``"KG"``), and APRODQNT's flag and rounding base, APQNTFLAG and
    APQNTBASE. A value is a number, or the text Eurostat prints for a unit or a flag
    (``"KG"``). ``product`` is checked against the package's copy of the dataset's
    product list (CXT_PRODCOM2_TOTAL, which ``list_codes("cxt_prodcom2_total")`` lists),
    and each indicator against CXT_INDICATORS, before any request: a code they lack
    raises ``UnknownCode`` naming the closest. A reporter is sent as given, and one the
    dataset lacks gives an empty list. ``meta`` is ``get_data``'s: ``meta.request`` holds
    the dataset and the filters sent, ``meta.published_at`` the dataset's last update
    with Eurostat's zone and ``meta.vintage`` the same time as printed. A query Eurostat
    refuses or judges too large raises ``InvalidRequestError`` with its message.

    Args:
        product: One product code of CXT_PRODCOM2_TOTAL, e.g. ``"20158000"`` (animal or
            vegetable fertilisers), ``"20153130"`` (urea of more than 45 % nitrogen) or
            ``"20151075"`` (anhydrous ammonia).
        reporters: Reporting countries, as the cube's ``reporter`` codes, e.g.
            ``["AT"]`` or ``["DE", "FR"]``; ``None`` asks for every reporter.
        since: The first year, included, e.g. ``"2022"``; ``None`` starts at the
            dataset's first. Eurostat's ``sinceTimePeriod``.
        until: The last year, included, e.g. ``"2023"``; ``None`` runs to the latest.
            Eurostat's ``untilTimePeriod``.
        indicators: Indicator codes, e.g. ``["APRODQNT", "QNTUNIT"]``; ``None`` asks for
            every indicator the dataset serves.
    """
    return await _production(
        TOTAL_PRODUCTION, params.PRODCOM_TOTAL, product, reporters, since, until, indicators
    )


get_total_production = sync(get_total_production_async)


LAST_UPDATE = "%d/%m/%y %H:%M:%S"
"""How SDMX-CSV prints ``LAST UPDATE``: ``"05/10/26 23:00:00"``, day first, no zone.

The order is fixed by the snapshot's two answers for apro_mk_cola of 2026-10-27: the
JSON-stat sample's ``updated`` is ``"2026-10-05T23:00:00+0200"`` and the SDMX-CSV
sample's ``LAST UPDATE`` ``"05/10/26 23:00:00"``, the same time without its zone. The
Comext base prints it alike: DS-059358's ``"2026-10-20T11:00:00+0200"`` is
``"20/10/26 11:00:00"`` (recorded 2026-10-28), whose day cannot be read as a month."""

DOT_SEGMENTS = frozenset({".", ".."})
"""Keys a URL resolves away as a path segment before sending."""


async def download_dataset_async(
    dataset: str,
    key: str = "",
    *,
    since: str | None = None,
    until: str | None = None,
    last_n_observations: int | None = None,
    dest: str | os.PathLike[str],
) -> Result[Downloaded]:
    """Download a Eurostat dataset, or a slice of it, as a gzip-compressed SDMX-CSV file.

    Python only, no MCP tool or HTTP route (a bulk task). One request to the SDMX 2.1 API
    (``sdmx/2.1/data/{dataset}/{key}?format=SDMX-CSV&compressed=true``), on Eurostat's
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
    asynchronously or refuses as too large (the user guide names 500,000 and 5,000,000
    cells for a query it has not cached) raises
    ``InvalidRequestError`` naming how to narrow it, and ``dest`` is left untouched; a
    file that is not SDMX-CSV raises ``ValidationError`` and stays at ``dest``. ``dest``
    must name a file in a directory that exists: a directory, or a missing one, is
    refused before any request.

    Args:
        dataset: The dataset's online data code, e.g. ``"apro_mk_cola"`` (cows' milk
            collection and dairy products, annual), ``"ef_m_farmleg"`` (farm
            indicators by legal status) or ``"DS-059358"`` (Prodcom: sold production,
            exports and imports).
        key: Eurostat's series key, e.g. ``"A...THS_T.AT"`` for apro_mk_cola (freq A,
            every milkitem and dairyprod, unit THS_T, geo AT), ``"A.PRD.D1110D.THS_T.AT+DE"``
            (two geo codes) or ``"A.AT.10411200."`` for DS-059358 (freq A, reporter AT,
            product 10411200, every indicator); ``""``, the default, downloads every code
            of every dimension, the whole dataset.
        since: The first period, included, as the dataset prints it, e.g. ``"2022"`` or
            ``"2026-08"``; Eurostat's ``startPeriod``. ``None`` starts at the first.
        until: The last period, included, e.g. ``"2023"``; Eurostat's ``endPeriod``.
            ``None`` runs to the latest.
        last_n_observations: The most recent observations of each series, e.g. ``2``;
            Eurostat's ``lastNObservations``. ``None`` keeps them all.
        dest: The file to write, e.g. ``"apro_mk_cola.csv.gz"`` or
            ``Path("data") / "ef_m_farmleg.csv.gz"``, in a directory that exists; a file
            there is replaced once the download is complete.
    """
    if key in DOT_SEGMENTS:
        raise InvalidRequestError(
            f"key={key!r} wildcards every dimension, which a URL cannot carry as a path "
            'segment: pass key="" for every code of every dimension',
            source=SOURCE,
        )
    target = Path(dest)
    if target.is_dir():
        raise InvalidRequestError("dest is a directory; name the file to write", source=SOURCE)
    if not target.parent.is_dir():
        raise InvalidRequestError("dest's directory does not exist; create it first", source=SOURCE)
    downloaded = await api.sdmx.data_query(
        dataset,
        target,
        key=key,
        start_period=since,
        end_period=until,
        last_n_observations=last_n_observations,
        compressed=True,
    )
    with closing(parse_sdmx_csv(downloaded.path)) as rows:
        first = next(rows, None)
    vintage = None if first is None else first.last_update
    try:
        published = None if vintage is None else datetime.strptime(vintage, LAST_UPDATE)
    except ValueError:
        raise ValidationError(
            f"{SOURCE} {api.sdmx.DATA_ENDPOINT}: the first row's LAST UPDATE is not printed "
            "as dd/mm/yy HH:MM:SS",
            raw=vintage,
            source=SOURCE,
        ) from None
    meta = ResultMeta(
        source=SOURCE,
        endpoint=api.sdmx.DATA_ENDPOINT,
        retrieved_at=downloaded.retrieved_at,
        published_at=published,
        published_at_naive=published is not None,
        vintage=vintage,
        request={
            "dataset": dataset,
            "key": key,
            "start_period": since,
            "end_period": until,
            "last_n_observations": last_n_observations,
            "format": api.sdmx.DATA_FORMAT,
            "compressed": True,
        },
    )
    return Result(data=downloaded, meta=meta)


download_dataset = sync(download_dataset_async)
