"""The package's one configured ``AsyncClient`` and its error mapping (conventions §6).

Eurostat serves its datasets from two base URLs: ``BASE_URL``, the main one, and
``COMEXT_BASE_URL`` for the Comext and Prodcom datasets, whose codes start with ``DS-``
(``docs/upstream/user-guide/api-detailed-guidelines/prefixed-datasets.md``; the
Comext base's WADLs under ``docs/upstream/api/comext/`` are the main base's but for
``resources base``). The one client serves both: it is built on ``BASE_URL``, and
``url_for`` gives a wrapper the absolute URL on ``COMEXT_BASE_URL`` for a ``DS-`` code,
which the client sends as it is. One pace, one cache and one ``classify`` therefore hold
for both bases (conventions §6, sdk-core ADR-0037), and the main base's requests and cache keys
are those of a client with one base.

``classify`` maps the Statistics API's documented refusals, and the SDMX 2.1 data API's
answers that are no SDMX-CSV, onto the family's taxonomy once (sdk-core ADR-0031); ``errors``
reads them. Both bases answer in the same shapes, recorded on each, though not always to
the same request: a filter on a dimension the dataset lacks is fault 150 at HTTP 400 on
the main base, and HTTP 413 as too large on the Comext base, whose estimate for
DS-059358, 151,971,120 rows, is that of an unfiltered query, so the unknown filter seems
to be ignored. Answers of HTTP 200 are cached in core's ``MemoryCache`` with its default
lifetime of five minutes for every path, up to core's ``cache_max_bytes`` of 8 MiB a body
and 64 MiB of bodies in all, an expired answer dropped (sdk-core ADR-0040 decision 3), so a
larger cube is returned and fetched again the next time; a file streamed to disk with
``download`` never touches the cache.
"""

import re

import httpx
from xippios.core import (
    AsyncClient,
    ClientConfig,
    EnvVar,
    InvalidRequestError,
    NotFoundError,
    QueryTooLarge,
    RateLimit,
    XippiosError,
    request_description,
)
from xippios.core.client import MemoryCache

from xippios.eurostat._version import __version__
from xippios.eurostat.errors import (
    AGAIN_LATER,
    NARROW_HINT,
    NO_RESULTS,
    Fault,
    asynchronous_fault,
    error_faults,
    fault_payload,
    soap_faultstring,
)

SOURCE = "eurostat"
BASE_URL = "https://ec.europa.eu/eurostat/api/dissemination"
"""The main base URL, the client's: every dataset but the ``DS-`` ones."""
COMEXT_BASE_URL = "https://ec.europa.eu/eurostat/api/comext/dissemination"
"""The base URL of the Comext and Prodcom datasets: "For these datasets, the
<api_base_uri> is: https://ec.europa.eu/eurostat/api/comext/dissemination"
(``prefixed-datasets.md``). It serves the main base's services, the Statistics API and
the SDMX 2.1 API among them, at the same paths; not ``catalogue/toc/xml``, which it
answers with HTTP 404 (probed 2026-10-28)."""
COMEXT_PREFIX = "DS-"
"""How the code of a Comext or Prodcom dataset begins, as upstream writes it: "Comext and
Prodcom datasets (DS- prefixed dataset code, i.e DS-057555) are separated"
(``prefixed-datasets.md``)."""
SDMX_DATA_PATHS = tuple(
    f"{httpx.URL(base).path}/sdmx/2.1/data/" for base in (BASE_URL, COMEXT_BASE_URL)
)
"""Where the SDMX 2.1 API's data queries go (``api.sdmx.data_query``) on either base, as a
request path begins."""
SDMX_CSV = "application/vnd.sdmx.data+csv"
"""The media type of an SDMX-CSV answer, plain or ``compressed=true`` (recorded
2026-10-27; ``version=1.0.0`` as its parameter)."""
ENV_VARS: tuple[EnvVar, ...] = ()
"""The variables the package reads, for a host (conventions §7; sdk-core ADR-0026, amendment
2026-11-18, point c): none, since the API is open. An ``EnvVar`` names a variable and reads
none; a variable the source reads joins the list."""
EXTRACTION_LIMIT = 5_000_000
"""The most cells Eurostat extracts for one query it has not cached, "if above 5 000 000
cells, a client request error is returned" (``asynchronous-api.md``): the limit of a
``QueryTooLarge`` whose refusal states none, as each recorded one states it, "max
authorised is 5000000"."""
TOO_LARGE_NARROW = (
    f"Eurostat estimates an extraction in cells and refuses one over its limit: {NARROW_HINT}."
)
"""What closes the refusal of a query too large, after core's count and limit."""
_ESTIMATED = re.compile(r"estimated (\d+) rows")
_AUTHORISED = re.compile(r"max authorised is (\d+)")
# A self-imposed pace: upstream documents no rate in numbers, only a fair-use rule
# without one (sdk-core ADR-0033 decision 1; asynchronous-api.md, "Fair use of the service").
RATE_LIMIT = RateLimit(per_minute=30, burst=1)


