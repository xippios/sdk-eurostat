"""Replay tests on recorded fixtures, at least one per task (conventions §10).

``/add-endpoint`` and ``/record-fixture`` add them.

The fixtures are ``tests/fixtures/get_data/<case>.json``, recorded on the main base on
2026-10-27, and its ``DS-*`` cases, recorded on the Comext base on 2026-10-28 for the
Prodcom datasets ``DS-059358`` and ``DS-059359``; each test sends exactly the recorded
URL, parameter order included. The Statistics API's asynchronous answer is not recorded
(``tests/test_client.py`` says why); its test serves the user guide's documented body.
The slices (``get_series``, ``get_latest_period``, ``get_cross_section``) each send one
getData request, so their fixtures are getData answers too: ``*_series_*``,
``*_latest_*`` and ``*_cross_section_*``, plus two of ``get_data``'s whose URL a slice
sends as well (``apro_cpnh1_AT_2022_2023``, a series refused, and ``unknown_code``, an
empty cross-section). The production tasks (``get_sold_production``,
``get_total_production``) send one getData request too: the first replays
``DS-059358_AT_10411200_2022_2023``, the request ``get_data``'s test sends, and
``DS-059358_unknown_code``, an unknown reporter; the second
``DS-059359_AT_20158000_2022_2023`` and
``DS-059359_AT_20158000_indicator_not_in_dataset``, an indicator of CXT_INDICATORS that
DS-059359 lacks, answered with an empty cube. The list tasks (``list_datasets``,
``list_codes``, ``list_products``) send nothing: their tests read the packaged files
under ``src/xippios/eurostat/reference/`` and take the expected values from them. The bulk
task ``download_dataset`` replays ``tests/fixtures/data_query/<case>.json``, the SDMX 2.1
data query recorded with ``compressed=true`` (a gzip file) and without it, on the main
base on 2026-10-27 and on the Comext base on 2026-10-28, through core's ``download``;
its refusals of an asynchronous answer and of an extraction too big replay the answers
recorded on the Comext base for ``DS-045409``.
"""

import json
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
import respx
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from xippios.core import (
    Downloaded,
    InvalidRequestError,
    NotFoundError,
    UnknownCode,
    ValidationError,
)
from xippios.core.client import cache_key
from xippios.core.testing import (
    CLOCK_SLACK,
    REDACTED,
    Fixture,
    ReplayFixture,
    assert_time_between,
    load_fixture,
    mcp_call,
    mcp_call_text,
    sent_query,
    sent_urls,
)

from xippios.eurostat import (
    api,
    download_dataset,
    get_cross_section,
    get_data,
    get_latest_period,
    get_series,
    get_sold_production,
    get_total_production,
    list_codes,
    list_datasets,
    list_products,
    params,
    tasks,
)
from xippios.eurostat._client import BASE_URL, COMEXT_BASE_URL, config
from xippios.eurostat.http import router
from xippios.eurostat.mcp import server
from xippios.eurostat.models import Code, Cube, Dataset, GeoLevel, Lang, LeafType, Observation
from xippios.eurostat.parse import parse_sdmx_csv

FIXTURES = Path(__file__).parent / "fixtures"
GUIDE = Path(__file__).parents[1] / "docs" / "upstream" / "user-guide" / "api-detailed-guidelines"
GET_DATA = "get_data"
CEST = timezone(timedelta(hours=2))


def recorded_url(case: str) -> str:
    return load_fixture(FIXTURES / GET_DATA / f"{case}.json").request.url


def recorded_updated(case: str) -> str:
    body = json.loads(load_fixture(FIXTURES / GET_DATA / f"{case}.json").response.body)
    updated: str = body["updated"]
    return updated


def test_get_data_apro_mk_cola(replay_fixture: ReplayFixture) -> None:
    case = "apro_mk_cola_AT_2022_2023"
    route = replay_fixture(GET_DATA, case)
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
    route = replay_fixture(GET_DATA, case)
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
    route = replay_fixture(GET_DATA, case)
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
    route = replay_fixture(GET_DATA, case)
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
    route = replay_fixture(GET_DATA, case)
    result = get_data("apro_mk_cola", {"geo": "XX", "time": "2023"})
    assert sent_urls(route) == [recorded_url(case)]
    assert result.data.size[result.data.id.index("geo")] == 0
    assert result.data.value == {}
    assert list(result.data.observations()) == []
    assert result.meta.vintage == recorded_updated(case)
    assert result.meta.request["filters"] == {"geo": "XX", "time": "2023"}


def test_get_data_unknown_dataset(replay_fixture: ReplayFixture) -> None:
    route = replay_fixture(GET_DATA, "unknown_dataset")
    with pytest.raises(NotFoundError, match="NO_SUCH_DATASET"):
        tasks.get_data("no_such_dataset")
    assert sent_urls(route) == [recorded_url("unknown_dataset")]


def test_get_data_unknown_dimension(replay_fixture: ReplayFixture) -> None:
    replay_fixture(GET_DATA, "unknown_dimension")
    with pytest.raises(InvalidRequestError, match="INVALID_QUERY_DIMENSION"):
        tasks.get_data("apro_mk_cola", {"nosuchdim": "AT"})


@pytest.mark.parametrize("level", [GeoLevel.COUNTRY, "country"], ids=["member", "plain"])
def test_get_data_geo_with_geo_level(replay_fixture: ReplayFixture, level: str) -> None:
    """A plain string is accepted where the enumeration is expected, and sent as it."""
    route = replay_fixture(GET_DATA, "geo_with_geo_level")
    with pytest.raises(InvalidRequestError, match="cannot be set at the same time"):
        tasks.get_data("apro_mk_cola", {"geo": "AT"}, geo_level=cast(GeoLevel, level))
    assert sent_urls(route) == [recorded_url("geo_with_geo_level")]


