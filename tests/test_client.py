"""``classify`` against the recorded refusals and the documented ones, on both bases.

Recorded on the main base on 2026-10-27: under ``tests/fixtures/get_data/`` an unknown
dataset, an unknown dimension and ``geo`` with ``geoLevel``, all with ``error`` as an
array, and the empty cube of an unknown code; under ``tests/fixtures/data_query/`` two
SDMX-CSV answers, plain and ``compressed=true``. Recorded on the Comext base on
2026-10-28, mirroring them: under ``get_data/`` the Prodcom cube ``DS-059358``, an
unknown ``DS-`` dataset (HTTP 404, the same ``error`` array), a filter on a dimension
``DS-059358`` lacks, which the Comext base does not refuse as the main base does but
counts unfiltered and refuses as too large (HTTP 413, an ``error`` array with id 413,
``EXTRACTION_TOO_BIG``), and the empty cube of an unknown reporter; under
``data_query/`` two SDMX-CSV answers of ``DS-059358``, the envelope that queues an
asynchronous answer (``DS-045409``, the whole monthly flow: HTTP 200,
``application/xml``, status ``SUBMITTED``) and the SOAP fault ``EXTRACTION_TOO_BIG`` at
HTTP 413 (``DS-045409``, five reporters and one partner for a year). The two SDMX
answers replace the tests that served the user guide's documented bodies (rows 59 and
83). Not recorded, two kinds of tests serve answers the service was not seen to send:

- ``test_documented_shape_*`` read a documented body verbatim from the snapshot's user
  guide at test time, so it is neither recorded nor hand-written: the Statistics API's
  asynchronous ``warning`` and the single-object ``error`` the guide shows for ``geo``
  with ``geoLevel`` (``api-statistics.md``). Four unfiltered requests to datasets of
  624,554 to 853,146 values answered synchronously on 2026-10-27; probing stopped
  there, and the first such answer seen is recorded and replaces its test (Johannes,
  2026-10-27; gap row 83).
- ``test_fault_table_*`` compose a body from a row of the fault table
  (``api-statistics.md``), read at test time, in the recorded ``error`` array form: the
  guide documents the fault codes, not their bodies (faults 100, 140 and 150 at HTTP 400).
"""

import json
from pathlib import Path

import httpx
import pytest
from xippios.core import InvalidRequestError, NotFoundError
from xippios.core.client import MemoryCache
from xippios.core.testing import load_fixture, response_from_fixture

from xippios.eurostat._client import (
    BASE_URL,
    COMEXT_BASE_URL,
    RATE_LIMIT,
    SDMX_DATA_PATHS,
    classify,
    config,
    url_for,
)

FIXTURES = Path(__file__).parent / "fixtures" / "get_data"
SDMX_FIXTURES = Path(__file__).parent / "fixtures" / "data_query"
GUIDE = Path(__file__).parents[1] / "docs" / "upstream" / "user-guide" / "api-detailed-guidelines"
DATA_URL = f"{BASE_URL}/statistics/1.0/data/apro_mk_cola?format=JSON&lang=EN"
WHERE = "GET /eurostat/api/dissemination/statistics/1.0/data/apro_mk_cola"
SDMX_URL = f"{BASE_URL}/sdmx/2.1/data/ef_m_farmleg?format=SDMX-CSV&compressed=true"
COMEXT_WHERE = "GET /eurostat/api/comext/dissemination"


def recorded(case: str) -> httpx.Response:
    return response_from_fixture(load_fixture(FIXTURES / f"{case}.json"))


def recorded_sdmx(case: str) -> httpx.Response:
    return response_from_fixture(load_fixture(SDMX_FIXTURES / f"{case}.json"))


def downloaded(case: str, content_type: str | None = None) -> httpx.Response:
    """The recorded SDMX exchange as a download hands it to ``classify``: its status and
    headers, the body unread (ADR-0019, amendment 2026-10-27). ``content_type`` replaces
    the recorded ``Content-Type`` in memory, ``""`` removes it."""
    fixture = load_fixture(SDMX_FIXTURES / f"{case}.json")
    headers = [
        (name, value)
        for name, value in fixture.response.headers
        if content_type is None or name.lower() != "content-type"
    ]
    if content_type:
        headers.append(("content-type", content_type))
    return httpx.Response(
        fixture.response.status,
        headers=headers,
        stream=httpx.ByteStream(fixture.response.content),
        request=httpx.Request("GET", fixture.request.url),
    )


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


