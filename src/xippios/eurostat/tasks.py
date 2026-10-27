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
``updated`` without a zone, never seen, would leave ``published_at`` empty, since
``ResultMeta`` takes only a zoned time on a core without ADR-0022's flag.
``meta.endpoint`` is the operation's
name, ``"getData"``; ``meta.request`` holds what was sent, a parameter left ``None``
omitted; ``meta.total`` stays ``None``: the answer counts no records for the request
(its ``OBS_COUNT`` annotation counts the whole dataset's, ADR-0012).
"""

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from xippios.core import InvalidRequestError, Result, ResultMeta, sync

from xippios.eurostat import api
from xippios.eurostat._client import SOURCE
from xippios.eurostat.api.statistics import ENDPOINT
from xippios.eurostat.models import Cube, GeoLevel, Lang

__all__ = ["get_data"]

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

# MCP_CAPS, only where a tool needs a result cap of its own: a list an agent needs whole
# (conventions §8, ADR-0016), keyed by task function name; mcp.py reads it with getattr,
# so a source without one adds nothing. ResultCap needs the mcp extra, which a base
# install lacks, so its import is guarded and a base install, which serves no tool, gets
# an empty mapping (the annotation quoted, Mapping from collections.abc):
#
# try:
#     from xippios.core.mcp import ResultCap
# except ImportError:  # pragma: no cover - a base install has no MCP server
#     MCP_CAPS: "Mapping[str, ResultCap]" = {}
# else:
#     MCP_CAPS = {"list_<thing>": ResultCap(max_rows=400)}


def _filters(filters: Mapping[str, str | Sequence[str]] | None) -> dict[str, str | list[str]]:
    """The filters as sent: one code or a list of codes per dimension; refusals first.

    Raises:
        InvalidRequestError: A filter names one of the API's own parameters, or gives an
            empty list of codes, which would send no filter for that dimension.
    """
    sent: dict[str, str | list[str]] = {}
    for code, values in (filters or {}).items():
        if code.lower() in RESERVED_PARAMETERS:
            raise InvalidRequestError(
                f"filters[{code!r}]: {code} is a parameter of the Statistics API, not a "
                "dimension; format is always JSON, and lang, since_time_period, "
                "until_time_period, last_time_period and geo_level are arguments of "
                "get_data",
                source=SOURCE,
            )
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
        retrieved_at=answer.stored_at or datetime.now(UTC),
        published_at=updated if updated is not None and updated.tzinfo is not None else None,
        vintage=answer.updated,
        request={name: value for name, value in request.items() if value is not None},
    )
    return Result(data=answer.cube, meta=meta)


get_data = sync(get_data_async)