def test_get_data_takes_lang_as_a_plain_string(replay_fixture: ReplayFixture) -> None:
    case = "apro_mk_cola_AT_2022_2023"
    route = replay_fixture(GET_DATA, case)
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
    hand-written: the asynchronous answer of api-statistics.md. The Statistics API's first
    asynchronous answer seen is recorded and replaces this test (Johannes, 2026-10-27)."""
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
    fixture = load_fixture(FIXTURES / GET_DATA / "apro_mk_cola_AT_2022_2023.json")
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
    route = replay_fixture(GET_DATA, case)
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
    route = replay_fixture(GET_DATA, case)
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
    replay_fixture(GET_DATA, "unknown_dimension")
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as http:
        answer = http.post(
            "/eurostat/get_data", json={"dataset": "apro_mk_cola", "filters": {"nosuchdim": "AT"}}
        )
    assert answer.status_code == 422
    assert "INVALID_QUERY_DIMENSION" in answer.text


# The Comext base: a DS- dataset is requested on COMEXT_BASE_URL (prefixed-datasets.md),
# through the same client; the fixtures mirror the main base's, recorded on 2026-10-28.

PRODCOM = "DS-059358_AT_10411200_2022_2023"
FISH_OIL = {"reporter": "AT", "product": "10411200"}
"""DS-059358 (Prodcom: sold production, exports and imports) for Austria and product
10411200, fats and oils of fish or marine mammals (NACE 10.41)."""
COMEXT_STATISTICS = f"{COMEXT_BASE_URL}/statistics/1.0/data"


def test_get_data_ds_059358_on_the_comext_base(replay_fixture: ReplayFixture) -> None:
    route = replay_fixture(GET_DATA, PRODCOM)
    before = datetime.now(UTC)
    result = tasks.get_data(
        "DS-059358", FISH_OIL, since_time_period="2022", until_time_period="2023"
    )
    after = datetime.now(UTC)
    assert sent_urls(route) == [recorded_url(PRODCOM)]
    assert recorded_url(PRODCOM) == (
        "https://ec.europa.eu/eurostat/api/comext/dissemination/statistics/1.0/data/"
        "DS-059358?format=JSON&lang=EN&reporter=AT&product=10411200&sinceTimePeriod=2022"
        "&untilTimePeriod=2023"
    ), "the Comext host and path, the code as given"
    cube = result.data
    assert cube.id == ["freq", "reporter", "product", "indicators", "time"]
    assert cube.size == [1, 1, 1, 23, 2]
    assert result.meta.source == "eurostat"
    assert result.meta.endpoint == "getData"
    assert result.meta.published_at == datetime(2026, 10, 20, 11, 0, tzinfo=CEST)
    assert result.meta.published_at == cube.updated
    assert result.meta.published_at_naive is False
    assert result.meta.vintage == "2026-10-20T11:00:00+0200" == recorded_updated(PRODCOM)
    assert result.meta.request == {
        "dataset": "DS-059358",
        "filters": FISH_OIL,
        "lang": "EN",
        "since_time_period": "2022",
        "until_time_period": "2023",
    }
    assert_time_between(result.meta.retrieved_at, before, after)
    values = {(o.codes["indicators"], o.codes["time"]): o.value for o in cube.observations()}
    assert values[("QNTUNIT", "2022")] == "KG", "a unit among the measures, as printed"
    assert values[("SCQNTFLAG", "2023")] == values[("SCVALFLAG", "2023")] == ":E"
    assert {value for value in values.values() if isinstance(value, str)} == {"KG", ":E"}
    assert values[("EXPVAL", "2022")] == 349477
    assert isinstance(values[("EXPVAL", "2022")], int), "an integer stays an integer"


def test_get_data_unknown_ds_dataset(replay_fixture: ReplayFixture) -> None:
    route = replay_fixture(GET_DATA, "DS_unknown_dataset")
    with pytest.raises(NotFoundError, match=r"DS-000000 \(DATA_FLOW:ALL,1\.0\) is not available"):
        tasks.get_data("DS-000000")
    assert sent_urls(route) == [recorded_url("DS_unknown_dataset")]
    assert recorded_url("DS_unknown_dataset").startswith(f"{COMEXT_STATISTICS}/DS-000000?")


def test_get_data_ds_059358_unknown_dimension_is_too_large(replay_fixture: ReplayFixture) -> None:
    """The Comext base does not refuse a filter on a dimension the dataset lacks, as the
    main base does (fault 150 at HTTP 400): it counts the query unfiltered and refuses it
    as too large, HTTP 413 with an ``error`` array, whose fault reaches the caller."""
    route = replay_fixture(GET_DATA, "DS-059358_unknown_dimension_too_big")
    with pytest.raises(InvalidRequestError) as refused:
        tasks.get_data("DS-059358", {"geo": "AT"})
    assert sent_urls(route) == [recorded_url("DS-059358_unknown_dimension_too_big")]
    assert str(refused.value) == (
        "Eurostat refused GET /eurostat/api/comext/dissemination/statistics/1.0/data/"
        "DS-059358 as too large (HTTP 413: fault 413: EXTRACTION_TOO_BIG: The requested "
        "extraction is too big, estimated 151971120 rows, max authorised is 5000000, please "
        "change your filters to reduce the extraction size): narrow the query with fewer "
        "codes per dimension or a shorter period."
    )


def test_get_data_ds_059358_unknown_code_is_an_empty_cube(replay_fixture: ReplayFixture) -> None:
    case = "DS-059358_unknown_code"
    route = replay_fixture(GET_DATA, case)
    result = get_data(
        "DS-059358",
        {"reporter": "XX", "product": "10411200"},
        since_time_period="2022",
        until_time_period="2023",
    )
    assert sent_urls(route) == [recorded_url(case)]
    assert result.data.size[result.data.id.index("reporter")] == 0
    assert result.data.value == {}
    assert list(result.data.observations()) == []
    assert result.meta.vintage == recorded_updated(case)


@pytest.mark.anyio
async def test_get_data_ds_059358_tool_end_to_end(replay_fixture: ReplayFixture) -> None:
    route = replay_fixture(GET_DATA, PRODCOM)
    payload = await mcp_call(
        server,
        "eurostat_get_data",
        {
            "dataset": "DS-059358",
            "filters": FISH_OIL,
            "since_time_period": "2022",
            "until_time_period": "2023",
        },
    )
    assert sent_urls(route) == [recorded_url(PRODCOM)]
    assert payload["data"]["id"] == ["freq", "reporter", "product", "indicators", "time"]
    assert payload["data"]["value"]["12"] == "KG", "QNTUNIT 2022, text as printed"
    assert payload["data"]["value"]["43"] == ":E", "SCQNTFLAG 2023"
    assert payload["data"]["value"]["6"] == 349477, "EXPVAL 2022, a number"
    assert payload["meta"]["endpoint"] == "getData"
    assert payload["meta"]["vintage"] == "2026-10-20T11:00:00+0200"
    assert payload["meta"]["published_at"] == "2026-10-20T11:00:00+02:00"
    assert payload["meta"]["request"]["dataset"] == "DS-059358"


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
    body = json.loads(load_fixture(FIXTURES / GET_DATA / f"{case}.json").response.body)
    return Cube.model_validate(body)


def cube_order(cube: Cube) -> list[dict[str, str]]:
    """Each cell's codes, in cell order, of the cells that have a value or a status."""
    return [observation.codes for observation in cube.observations()]


def test_get_series_apro_mk_cola(replay_fixture: ReplayFixture) -> None:
    case = "apro_mk_cola_series_AT_2015_2023"
    route = replay_fixture(GET_DATA, case)
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
    route = replay_fixture(GET_DATA, case)
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
    route = replay_fixture(GET_DATA, case)
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
    route = replay_fixture(GET_DATA, case)
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
    route = replay_fixture(GET_DATA, case)
    result = get_series("apro_mk_cola", {**MILK, "geo": "XX"}, since="2015", until="2023")
    assert sent_urls(route) == [recorded_url(case)]
    assert result.data == []
    assert result.meta.vintage == recorded_updated(case)
    assert result.meta.request["filters"] == {**MILK, "geo": "XX"}


def test_get_latest_period_apro_mk_cola(replay_fixture: ReplayFixture) -> None:
    case = "apro_mk_cola_latest_AT"
    route = replay_fixture(GET_DATA, case)
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
    route = replay_fixture(GET_DATA, case)
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
    route = replay_fixture(GET_DATA, case)
    result = get_latest_period("apro_mk_cola", {**MILK, "geo": "XX"})
    assert sent_urls(route) == [recorded_url(case)]
    assert result.data == []
    assert result.meta.vintage == recorded_updated(case)


def test_get_cross_section_apro_mk_cola(replay_fixture: ReplayFixture) -> None:
    """geo left out: every geo code the dataset holds for 2023, in cube order."""
    case = "apro_mk_cola_cross_section_2023"
    route = replay_fixture(GET_DATA, case)
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
    route = replay_fixture(GET_DATA, case)
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
    route = replay_fixture(GET_DATA, case)
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
    route = replay_fixture(GET_DATA, case)
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
    replay_fixture(GET_DATA, "apro_mk_cola_series_two_dairyprod")
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
    route = replay_fixture(GET_DATA, case)
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
    route = replay_fixture(GET_DATA, case)
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
    route = replay_fixture(GET_DATA, case)
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


# The list tasks answer from the packaged files under src/xippios/eurostat/reference/,
# written by scripts/refresh_reference.py: no fixture and no request. The expected values
# are read from the files themselves, so a refresh changes the data and not the tests.

REFERENCE = Path(__file__).parents[1] / "src" / "xippios" / "eurostat" / "reference"


def packaged_file(name: str) -> dict[str, Any]:
    payload: dict[str, Any] = json.loads((REFERENCE / f"{name}.json").read_text(encoding="utf-8"))
    return payload


