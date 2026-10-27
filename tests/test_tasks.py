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
documented body. The slices (``get_series``, ``get_latest_period``,
``get_cross_section``) each send one getData request, so their fixtures are getData
answers too: ``*_series_*``, ``*_latest_*`` and ``*_cross_section_*``, plus two of
``get_data``'s whose URL a slice sends as well (``apro_cpnh1_AT_2022_2023``, a series
refused, and ``unknown_code``, an empty cross-section).
"""

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
import respx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from xippios.core import InvalidRequestError, NotFoundError
from xippios.core.client import cache_key
from xippios.core.testing import (
    CLOCK_SLACK,
    ReplayFixture,
    assert_time_between,
    load_fixture,
    mcp_call,
    mcp_call_text,
    sent_urls,
)

from xippios.eurostat import get_cross_section, get_data, get_latest_period, get_series, tasks
from xippios.eurostat._client import config
from xippios.eurostat.http import router
from xippios.eurostat.mcp import server
from xippios.eurostat.models import Cube, GeoLevel, Lang, Observation

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
    assert result.meta.published_at_naive is False, "a zoned updated is no naive time"
    assert result.meta.vintage == "2026-10-05T23:00:00+0200" == recorded_updated(case)
    assert result.meta.request == {
        "dataset": "apro_mk_cola",
        "filters": {"geo": "AT", "time": ["2022", "2023"]},
        "lang": "EN",
    }
    assert result.meta.total is None
    assert result.meta.tenant is None
    assert_time_between(result.meta.retrieved_at, before, after)


def test_get_data_answers_a_repeated_request_from_the_cache(replay_fixture: ReplayFixture) -> None:
    """The same request twice is one request on the wire: the client's cache answers the
    second, whose ``meta.retrieved_at`` is the time the first answer was stored
    (conventions §4; ADR-0015 decision 5), within the readings around the first call. The
    testing plugin clears the cache around each test, so the first call is a miss."""
    case = "apro_mk_cola_AT_2022_2023"
    route = replay_fixture(ENDPOINT, case)
    filters = {"geo": "AT", "time": ["2022", "2023"]}
    before = datetime.now(UTC)
    first = tasks.get_data("apro_mk_cola", filters)
    after = datetime.now(UTC)
    second = tasks.get_data("apro_mk_cola", filters)
    assert sent_urls(route) == [recorded_url(case)], "one request on the wire"
    assert config.cache is not None
    entry = config.cache.get(cache_key("GET", httpx.URL(recorded_url(case))))
    assert entry is not None
    assert second.meta.retrieved_at == datetime.fromtimestamp(entry.stored_at, UTC)
    assert_time_between(first.meta.retrieved_at, before, after)
    assert_time_between(second.meta.retrieved_at, before, after)
    assert abs(second.meta.retrieved_at - first.meta.retrieved_at) <= CLOCK_SLACK
    assert second.data == first.data
    assert second.meta.model_dump(exclude={"retrieved_at"}) == first.meta.model_dump(
        exclude={"retrieved_at"}
    )


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


@pytest.mark.parametrize("level", [GeoLevel.COUNTRY, "country"], ids=["member", "plain"])
def test_get_data_geo_with_geo_level(replay_fixture: ReplayFixture, level: str) -> None:
    """A plain string is accepted where the enumeration is expected, and sent as it."""
    route = replay_fixture(ENDPOINT, "geo_with_geo_level")
    with pytest.raises(InvalidRequestError, match="cannot be set at the same time"):
        tasks.get_data("apro_mk_cola", {"geo": "AT"}, geo_level=cast(GeoLevel, level))
    assert sent_urls(route) == [recorded_url("geo_with_geo_level")]


def test_get_data_takes_lang_as_a_plain_string(replay_fixture: ReplayFixture) -> None:
    case = "apro_mk_cola_AT_2022_2023"
    route = replay_fixture(ENDPOINT, case)
    result = tasks.get_data(
        "apro_mk_cola", {"geo": "AT", "time": ["2022", "2023"]}, lang=cast(Lang, "EN")
    )
    assert sent_urls(route) == [recorded_url(case)]
    assert result.meta.request["lang"] == "EN"
    assert type(result.meta.request["lang"]) is str, "meta.request holds the plain value"


@pytest.mark.parametrize(
    ("argument", "value"), [("lang", "en"), ("lang", "IT"), ("geo_level", "region")]
)
def test_get_data_refuses_a_value_outside_the_enumeration(
    respx_mock: respx.MockRouter, argument: str, value: str
) -> None:
    with pytest.raises(InvalidRequestError, match=f"{argument}={value!r} is not one of"):
        tasks.get_data("apro_mk_cola", {"geo": "AT"}, **{argument: cast(Any, value)})
    assert not respx_mock.calls, "refused before any request"


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


def test_get_data_keeps_an_updated_without_zone_as_a_naive_published_at(
    respx_mock: respx.MockRouter,
) -> None:
    """NOT RECORDED: the recorded cube with ``updated`` stripped of its zone in memory, a
    form never seen; ``published_at`` keeps it as printed, no zone invented, with
    ``published_at_naive`` set, and the text stays the vintage (ADR-0022 rule 2)."""
    fixture = load_fixture(FIXTURES / ENDPOINT / "apro_mk_cola_AT_2022_2023.json")
    body: dict[str, Any] = json.loads(fixture.response.body)
    body["updated"] = "2026-10-05T23:00:00"
    respx_mock.route(method="GET", host="ec.europa.eu").mock(
        return_value=httpx.Response(200, json=body)
    )
    result = tasks.get_data("apro_mk_cola", {"geo": "AT", "time": ["2022", "2023"]})
    assert result.meta.published_at == datetime(2026, 10, 5, 23, 0)
    assert result.meta.published_at.tzinfo is None
    assert result.meta.published_at_naive is True
    assert result.meta.vintage == "2026-10-05T23:00:00"


@pytest.mark.anyio
async def test_get_data_tool_end_to_end(replay_fixture: ReplayFixture) -> None:
    case = "apro_mk_cola_AT_2022_2023"
    route = replay_fixture(ENDPOINT, case)
    payload = await mcp_call(
        server,
        "eurostat_get_data",
        {
            "dataset": "apro_mk_cola",
            "filters": {"geo": "AT", "time": ["2022", "2023"]},
            "lang": "EN",
        },
    )
    assert sent_urls(route) == [recorded_url(case)]
    assert payload["meta"]["request"]["lang"] == "EN"
    assert payload["data"]["id"] == ["freq", "milkitem", "dairyprod", "unit", "geo", "time"]
    assert payload["data"]["class_"] == "dataset"
    assert payload["data"]["value"]["40"] == 3247.05
    assert payload["meta"]["endpoint"] == "getData"
    assert payload["meta"]["vintage"] == "2026-10-05T23:00:00+0200"
    assert payload["meta"]["published_at"] == "2026-10-05T23:00:00+02:00"
    assert payload["meta"]["published_at_naive"] is False


@pytest.mark.anyio
async def test_get_data_tool_schema_lists_the_enumerations() -> None:
    """The MCP schema carries ``Lang`` and ``GeoLevel`` as enumerations of strings, so an
    agent sees the valid values; the tool validates a string against them."""
    tools = {tool.name: tool for tool in await server.list_tools()}
    schema = tools["eurostat_get_data"].input_schema
    assert schema["properties"]["lang"] == {"$ref": "#/$defs/Lang", "default": "EN"}
    assert schema["$defs"]["Lang"]["enum"] == ["EN", "FR", "DE"]
    assert schema["$defs"]["GeoLevel"]["enum"] == [
        "aggregate",
        "country",
        "nuts1",
        "nuts2",
        "nuts3",
        "city",
    ]


SCHEMA_REFUSALS = [
    ({"lang": "IT"}, "lang: Input should be 'EN', 'FR' or 'DE'"),
    ({"lang": "en"}, "lang: Input should be 'EN', 'FR' or 'DE'"),
    (
        {"geo_level": "region"},
        "geo_level: Input should be 'aggregate', 'country', 'nuts1', 'nuts2', 'nuts3' or 'city'",
    ),
    (
        {"last_time_period": "two"},
        "last_time_period: Input should be a valid integer, unable to parse string as an integer",
    ),
]
"""Arguments the tool's schema refuses (the StrEnums ``Lang`` and ``GeoLevel``, an int),
with core's text for each: the argument and pydantic's message, never the input."""


@pytest.mark.anyio
@pytest.mark.parametrize(("arguments", "message"), SCHEMA_REFUSALS)
async def test_get_data_tool_refuses_an_argument_its_schema_refuses(
    respx_mock: respx.MockRouter, arguments: dict[str, Any], message: str
) -> None:
    """Core's argument middleware answers before the tool runs (ADR-0014, amendment
    2026-10-27; conventions §8), in the family's error form."""
    text = await mcp_call_text(
        server, "eurostat_get_data", {"dataset": "apro_mk_cola", **arguments}
    )
    assert text == f"error: InvalidRequestError: {message}"
    assert not respx_mock.calls, "refused before any request"


