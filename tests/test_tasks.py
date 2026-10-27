"""Per-task tests with recorded fixtures: at least one replay test for every task.

What every task shares (a sync function returning ``Result[T]`` with an agent docstring,
registered by the adapters and listed in the README status table) is core's family check,
which ``tests/test_family.py`` collects. A replay test that checks what was sent compares
``xippios.core.testing.sent_query(route)``, the scrubbed query of the last request, or
``sent_urls(route)``, the URLs the route received with credentials redacted, rather than
keep a request from ``route.calls`` in its frame, where a failure or ``pytest -l`` would
print it.

The fixtures are ``tests/fixtures/getData/<case>.json``, recorded on 2026-10-27; each
test sends exactly the recorded URL, parameter order included. The asynchronous answer
is not recorded (``tests/test_client.py`` says why); its test serves the user guide's
documented body.
"""

import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from xippios.core import InvalidRequestError, NotFoundError
from xippios.core.testing import (
    ReplayFixture,
    assert_time_between,
    load_fixture,
    mcp_call,
    sent_urls,
)

from xippios.eurostat import get_data, tasks
from xippios.eurostat.http import router
from xippios.eurostat.mcp import server
from xippios.eurostat.models import Cube

FIXTURES = Path(__file__).parent / "fixtures"
GUIDE = Path(__file__).parents[1] / "docs" / "upstream" / "user-guide" / "api-detailed-guidelines"
ENDPOINT = "getData"
CEST = timezone(timedelta(hours=2))


def recorded_url(case: str) -> str:
    return load_fixture(FIXTURES / ENDPOINT / f"{case}.json").request.url


def recorded_updated(case: str) -> str:
    body = json.loads(load_fixture(FIXTURES / ENDPOINT / f"{case}.json").response.body)
    updated: str = body["updated"]
    return updated


def test_get_data_apro_mk_cola(replay_fixture: ReplayFixture) -> None:
    case = "apro_mk_cola_AT_2022_2023"
    route = replay_fixture(ENDPOINT, case)
    before = datetime.now(UTC)
    result = tasks.get_data("apro_mk_cola", {"geo": "AT", "time": ["2022", "2023"]})
    after = datetime.now(UTC)
    assert sent_urls(route) == [recorded_url(case)]
    assert isinstance(result.data, Cube)
    assert result.data.id == ["freq", "milkitem", "dairyprod", "unit", "geo", "time"]
    assert result.data.size == [1, 3, 10, 2, 1, 2]
    assert result.meta.source == "eurostat"
    assert result.meta.endpoint == "getData"
    assert result.meta.published_at == datetime(2026, 10, 5, 23, 0, tzinfo=CEST)
    assert result.meta.published_at == result.data.updated
    assert result.meta.published_at.utcoffset() == timedelta(hours=2)
    assert result.meta.vintage == "2026-10-05T23:00:00+0200" == recorded_updated(case)
    assert result.meta.request == {
        "dataset": "apro_mk_cola",
        "filters": {"geo": "AT", "time": ["2022", "2023"]},
        "lang": "EN",
    }
    assert result.meta.total is None
    assert result.meta.tenant is None
    assert_time_between(result.meta.retrieved_at, before, after)


def test_get_data_apro_cpnh1_since_until(replay_fixture: ReplayFixture) -> None:
    case = "apro_cpnh1_AT_2022_2023"
    route = replay_fixture(ENDPOINT, case)
    result = tasks.get_data(
        "apro_cpnh1", {"geo": "AT"}, since_time_period="2022", until_time_period="2023"
    )
    assert sent_urls(route) == [recorded_url(case)]
    assert result.data.id == ["freq", "crops", "strucpro", "geo", "time"]
    assert result.data.dimension["time"].category.index == {"2022": 0, "2023": 1}
    assert result.meta.published_at == datetime(2026, 9, 28, 23, 0, tzinfo=CEST)
    assert result.meta.vintage == "2026-09-28T23:00:00+0200" == recorded_updated(case)
    assert result.meta.request == {
        "dataset": "apro_cpnh1",
        "filters": {"geo": "AT"},
        "lang": "EN",
        "since_time_period": "2022",
        "until_time_period": "2023",
    }