def index_record(name: str) -> dict[str, Any]:
    records = packaged_file("lists")["lists"]
    return next(record for record in records if record["name"] == name)


def fetched(name: str) -> datetime:
    return datetime.fromisoformat(packaged_file(name)["fetched"])


def test_list_datasets_answers_the_whole_table_of_contents() -> None:
    result = list_datasets()
    raw = packaged_file("toc")
    assert len(result.data) == len(raw["records"]) == index_record("toc")["count"]
    assert all(isinstance(leaf, Dataset) for leaf in result.data)
    assert [leaf.dump_upstream() for leaf in result.data[:50]] == raw["records"][:50]
    assert {leaf.type for leaf in result.data} == {LeafType.DATASET, LeafType.TABLE}
    assert all(leaf.path for leaf in result.data), "every leaf sits in a folder"


def test_list_datasets_meta_is_the_packaged_answer() -> None:
    """ADR-0022 rule 1 and D4: the file's fetched, the operation, creationDate as
    vintage and its naive time as published_at."""
    result = list_datasets()
    created = index_record("toc")["creationDate"]
    assert result.meta.source == "eurostat"
    assert result.meta.endpoint == "catalogue/toc/xml" == packaged_file("toc")["endpoint"]
    assert result.meta.retrieved_at == fetched("toc")
    assert result.meta.vintage == created
    assert re.fullmatch(r"\d{8}T\d{4}", created)
    assert result.meta.published_at == datetime.strptime(created, "%Y%m%dT%H%M")
    assert result.meta.published_at.tzinfo is None
    assert result.meta.published_at_naive is True
    assert result.meta.request == {}
    assert result.meta.total is None


def test_list_datasets_search_keeps_code_or_title_ignoring_case() -> None:
    result = list_datasets(search="MILK")
    expected = [
        record
        for record in packaged_file("toc")["records"]
        if "milk" in record["code"].casefold() or "milk" in record["title"].casefold()
    ]
    assert [leaf.dump_upstream() for leaf in result.data] == expected
    assert "apro_mk_cola" in {leaf.code for leaf in result.data}
    assert result.meta.request == {"search": "MILK"}


def test_list_datasets_search_by_code() -> None:
    result = list_datasets(search="apro_mk_cola")
    assert [leaf.code for leaf in result.data] == ["apro_mk_cola"]
    cola = result.data[0]
    assert cola.type == LeafType.DATASET
    assert cola.path.endswith(" > Milk and milk products")
    assert re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", cola.last_update), "as printed, day first"


def test_list_datasets_search_without_a_match_is_empty() -> None:
    assert list_datasets(search="no dataset is called this").data == []


def test_list_datasets_returns_a_new_list_each_call() -> None:
    first = list_datasets(search="apro_mk_cola")
    first.data.clear()
    assert list_datasets(search="apro_mk_cola").data


@pytest.mark.parametrize("name", ["GEO", "geo", "Geo"])
def test_list_codes_geo(name: str) -> None:
    result = list_codes(name)
    raw = packaged_file("geo")
    info = index_record("geo")
    assert [code.dump_upstream() for code in result.data] == raw["records"]
    assert all(isinstance(code, Code) for code in result.data)
    assert result.meta.endpoint == "sdmx/2.1/codelist/ESTAT/GEO" == raw["endpoint"]
    assert result.meta.retrieved_at == fetched("geo")
    assert result.meta.vintage == info["version"]
    assert result.meta.published_at == datetime.fromisoformat(info["LAST_UPDATED"])
    assert result.meta.published_at.utcoffset() is not None
    assert result.meta.published_at_naive is False
    assert result.meta.request == {"codelist": "GEO"}
    assert result.meta.total is None


@pytest.mark.parametrize("codelist", params.CODELISTS)
def test_list_codes_serves_every_packaged_codelist(codelist: str) -> None:
    result = list_codes(codelist.lower())
    raw = packaged_file(codelist.lower())
    origin = params.CODELISTS[codelist]
    assert raw["param"] == origin.param, "the dimension code the Statistics API takes"
    assert len(result.data) == len(raw["records"]) == index_record(codelist.lower())["count"]
    path = f"sdmx/2.1/codelist/ESTAT/{codelist}"
    assert result.meta.endpoint == (
        path if origin.base_url == BASE_URL else f"{COMEXT_BASE_URL}/{path}"
    )
    assert result.meta.vintage == index_record(codelist.lower())["version"]
    assert result.meta.published_at is not None
    assert result.meta.request == {"codelist": codelist}


def test_list_codes_serves_the_comext_codelists() -> None:
    """CXT_INDICATORS whole, CXT_PRODCOM2_TOTAL searched: the Comext base's codelists
    are served as the main base's are, their endpoint the full URL."""
    indicators = list_codes("CXT_INDICATORS")
    assert Code(code="PRODVAL", label="Sold production value, euro") in indicators.data
    assert indicators.meta.endpoint == (f"{COMEXT_BASE_URL}/sdmx/2.1/codelist/ESTAT/CXT_INDICATORS")
    assert indicators.meta.published_at == datetime.fromisoformat(
        index_record("cxt_indicators")["LAST_UPDATED"]
    )
    fertilisers = list_codes("cxt_prodcom2_total", search="Animal or vegetable fertilisers")
    assert [code.code for code in fertilisers.data] == ["20158000"]
    assert fertilisers.meta.request == {
        "codelist": "CXT_PRODCOM2_TOTAL",
        "search": "Animal or vegetable fertilisers",
    }


def test_list_codes_search_keeps_code_or_label_ignoring_case() -> None:
    result = list_codes("geo", search="austria")
    assert Code(code="AT", label="Austria") in result.data
    assert all("austria" in (code.label or "").casefold() for code in result.data)
    assert result.meta.request == {"codelist": "GEO", "search": "austria"}
    units = list_codes("unit", search="ths_t")
    assert "THS_T" in {code.code for code in units.data}


def test_list_codes_refuses_an_unknown_codelist_naming_the_closest() -> None:
    with pytest.raises(UnknownCode) as refused:
        list_codes("goe")
    assert isinstance(refused.value, InvalidRequestError)
    assert refused.value.closest[0][0] == "GEO"
    message = str(refused.value)
    day = f"{fetched('lists'):%Y-%m-%d}"
    assert message.startswith(
        f"'goe' is not a codelist in the packaged codelist list (fetched {day}). "
        "Did you mean GEO (Geopolitical entity (reporting))"
    )
    assert tasks.UNPACKAGED_CODELIST in message


def test_list_codes_refuses_a_codelist_the_package_does_not_carry() -> None:
    with pytest.raises(UnknownCode, match=r"^'nace_r2' is not a codelist") as refused:
        list_codes("nace_r2")
    assert "the dimensions of apro_cpnh1, apro_mk_cola and ef_m_farmleg" in str(refused.value)
    assert "DS-059358 and DS-059359" in str(refused.value)


def test_list_codes_names_a_comext_codelist_among_the_closest() -> None:
    with pytest.raises(UnknownCode) as refused:
        list_codes("cxt_prodcom_sold")
    assert "CXT_PRODCOM2_SOLD" in {code for code, _ in refused.value.closest}


@pytest.mark.anyio
async def test_list_datasets_tool_cuts_the_whole_list_with_its_note() -> None:
    payload = await mcp_call(server, "eurostat_list_datasets", {})
    cap = tasks.MCP_CAPS["list_datasets"]
    shown = len(payload["data"])
    total = index_record("toc")["count"]
    assert 0 < shown <= cap.max_rows
    assert payload["note"] == (
        f"showing {shown} of {total} rows (cap: {cap.max_rows} rows or {cap.max_bytes} bytes); "
        "pass search, a word of the title or a part of the code (milk, apro_mk), to see the rest"
    )
    assert payload["meta"]["vintage"] == index_record("toc")["creationDate"]
    assert payload["meta"]["published_at_naive"] is True