@pytest.mark.parametrize(("arguments", "message"), SCHEMA_REFUSALS)
def test_get_data_route_refuses_an_argument_its_schema_refuses(
    respx_mock: respx.MockRouter, arguments: dict[str, Any], message: str
) -> None:
    """FastAPI validates the body before the task runs and answers 422 naming the
    argument; core installs no handler of its own for it."""
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as http:
        answer = http.post("/eurostat/get_data", json={"dataset": "apro_mk_cola", **arguments})
    assert answer.status_code == 422
    argument = message.split(":", 1)[0]
    assert answer.json()["detail"][0]["loc"] == ["body", argument]
    assert not respx_mock.calls, "refused before any request"


def test_get_data_route_end_to_end(replay_fixture: ReplayFixture) -> None:
    """A mapping parameter makes the route a POST with a JSON body (ADR-0007)."""
    case = "apro_mk_cola_AT_2022_2023"
    route = replay_fixture(ENDPOINT, case)
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as http:
        answer = http.post(
            "/eurostat/get_data",
            json={
                "dataset": "apro_mk_cola",
                "filters": {"geo": "AT", "time": ["2022", "2023"]},
                "lang": "EN",
            },
        )
    assert answer.status_code == 200
    assert sent_urls(route) == [recorded_url(case)]
    assert answer.json()["meta"]["request"]["lang"] == "EN"
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


