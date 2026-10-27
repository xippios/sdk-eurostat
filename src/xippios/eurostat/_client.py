"""The configured ``xippios.core`` client for Eurostat dissemination API.

One ``AsyncClient`` for the whole package: task functions share its rate limiter, and
the same instance serves the sync facades and the MCP server. ``classify`` maps the
Statistics API's documented refusals onto the family's taxonomy once (ADR-0008);
``errors`` reads them. Answers of HTTP 200 are cached in core's ``MemoryCache`` with its
default lifetime of five minutes, up to core's ``cache_max_bytes`` of 8 MiB a body
(ADR-0019 decision 3), so a larger cube is returned and fetched again the next time.
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
API_KEY_ENV: str | None = None
# A self-imposed pace: upstream documents no rate in numbers, only a fair-use rule
# without one (ADR-0010 decision 1; asynchronous-api.md, "Fair use of the service").
RATE_LIMIT = RateLimit(per_minute=30, burst=1)


def _where(response: httpx.Response) -> str:
    """The request's method and path, never its host or query (conventions §5)."""
    return f"{response.request.method} {response.request.url.path}"


def classify(response: httpx.Response) -> XippiosError | None:
    """The Statistics API's documented refusals, mapped once (ADR-0008).

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
    - HTTP 413 otherwise, the SOAP fault ``EXTRACTION_TOO_BIG`` the user guide documents
      for the SDMX APIs among them: ``InvalidRequestError`` naming how to narrow it.

    Everything else falls through to core's status mapping, a 5xx included, so that it
    is retried. An unknown code (``geo=XX``) is no error: the service answers HTTP 200
    with an empty cube (``tests/fixtures/getData/unknown_code.json``).
    """
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

# An upstream that reports an hourly or daily quota installs one QuotaPolicy, from
# xippios.core, on config: it reads the quota headers of every answer and never sends
# into a spent quota, waiting within the retry backoff or raising RateLimitError
# (ADR-0015; ADR-0010 decisions 3 and 4). Name only headers that count that quota, never
# a pace (None turns one off); window is the fallback wait, 86400.0 for a daily quota.
# classify, the ClientConfig hook, maps upstream's answer to a spent quota to
# RateLimitError with retry_after. A source without a quota adds nothing.
#
# policy = QuotaPolicy(
#     window=3600.0,
#     limit_header="x-ratelimit-limit",
#     remaining_header="x-ratelimit-remaining",
#     source=SOURCE,
# )
# config = policy.install(config)

client = AsyncClient(config)

__all__ = [
    "API_KEY_ENV",
    "BASE_URL",
    "RATE_LIMIT",
    "SOURCE",
    "classify",
    "client",
    "config",
]