@pytest.mark.anyio
async def test_list_datasets_tool_end_to_end() -> None:
    payload = await mcp_call(server, "eurostat_list_datasets", {"search": "apro_mk_cola"})
    assert "note" not in payload
    assert [leaf["code"] for leaf in payload["data"]] == ["apro_mk_cola"]
    assert set(payload["data"][0]) == {
        "code",
        "type",
        "title",
        "path",
        "last_update",
        "last_modified",
        "data_start",
        "data_end",
        "values",
    }
    assert payload["meta"]["endpoint"] == "catalogue/toc/xml"
    assert payload["meta"]["request"] == {"search": "apro_mk_cola"}


@pytest.mark.anyio
async def test_list_codes_tool_cuts_geo_with_its_note() -> None:
    payload = await mcp_call(server, "eurostat_list_codes", {"codelist": "geo"})
    cap = tasks.MCP_CAPS["list_codes"]
    shown = len(payload["data"])
    total = index_record("geo")["count"]
    assert 0 < shown <= cap.max_rows < total
    assert payload["note"] == (
        f"showing {shown} of {total} rows (cap: {cap.max_rows} rows or {cap.max_bytes} bytes); "
        "pass search, a part of the code or of the label (AT, austria), to see the rest"
    )
    assert payload["meta"]["vintage"] == index_record("geo")["version"]


@pytest.mark.anyio
async def test_list_codes_tool_answers_unit_whole() -> None:
    """UNIT, the largest codelist but GEO, fits the cap: 1,000 rows within 64 KB."""
    payload = await mcp_call(server, "eurostat_list_codes", {"codelist": "UNIT"})
    assert "note" not in payload
    assert len(payload["data"]) == index_record("unit")["count"]
    assert payload["meta"]["request"] == {"codelist": "UNIT"}


@pytest.mark.anyio
async def test_list_codes_tool_answers_the_refusal_as_text() -> None:
    text = await mcp_call_text(server, "eurostat_list_codes", {"codelist": "goe"})
    assert text.startswith("error: UnknownCode: 'goe' is not a codelist in the packaged codelist")
    assert "Did you mean GEO" in text


def test_list_codes_route_end_to_end() -> None:
    """Scalar parameters make the route a GET with query parameters (ADR-0007)."""
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as http:
        answer = http.get("/eurostat/list_codes", params={"codelist": "geo", "search": "austria"})
        refused = http.get("/eurostat/list_codes", params={"codelist": "goe"})
    assert answer.status_code == 200
    assert {"code": "AT", "label": "Austria"} in answer.json()["data"]
    assert answer.json()["meta"]["vintage"] == index_record("geo")["version"]
    assert refused.status_code == 422


DATA_QUERY = "data_query"
MILK_SLICE = "apro_mk_cola_AT_THS_T_2022_2023"
MILK_SLICE_GZ = "apro_mk_cola_AT_THS_T_2022_2023_compressed"
MILK_KEY = "A...THS_T.AT"
DATA_URL = "https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data"
PRODCOM_SLICE = "DS-059358_A_AT_10411200_2022_2023"
PRODCOM_SLICE_GZ = "DS-059358_A_AT_10411200_2022_2023_compressed"
PRODCOM_KEY = "A.AT.10411200."
"""DS-059358's key: freq A, reporter AT, product 10411200, every indicator."""
COMEXT_DATA_URL = f"{COMEXT_BASE_URL}/sdmx/2.1/data"


def recorded_data(case: str) -> Fixture:
    return load_fixture(FIXTURES / DATA_QUERY / f"{case}.json")


def leftovers(directory: Path) -> list[str]:
    """What a download left in ``directory``: nothing, after a refusal."""
    return sorted(path.name for path in directory.iterdir())


def test_download_dataset_apro_mk_cola(replay_fixture: ReplayFixture, tmp_path: Path) -> None:
    route = replay_fixture(DATA_QUERY, MILK_SLICE_GZ)
    recorded = recorded_data(MILK_SLICE_GZ)
    dest = tmp_path / "milk.csv.gz"
    before = datetime.now(UTC)
    result = download_dataset("apro_mk_cola", MILK_KEY, since="2022", until="2023", dest=dest)
    after = datetime.now(UTC)
    assert sent_urls(route) == [recorded.request.url], "one exchange on the wire"
    assert recorded.request.url.endswith(
        f"/apro_mk_cola/{MILK_KEY}?format=SDMX-CSV&startPeriod=2022&endPeriod=2023&compressed=true"
    )
    downloaded = result.data
    assert isinstance(downloaded, Downloaded)
    assert downloaded.path == dest
    assert dest.read_bytes() == recorded.response.content, "the gzip file as Eurostat sent it"
    assert downloaded.bytes == len(recorded.response.content)
    assert downloaded.content_type == "application/vnd.sdmx.data+csv;version=1.0.0"
    assert downloaded.filename == "estat_apro_mk_cola_filtered_en.csv.gz"
    assert downloaded.etag is None
    assert downloaded.last_modified is None
    assert_time_between(downloaded.retrieved_at, before, after)
    assert leftovers(tmp_path) == ["milk.csv.gz"], "no temporary file left"
    meta = result.meta
    assert meta.source == "eurostat"
    assert meta.endpoint == "dataQuery"
    assert meta.retrieved_at == downloaded.retrieved_at
    assert meta.vintage == "05/10/26 23:00:00" == next(parse_sdmx_csv(dest)).last_update
    assert meta.published_at == datetime(2026, 10, 5, 23, 0)
    assert meta.published_at.tzinfo is None
    assert meta.published_at_naive is True
    assert meta.request == {
        "dataset": "apro_mk_cola",
        "key": MILK_KEY,
        "start_period": "2022",
        "end_period": "2023",
        "format": "SDMX-CSV",
        "compressed": True,
    }
    assert meta.request["key"] != REDACTED, "the SDMX series key is data (ADR-0019 decision 6)"
    assert meta.total is None


@pytest.mark.parametrize(
    ("cube", "sample"),
    [("apro_mk_cola_AT_2022_2023", MILK_SLICE), (PRODCOM, PRODCOM_SLICE)],
    ids=["main", "comext"],
)
def test_download_dataset_reads_last_update_day_first(cube: str, sample: str) -> None:
    """The recorded pairs fix the order: the JSON-stat answer's ``updated`` and the
    SDMX-CSV answer's ``LAST UPDATE`` of one dataset, recorded the same day, are one time,
    the CSV's printed day first and without the zone, on either base (apro_mk_cola's
    05/10/26, DS-059358's 20/10/26)."""
    updated = datetime.fromisoformat(recorded_updated(cube))
    printed = next(parse_sdmx_csv(FIXTURES / "files" / "sdmx-csv" / f"{sample}.csv"))
    assert datetime.strptime(printed.last_update, tasks.LAST_UPDATE) == updated.replace(tzinfo=None)