# The slices: get_series, get_latest_period, get_cross_section. Each sends one getData
# request through get_data, so meta is get_data's; the fixtures are slices recorded on
# 2026-10-27 through the same URL the task sends.

MILK = {"milkitem": "PRD", "dairyprod": "D1110D", "unit": "THS_T"}
"""apro_mk_cola's raw cows' milk delivered to dairies, in thousand tonnes."""

FARMS = {
    "statinfo": "TOTAL",
    "leg_form": "PER_NTL",
    "farmtype": "FT1",
    "so_eur": "TOTAL",
    "uaarea": "TOTAL",
    "unit": "HLD",
    "geo": "AT",
}
"""ef_m_farmleg's holdings of natural persons specialised in field crops, Austria."""


def recorded_cube(case: str) -> Cube:
    body = json.loads(load_fixture(FIXTURES / ENDPOINT / f"{case}.json").response.body)
    return Cube.model_validate(body)


def cube_order(cube: Cube) -> list[dict[str, str]]:
    """Each cell's codes, in cell order, of the cells that have a value or a status."""
    return [observation.codes for observation in cube.observations()]


def test_get_series_apro_mk_cola(replay_fixture: ReplayFixture) -> None:
    case = "apro_mk_cola_series_AT_2015_2023"
    route = replay_fixture(ENDPOINT, case)
    before = datetime.now(UTC)
    result = get_series("apro_mk_cola", {**MILK, "geo": "AT"}, since="2015", until="2023")
    after = datetime.now(UTC)
    assert sent_urls(route) == [recorded_url(case)]
    assert all(isinstance(observation, Observation) for observation in result.data)
    periods = [observation.codes["time"] for observation in result.data]
    assert periods == [str(year) for year in range(2015, 2024)]
    time_index = recorded_cube(case).dimension["time"].category.index
    assert periods == sorted(time_index, key=time_index.__getitem__), "the time index's order"
    assert {name: code for name, code in result.data[0].codes.items() if name != "time"} == {
        "freq": "A",
        **MILK,
        "geo": "AT",
    }
    assert all(
        observation.codes.keys() == result.data[0].codes.keys() for observation in result.data
    )
    assert result.data[-1].value == 3242.85
    assert result.data[-1].labels["dairyprod"] == "Raw cows' milk delivered to dairies"
    assert result.meta.source == "eurostat"
    assert result.meta.endpoint == "getData"
    assert result.meta.published_at == datetime(2026, 10, 5, 23, 0, tzinfo=CEST)
    assert result.meta.vintage == "2026-10-05T23:00:00+0200" == recorded_updated(case)
    assert result.meta.request == {
        "dataset": "apro_mk_cola",
        "filters": {**MILK, "geo": "AT"},
        "lang": "EN",
        "since_time_period": "2015",
        "until_time_period": "2023",
    }
    assert result.meta.total is None
    assert_time_between(result.meta.retrieved_at, before, after)