def url_for(code: str, path: str) -> str:
    """What a wrapper requests for an operation on one dataset: its path, or a Comext URL.

    Upstream's rule (``prefixed-datasets.md``): the Comext and Prodcom datasets, "DS-
    prefixed dataset code", are served on ``COMEXT_BASE_URL``, every other dataset on
    ``BASE_URL``. A code that starts with ``COMEXT_PREFIX`` gets the absolute URL
    ``COMEXT_BASE_URL + path``, which the client sends as it is (an absolute URL
    overrides its base URL), on its one pace, cache and ``classify``; any other code gets
    ``path`` unchanged, which the client joins onto ``BASE_URL`` as before. The prefix is
    matched as upstream writes it, in capitals, and the code is never folded: it is sent
    as given, inside ``path``.

    Args:
        code: The dataset's code, a ``datasetCode`` or a ``flowRef``, e.g. ``"DS-059358"``
            (Prodcom, sold production, exports and imports) or ``"apro_mk_cola"``.
        path: The operation's path under either base, from its first slash, its query
            included where the wrapper builds one, e.g.
            ``"/statistics/1.0/data/DS-059358"``.

    Returns:
        ``path`` for the main base, e.g. ``"/statistics/1.0/data/apro_mk_cola"``, or the
        Comext base's URL, e.g.
        ``"https://ec.europa.eu/eurostat/api/comext/dissemination/statistics/1.0/data/DS-059358"``.
    """
    return f"{COMEXT_BASE_URL}{path}" if code.startswith(COMEXT_PREFIX) else path


def _not_sdmx_csv(response: httpx.Response) -> str | None:
    """The media type of a 2xx data query answer that is no SDMX-CSV, else ``None``.

    A data query on either base (``SDMX_DATA_PATHS``). Read from the request path and the
    headers alone: a download hands ``classify`` no body (sdk-core ADR-0040, decision
    1).
    """
    if not response.is_success or not response.request.url.path.startswith(SDMX_DATA_PATHS):
        return None
    media = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    return None if media == SDMX_CSV else media or "no content type"


def _too_large(response: httpx.Response, text: str) -> QueryTooLarge:
    """Eurostat's refusal of an extraction as too large, as core's ``QueryTooLarge``.

    The count and the limit are read from upstream's text where it states them, as each
    recorded refusal does ("estimated 13344840 rows, max authorised is 5000000"); a text
    without a count gives ``None``, and one without a limit the user guide's
    ``EXTRACTION_LIMIT`` (conventions §5).
    """
    estimated = _ESTIMATED.search(text)
    authorised = _AUTHORISED.search(text)
    return QueryTooLarge(
        int(estimated.group(1)) if estimated else None,
        limit=int(authorised.group(1)) if authorised else EXTRACTION_LIMIT,
        narrow=TOO_LARGE_NARROW,
        request=request_description(response),
        source=SOURCE,
    )