def test_download_dataset_ds_059358_on_the_comext_base(
    replay_fixture: ReplayFixture, tmp_path: Path
) -> None:
    route = replay_fixture(DATA_QUERY, PRODCOM_SLICE_GZ)
    recorded = recorded_data(PRODCOM_SLICE_GZ)
    dest = tmp_path / "fish_oil.csv.gz"
    result = download_dataset("DS-059358", PRODCOM_KEY, since="2022", until="2023", dest=dest)
    assert sent_urls(route) == [recorded.request.url], "one exchange on the wire"
    assert recorded.request.url == (
        f"{COMEXT_DATA_URL}/DS-059358/{PRODCOM_KEY}?format=SDMX-CSV&startPeriod=2022"
        "&endPeriod=2023&compressed=true"
    ), "the Comext host and path, the code as given"
    assert dest.read_bytes() == recorded.response.content, "the gzip file as Eurostat sent it"
    assert result.data.bytes == len(recorded.response.content)
    assert result.data.content_type == "application/vnd.sdmx.data+csv;version=1.0.0"
    assert result.data.filename == "estat_ds-059358_filtered_en.csv.gz"
    assert leftovers(tmp_path) == ["fish_oil.csv.gz"]
    rows = list(parse_sdmx_csv(dest))
    assert {tuple(row.dimensions) for row in rows} == {
        ("freq", "reporter", "product", "indicators")
    }
    assert all(row.attributes == {} and row.obs_flag is None for row in rows), "no attribute"
    values = {(row.dimensions["indicators"], row.time_period): row.obs_value for row in rows}
    assert values[("QNTUNIT", "2022")] == "KG", "a unit among the measures, as printed"
    assert values[("SCQNTFLAG", "2023")] == values[("SCVALFLAG", "2023")] == ":E"
    assert {value for value in values.values() if isinstance(value, str)} == {"KG", ":E"}
    assert values[("EXPVAL", "2022")] == Decimal("349477")
    meta = result.meta
    assert meta.endpoint == "dataQuery"
    assert meta.vintage == "20/10/26 11:00:00" == rows[0].last_update
    assert meta.published_at == datetime(2026, 10, 20, 11, 0)
    assert meta.published_at_naive is True
    assert meta.request == {
        "dataset": "DS-059358",
        "key": PRODCOM_KEY,
        "start_period": "2022",
        "end_period": "2023",
        "format": "SDMX-CSV",
        "compressed": True,
    }


def test_download_dataset_without_a_key_downloads_the_whole_dataset(
    replay_fixture: ReplayFixture, tmp_path: Path
) -> None:
    """The recorded answer served at the URL without a key segment (``data/{flowRef}``):
    moved, not written by hand. ``key`` is recorded as the empty string sent."""
    url = f"{DATA_URL}/apro_mk_cola?format=SDMX-CSV&compressed=true"
    route = replay_fixture(DATA_QUERY, MILK_SLICE_GZ, url=url)
    result = download_dataset("apro_mk_cola", dest=tmp_path / "all.csv.gz")
    assert sent_urls(route) == [url]
    assert result.meta.request == {
        "dataset": "apro_mk_cola",
        "key": "",
        "format": "SDMX-CSV",
        "compressed": True,
    }


def test_download_dataset_sends_last_n_observations_and_quotes_the_key(
    replay_fixture: ReplayFixture, tmp_path: Path
) -> None:
    """The recorded answer moved to the URL of another request: ``+`` and the dots stay in
    the key, ``lastNObservations`` follows ``format``."""
    key = "A.PRD.D1110D.THS_T.AT+DE"
    url = f"{DATA_URL}/apro_mk_cola/{key}?format=SDMX-CSV&lastNObservations=2&compressed=true"
    route = replay_fixture(DATA_QUERY, MILK_SLICE_GZ, url=url)
    result = download_dataset("apro_mk_cola", key, last_n_observations=2, dest=tmp_path / "f")
    assert sent_urls(route) == [url]
    assert result.meta.request["last_n_observations"] == 2


def test_download_dataset_answers_an_empty_file_without_a_release(
    respx_mock: respx.MockRouter, tmp_path: Path
) -> None:
    """NOT RECORDED: the recorded plain answer cut to its header line in memory, served
    with its recorded headers: a file without a row has no ``LAST UPDATE`` to read."""
    recorded = recorded_data(MILK_SLICE)
    header = recorded.response.content.split(b"\r\n", 1)[0] + b"\r\n"
    respx_mock.route(method="GET", host="ec.europa.eu").mock(
        return_value=httpx.Response(200, headers=recorded.response.headers, content=header)
    )
    result = download_dataset("apro_mk_cola", MILK_KEY, dest=tmp_path / "empty.csv")
    assert result.data.bytes == len(header)
    assert result.meta.vintage is None
    assert result.meta.published_at is None
    assert result.meta.published_at_naive is False


def test_download_dataset_refuses_a_last_update_it_cannot_read(
    respx_mock: respx.MockRouter, tmp_path: Path
) -> None:
    """NOT RECORDED: the recorded plain answer with its LAST UPDATE printed year first in
    memory, served with its recorded headers. The file is written and stays at ``dest``;
    the message names the form expected, never the text."""
    recorded = recorded_data(MILK_SLICE)
    body = recorded.response.content.replace(b"05/10/26 23:00:00", b"2026-10-05 23:00:00")
    respx_mock.route(method="GET", host="ec.europa.eu").mock(
        return_value=httpx.Response(200, headers=recorded.response.headers, content=body)
    )
    dest = tmp_path / "milk.csv"
    with pytest.raises(ValidationError) as refused:
        download_dataset("apro_mk_cola", MILK_KEY, dest=dest)
    assert str(refused.value) == (
        "eurostat dataQuery: the first row's LAST UPDATE is not printed as dd/mm/yy HH:MM:SS"
    )
    assert dest.read_bytes() == body, "the file stays at dest"
    assert leftovers(tmp_path) == ["milk.csv"]


@pytest.mark.parametrize("key", [".", ".."])
def test_download_dataset_refuses_a_dot_segment_key(
    respx_mock: respx.MockRouter, tmp_path: Path, key: str
) -> None:
    with pytest.raises(InvalidRequestError, match='pass key="" for every code'):
        download_dataset("apro_mk_cola", key, dest=tmp_path / "f.csv.gz")
    assert not respx_mock.calls, "refused before any request"


def test_download_dataset_refuses_a_directory_or_a_missing_one(
    respx_mock: respx.MockRouter, tmp_path: Path
) -> None:
    """Core's own text (``AsyncClient.download``), as the taxonomy's refusal."""
    with pytest.raises(InvalidRequestError) as directory:
        download_dataset("apro_mk_cola", MILK_KEY, dest=tmp_path)
    assert str(directory.value) == "dest is a directory; name the file to write"
    with pytest.raises(InvalidRequestError) as missing:
        download_dataset("apro_mk_cola", MILK_KEY, dest=tmp_path / "no" / "f.csv.gz")
    assert str(missing.value) == "dest's directory does not exist; create it first"
    assert not respx_mock.calls, "refused before any request"


ASYNCHRONOUS_SDMX = "DS-045409_asynchronous"
TOO_BIG = "DS-045409_too_big_413"


def test_download_dataset_refuses_an_asynchronous_answer(
    replay_fixture: ReplayFixture, tmp_path: Path
) -> None:
    """Recorded on the Comext base: DS-045409, the whole monthly flow, is answered with the
    envelope that queues it (``asynchronous-api.md``, "Step 1: Initial request"), at HTTP
    200 with ``application/xml``. ``classify`` refuses it from the headers alone, before
    the body reaches a file, and a file at ``dest`` stays as it was; the recording replaces
    the test of the user guide's documented body (gap row 83). It queued one extraction on
    Eurostat's side that nobody fetches (Johannes, 2026-10-28)."""
    route = replay_fixture(DATA_QUERY, ASYNCHRONOUS_SDMX)
    dest = tmp_path / "trade.csv.gz"
    dest.write_bytes(b"an earlier download")
    with pytest.raises(InvalidRequestError) as refused:
        download_dataset("DS-045409", "M.....", dest=dest)
    assert sent_urls(route) == [recorded_data(ASYNCHRONOUS_SDMX).request.url]
    assert str(refused.value) == (
        "Eurostat answered GET /eurostat/api/comext/dissemination/sdmx/2.1/data/DS-045409/"
        "M..... with application/xml, not SDMX-CSV: a data query the SDMX API will treat "
        "asynchronously is answered with an XML envelope that queues it, and this package "
        "does not poll asynchronous answers: narrow the query with fewer codes per dimension "
        "or a shorter period."
    )
    assert dest.read_bytes() == b"an earlier download", "dest untouched"
    assert leftovers(tmp_path) == ["trade.csv.gz"], "no temporary file left"


