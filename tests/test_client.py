"""``classify`` against the recorded refusals and the documented ones.

Recorded on 2026-10-27 (``tests/fixtures/getData/``): an unknown dataset, an unknown
dimension and ``geo`` with ``geoLevel``, all with ``error`` as an array, and the empty
cube of an unknown code. The tests named ``test_documented_shape_*`` serve shapes the
service was not seen to send: each reads its body verbatim from the snapshot's user guide
at test time, so it is neither recorded nor hand-written. They are the single-object
``error`` the guide shows for ``geo`` with ``geoLevel``, the fault table's "No results
found" at HTTP 400 and the asynchronous answer (``api-statistics.md``), and the SOAP fault
``EXTRACTION_TOO_BIG`` (``asynchronous-api.md``). Four unfiltered requests to datasets of
624,554 to 853,146 values answered synchronously on 2026-10-27 and probing stopped there;
the first asynchronous answer ever seen is recorded and replaces its test (Johannes,
2026-10-27; gap row 83).
"""

import json
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


def documented_fault_row(code: int, status: int) -> tuple[str, str]:
    """The fault table row of ``api-statistics.md`` for ``code`` at ``status``: its name and
    description, e.g. ``("No results found", "The result from the query is empty.")``."""
    text = (GUIDE / "api-statistics.md").read_text(encoding="utf-8")
    for line in text.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if (
            len(cells) == 3
            and cells[0].startswith(f"{code} ")
            and cells[1].startswith(f"{status} ")
        ):
            return cells[0].removeprefix(f"{code} "), cells[2]
    raise AssertionError(f"api-statistics.md has no fault table row {code} at HTTP {status}")


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
    assert config.cache is None, "the cache is off until core bounds a cached body"
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


def test_documented_shape_geo_with_geo_level_object_is_refused() -> None:
    """Documented shape, read verbatim from the snapshot at test time; neither recorded nor
    hand-written: one ``error`` object, its status as text, no id."""
    assert GEO_AND_GEO_LEVEL.startswith('{"error":{"status":"400","label":')
    error = classify(answer(400, GEO_AND_GEO_LEVEL))
    assert isinstance(error, InvalidRequestError)
    assert str(error) == (
        f"Eurostat refused the query {WHERE} with HTTP 400 ('geo' parameter and "
        "'geoLevel' parameter cannot be set at the same time. Please choose one or the "
        "other.)."
    )


def test_documented_shape_no_results_at_400_is_not_found() -> None:
    """Documented shape, read verbatim from the snapshot at test time; neither recorded nor
    hand-written: the fault table's row "100 No results found | 400 Bad request | The
    result from the query is empty.", in the recorded ``error`` array form, its name and
    description as the label. Upstream signals absence: ``NotFoundError``."""
    name, description = documented_fault_row(100, 400)
    assert (name, description) == ("No results found", "The result from the query is empty.")
    body = json.dumps({"error": [{"status": 400, "id": 100, "label": f"{name}: {description}"}]})
    error = classify(answer(400, body))
    assert isinstance(error, NotFoundError)
    assert str(error) == (
        f"Eurostat answered {WHERE} with HTTP 400 (fault 100: No results found: The result "
        "from the query is empty.)."
    )


@pytest.mark.parametrize(("code", "status"), [(140, 400), (150, 400)])
def test_documented_shape_syntax_and_semantic_errors_are_refused(code: int, status: int) -> None:
    """Documented shape, read verbatim from the snapshot at test time; neither recorded nor
    hand-written: the fault table's 140 and 150 rows at HTTP 400 stay refusals."""
    name, description = documented_fault_row(code, status)
    body = json.dumps(
        {"error": [{"status": status, "id": code, "label": f"{name}: {description}"}]}
    )
    assert isinstance(classify(answer(status, body)), InvalidRequestError)


@pytest.mark.parametrize("status", [200, 413])
def test_documented_shape_asynchronous_answer_is_refused(status: int) -> None:
    """Documented shape, read verbatim from the snapshot at test time; neither recorded nor
    hand-written; the first asynchronous answer seen is recorded and replaces this test.
    The guide names no HTTP status for it: both are read."""
    assert ASYNCHRONOUS.startswith('{"warning":{"status":413, "label":"ASYNCHRONOUS_RESPONSE.')
    error = classify(answer(status, ASYNCHRONOUS))
    assert isinstance(error, InvalidRequestError)
    text = str(error)
    assert text.startswith(f"Eurostat will answer {WHERE} asynchronously (ASYNCHRONOUS_RESPONSE.")
    assert "this package does not poll asynchronous answers" in text
    assert "send the same request again later" in text
    assert "fewer codes per dimension in filters" in text
    assert "(since_time_period and until_time_period, or last_time_period)" in text
    assert "bulk download" in text
    assert_host_and_query_free(error)


def test_documented_shape_extraction_too_big_is_refused() -> None:
    """Documented shape, read verbatim from the snapshot at test time; neither recorded nor
    hand-written: the SDMX APIs' SOAP fault, read in case the Statistics API sends it
    too."""
    error = classify(answer(413, EXTRACTION_TOO_BIG, "text/xml"))
    assert isinstance(error, InvalidRequestError)
    text = str(error)
    assert text.startswith(
        f"Eurostat refused {WHERE} as too large (HTTP 413: EXTRACTION_TOO_BIG: The requested "
        "extraction is too big, estimated 420709314 rows, max authorised is 5000000"
    )
    assert "fewer codes per dimension" in text
    assert "again later" not in text, "too large is not a matter of waiting"


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