def test_get_data_ef_m_farmleg_last_periods(replay_fixture: ReplayFixture) -> None:
    case = "ef_m_farmleg_AT_HLD_last_2"
    route = replay_fixture(ENDPOINT, case)
    result = tasks.get_data("ef_m_farmleg", {"geo": "AT", "unit": "HLD"}, last_time_period=2)
    assert sent_urls(route) == [recorded_url(case)]
    assert result.data.id[-2:] == ["geo", "time"]
    assert result.data.dimension["unit"].category.label == {"HLD": "Holding"}
    assert result.data.dimension["time"].category.index == {"2020": 0, "2023": 1}
    assert result.meta.published_at == datetime(2026, 6, 17, 23, 0, tzinfo=CEST)
    assert result.meta.vintage == "2026-06-17T23:00:00+0200" == recorded_updated(case)
    assert result.meta.request == {
        "dataset": "ef_m_farmleg",
        "filters": {"geo": "AT", "unit": "HLD"},
        "lang": "EN",
        "last_time_period": 2,
    }


def test_get_data_unknown_code_is_an_empty_cube(replay_fixture: ReplayFixture) -> None:
    case = "unknown_code"
    route = replay_fixture(ENDPOINT, case)
    result = get_data("apro_mk_cola", {"geo": "XX", "time": "2023"})
    assert sent_urls(route) == [recorded_url(case)]
    assert result.data.size[result.data.id.index("geo")] == 0
    assert result.data.value == {}
    assert list(result.data.observations()) == []
    assert result.meta.vintage == recorded_updated(case)
    assert result.meta.request["filters"] == {"geo": "XX", "time": "2023"}


def test_get_data_unknown_dataset(replay_fixture: ReplayFixture) -> None:
    route = replay_fixture(ENDPOINT, "unknown_dataset")
    with pytest.raises(NotFoundError, match="NO_SUCH_DATASET"):
        tasks.get_data("no_such_dataset")
    assert sent_urls(route) == [recorded_url("unknown_dataset")]


def test_get_data_unknown_dimension(replay_fixture: ReplayFixture) -> None:
    replay_fixture(ENDPOINT, "unknown_dimension")
    with pytest.raises(InvalidRequestError, match="INVALID_QUERY_DIMENSION"):
        tasks.get_data("apro_mk_cola", {"nosuchdim": "AT"})


def test_get_data_geo_with_geo_level(replay_fixture: ReplayFixture) -> None:
    route = replay_fixture(ENDPOINT, "geo_with_geo_level")
    with pytest.raises(InvalidRequestError, match="cannot be set at the same time"):
        tasks.get_data("apro_mk_cola", {"geo": "AT"}, geo_level="country")
    assert sent_urls(route) == [recorded_url("geo_with_geo_level")]


@pytest.mark.parametrize(
    ("filters", "times", "named"),
    [
        ({"time": "2023"}, {"last_time_period": 2}, "filters['time'], last_time_period"),
        ({"time": "2023"}, {"since_time_period": "2020"}, "filters['time'], since_time_period"),
        ({"TIME": "2023"}, {"until_time_period": "2023"}, "filters['TIME'], until_time_period"),
        ({"time": "2023", "time_period": "2022"}, {}, "filters['time'], filters['time_period']"),
        (
            {},
            {"since_time_period": "2020", "last_time_period": 2},
            "since_time_period, last_time_period",
        ),
        (
            {},
            {"until_time_period": "2023", "last_time_period": 2},
            "until_time_period, last_time_period",
        ),
        (
            {},
            {"since_time_period": "2020", "until_time_period": "2023", "last_time_period": 2},
            "since_time_period, until_time_period, last_time_period",
        ),
    ],
)
def test_get_data_refuses_more_than_one_time_parameter(
    respx_mock: respx.MockRouter, filters: dict[str, str], times: dict[str, Any], named: str
) -> None:
    """api-statistics.md, "The Time parameter": "Using more than one Time parameter in the
    same query is not accepted. The only exception is using both sinceTimePeriod and
    untilTimePeriod." Refused before any request (ADR-0007), so nothing is replayed."""
    with pytest.raises(InvalidRequestError) as refused:
        tasks.get_data("apro_mk_cola", {"geo": "AT", **filters}, **times)
    assert str(refused.value) == (
        f"{named}: the Statistics API does not accept more than one time parameter in a "
        "query; the one exception is since_time_period with until_time_period"
    )
    assert not respx_mock.calls, "refused before any request"