def test_download_dataset_refuses_an_extraction_too_big(
    replay_fixture: ReplayFixture, tmp_path: Path
) -> None:
    """Recorded on the Comext base: the SOAP fault ``EXTRACTION_TOO_BIG`` at HTTP 413 for
    five reporters and one partner over every product, monthly, for a year; a download
    reads an error's body for the error's text. The recording replaces the test of the
    user guide's documented body (rows 59 and 83)."""
    route = replay_fixture(DATA_QUERY, TOO_BIG)
    key = "M.AT+DE+FR+IT+NL.US..."
    with pytest.raises(InvalidRequestError) as refused:
        download_dataset("DS-045409", key, since="2023", until="2023", dest=tmp_path / "t.csv.gz")
    assert sent_urls(route) == [recorded_data(TOO_BIG).request.url]
    assert recorded_data(TOO_BIG).request.url == (
        f"{COMEXT_DATA_URL}/DS-045409/{key}?format=SDMX-CSV&startPeriod=2023&endPeriod=2023"
        "&compressed=true"
    ), "the plus signs and dots of the key as sent"
    text = str(refused.value)
    assert text.startswith(
        f"Eurostat refused GET /eurostat/api/comext/dissemination/sdmx/2.1/data/DS-045409/{key} "
        "as too large (HTTP 413: EXTRACTION_TOO_BIG: The requested extraction is too big"
    )
    assert text.endswith("narrow the query with fewer codes per dimension or a shorter period.")
    assert leftovers(tmp_path) == []


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("flow", "case", "key", "filename"),
    [
        ("apro_mk_cola", MILK_SLICE, MILK_KEY, "estat_apro_mk_cola_filtered_en.csv"),
        ("DS-059358", PRODCOM_SLICE, PRODCOM_KEY, "estat_ds-059358_filtered_en.csv"),
    ],
    ids=["main", "comext"],
)
async def test_data_query_downloads_the_plain_answer(
    replay_fixture: ReplayFixture, tmp_path: Path, flow: str, case: str, key: str, filename: str
) -> None:
    """The wrapper without ``compressed``: the plain recording, CSV as Eurostat sends it,
    on either base."""
    route = replay_fixture(DATA_QUERY, case)
    recorded = recorded_data(case)
    dest = tmp_path / "slice.csv"
    downloaded = await api.sdmx.data_query(
        flow, dest, key=key, start_period="2022", end_period="2023"
    )
    assert sent_urls(route) == [recorded.request.url]
    assert dest.read_bytes() == recorded.response.content
    assert downloaded.filename == filename
    assert [row.time_period for row in parse_sdmx_csv(dest)][:2] == ["2022", "2023"]


@pytest.mark.anyio
async def test_code_list_query_takes_the_comext_base(replay_fixture: ReplayFixture) -> None:
    """``base_url`` sends the codelist query to the Comext base. The recorded 404 of an
    unknown ``DS-`` dataset is served at that URL: moved, not written by hand; its refusal
    is ``classify``'s, as for any codelist query."""
    url = f"{COMEXT_BASE_URL}/sdmx/2.1/codelist/ESTAT/FREQ?format=JSON&lang=en"
    route = replay_fixture(GET_DATA, "DS_unknown_dataset", url=url)
    with pytest.raises(NotFoundError):
        await api.sdmx.code_list_query("ESTAT", "FREQ", lang="en", base_url=COMEXT_BASE_URL)
    assert sent_urls(route) == [url]


def test_download_dataset_is_no_tool_and_no_route() -> None:
    """A bulk task: ``BULK_TASKS`` names it, so core's adapters skip it (ADR-0019 decision
    4); the family check (``tests/test_family.py``) serves ``tasks.__all__`` minus it."""
    assert "download_dataset" in tasks.__all__
    assert {"download_dataset"} == set(tasks.BULK_TASKS)
    paths = {route.path for route in router.routes if isinstance(route, APIRoute)}
    assert "/eurostat/download_dataset" not in paths
    assert "/eurostat/get_data" in paths
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as http:
        assert http.post("/eurostat/download_dataset", json={}).status_code == 404
        assert http.get("/eurostat/download_dataset").status_code == 404


@pytest.mark.anyio
async def test_download_dataset_is_no_mcp_tool(respx_mock: respx.MockRouter) -> None:
    names = {tool.name for tool in await server.list_tools()}
    assert "eurostat_download_dataset" not in names
    assert "eurostat_get_data" in names
    with pytest.raises(AssertionError, match="Unknown tool: eurostat_download_dataset"):
        await mcp_call(server, "eurostat_download_dataset", {"dataset": "apro_mk_cola"})
    assert not respx_mock.calls


# list_products: the packaged CXT_PRODCOM2_SOLD, as list_codes serves it; no request.

PRODUCTS = "cxt_prodcom2_sold"
PRODUCTS_URL = f"{COMEXT_BASE_URL}/sdmx/2.1/codelist/ESTAT/CXT_PRODCOM2_SOLD"
EIGHT_CHARACTER_CODE = re.compile(r'``"?(\d{4}[0-9A-Z]{4})"?``')
"""A PRODCOM code as a docstring names it, ``10412100`` or ``"10412100"``."""


def test_list_products_answers_the_whole_packaged_list(respx_mock: respx.MockRouter) -> None:
    """ADR-0022 rule 1: the file's fetched, the codelist's full URL on the Comext base,
    its version as vintage and its LAST_UPDATED, zoned, as published_at."""
    result = list_products()
    raw = packaged_file(PRODUCTS)
    info = index_record(PRODUCTS)
    assert [code.dump_upstream() for code in result.data] == raw["records"]
    assert len(result.data) == info["count"]
    assert all(isinstance(code, Code) for code in result.data)
    assert result.meta.source == "eurostat"
    assert result.meta.endpoint == PRODUCTS_URL == raw["endpoint"]
    assert result.meta.retrieved_at == fetched(PRODUCTS)
    assert result.meta.vintage == info["version"]
    assert result.meta.published_at == datetime.fromisoformat(info["LAST_UPDATED"])
    assert result.meta.published_at.utcoffset() is not None
    assert result.meta.published_at_naive is False
    assert result.meta.request == {}
    assert result.meta.total is None
    assert not respx_mock.calls, "no request"


def test_list_products_search_keeps_code_or_label_ignoring_case() -> None:
    result = list_products(search="SOYA")
    expected = [
        record
        for record in packaged_file(PRODUCTS)["records"]
        if "soya" in record["code"].casefold() or "soya" in (record["label"] or "").casefold()
    ]
    assert [code.dump_upstream() for code in result.data] == expected
    assert "10412100" in {code.code for code in result.data}, "crude soya-bean oil"
    assert result.meta.request == {"search": "SOYA"}
    oils = list_products(search="1041").data
    assert "10411200" in {code.code for code in oils}
    assert all("1041" in code.code or "1041" in (code.label or "") for code in oils)


def test_list_products_returns_a_new_list_each_call() -> None:
    first = list_products(search="1041")
    first.data.clear()
    assert list_products(search="1041").data


@pytest.mark.parametrize(
    ("task", "codelist"),
    [
        (tasks.list_products_async, "cxt_prodcom2_sold"),
        (tasks.get_sold_production_async, "cxt_prodcom2_sold"),
        (tasks.get_total_production_async, "cxt_prodcom2_total"),
    ],
)
def test_production_docstrings_name_packaged_products(
    task: Callable[..., Any], codelist: str
) -> None:
    """Every product code a docstring names is in the packaged list it points to, so the
    examples an agent reads are real codes; a refresh that drops one fails here."""
    named = EIGHT_CHARACTER_CODE.findall(task.__doc__ or "")
    assert named
    known = {record["code"] for record in packaged_file(codelist)["records"]}
    assert set(named) <= known, sorted(set(named) - known)