ASYNCHRONOUS = documented_line("api-statistics.md", '{"warning"')
GEO_AND_GEO_LEVEL = documented_line("api-statistics.md", '{"error"')


def answer(
    status: int, body: str, content_type: str = "application/json", url: str = DATA_URL
) -> httpx.Response:
    """NOT RECORDED: an answer with a body the snapshot documents, at ``status``."""
    return httpx.Response(
        status,
        content=body.encode("utf-8"),
        headers={"content-type": content_type},
        request=httpx.Request("GET", url),
    )


def unread(status: int, body: str, content_type: str, url: str = SDMX_URL) -> httpx.Response:
    """NOT RECORDED: an answer whose body is not read, as a download hands it to
    ``classify``: its status and headers only (ADR-0019, amendment 2026-10-27)."""
    return httpx.Response(
        status,
        headers={"content-type": content_type},
        stream=httpx.ByteStream(body.encode("utf-8")),
        request=httpx.Request("GET", url),
    )


def assert_host_and_query_free(error: Exception) -> None:
    text = str(error)
    assert "ec.europa.eu" not in text
    assert "format=JSON" not in text


def test_config() -> None:
    assert config.classify is classify
    assert isinstance(config.cache, MemoryCache), "core's backend, its default lifetime"
    assert config.cache_max_bytes == 8 * 1024 * 1024, "core's bound, ADR-0019 decision 3"
    assert RATE_LIMIT.per_minute == 30
    assert RATE_LIMIT.capacity == 1


def test_url_for_requests_a_ds_code_on_the_comext_base() -> None:
    """Upstream's rule (prefixed-datasets.md): a "DS- prefixed dataset code" is served on
    the Comext base, as an absolute URL the client sends as it is; every other code keeps
    the path, which the client joins onto the main base as before."""
    assert BASE_URL == "https://ec.europa.eu/eurostat/api/dissemination"
    assert COMEXT_BASE_URL == "https://ec.europa.eu/eurostat/api/comext/dissemination"
    prodcom = "/statistics/1.0/data/DS-059358"
    assert url_for("DS-059358", prodcom) == (
        "https://ec.europa.eu/eurostat/api/comext/dissemination/statistics/1.0/data/DS-059358"
    )
    trade = "/sdmx/2.1/data/DS-045409/M.AT.US.1201.1.?format=SDMX-CSV&compressed=true"
    assert url_for("DS-045409", trade) == f"{COMEXT_BASE_URL}{trade}"
    milk = "/statistics/1.0/data/apro_mk_cola"
    assert url_for("apro_mk_cola", milk) == milk, "the main base's path, unchanged"
    assert url_for("ds-059358", "/statistics/1.0/data/ds-059358") == (
        "/statistics/1.0/data/ds-059358"
    ), "the prefix as upstream writes it; the code is never folded"


def test_sdmx_data_paths_are_both_bases() -> None:
    assert SDMX_DATA_PATHS == (
        "/eurostat/api/dissemination/sdmx/2.1/data/",
        "/eurostat/api/comext/dissemination/sdmx/2.1/data/",
    )


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


def test_fault_table_no_results_at_400_is_not_found() -> None:
    """NOT RECORDED: composed from the fault table's row in the recorded array form, "100
    No results found | 400 Bad request | The result from the query is empty.", its name
    and description as the label. Upstream signals absence: ``NotFoundError``."""
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
def test_fault_table_syntax_and_semantic_errors_are_refused(code: int, status: int) -> None:
    """NOT RECORDED: composed from the fault table's row in the recorded array form; the
    140 and 150 rows at HTTP 400 stay refusals."""
    name, description = documented_fault_row(code, status)
    body = json.dumps(
        {"error": [{"status": status, "id": code, "label": f"{name}: {description}"}]}
    )
    assert isinstance(classify(answer(status, body)), InvalidRequestError)