def test_get_series_ef_m_farmleg_every_period(replay_fixture: ReplayFixture) -> None:
    """Without since and until the series runs over every period the dataset has: the
    farm structure survey's years, irregular, each value an integer count of holdings."""
    case = "ef_m_farmleg_series_AT_PER_NTL_FT1"
    route = replay_fixture(ENDPOINT, case)
    result = get_series("ef_m_farmleg", FARMS)
    assert sent_urls(route) == [recorded_url(case)]
    assert [observation.codes["time"] for observation in result.data] == [
        "2010",
        "2013",
        "2016",
        "2020",
        "2023",
    ]
    assert all(type(observation.value) is int for observation in result.data)
    assert result.data[0].labels["leg_form"] == "Natural person"
    assert result.meta.published_at == datetime(2026, 6, 17, 23, 0, tzinfo=CEST)
    assert result.meta.vintage == recorded_updated(case)
    assert result.meta.request == {"dataset": "ef_m_farmleg", "filters": FARMS, "lang": "EN"}


def test_get_series_refuses_an_answer_of_two_series(replay_fixture: ReplayFixture) -> None:
    """Two dairy products give two series: refused after the one request, which alone
    shows it, naming the dimension to pin and its codes."""
    case = "apro_mk_cola_series_two_dairyprod"
    route = replay_fixture(ENDPOINT, case)
    with pytest.raises(InvalidRequestError) as refused:
        get_series(
            "apro_mk_cola",
            {"milkitem": "PRD", "dairyprod": ["D1110D", "D2100"], "unit": "THS_T", "geo": "AT"},
            since="2022",
            until="2023",
        )
    assert sent_urls(route) == [recorded_url(case)]
    assert str(refused.value) == (
        "the answer for apro_mk_cola spans up to 2 series, not one: pin each of these dimensions "
        "to one code in filters: dairyprod (2 codes: D1110D, D2100)"
    )


def test_get_series_refusal_lists_at_most_twenty_codes(replay_fixture: ReplayFixture) -> None:
    """crops (214 codes) and strucpro (5) left open: both named, crops' first 20 codes
    and how many more."""
    case = "apro_cpnh1_AT_2022_2023"
    route = replay_fixture(ENDPOINT, case)
    with pytest.raises(InvalidRequestError) as refused:
        get_series("apro_cpnh1", {"geo": "AT"}, since="2022", until="2023")
    assert sent_urls(route) == [recorded_url(case)]
    crops = recorded_cube(case).dimension["crops"].category.index
    first = ", ".join(sorted(crops, key=crops.__getitem__)[:20])
    assert str(refused.value) == (
        "the answer for apro_cpnh1 spans up to 1070 series, not one: pin each of these dimensions "
        f"to one code in filters: crops (214 codes: {first} and 194 more); strucpro (5 codes: "
        "AR_THS_HA, HPRD_THS_T, MAR_THS_HA, HUMD_PC, YLD_T_HA)"
    )


def test_get_series_unknown_code_is_an_empty_list(replay_fixture: ReplayFixture) -> None:
    """An empty answer is an empty list, before the one-series check: the empty cube has
    size 0 on geo."""
    case = "apro_mk_cola_series_XX"
    route = replay_fixture(ENDPOINT, case)
    result = get_series("apro_mk_cola", {**MILK, "geo": "XX"}, since="2015", until="2023")
    assert sent_urls(route) == [recorded_url(case)]
    assert result.data == []
    assert result.meta.vintage == recorded_updated(case)
    assert result.meta.request["filters"] == {**MILK, "geo": "XX"}