@pytest.mark.anyio
async def test_list_products_tool_cuts_the_list_with_its_note() -> None:
    payload = await mcp_call(server, "eurostat_list_products", {})
    cap = tasks.MCP_CAPS["list_products"]
    shown = len(payload["data"])
    total = index_record(PRODUCTS)["count"]
    assert 0 < shown <= cap.max_rows < total
    assert payload["note"] == (
        f"showing {shown} of {total} rows (cap: {cap.max_rows} rows or {cap.max_bytes} bytes); "
        "pass search, a part of the code or of the label (1041, soya, oilcake), to see the rest"
    )
    assert payload["meta"]["endpoint"] == PRODUCTS_URL
    assert payload["meta"]["vintage"] == index_record(PRODUCTS)["version"]


@pytest.mark.anyio
async def test_list_products_tool_answers_a_nace_class_whole() -> None:
    payload = await mcp_call(server, "eurostat_list_products", {"search": "1041"})
    assert "note" not in payload
    assert payload["data"] == [code.model_dump() for code in list_products(search="1041").data]
    assert payload["meta"]["request"] == {"search": "1041"}


# The production tasks: one getData request each on the Comext base, through get_data,
# so meta is get_data's. get_sold_production sends the request PR 3 recorded for
# get_data; get_total_production's fixture was recorded with it on 2026-10-28.

TOTAL = "DS-059359_AT_20158000_2022_2023"
FERTILISERS = "20158000"
"""CXT_PRODCOM2_TOTAL's animal or vegetable fertilisers."""


def test_get_sold_production_sends_get_data_s_request(replay_fixture: ReplayFixture) -> None:
    route = replay_fixture(GET_DATA, PRODCOM)
    before = datetime.now(UTC)
    result = get_sold_production("10411200", reporters=["AT"], since="2022", until="2023")
    after = datetime.now(UTC)
    assert sent_urls(route) == [recorded_url(PRODCOM)]
    assert sent_urls(route)[0].startswith(f"{COMEXT_STATISTICS}/DS-059358?"), "the Comext host"
    assert sent_query(route) == {
        "format": "JSON",
        "lang": "EN",
        "reporter": "AT",
        "product": "10411200",
        "sinceTimePeriod": "2022",
        "untilTimePeriod": "2023",
    }
    assert all(isinstance(observation, Observation) for observation in result.data)
    assert [observation.codes for observation in result.data] == cube_order(
        recorded_cube(PRODCOM)
    ), "cube order"
    assert {observation.codes["reporter"] for observation in result.data} == {"AT"}
    assert {observation.codes["product"] for observation in result.data} == {"10411200"}
    values = {(o.codes["indicators"], o.codes["time"]): o.value for o in result.data}
    assert values[("QNTUNIT", "2022")] == "KG", "a unit among the measures, as printed"
    assert values[("SCQNTFLAG", "2023")] == ":E", "a flag, as printed"
    assert values[("EXPVAL", "2022")] == 349477
    assert result.data[0].labels["product"] == (
        "Fats and oils and their fractions of fish or marine mammals (excluding chemically "
        "modified)"
    )
    assert result.meta.source == "eurostat"
    assert result.meta.endpoint == "getData"
    assert result.meta.published_at == datetime(2026, 10, 20, 11, 0, tzinfo=CEST)
    assert result.meta.published_at_naive is False
    assert result.meta.vintage == "2026-10-20T11:00:00+0200" == recorded_updated(PRODCOM)
    assert result.meta.request == {
        "dataset": "DS-059358",
        "filters": {"reporter": ["AT"], "product": "10411200"},
        "lang": "EN",
        "since_time_period": "2022",
        "until_time_period": "2023",
    }
    assert result.meta.total is None
    assert_time_between(result.meta.retrieved_at, before, after)


def test_get_sold_production_takes_a_plain_string_as_one_reporter(
    replay_fixture: ReplayFixture,
) -> None:
    route = replay_fixture(GET_DATA, PRODCOM)
    result = get_sold_production("10411200", reporters="AT", since="2022", until="2023")
    assert sent_urls(route) == [recorded_url(PRODCOM)]
    assert result.meta.request["filters"] == {"reporter": ["AT"], "product": "10411200"}


def test_get_sold_production_sends_indicators_and_leaves_reporter_out(
    replay_fixture: ReplayFixture,
) -> None:
    """NOT RECORDED: this request was never sent upstream. What is sent with indicators
    and without reporters: ``indicators`` once per code, after ``product``, and no
    ``reporter``. The recorded answer of another request (``DS-059358_AT_10411200_2022_
    2023``, every indicator for AT) is served at this URL, moved, not written by hand;
    the answer is not checked, only the request and its record in ``meta.request``."""
    url = (
        f"{COMEXT_STATISTICS}/DS-059358?format=JSON&lang=EN&product=10411200"
        "&indicators=PRODVAL&indicators=QNTUNIT&sinceTimePeriod=2022"
    )
    route = replay_fixture(GET_DATA, PRODCOM, url=url)
    result = get_sold_production("10411200", since="2022", indicators=["PRODVAL", "QNTUNIT"])
    assert sent_urls(route) == [url]
    assert result.meta.request == {
        "dataset": "DS-059358",
        "filters": {"product": "10411200", "indicators": ["PRODVAL", "QNTUNIT"]},
        "lang": "EN",
        "since_time_period": "2022",
    }


def test_get_sold_production_unknown_reporter_is_an_empty_list(
    replay_fixture: ReplayFixture,
) -> None:
    """A reporter is sent as given: no list of reporters is packaged, and Eurostat
    answers one the dataset lacks with an empty cube (recorded for ``XX``)."""
    case = "DS-059358_unknown_code"
    route = replay_fixture(GET_DATA, case)
    result = get_sold_production("10411200", reporters=["XX"], since="2022", until="2023")
    assert sent_urls(route) == [recorded_url(case)]
    assert result.data == []
    assert result.meta.vintage == recorded_updated(case)


def test_get_sold_production_refuses_an_unknown_product_naming_the_closest(
    respx_mock: respx.MockRouter,
) -> None:
    with pytest.raises(UnknownCode) as refused:
        get_sold_production("1041120", reporters=["AT"])
    assert isinstance(refused.value, InvalidRequestError)
    assert refused.value.param == "product"
    assert refused.value.list_name == "CXT_PRODCOM2_SOLD"
    assert "10411200" in {code for code, _ in refused.value.closest}
    message = str(refused.value)
    day = f"{fetched(PRODUCTS):%Y-%m-%d}"
    assert message.startswith(
        f"'1041120' is not a product in the packaged CXT_PRODCOM2_SOLD list (fetched {day}). "
        "Did you mean "
    )
    assert "10411200 (Fats and oils and their fractions of fish or marine mammals" in message
    assert "list_products lists them." in message
    assert not respx_mock.calls, "refused before any request"


def test_get_total_production_refuses_a_product_its_list_lacks(
    respx_mock: respx.MockRouter,
) -> None:
    """DS-059359's products are CXT_PRODCOM2_TOTAL's, a part of the sold list's: a sold
    product outside it, crude soya-bean oil, is refused before any request, naming
    list_codes and the task that serves it."""
    total = {record["code"] for record in packaged_file("cxt_prodcom2_total")["records"]}
    sold = {record["code"] for record in packaged_file(PRODUCTS)["records"]}
    assert "10412100" in sold - total
    with pytest.raises(UnknownCode) as refused:
        get_total_production("10412100")
    assert refused.value.list_name == "CXT_PRODCOM2_TOTAL"
    message = str(refused.value)
    assert 'list_codes("cxt_prodcom2_total") lists them.' in message
    assert (
        "10412100 is a product of DS-059358 (sold production, exports and imports): "
        "get_sold_production serves it."
    ) in message
    assert not respx_mock.calls