@pytest.mark.parametrize("status", [200, 413])
def test_documented_shape_asynchronous_answer_is_refused(status: int) -> None:
    """Documented shape, read verbatim from the snapshot at test time; neither recorded nor
    hand-written; the Statistics API's first asynchronous answer seen is recorded and
    replaces this test. The guide names no HTTP status for it: both are read."""
    assert ASYNCHRONOUS.startswith('{"warning":{"status":413, "label":"ASYNCHRONOUS_RESPONSE.')
    error = classify(answer(status, ASYNCHRONOUS))
    assert isinstance(error, InvalidRequestError)
    text = str(error)
    assert text.startswith(f"Eurostat will answer {WHERE} asynchronously (ASYNCHRONOUS_RESPONSE.")
    assert "this package does not poll asynchronous answers" in text
    assert text.endswith(
        "this package does not poll asynchronous answers: the Statistics API prepares the "
        "answer meanwhile and does not say when it is ready: send the same request again "
        "later, or narrow the query with fewer codes per dimension or a shorter period."
    )
    assert "since_time_period" not in text, "classify serves every task: no task's names"
    assert_host_and_query_free(error)


def test_extraction_too_big_is_refused() -> None:
    """Recorded on the Comext base: the SDMX API's SOAP fault ``EXTRACTION_TOO_BIG`` at
    HTTP 413, which a download reads for the error's text; its ``faultstring`` goes into
    the message."""
    error = classify(recorded_sdmx("DS-045409_too_big_413"))
    assert isinstance(error, InvalidRequestError)
    text = str(error)
    assert text.startswith(
        f"Eurostat refused {COMEXT_WHERE}/sdmx/2.1/data/DS-045409/M.AT+DE+FR+IT+NL.US... as "
        "too large (HTTP 413: EXTRACTION_TOO_BIG: The requested extraction is too big, "
        "estimated "
    )
    assert text.endswith(
        "please change your filters to reduce the extraction size): narrow the query with "
        "fewer codes per dimension or a shorter period."
    )
    assert "again later" not in text, "too large is not a matter of waiting"
    assert_host_and_query_free(error)


def test_statistics_api_too_big_is_refused_on_the_comext_base() -> None:
    """Recorded on the Comext base: a filter on a dimension ``DS-059358`` lacks (``geo``)
    is counted unfiltered and answered with HTTP 413 and an ``error`` array whose id is
    413 (``EXTRACTION_TOO_BIG``), not with the main base's fault 150 at HTTP 400. It is
    refused as too large, the array's fault described as at HTTP 400."""
    response = recorded("DS-059358_unknown_dimension_too_big")
    assert response.status_code == 413
    assert '"label": "EXTRACTION_TOO_BIG' in response.text
    error = classify(response)
    assert isinstance(error, InvalidRequestError)
    assert str(error) == (
        f"Eurostat refused {COMEXT_WHERE}/statistics/1.0/data/DS-059358 as too large "
        "(HTTP 413: fault 413: EXTRACTION_TOO_BIG: The requested extraction is too big, "
        "estimated 151971120 rows, max authorised is 5000000, please change your filters "
        "to reduce the extraction size): narrow the query with fewer codes per dimension or "
        "a shorter period."
    )
    assert_host_and_query_free(error)


def test_unknown_ds_dataset_is_not_found() -> None:
    """Recorded on the Comext base: the main base's shape, an ``error`` array at HTTP 404."""
    error = classify(recorded("DS_unknown_dataset"))
    assert isinstance(error, NotFoundError)
    assert str(error) == (
        f"Eurostat answered {COMEXT_WHERE}/statistics/1.0/data/DS-000000 with HTTP 404 "
        "(fault 100: ERR_NOT_FOUND_4: DS-000000 (DATA_FLOW:ALL,1.0) is not available for "
        "dissemination.)."
    )
    assert_host_and_query_free(error)


@pytest.mark.parametrize(
    "case",
    [
        "apro_mk_cola_AT_2022_2023",
        "unknown_code",
        "DS-059358_AT_10411200_2022_2023",
        "DS-059358_unknown_code",
    ],
)
def test_a_cube_and_the_empty_cube_are_no_error(case: str) -> None:
    assert classify(recorded(case)) is None


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


ASYNCHRONOUS_SDMX = "DS-045409_asynchronous"


