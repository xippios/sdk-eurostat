"""The package's one configured ``AsyncClient`` and its error mapping (conventions §6).

Eurostat serves its datasets from two base URLs: ``BASE_URL``, the main one, and
``COMEXT_BASE_URL`` for the Comext and Prodcom datasets, whose codes start with ``DS-``
(``docs/upstream/user-guide/api-detailed-guidelines/prefixed-datasets.md``; the
Comext base's WADLs under ``docs/upstream/api/comext/`` are the main base's but for
``resources base``). The one client serves both: it is built on ``BASE_URL``, and
``url_for`` gives a wrapper the absolute URL on ``COMEXT_BASE_URL`` for a ``DS-`` code,
which the client sends as it is. One pace, one cache and one ``classify`` therefore hold
for both bases (conventions §6, ADR-0015), and the main base's requests and cache keys
are those of a client with one base.

``classify`` maps the Statistics API's documented refusals, and the SDMX 2.1 data API's
answers that are no SDMX-CSV, onto the family's taxonomy once (ADR-0008); ``errors``
reads them. Both bases answer in the same shapes, recorded on each. Answers of HTTP 200
are cached in core's ``MemoryCache`` with its default lifetime of five minutes, up to
core's ``cache_max_bytes`` of 8 MiB a body (ADR-0019 decision 3), so a larger cube is
returned and fetched again the next time; a file streamed to disk with ``download``
never touches the cache.
"""

import httpx
from xippios.core import (
    AsyncClient,
    ClientConfig,
    InvalidRequestError,
    NotFoundError,
    RateLimit,
    XippiosError,
)
from xippios.core.client import MemoryCache