def test_get_latest_period_apro_mk_cola(replay_fixture: ReplayFixture) -> None:
    case = "apro_mk_cola_latest_AT"
    route = replay_fixture(ENDPOINT, case)
    before = datetime.now(UTC)
    result = get_latest_period("apro_mk_cola", {**MILK, "geo": "AT"})
    after = datetime.now(UTC)
    assert sent_urls(route) == [recorded_url(case)]
    assert len(result.data) == 1
    assert result.data[0].codes == {"freq": "A", **MILK, "geo": "AT", "time": "2025"}
    assert result.data[0].value == 3503.31
    assert result.meta.endpoint == "getData"
    assert result.meta.published_at == datetime(2026, 10, 5, 23, 0, tzinfo=CEST)
    assert result.meta.vintage == recorded_updated(case)
    assert result.meta.request == {
        "dataset": "apro_mk_cola",
        "filters": {**MILK, "geo": "AT"},
        "lang": "EN",
        "last_time_period": 1,
    }
    assert result.meta.total is None
    assert_time_between(result.meta.retrieved_at, before, after)


def test_get_latest_period_apro_cpnh1_several_series(replay_fixture: ReplayFixture) -> None:
    """One crop, strucpro left open: four series with a cell in 2026, the dataset's
    latest period, in cube order; one cell carries a status."""
    case = "apro_cpnh1_latest_AT_C1110"
    route = replay_fixture(ENDPOINT, case)
    result = get_latest_period("apro_cpnh1", {"crops": "C1110", "geo": "AT"})
    assert sent_urls(route) == [recorded_url(case)]
    assert [observation.codes for observation in result.data] == cube_order(recorded_cube(case))
    assert [observation.codes["strucpro"] for observation in result.data] == [
        "AR_THS_HA",
        "HPRD_THS_T",
        "HUMD_PC",
        "YLD_T_HA",
    ]
    assert {observation.codes["time"] for observation in result.data} == {"2026"}
    assert [observation.status for observation in result.data] == [None, None, "i", None]
    assert result.meta.published_at == datetime(2026, 9, 28, 23, 0, tzinfo=CEST)
    assert result.meta.request == {
        "dataset": "apro_cpnh1",
        "filters": {"crops": "C1110", "geo": "AT"},
        "lang": "EN",
        "last_time_period": 1,
    }


def test_get_latest_period_unknown_code_is_an_empty_list(replay_fixture: ReplayFixture) -> None:
    case = "apro_mk_cola_latest_XX"
    route = replay_fixture(ENDPOINT, case)
    result = get_latest_period("apro_mk_cola", {**MILK, "geo": "XX"})
    assert sent_urls(route) == [recorded_url(case)]
    assert result.data == []
    assert result.meta.vintage == recorded_updated(case)


def test_get_cross_section_apro_mk_cola(replay_fixture: ReplayFixture) -> None:
    """geo left out: every geo code the dataset holds for 2023, in cube order."""
    case = "apro_mk_cola_cross_section_2023"
    route = replay_fixture(ENDPOINT, case)
    before = datetime.now(UTC)
    result = get_cross_section("apro_mk_cola", "2023", MILK)
    after = datetime.now(UTC)
    assert sent_urls(route) == [recorded_url(case)]
    cube = recorded_cube(case)
    assert cube.size[cube.id.index("geo")] == 45
    assert [observation.codes for observation in result.data] == cube_order(cube)
    assert len(result.data) == 36
    assert {observation.codes["time"] for observation in result.data} == {"2023"}
    assert len({observation.codes["geo"] for observation in result.data}) == 36
    assert result.meta.endpoint == "getData"
    assert result.meta.published_at == datetime(2026, 10, 5, 23, 0, tzinfo=CEST)
    assert result.meta.vintage == recorded_updated(case)
    assert result.meta.request == {
        "dataset": "apro_mk_cola",
        "filters": {**MILK, "time": "2023"},
        "lang": "EN",
    }
    assert result.meta.total is None
    assert_time_between(result.meta.retrieved_at, before, after)