def test_get_sold_production_names_the_total_production_task_for_its_product(
    respx_mock: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other way round: every product of DS-059359 is in the sold list today, so the
    sold list is emptied by a monkeypatch to show the refusal naming get_total_production."""
    labels = tasks._labels
    monkeypatch.setattr(tasks, "_labels", lambda name: {} if name == PRODUCTS else labels(name))
    with pytest.raises(UnknownCode) as refused:
        get_sold_production(FERTILISERS)
    assert (
        f"{FERTILISERS} is a product of DS-059359 (total production): "
        "get_total_production serves it."
    ) in str(refused.value)
    assert not respx_mock.calls


@pytest.mark.parametrize(
    ("task", "product", "indicator"),
    [
        (get_sold_production, "10411200", "PRODVAL"),
        (get_total_production, FERTILISERS, "APRODQNT"),
    ],
)
def test_production_refuses_an_unknown_indicator(
    respx_mock: respx.MockRouter, task: Callable[..., Any], product: str, indicator: str
) -> None:
    """An indicator of the dataset passes, one CXT_INDICATORS lacks is refused."""
    with pytest.raises(UnknownCode) as refused:
        task(product, indicators=[indicator, "PRODVALUE"])
    assert refused.value.param == "indicator"
    assert refused.value.list_name == "CXT_INDICATORS"
    assert "PRODVAL" in {code for code, _ in refused.value.closest}
    assert str(refused.value).startswith(
        "'PRODVALUE' is not an indicator in the packaged CXT_INDICATORS list"
    )
    assert not respx_mock.calls


@pytest.mark.parametrize(
    ("argument", "every"), [("reporters", "reporter"), ("indicators", "indicator")]
)
def test_production_refuses_an_empty_list(
    respx_mock: respx.MockRouter, argument: str, every: str
) -> None:
    empty: dict[str, Any] = {argument: []}
    with pytest.raises(InvalidRequestError) as refused:
        get_sold_production("10411200", **empty)
    assert str(refused.value) == (
        f"{argument} lists no code: give one code or several, or leave {argument} out for "
        f"every {every}"
    )
    assert not respx_mock.calls


def test_get_total_production_ds_059359(replay_fixture: ReplayFixture) -> None:
    route = replay_fixture(GET_DATA, TOTAL)
    before = datetime.now(UTC)
    result = get_total_production(FERTILISERS, reporters=["AT"], since="2022", until="2023")
    after = datetime.now(UTC)
    assert sent_urls(route) == [recorded_url(TOTAL)]
    assert recorded_url(TOTAL) == (
        f"{COMEXT_STATISTICS}/DS-059359?format=JSON&lang=EN&reporter=AT&product=20158000"
        "&sinceTimePeriod=2022&untilTimePeriod=2023"
    ), "the Comext host and path"
    assert sent_query(route)["product"] == FERTILISERS
    cube = recorded_cube(TOTAL)
    assert cube.id == ["freq", "reporter", "product", "indicators", "time"]
    assert [observation.codes for observation in result.data] == cube_order(cube)
    values = {(o.codes["indicators"], o.codes["time"]): o.value for o in result.data}
    assert set(values) == {
        (indicator, year) for indicator in ("APRODQNT", "QNTUNIT") for year in ("2022", "2023")
    }
    assert values[("QNTUNIT", "2023")] == "KG", "the unit, as printed"
    assert all(isinstance(values[("APRODQNT", year)], int) for year in ("2022", "2023"))
    assert result.data[0].labels["indicators"] == "Actual production quantity"
    assert result.meta.endpoint == "getData"
    assert result.meta.published_at == datetime(2026, 10, 20, 11, 0, tzinfo=CEST)
    assert result.meta.vintage == recorded_updated(TOTAL)
    assert result.meta.request == {
        "dataset": "DS-059359",
        "filters": {"reporter": ["AT"], "product": FERTILISERS},
        "lang": "EN",
        "since_time_period": "2022",
        "until_time_period": "2023",
    }
    assert_time_between(result.meta.retrieved_at, before, after)


def test_get_total_production_indicator_the_dataset_lacks_is_an_empty_list(
    replay_fixture: ReplayFixture,
) -> None:
    """The check is against the whole CXT_INDICATORS list: PRODVAL, DS-059358's sold
    production value, is in it but not in DS-059359, so it is sent, and Eurostat answers
    HTTP 200 with an empty cube, no code on ``indicators`` (recorded 2026-10-28)."""
    case = "DS-059359_AT_20158000_indicator_not_in_dataset"
    indicators = {record["code"] for record in packaged_file("cxt_indicators")["records"]}
    served = recorded_cube(TOTAL).dimension["indicators"].category.index
    assert "PRODVAL" in indicators - set(served)
    route = replay_fixture(GET_DATA, case)
    result = get_total_production(
        FERTILISERS, reporters=["AT"], since="2022", until="2023", indicators=["PRODVAL"]
    )
    assert sent_urls(route) == [recorded_url(case)]
    assert sent_query(route)["indicators"] == "PRODVAL"
    assert recorded_cube(case).size[recorded_cube(case).id.index("indicators")] == 0
    assert result.data == []
    assert result.meta.request["filters"] == {
        "reporter": ["AT"],
        "product": FERTILISERS,
        "indicators": ["PRODVAL"],
    }
    assert result.meta.vintage == recorded_updated(case)


@pytest.mark.anyio
async def test_get_sold_production_tool_end_to_end(replay_fixture: ReplayFixture) -> None:
    route = replay_fixture(GET_DATA, PRODCOM)
    payload = await mcp_call(
        server,
        "eurostat_get_sold_production",
        {"product": "10411200", "reporters": ["AT"], "since": "2022", "until": "2023"},
    )
    assert sent_urls(route) == [recorded_url(PRODCOM)]
    assert "note" not in payload, "22 rows: nothing cut"
    assert len(payload["data"]) == 22
    units = {row["value"] for row in payload["data"] if row["codes"]["indicators"] == "QNTUNIT"}
    assert units == {"KG"}
    assert payload["meta"]["endpoint"] == "getData"
    assert payload["meta"]["request"]["filters"] == {"reporter": ["AT"], "product": "10411200"}
    assert payload["meta"]["published_at"] == "2026-10-20T11:00:00+02:00"


@pytest.mark.anyio
async def test_get_total_production_tool_end_to_end(replay_fixture: ReplayFixture) -> None:
    route = replay_fixture(GET_DATA, TOTAL)
    payload = await mcp_call(
        server,
        "eurostat_get_total_production",
        {"product": FERTILISERS, "reporters": ["AT"], "since": "2022", "until": "2023"},
    )
    assert sent_urls(route) == [recorded_url(TOTAL)]
    assert [row["codes"]["indicators"] for row in payload["data"]] == [
        "APRODQNT",
        "APRODQNT",
        "QNTUNIT",
        "QNTUNIT",
    ]
    assert payload["meta"]["request"]["dataset"] == "DS-059359"


@pytest.mark.anyio
async def test_get_sold_production_tool_answers_the_refusal_as_text() -> None:
    text = await mcp_call_text(server, "eurostat_get_sold_production", {"product": "1041120"})
    assert text.startswith(
        "error: UnknownCode: '1041120' is not a product in the packaged CXT_PRODCOM2_SOLD list"
    )


def test_get_sold_production_route_end_to_end(replay_fixture: ReplayFixture) -> None:
    """A list parameter makes the route a POST with a JSON body (ADR-0007)."""
    route = replay_fixture(GET_DATA, PRODCOM)
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as http:
        answer = http.post(
            "/eurostat/get_sold_production",
            json={"product": "10411200", "reporters": ["AT"], "since": "2022", "until": "2023"},
        )
        refused = http.post("/eurostat/get_sold_production", json={"product": "1041120"})
    assert answer.status_code == 200
    assert sent_urls(route) == [recorded_url(PRODCOM)]
    assert len(answer.json()["data"]) == 22
    assert refused.status_code == 422