def test_documented_shape_get_data_refuses_an_asynchronous_answer(
    respx_mock: respx.MockRouter,
) -> None:
    """Documented shape, read verbatim from the snapshot at test time; neither recorded nor
    hand-written: the asynchronous answer of api-statistics.md. The first asynchronous
    answer seen is recorded and replaces this test (Johannes, 2026-10-27)."""
    documented = next(
        line.strip()
        for line in (GUIDE / "api-statistics.md").read_text(encoding="utf-8").splitlines()
        if line.startswith('{"warning"')
    )
    respx_mock.route(
        method="GET",
        host="ec.europa.eu",
        path="/eurostat/api/dissemination/statistics/1.0/data/apro_ec_poulm",
    ).mock(return_value=httpx.Response(200, content=documented.encode("utf-8")))
    with pytest.raises(InvalidRequestError, match="asynchronously") as refused:
        tasks.get_data("apro_ec_poulm")
    assert "send the same request again later" in str(refused.value)
    assert "fewer codes per dimension" in str(refused.value)


@pytest.mark.parametrize(
    "filters",
    [{"format": "XML"}, {"LANG": "FR"}, {"geoLevel": "country"}, {"lastTimePeriod": "2"}],
)
def test_get_data_refuses_a_parameter_as_a_filter(
    respx_mock: respx.MockRouter, filters: dict[str, str]
) -> None:
    with pytest.raises(InvalidRequestError, match="is a parameter of the Statistics API"):
        tasks.get_data("apro_mk_cola", filters)
    assert not respx_mock.calls, "refused before any request"


def test_get_data_refuses_an_empty_list_of_codes(respx_mock: respx.MockRouter) -> None:
    with pytest.raises(InvalidRequestError, match="lists no code"):
        tasks.get_data("apro_mk_cola", {"geo": []})
    assert not respx_mock.calls


def test_get_data_leaves_published_at_empty_for_an_updated_without_zone(
    respx_mock: respx.MockRouter,
) -> None:
    """NOT RECORDED: the recorded cube with ``updated`` stripped of its zone in memory, a
    form never seen; ``ResultMeta`` takes a zoned time only, the text stays the vintage."""
    fixture = load_fixture(FIXTURES / ENDPOINT / "apro_mk_cola_AT_2022_2023.json")
    body: dict[str, Any] = json.loads(fixture.response.body)
    body["updated"] = "2026-10-05T23:00:00"
    respx_mock.route(method="GET", host="ec.europa.eu").mock(
        return_value=httpx.Response(200, json=body)
    )
    result = tasks.get_data("apro_mk_cola", {"geo": "AT", "time": ["2022", "2023"]})
    assert result.meta.published_at is None
    assert result.meta.vintage == "2026-10-05T23:00:00"


@pytest.mark.anyio
async def test_get_data_tool_end_to_end(replay_fixture: ReplayFixture) -> None:
    case = "apro_mk_cola_AT_2022_2023"
    route = replay_fixture(ENDPOINT, case)
    payload = await mcp_call(
        server,
        "eurostat_get_data",
        {"dataset": "apro_mk_cola", "filters": {"geo": "AT", "time": ["2022", "2023"]}},
    )
    assert sent_urls(route) == [recorded_url(case)]
    assert payload["data"]["id"] == ["freq", "milkitem", "dairyprod", "unit", "geo", "time"]
    assert payload["data"]["class_"] == "dataset"
    assert payload["data"]["value"]["40"] == 3247.05
    assert payload["meta"]["endpoint"] == "getData"
    assert payload["meta"]["vintage"] == "2026-10-05T23:00:00+0200"
    assert payload["meta"]["published_at"] == "2026-10-05T23:00:00+02:00"


def test_get_data_route_end_to_end(replay_fixture: ReplayFixture) -> None:
    """A mapping parameter makes the route a POST with a JSON body (ADR-0007)."""
    case = "apro_mk_cola_AT_2022_2023"
    route = replay_fixture(ENDPOINT, case)
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as http:
        answer = http.post(
            "/eurostat/get_data",
            json={"dataset": "apro_mk_cola", "filters": {"geo": "AT", "time": ["2022", "2023"]}},
        )
    assert answer.status_code == 200
    assert sent_urls(route) == [recorded_url(case)]
    assert answer.json()["meta"]["request"]["filters"] == {"geo": "AT", "time": ["2022", "2023"]}


def test_get_data_route_answers_a_refusal_with_422(replay_fixture: ReplayFixture) -> None:
    replay_fixture(ENDPOINT, "unknown_dimension")
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as http:
        answer = http.post(
            "/eurostat/get_data", json={"dataset": "apro_mk_cola", "filters": {"nosuchdim": "AT"}}
        )
    assert answer.status_code == 422
    assert "INVALID_QUERY_DIMENSION" in answer.text