def test_get_cross_section_apro_cpnh1_one_crop(replay_fixture: ReplayFixture) -> None:
    """One crop over every geo code, strucpro left open: strucpro outer, geo inner."""
    case = "apro_cpnh1_cross_section_C1110_2024"
    route = replay_fixture(ENDPOINT, case)
    result = get_cross_section("apro_cpnh1", "2024", {"crops": "C1110"})
    assert sent_urls(route) == [recorded_url(case)]
    cube = recorded_cube(case)
    assert cube.size == [1, 1, 5, 41, 1]
    assert [observation.codes for observation in result.data] == cube_order(cube)
    assert len(result.data) == 151
    strucpro = [observation.codes["strucpro"] for observation in result.data]
    assert strucpro == sorted(strucpro, key=cube.dimension["strucpro"].category.index.__getitem__)
    assert result.meta.published_at == datetime(2026, 9, 28, 23, 0, tzinfo=CEST)
    assert result.meta.request == {
        "dataset": "apro_cpnh1",
        "filters": {"crops": "C1110", "time": "2024"},
        "lang": "EN",
    }


@pytest.mark.parametrize("period", ["", "  "])
def test_get_cross_section_refuses_an_empty_period(
    respx_mock: respx.MockRouter, period: str
) -> None:
    """Refused in the task's own terms, not as get_data's empty time filter."""
    with pytest.raises(InvalidRequestError) as refused:
        get_cross_section("apro_mk_cola", period, MILK)
    assert str(refused.value) == (
        f"period={period!r}: give one period as the dataset's time dimension prints it, "
        'e.g. "2023" or "2026-08"'
    )
    assert not respx_mock.calls, "refused before any request"


def test_get_cross_section_unknown_code_is_an_empty_list(replay_fixture: ReplayFixture) -> None:
    """The recorded empty cube of PR 4: the same URL, geo=XX and time=2023."""
    case = "unknown_code"
    route = replay_fixture(ENDPOINT, case)
    result = get_cross_section("apro_mk_cola", "2023", {"geo": "XX"})
    assert sent_urls(route) == [recorded_url(case)]
    assert result.data == []
    assert result.meta.request["filters"] == {"geo": "XX", "time": "2023"}


SLICES: list[tuple[str, Callable[..., Any], tuple[Any, ...], dict[str, Any]]] = [
    ("get_series", get_series, ("apro_mk_cola",), {"since": "2015"}),
    ("get_latest_period", get_latest_period, ("apro_mk_cola",), {}),
    ("get_cross_section", get_cross_section, ("apro_mk_cola", "2023"), {}),
]
"""Each slice with its leading arguments, for the refusals before sending."""


