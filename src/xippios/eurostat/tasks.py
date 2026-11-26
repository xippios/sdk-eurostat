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
dataset's, sdk-core ADR-0034).

The list tasks, ``list_datasets`` and ``list_codes``, answer from the packaged lists
(``params``) without a request, by sdk-core ADR-0041 decision 1: ``meta.retrieved_at``
is the list's ``fetched``, ``meta.endpoint`` the operation it was fetched from
(``catalogue/toc/xml``, ``sdmx/2.1/codelist/ESTAT/<ID>``, or for a codelist of the
Comext base its full URL), ``meta.total`` ``None``. Their release metadata (decision D4
of https://github.com/xippios/sdk-eurostat/pull/6) comes from ``reference/lists.json``:
for the table of contents
``meta.vintage`` is its ``creationDate`` as printed (``"20261120T1004"``) and
``meta.published_at`` the same time without a zone, ``published_at_naive`` set (sdk-core ADR-0041
decision 2); for a codelist ``meta.vintage`` is its version (``"28.1"``) and
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
from pathlib import Path
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
from xippios.eurostat.models import Code, Cube, Dataset, GeoLevel, Lang
from xippios.eurostat.parse import parse_sdmx_csv

__all__ = [
    "download_dataset",
    "get_data",
    "list_codes",
    "list_datasets",
]

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
"""


GET_DATA_ARGUMENTS = (
    "format is always JSON, and lang, since_time_period, until_time_period, "
    "last_time_period and geo_level are arguments of get_data"
)
"""Where ``get_data`` sets the API's own parameters, for the refusal of one as a filter."""


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
                f"dimension; {GET_DATA_ARGUMENTS}",
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
    values, each ``None`` where Eurostat prints none.
    ``search`` keeps the leaves whose code or title contains the text, ignoring case:
    give one, since the whole list is far more than one answer shows. A dataset's
    ``code`` is what ``get_data`` and ``download_dataset`` take as ``dataset``. ``meta.vintage`` is
    the table of contents' ``creationDate`` as printed (``"20261120T1004"``) and
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
    "ef_m_farmleg, of the product and indicators dimensions of the Prodcom datasets "
    "DS-059358 and DS-059359, and of the product, reporter and partner, and flow dimensions "
    "of the Comext trade datasets DS-045409 and DS-059341, only; for any other dataset, "
    "the cube of get_data (over MCP, the tool eurostat_get_data) lists the codes it "
    "answers with on each dimension, with their labels."
)
"""Why ``list_codes`` refuses a codelist the package does not carry."""


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


async def list_codes_async(codelist: str, search: str | None = None) -> Result[list[Code]]:
    """List the codes of one Eurostat codelist, the values a dimension filter takes.

    Answers from the package's copies of eighteen SDMX codelists
    (``sdmx/2.1/codelist/ESTAT/<ID>``, English labels), without a request. Twelve come
    from Eurostat's main base: FREQ, GEO, UNIT, CROPS, STRUCPRO, MILKITEM, DAIRYPROD,
    STATINFO, LEG_FORM, FARMTYPE, SO_EUR and UAAREA, the codelists of the dimensions of
    apro_cpnh1, apro_mk_cola and ef_m_farmleg, each named as its dimension is in upper
    case. Six come from the Comext base, the codelists of the Prodcom and Comext trade
    datasets: CXT_PRODCOM2_SOLD, the ``product`` codes of DS-059358 (sold production,
    exports and imports), CXT_PRODCOM2_TOTAL, the ``product`` codes of DS-059359 (total
    production), CXT_INDICATORS, the ``indicators`` codes of both, which Comext's trade
    datasets share, CXT_NC, the ``product`` codes of the trade datasets DS-045409 and
    DS-059341, CXT_FREE_ISO, their ``reporter`` and ``partner`` codes, which the Prodcom
    datasets' reporters take too, and CXT_EU_FLUX, their ``flow`` codes.
    A codelist holds every code Eurostat defines in it, more than any one dataset uses:
    GEO has thousands. A dimension's filter takes its codes, e.g.
    ``get_data("apro_mk_cola", {"geo": "AT"})``. ``search`` keeps the codes whose code or
    label contains the text, ignoring case. A codelist the package does not carry raises
    ``UnknownCode`` naming the closest it does. ``meta.vintage`` is the codelist's version
    (``"28.1"``) and ``meta.published_at`` its last update, with Eurostat's zone, or
    ``None`` where the codelist names none (CXT_EU_FLUX); ``meta.retrieved_at`` is when
    the package's copy was fetched. A code Eurostat added since is missing until the
    package is refreshed.

    Args:
        codelist: The codelist, case-insensitive: ``"geo"``, ``"unit"``, ``"freq"``,
            ``"crops"``, ``"strucpro"``, ``"milkitem"``, ``"dairyprod"``,
            ``"statinfo"``, ``"leg_form"``, ``"farmtype"``, ``"so_eur"``, ``"uaarea"``,
            ``"cxt_prodcom2_sold"``, ``"cxt_prodcom2_total"``, ``"cxt_indicators"``,
            ``"cxt_nc"``, ``"cxt_free_iso"`` or ``"cxt_eu_flux"``.
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


LAST_UPDATE = "%d/%m/%y %H:%M:%S"
"""How SDMX-CSV prints ``LAST UPDATE``: ``"05/10/26 23:00:00"``, day first, no zone.

The order is fixed by the snapshot's two answers for apro_mk_cola of 2026-10-27: the
JSON-stat sample's ``updated`` is ``"2026-10-05T23:00:00+0200"`` and the SDMX-CSV
sample's ``LAST UPDATE`` ``"05/10/26 23:00:00"``, the same time without its zone. The
Comext base prints it alike: DS-059358's ``"2026-10-20T11:00:00+0200"`` is
``"20/10/26 11:00:00"`` (recorded 2026-10-28), whose day cannot be read as a month."""

DOT_SEGMENTS = frozenset({".", ".."})
"""Keys a URL resolves away as a path segment before sending."""


async def _download(
    dataset: str,
    target: Path,
    request: Mapping[str, Any],
    *,
    key: str,
    since: str | None,
    until: str | None,
    last_n_observations: int | None = None,
) -> Result[Downloaded]:
    """Stream one SDMX-CSV data query, gzip-compressed, to ``target``, with its meta.

    The release is read from the file's first row through the parser: ``LAST UPDATE`` as
    ``vintage`` and its naive time as ``published_at`` (sdk-core ADR-0041 decision 2);
    ``request`` is ``meta.request`` as given.

    Raises:
        ValidationError: The first row's ``LAST UPDATE`` is not printed as
            ``LAST_UPDATE`` says; the file stays at ``target``.
    """
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
        request=dict(request),
    )
    return Result(data=downloaded, meta=meta)


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
    request = {
        "dataset": dataset,
        "key": key,
        "start_period": since,
        "end_period": until,
        "last_n_observations": last_n_observations,
        "format": api.sdmx.DATA_FORMAT,
        "compressed": True,
    }
    return await _download(
        dataset,
        Path(dest),
        request,
        key=key,
        since=since,
        until=until,
        last_n_observations=last_n_observations,
    )


download_dataset = sync(download_dataset_async)