from xippios.eurostat._version import __version__
from xippios.eurostat.errors import (
    AGAIN_LATER,
    ASYNCHRONOUS_LABEL,
    NARROW_HINT,
    NO_RESULTS,
    error_faults,
    fault_payload,
    soap_faultstring,
    warning_fault,
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
API_KEY_ENV: str | None = None
# A self-imposed pace: upstream documents no rate in numbers, only a fair-use rule
# without one (ADR-0010 decision 1; asynchronous-api.md, "Fair use of the service").
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


def _where(response: httpx.Response) -> str:
    """The request's method and path, never its host or query (conventions §5)."""
    return f"{response.request.method} {response.request.url.path}"


def _not_sdmx_csv(response: httpx.Response) -> str | None:
    """The media type of a 2xx data query answer that is no SDMX-CSV, else ``None``.

    A data query on either base (``SDMX_DATA_PATHS``). Read from the request path and the
    headers alone: a download hands ``classify`` no body (ADR-0019, amendment
    2026-10-27).
    """
    if not response.is_success or not response.request.url.path.startswith(SDMX_DATA_PATHS):
        return None
    media = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    return None if media == SDMX_CSV else media or "no content type"


def classify(response: httpx.Response) -> XippiosError | None:
    """The Statistics API's documented refusals and the SDMX data API's, mapped once (ADR-0008).

    Both bases answer in the same shapes, so one mapping serves both; a message names
    the request's path, which tells the bases apart, never its host.

    - A 2xx answer to an SDMX 2.1 data query (``sdmx/2.1/data/`` on either base) whose
      ``Content-Type`` is not SDMX-CSV's: ``InvalidRequestError`` naming how to narrow the
      query (Johannes, 2026-10-27, B3). The package asks for SDMX-CSV only, and a request
      the service will treat asynchronously is answered with an XML envelope that queues
      it, status ``SUBMITTED`` (``asynchronous-api.md``, "Step 1: Initial request"), which
      this package does not poll (design round Q4); the guide names no HTTP status for it,
      so any 2xx is read. Recorded on the Comext base for ``DS-045409``, the whole
      monthly flow: HTTP 200, ``application/xml``, the SOAP envelope with ``SUBMITTED``
      (``tests/fixtures/data_query/DS-045409_asynchronous.json``). Judged by the headers
      alone, since a download's body goes to the file unread.
    - A ``warning`` whose status is 413 or whose label starts ``ASYNCHRONOUS_RESPONSE``,
      at any HTTP status: the service will treat the request asynchronously, which this
      package does not poll (design round Q4, 2026-10-27): ``InvalidRequestError`` saying
      to send the request again later, the Statistics API's own route, or to narrow it.
    - HTTP 404 with an ``error`` member: ``NotFoundError`` with upstream's label
      (recorded for an unknown dataset, fault 100).
    - HTTP 400 with an ``error`` member whose faults are all 100, "No results found: The
      result from the query is empty" (the fault table): ``NotFoundError``, upstream
      signalling absence (conventions §5). Documented, not recorded.
    - HTTP 400 with any other ``error`` member, an array or one object:
      ``InvalidRequestError`` with upstream's label (recorded for an unknown dimension,
      fault 150, and for ``geo`` with ``geoLevel``; the fault table's 140 alike).
    - HTTP 413 otherwise: ``InvalidRequestError`` naming how to narrow the query, with the
      ``faultstring`` of a SOAP fault where the body is one. Recorded on the Comext base:
      the SOAP fault ``EXTRACTION_TOO_BIG`` the user guide documents for the SDMX APIs
      (an extraction over 5,000,000 cells;
      ``tests/fixtures/data_query/DS-045409_too_big_413.json``), and the Statistics API's
      ``error`` array with id 413 and the same text, its answer to a filter on a
      dimension the dataset lacks, which it counts unfiltered
      (``tests/fixtures/get_data/DS-059358_unknown_dimension.json``); the array's label
      is not read at 413.

    Everything else falls through to core's status mapping, a 5xx included, so that it
    is retried. An unknown code (``geo=XX``) is no error: the service answers HTTP 200
    with an empty cube (``tests/fixtures/get_data/unknown_code.json``).
    """
    media = _not_sdmx_csv(response)
    if media is not None:
        return InvalidRequestError(
            f"Eurostat answered {_where(response)} with {media}, not SDMX-CSV: a data "
            "query the SDMX API will treat asynchronously is answered with an XML envelope "
            f"that queues it, and this package does not poll asynchronous answers: {NARROW_HINT}.",
            source=SOURCE,
        )
    status = response.status_code
    payload = fault_payload(response)
    if payload is not None:
        warning = warning_fault(payload)
        if warning is not None and (
            warning.status == 413 or warning.label.startswith(ASYNCHRONOUS_LABEL)
        ):
            return InvalidRequestError(
                f"Eurostat will answer {_where(response)} asynchronously "
                f"({warning.label}), and this package does not poll asynchronous answers: "
                f"{AGAIN_LATER}, or {NARROW_HINT}.",
                source=SOURCE,
            )
        faults = error_faults(payload)
        if faults and status in (400, 404):
            described = "; ".join(fault.describe() for fault in faults)
            if status == 404 or all(fault.id == NO_RESULTS for fault in faults):
                return NotFoundError(
                    f"Eurostat answered {_where(response)} with HTTP {status} ({described}).",
                    source=SOURCE,
                )
            return InvalidRequestError(
                f"Eurostat refused the query {_where(response)} with HTTP 400 ({described}).",
                source=SOURCE,
            )
    if status == 413:
        fault = soap_faultstring(response)
        return InvalidRequestError(
            f"Eurostat refused {_where(response)} as too large "
            f"(HTTP 413{': ' + fault if fault else ''}): {NARROW_HINT}.",
            source=SOURCE,
        )
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
# config (conventions §6, ADR-0015); core's README shows how.

client = AsyncClient(config)

__all__ = [
    "API_KEY_ENV",
    "BASE_URL",
    "COMEXT_BASE_URL",
    "COMEXT_PREFIX",
    "RATE_LIMIT",
    "SDMX_CSV",
    "SDMX_DATA_PATHS",
    "SOURCE",
    "classify",
    "client",
    "config",
    "url_for",
]
