"""``classify`` against the recorded refusals and the documented ones.

Recorded on 2026-10-27 (``tests/fixtures/getData/``): an unknown dataset, an unknown
dimension and ``geo`` with ``geoLevel``, all with ``error`` as an array, and the empty
cube of an unknown code. Not recorded, taken verbatim from the snapshot's user guide:
the single-object ``error`` the guide shows for ``geo`` with ``geoLevel``, the
asynchronous answer (``api-statistics.md``) and the SOAP fault ``EXTRACTION_TOO_BIG``
(``asynchronous-api.md``). Four unfiltered requests to datasets of 624,554 to 853,146
values answered synchronously on 2026-10-27, so the asynchronous answer is the documented
shape, not recorded; the recorded fixture follows when the service answers
asynchronously. Each such test reads the body from the snapshot and says so.
"""

import re
from pathlib import Path

import httpx
import pytest
from xippios.core import InvalidRequestError, NotFoundError
from xippios.core.testing import load_fixture, response_from_fixture

from xippios.eurostat._client import BASE_URL, RATE_LIMIT, classify, config, stored_at

FIXTURES = Path(__file__).parent / "fixtures" / "getData"
GUIDE = Path(__file__).parents[1] / "docs" / "upstream" / "user-guide" / "api-detailed-guidelines"
DATA_URL = f"{BASE_URL}/statistics/1.0/data/apro_mk_cola?format=JSON&lang=EN"
WHERE = "GET /eurostat/api/dissemination/statistics/1.0/data/apro_mk_cola"


def recorded(case: str) -> httpx.Response:
    return response_from_fixture(load_fixture(FIXTURES / f"{case}.json"))


def documented_line(page: str, start: str) -> str:
    """The line of the snapshot's ``page`` that starts with ``start``, backticks removed."""
    for line in (GUIDE / page).read_text(encoding="utf-8").splitlines():
        text = line.strip().strip("`")
        if text.startswith(start):
            return text
    raise AssertionError(f"{page} has no line starting {start!r}")


def documented_xml(page: str, contains: str) -> str:
    """The ```xml block of the snapshot's ``page`` that contains ``contains``."""
    text = (GUIDE / page).read_text(encoding="utf-8")
    for block in re.findall(r"```xml\n(.*?)```", text, flags=re.DOTALL):
        if contains in block:
            return str(block)
    raise AssertionError(f"{page} has no xml block with {contains!r}")


ASYNCHRONOUS = documented_line("api-statistics.md", '{"warning"')
GEO_AND_GEO_LEVEL = documented_line("api-statistics.md", '{"error"')
EXTRACTION_TOO_BIG = documented_xml("asynchronous-api.md", "EXTRACTION_TOO_BIG")


def answer(status: int, body: str, content_type: str = "application/json") -> httpx.Response:
    """NOT RECORDED: an answer with a body the snapshot documents, at ``status``."""
    return httpx.Response(
        status,
        content=body.encode("utf-8"),
        headers={"content-type": content_type},
        request=httpx.Request("GET", DATA_URL),
    )


def assert_host_and_query_free(error: Exception) -> None:
    text = str(error)
    assert "ec.europa.eu" not in text
    assert "format=JSON" not in text


def test_config() -> None:
    assert config.classify is classify
    assert config.cache is None, "no cache on core 0.2.1, which bounds no cached body"
    assert RATE_LIMIT.per_minute == 30
    assert RATE_LIMIT.capacity == 1


def test_unknown_dataset_is_not_found() -> None:
    error = classify(recorded("unknown_dataset"))
    assert isinstance(error, NotFoundError)
    assert str(error) == (
        "Eurostat answered GET /eurostat/api/dissemination/statistics/1.0/data/"
        "no_such_dataset with HTTP 404 (fault 100: ERR_NOT_FOUND_4: NO_SUCH_DATASET "
        "(DATA_FLOW:ALL,1.0) is not available for dissemination.)."
    )
    assert error.source == "eurostat"


def test_unknown_dimension_is_refused() -> None:
    error = classify(recorded("unknown_dimension"))
    assert isinstance(error, InvalidRequestError)
    assert str(error) == (
        f"Eurostat refused the query {WHERE} with HTTP 400 (fault 150: "
        "INVALID_QUERY_DIMENSION: Query is invalid as per its structure's definition. "
        'Dimension "NOSUCHDIM" is not defined).'
    )
    assert_host_and_query_free(error)


def test_geo_with_geo_level_is_refused_as_recorded() -> None:
    error = classify(recorded("geo_with_geo_level"))
    assert isinstance(error, InvalidRequestError)
    assert "fault 400: 'geo' parameter and 'geoLevel' parameter cannot be set" in str(error)


def test_geo_with_geo_level_is_refused_as_documented() -> None:
    """Documented shape, not recorded: one ``error`` object, its status as text, no id."""
    assert GEO_AND_GEO_LEVEL.startswith('{"error":{"status":"400","label":')
    error = classify(answer(400, GEO_AND_GEO_LEVEL))
    assert isinstance(error, InvalidRequestError)
    assert str(error) == (
        f"Eurostat refused the query {WHERE} with HTTP 400 ('geo' parameter and "
        "'geoLevel' parameter cannot be set at the same time. Please choose one or the "
        "other.)."
    )


@pytest.mark.parametrize("status", [200, 413])
def test_asynchronous_answer_is_refused_with_the_hint(status: int) -> None:
    """Documented shape, not recorded; the recorded fixture follows when the service
    answers asynchronously. The guide names no HTTP status for it: both are read."""
    assert ASYNCHRONOUS.startswith('{"warning":{"status":413, "label":"ASYNCHRONOUS_RESPONSE.')
    error = classify(answer(status, ASYNCHRONOUS))
    assert isinstance(error, InvalidRequestError)
    text = str(error)
    assert text.startswith(f"Eurostat will answer {WHERE} asynchronously (ASYNCHRONOUS_RESPONSE.")
    assert "this package does not poll asynchronous answers" in text
    assert "fewer codes per dimension" in text
    assert "bulk download" in text
    assert_host_and_query_free(error)


def test_extraction_too_big_is_refused_with_the_hint() -> None:
    """Documented shape, not recorded: the SDMX APIs' SOAP fault, read in case the
    Statistics API sends it too."""
    error = classify(answer(413, EXTRACTION_TOO_BIG, "text/xml"))
    assert isinstance(error, InvalidRequestError)
    text = str(error)
    assert text.startswith(
        f"Eurostat refused {WHERE} as too large (HTTP 413: EXTRACTION_TOO_BIG: The requested "
        "extraction is too big, estimated 420709314 rows, max authorised is 5000000"
    )
    assert "fewer codes per dimension" in text


def test_a_cube_and_the_empty_cube_are_no_error() -> None:
    assert classify(recorded("apro_mk_cola_AT_2022_2023")) is None
    assert classify(recorded("unknown_code")) is None


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (500, '{"error":[{"status":500,"id":500,"label":"Internal server error"}]}'),
        (400, "not json"),
        (404, ""),
    ],
)
def test_other_answers_fall_through_to_core(status: int, body: str) -> None:
    """NOT RECORDED: a 5xx stays core's, so it is retried; a body of no known shape too."""
    assert classify(answer(status, body)) is None


def test_stored_at_reads_the_cache_mark() -> None:
    hit = answer(200, "{}")
    hit.extensions["xippios_cache_stored_at"] = 1_793_000_000.0
    assert stored_at(hit) is not None
    assert stored_at(answer(200, "{}")) is None