def test_sdmx_asynchronous_envelope_is_refused() -> None:
    """Recorded on the Comext base: the envelope that queues an SDMX data request, status
    ``SUBMITTED`` (``asynchronous-api.md``, "Step 1: Initial request"), at HTTP 200 with
    ``application/xml``. Refused from the headers alone, as a download hands it over: the
    body is never read."""
    fixture = load_fixture(SDMX_FIXTURES / f"{ASYNCHRONOUS_SDMX}.json")
    assert (fixture.response.status, dict(fixture.response.headers)["content-type"]) == (
        200,
        "application/xml",
    )
    assert "<status>SUBMITTED</status>" in fixture.response.body
    response = downloaded(ASYNCHRONOUS_SDMX)
    error = classify(response)
    assert isinstance(error, InvalidRequestError)
    assert str(error) == (
        f"Eurostat answered {COMEXT_WHERE}/sdmx/2.1/data/DS-045409/M..... with "
        "application/xml, not SDMX-CSV: a data query the SDMX API will treat asynchronously "
        "is answered with an XML envelope that queues it, and this package does not poll "
        "asynchronous answers: narrow the query with fewer codes per dimension or a shorter "
        "period."
    )
    assert error.source == "eurostat"
    assert_host_and_query_free(error)
    assert "format=SDMX-CSV" not in str(error), "no query in the message"
    with pytest.raises(httpx.ResponseNotRead):
        _ = response.content


@pytest.mark.parametrize(
    ("content_type", "media"),
    [("text/xml", "text/xml"), ("application/xml;charset=UTF-8", "application/xml"), ("", None)],
)
def test_sdmx_asynchronous_envelope_is_refused_whatever_its_type(
    content_type: str, media: str | None
) -> None:
    """NOT RECORDED as such: the recorded envelope with its ``Content-Type`` replaced, or
    removed, in memory; the guide names no type for it, so any that is not SDMX-CSV's is
    refused, on the main base's data path as on the Comext base's."""
    error = classify(downloaded(ASYNCHRONOUS_SDMX, content_type))
    assert isinstance(error, InvalidRequestError)
    assert f" with {media or 'no content type'}, not SDMX-CSV: " in str(error)
    main = load_fixture(SDMX_FIXTURES / f"{ASYNCHRONOUS_SDMX}.json")
    moved = httpx.Response(
        200,
        headers={"content-type": content_type} if content_type else {},
        stream=httpx.ByteStream(main.response.content),
        request=httpx.Request("GET", SDMX_URL),
    )
    error = classify(moved)
    assert isinstance(error, InvalidRequestError)
    assert str(error).startswith(
        "Eurostat answered GET /eurostat/api/dissemination/sdmx/2.1/data/ef_m_farmleg with "
        f"{media or 'no content type'}, not SDMX-CSV: "
    )


@pytest.mark.parametrize(
    "case",
    [
        "apro_mk_cola_AT_THS_T_2022_2023",
        "apro_mk_cola_AT_THS_T_2022_2023_compressed",
        "DS-059358_A_AT_10411200_2022_2023",
        "DS-059358_A_AT_10411200_2022_2023_compressed",
    ],
)
def test_an_sdmx_csv_answer_is_no_error(case: str) -> None:
    """The recorded SDMX-CSV answers on both bases, plain and ``compressed=true``, pass,
    read or not."""
    recorded = recorded_sdmx(case)
    assert classify(recorded) is None
    content_type = recorded.headers["content-type"]
    assert content_type == "application/vnd.sdmx.data+csv;version=1.0.0"
    assert classify(downloaded(case)) is None


def test_the_content_type_rule_reads_sdmx_data_queries_only() -> None:
    """NOT RECORDED as such: the recorded envelope served from the Statistics API at HTTP
    200, and JSON from the SDMX codelist query, are not data queries; neither is a 4xx's
    body type a matter here."""
    envelope = load_fixture(SDMX_FIXTURES / f"{ASYNCHRONOUS_SDMX}.json").response.body
    assert classify(answer(200, envelope, "application/xml")) is None
    statistics = f"{COMEXT_BASE_URL}/statistics/1.0/data/DS-059358?format=JSON&lang=EN"
    assert classify(answer(200, envelope, "application/xml", statistics)) is None
    codelist = f"{BASE_URL}/sdmx/2.1/codelist/ESTAT/GEO?format=JSON&lang=en"
    assert classify(answer(200, "{}", "application/json", codelist)) is None
    assert classify(unread(404, "", "text/xml")) is None