@pytest.mark.parametrize("time", ["time", "TIME_PERIOD"])
@pytest.mark.parametrize(
    ("name", "task", "args", "kwargs"), SLICES, ids=[name for name, *_ in SLICES]
)
def test_slices_refuse_a_time_filter(
    respx_mock: respx.MockRouter,
    time: str,
    name: str,
    task: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> None:
    """Each slice selects its periods itself; a time filter is refused before any
    request, in the task's own terms."""
    with pytest.raises(InvalidRequestError, match=rf"^filters\['{time}'\]: {name} ") as refused:
        task(*args, filters={**MILK, time: "2023"}, **kwargs)
    assert "get_data" not in str(refused.value)
    assert not respx_mock.calls, "refused before any request"


@pytest.mark.parametrize(
    ("name", "task", "args", "kwargs"), SLICES, ids=[name for name, *_ in SLICES]
)
def test_slices_refuse_a_parameter_as_a_filter(
    respx_mock: respx.MockRouter,
    name: str,
    task: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> None:
    with pytest.raises(InvalidRequestError) as refused:
        task(*args, filters={**MILK, "lastTimePeriod": "2"}, **kwargs)
    assert str(refused.value).startswith(
        "filters['lastTimePeriod']: lastTimePeriod is a parameter of the Statistics API, "
        "not a dimension; format is always JSON"
    )
    assert f"lang is an argument of {name}" in str(refused.value)
    assert not respx_mock.calls, "refused before any request"


@pytest.mark.anyio
async def test_get_series_tool_end_to_end(replay_fixture: ReplayFixture) -> None:
    case = "apro_mk_cola_series_AT_2015_2023"
    route = replay_fixture(ENDPOINT, case)
    payload = await mcp_call(
        server,
        "eurostat_get_series",
        {
            "dataset": "apro_mk_cola",
            "filters": {**MILK, "geo": "AT"},
            "since": "2015",
            "until": "2023",
        },
    )
    assert sent_urls(route) == [recorded_url(case)]
    assert [row["codes"]["time"] for row in payload["data"]] == [str(y) for y in range(2015, 2024)]
    assert "note" not in payload, "nine rows: nothing cut"
    assert payload["meta"]["endpoint"] == "getData"
    assert payload["meta"]["request"]["since_time_period"] == "2015"
    assert payload["meta"]["published_at"] == "2026-10-05T23:00:00+02:00"


@pytest.mark.anyio
async def test_get_series_tool_answers_the_refusal_as_text(replay_fixture: ReplayFixture) -> None:
    replay_fixture(ENDPOINT, "apro_mk_cola_series_two_dairyprod")
    text = await mcp_call_text(
        server,
        "eurostat_get_series",
        {
            "dataset": "apro_mk_cola",
            "filters": {
                "milkitem": "PRD",
                "dairyprod": ["D1110D", "D2100"],
                "unit": "THS_T",
                "geo": "AT",
            },
            "since": "2022",
            "until": "2023",
        },
    )
    assert text.startswith(
        "error: InvalidRequestError: the answer for apro_mk_cola spans up to 2 series"
    )


@pytest.mark.anyio
async def test_get_cross_section_tool_end_to_end(replay_fixture: ReplayFixture) -> None:
    case = "apro_cpnh1_cross_section_C1110_2024"
    route = replay_fixture(ENDPOINT, case)
    payload = await mcp_call(
        server,
        "eurostat_get_cross_section",
        {"dataset": "apro_cpnh1", "period": "2024", "filters": {"crops": "C1110"}},
    )
    assert sent_urls(route) == [recorded_url(case)]
    assert len(payload["data"]) == 151
    assert "note" not in payload, "151 rows and 38,752 bytes of rows: within the cap"
    assert payload["meta"]["request"]["filters"] == {"crops": "C1110", "time": "2024"}


def test_get_latest_period_route_end_to_end(replay_fixture: ReplayFixture) -> None:
    """A mapping parameter makes the route a POST with a JSON body (ADR-0007)."""
    case = "apro_mk_cola_latest_AT"
    route = replay_fixture(ENDPOINT, case)
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as http:
        answer = http.post(
            "/eurostat/get_latest_period",
            json={"dataset": "apro_mk_cola", "filters": {**MILK, "geo": "AT"}},
        )
    assert answer.status_code == 200
    assert sent_urls(route) == [recorded_url(case)]
    assert answer.json()["data"][0]["codes"]["time"] == "2025"
    assert answer.json()["meta"]["request"]["last_time_period"] == 1


@pytest.mark.anyio
async def test_get_latest_period_tool_cuts_a_large_slice_with_its_note(
    replay_fixture: ReplayFixture,
) -> None:
    """The latest period of ef_m_farmleg for one country, every other dimension open:
    1,810 observations, about 719 KB of rows, cut by MCP_CAPS' byte bound (the
    family's 64 KB) with the task's own note (ADR-0016)."""
    case = "ef_m_farmleg_latest_AT_HLD"
    route = replay_fixture(ENDPOINT, case)
    payload = await mcp_call(
        server,
        "eurostat_get_latest_period",
        {"dataset": "ef_m_farmleg", "filters": {"geo": "AT", "unit": "HLD"}},
    )
    assert sent_urls(route) == [recorded_url(case)]
    cap = tasks.MCP_CAPS["get_latest_period"]
    shown = len(payload["data"])
    assert 0 < shown < cap.max_rows
    assert payload["note"] == (
        f"showing {shown} of 1810 rows (cap: {cap.max_rows} rows or {cap.max_bytes} bytes); "
        "pin more dimensions in filters, one code each (geo, unit, a product), to see the rest"
    )
    assert payload["meta"]["request"]["last_time_period"] == 1