def classify(response: httpx.Response) -> XippiosError | None:
    """The Statistics API's documented refusals and the SDMX data API's, mapped once.

    Upstream's error shapes go here once (sdk-core ADR-0031).

    Both bases answer in the same shapes, so one mapping serves both; a message names
    the request by core's ``request_description``, its method and path, which tells the
    bases apart, never its host or query (conventions §5).

    - A 2xx answer to an SDMX 2.1 data query (``sdmx/2.1/data/`` on either base) whose
      ``Content-Type`` is not SDMX-CSV's: ``InvalidRequestError`` naming how to narrow the
      query (decision B3 of https://github.com/xippios/sdk-eurostat/pull/7). The package
      asks for SDMX-CSV only, and a request the service will treat asynchronously is
      answered with an XML envelope that queues it, status ``SUBMITTED``
      (``asynchronous-api.md``, "Step 1: Initial request"), which this package does not
      poll (https://github.com/xippios/sdk-eurostat/pull/12); the guide names no HTTP
      status for it, so any 2xx is read. Recorded on the Comext base for ``DS-045409``, the whole
      monthly flow: HTTP 200, ``application/xml``, the SOAP envelope with ``SUBMITTED``
      (``tests/fixtures/data_query/DS-045409_asynchronous.json``). Judged by the headers
      alone, since a download's body goes to the file unread.
    - The Statistics API's asynchronous answer, at any HTTP status, 413 included: a
      ``warning`` whose status is 413 or whose label starts ``ASYNCHRONOUS_RESPONSE``, as
      the user guide documents it (never seen), or a fault of an ``error`` member whose
      label starts so, as recorded on the Comext base on 2026-10-28: an ``error`` array
      at HTTP 413 with id 413, DS-059341's answer to a CN8 code the dataset does not serve
      (``tests/fixtures/get_data/DS-059341_AT_DE_15071090_cn8_on_hs_flow.json``). The
      service will treat the request asynchronously, which this package does not poll
      (https://github.com/xippios/sdk-eurostat/pull/12): ``InvalidRequestError`` saying to
      send the request again later, the Statistics API's own route, or to narrow it.
      Checked before the HTTP 413 refusal below, which an ``EXTRACTION_TOO_BIG`` label
      takes.
    - HTTP 404 with an ``error`` member: ``NotFoundError`` with upstream's label
      (recorded for an unknown dataset, fault 100).
    - HTTP 400 with an ``error`` member whose faults are all 100, "No results found: The
      result from the query is empty" (the fault table): ``NotFoundError``, upstream
      signalling absence (conventions §5). Documented, not recorded.
    - HTTP 400 with any other ``error`` member, an array or one object:
      ``InvalidRequestError`` with upstream's label (recorded for an unknown dimension,
      fault 150, and for ``geo`` with ``geoLevel``; the fault table's 140 alike).
    - HTTP 413 otherwise: core's ``QueryTooLarge`` (conventions §5), its count and its
      limit read from upstream's text, the labels of an ``error`` member or else the
      ``faultstring`` of a SOAP fault, and naming how to narrow the query. Recorded on the
      Comext base: the
      Statistics API's ``error`` array with id 413, ``EXTRACTION_TOO_BIG``, its answer to
      a filter on a dimension the dataset lacks, whose estimate, 151,971,120 rows, is
      that of an unfiltered query, so the unknown filter seems to be ignored
      (``tests/fixtures/get_data/DS-059358_unknown_dimension_too_big.json``), and the SOAP
      fault ``EXTRACTION_TOO_BIG`` the user guide documents for the SDMX APIs (an
      extraction over 5,000,000 cells;
      ``tests/fixtures/data_query/DS-045409_too_big_413.json``).

    Everything else falls through to core's status mapping, a 5xx included, so that it
    is retried. An unknown code (``geo=XX``) is no error here: the service answers HTTP 200
    with an empty cube (``tests/fixtures/get_data/unknown_code.json``), and ``get_data``
    refuses the code before sending where one packaged codelist feeds its dimension, and a
    cube without a cell after the request.
    """
    where = request_description(response)
    media = _not_sdmx_csv(response)
    if media is not None:
        return InvalidRequestError(
            f"Eurostat answered {where} with {media}, not SDMX-CSV: a data "
            "query the SDMX API will treat asynchronously is answered with an XML envelope "
            f"that queues it, and this package does not poll asynchronous answers: {NARROW_HINT}.",
            source=SOURCE,
        )
    status = response.status_code
    payload = fault_payload(response)
    faults: list[Fault] = []
    if payload is not None:
        queued = asynchronous_fault(payload)
        if queued is not None:
            return InvalidRequestError(
                f"Eurostat will answer {where} asynchronously "
                f"({queued.label}), and this package does not poll asynchronous answers: "
                f"{AGAIN_LATER}, or {NARROW_HINT}.",
                source=SOURCE,
            )
        faults = error_faults(payload)
        if faults and status in (400, 404):
            described = "; ".join(fault.describe() for fault in faults)
            if status == 404 or all(fault.id == NO_RESULTS for fault in faults):
                return NotFoundError(
                    f"Eurostat answered {where} with HTTP {status} ({described}).",
                    source=SOURCE,
                )
            return InvalidRequestError(
                f"Eurostat refused the query {where} with HTTP 400 ({described}).",
                source=SOURCE,
            )
    if status == 413:
        text = "; ".join(item.label for item in faults) or soap_faultstring(response) or ""
        return _too_large(response, text)
    return None


config = ClientConfig(
    source=SOURCE,
    version=__version__,
    base_url=BASE_URL,
    rate_limit=RATE_LIMIT,
    classify=classify,
    cache=MemoryCache(),
)

# A source with a documented hourly or daily quota installs a QuotaPolicy of its own on
# config (conventions §6, sdk-core ADR-0037); core's README shows how.

client = AsyncClient(config)

__all__ = [
    "BASE_URL",
    "COMEXT_BASE_URL",
    "COMEXT_PREFIX",
    "ENV_VARS",
    "EXTRACTION_LIMIT",
    "RATE_LIMIT",
    "SDMX_CSV",
    "SDMX_DATA_PATHS",
    "SOURCE",
    "classify",
    "client",
    "config",
    "url_for",
]
