"""Replay tests on recorded fixtures, at least one per task (conventions §10).

``/add-endpoint`` and ``/record-fixture`` add them.

The fixtures are ``tests/fixtures/get_data/<case>.json``, recorded on the main base, and
its ``DS-*`` cases, recorded on the Comext base, each with its day in ``recorded_at``;
each test sends exactly the recorded URL, parameter order included. The user guide's
documented asynchronous ``warning``, which Eurostat answers in another shape
(``docs/upstream/OBSERVED.md``, "The asynchronous answer comes as an `error` array"), keeps
a test that serves its documented body. The list tasks (``list_datasets``, ``list_codes``) send
nothing: their tests read the packaged files under ``src/xippios/eurostat/reference/``
and take the expected values from them. The bulk task ``download_dataset`` replays
``tests/fixtures/data_query/<case>.json``, the SDMX 2.1 data query recorded with
``compressed=true`` (a gzip file) and without it, on the main base and on the Comext base,
through core's ``download``; the refusals of an
asynchronous answer and of an extraction too big replay the answers
recorded on the Comext base for ``DS-045409``.

The package serves the four tasks that the boundary of a source package leaves it
(sdk-core ``docs/conventions.md`` §14, sentence 4; sdk-core ADR-0060, decision 8): the
slices, the production and trade tasks and the lists cut from one codelist left in
0.4.0, and ``get_data``, ``download_dataset`` and ``list_codes`` take the same datasets,
codes and codelists.
"""

import importlib.util
import inspect
import json
import re
from datetime import UTC, date, datetime, timedelta, timezone
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
    QueryTooLarge,
    UnknownCode,
    ValidationError,
)
from xippios.core.client import Answer, cache_key
from xippios.core.testing import (
    CLOCK_SLACK,
    REDACTED,
    Fixture,
    ReplayFixture,
    assert_time_between,
    load_fixture,
    mcp_call,
    mcp_call_text,
    sent_urls,
)

import xippios.eurostat
from xippios.eurostat import (
    api,
    download_dataset,
    get_data,
    list_codes,
    list_datasets,
    models,
    params,
    tasks,
)
from xippios.eurostat._client import BASE_URL, COMEXT_BASE_URL, config
from xippios.eurostat.http import router
from xippios.eurostat.mcp import server
from xippios.eurostat.models import (
    Code,
    Cube,
    Dataset,
    GeoLevel,
    Lang,
    LeafType,
)
from xippios.eurostat.parse import parse_sdmx_csv

FIXTURES = Path(__file__).parent / "fixtures"
GUIDE = Path(__file__).parents[1] / "docs" / "upstream" / "user-guide" / "api-detailed-guidelines"
GET_DATA = "get_data"
CEST = timezone(timedelta(hours=2))
UNSENT = "Nothing was sent."
"""The sentence of every refusal before a request (conventions §5)."""


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
    result = tasks.get_data("apro_mk_cola", filters={"geo": "AT", "time": ["2022", "2023"]})
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
        "dataset_code": "apro_mk_cola",
        "filters": {"geo": "AT", "time": ["2022", "2023"]},
        "lang": "EN",
    }
    assert result.meta.names == {"geo": {"AT": label("geo", "AT")}}, "time names no code"
    assert result.meta.total is None
    assert result.meta.tenant is None
    assert_time_between(result.meta.retrieved_at, before, after)


def test_get_data_answers_a_repeated_request_from_the_cache(replay_fixture: ReplayFixture) -> None:
    """The same request twice is one request on the wire: the client's cache answers the
    second, whose ``meta.retrieved_at`` is the time the first answer was stored
    (conventions §4; sdk-core ADR-0037 decision 5), within the readings around the first call. The
    testing plugin clears the cache around each test, so the first call is a miss."""
    case = "apro_mk_cola_AT_2022_2023"
    route = replay_fixture(GET_DATA, case)
    filters = {"geo": "AT", "time": ["2022", "2023"]}
    before = datetime.now(UTC)
    first = tasks.get_data("apro_mk_cola", filters=filters)
    after = datetime.now(UTC)
    second = tasks.get_data("apro_mk_cola", filters=filters)
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
        "apro_cpnh1", filters={"geo": "AT"}, since_time_period="2022", until_time_period="2023"
    )
    assert sent_urls(route) == [recorded_url(case)]
    assert result.data.id == ["freq", "crops", "strucpro", "geo", "time"]
    assert result.data.dimension["time"].category.index == {"2022": 0, "2023": 1}
    assert result.meta.published_at == datetime(2026, 9, 28, 23, 0, tzinfo=CEST)
    assert result.meta.vintage == "2026-09-28T23:00:00+0200" == recorded_updated(case)
    assert result.meta.request == {
        "dataset_code": "apro_cpnh1",
        "filters": {"geo": "AT"},
        "lang": "EN",
        "since_time_period": "2022",
        "until_time_period": "2023",
    }


def test_get_data_ef_m_farmleg_last_periods(replay_fixture: ReplayFixture) -> None:
    case = "ef_m_farmleg_AT_HLD_last_2"
    route = replay_fixture(GET_DATA, case)
    result = tasks.get_data(
        "ef_m_farmleg", filters={"geo": "AT", "unit": "HLD"}, last_time_period=2
    )
    assert sent_urls(route) == [recorded_url(case)]
    assert result.data.id[-2:] == ["geo", "time"]
    assert result.data.dimension["unit"].category.label == {"HLD": "Holding"}
    assert result.data.dimension["time"].category.index == {"2020": 0, "2023": 1}
    assert result.meta.published_at == datetime(2026, 6, 17, 23, 0, tzinfo=CEST)
    assert result.meta.vintage == "2026-06-17T23:00:00+0200" == recorded_updated(case)
    assert result.meta.request == {
        "dataset_code": "ef_m_farmleg",
        "filters": {"geo": "AT", "unit": "HLD"},
        "lang": "EN",
        "last_time_period": 2,
    }
    assert result.meta.names == {
        "geo": {"AT": label("geo", "AT")},
        "unit": {"HLD": label("unit", "HLD")},
    }


def label(codelist: str, code: str) -> str:
    """The label of ``code`` in the packaged ``codelist``, as its file holds it."""
    return str(
        next(
            record["label"]
            for record in packaged_file(codelist)["records"]
            if record["code"] == code
        )
    )


def test_get_data_refuses_a_code_its_codelist_lacks_before_sending(
    respx_mock: respx.MockRouter,
) -> None:
    """The call of the recorded empty cube ``unknown_code`` (``geo=XX``): GEO,
    the one packaged codelist that feeds the main base's ``geo``, lacks ``XX``, so the call
    is refused before its request by core's check of a packaged list, saying that nothing
    was sent (conventions §5; the maintainer's decision of 2026-11-27 on
    https://github.com/xippios/sdk-eurostat/issues/82). The recording stays the evidence of
    what Eurostat answers such a code."""
    assert "&geo=XX&time=2023" in recorded_url("unknown_code")
    with pytest.raises(UnknownCode) as refused:
        get_data("apro_mk_cola", filters={"geo": "XX", "time": "2023"})
    assert (refused.value.param, refused.value.value, refused.value.list_name) == (
        "geo",
        "XX",
        "GEO",
    )
    message = str(refused.value)
    assert message.startswith(
        f"'XX' is not a geo in the packaged GEO list (fetched {fetched('geo'):%Y-%m-%d}). {UNSENT} "
    )
    assert tasks.UNKNOWN_FILTER_CODE in message
    assert not respx_mock.calls, "refused before any request"


def test_get_data_ds_059358_refuses_a_reporter_its_codelist_lacks(
    respx_mock: respx.MockRouter,
) -> None:
    """The call of the recorded empty cube ``DS-059358_unknown_code`` (``reporter=XX``): on
    the Comext base CXT_FREE_ISO is the one packaged codelist that feeds
    ``reporter``, so ``XX`` is refused before the request, and ``product``, which three
    codelists feed, is not checked."""
    assert "&reporter=XX&product=10411200&" in recorded_url("DS-059358_unknown_code")
    with pytest.raises(UnknownCode) as refused:
        get_data(
            "DS-059358",
            filters={"reporter": "XX", "product": "10411200"},
            since_time_period="2022",
            until_time_period="2023",
        )
    assert str(refused.value).startswith(
        "'XX' is not a reporter in the packaged CXT_FREE_ISO list (fetched "
        f"{fetched('cxt_free_iso'):%Y-%m-%d}). {UNSENT} "
    )
    assert not respx_mock.calls, "refused before any request"


@pytest.mark.parametrize(
    ("filters", "refused"),
    [
        ({"geo": ["AT", "XX"]}, ("geo", "XX")),
        ({"geo": "XX", "unit": "NO_SUCH_UNIT"}, ("geo", "XX")),
        ({"unit": "NO_SUCH_UNIT", "geo": "XX"}, ("unit", "NO_SUCH_UNIT")),
        ({"time": "2023", "MILKITEM": "NO_SUCH_ITEM"}, ("MILKITEM", "NO_SUCH_ITEM")),
    ],
    ids=["a-list", "geo-first", "unit-first", "a-key-in-capitals"],
)
def test_get_data_refuses_the_first_code_that_a_codelist_lacks(
    respx_mock: respx.MockRouter, filters: dict[str, Any], refused: tuple[str, str]
) -> None:
    """One refusal names the first problem it finds, in the caller's order: the first key
    whose code its codelist lacks, and in a list its first such code (sdk-core ADR-0061,
    decision 7). A dimension code is compared without case, as the Statistics API takes it
    ("DIMENSION_CODE and VALUE are case-insensitive", api-statistics.md), and named as the
    caller wrote it."""
    with pytest.raises(UnknownCode) as error:
        get_data("apro_mk_cola", filters=filters)
    assert (error.value.param, error.value.value) == refused
    assert not respx_mock.calls, "refused before any request"


def test_get_data_sends_a_checked_code_as_given(replay_fixture: ReplayFixture) -> None:
    """A code is compared with its codelist without case, as the Statistics API compares it,
    and sent, recorded in ``meta.request`` and named in ``meta.names`` as the caller gave it
    (conventions §5; sdk-core ADR-0067, decision 2). NOT RECORDED: the recorded answer to
    ``geo=AT`` served at the URL of ``GEO=at``, which Eurostat answers alike, since
    "DIMENSION_CODE and VALUE are case-insensitive" (api-statistics.md) (conventions §10,
    kind 3)."""
    url = recorded_url("apro_mk_cola_AT_2022_2023").replace("&geo=AT&", "&GEO=at&")
    route = replay_fixture(GET_DATA, "apro_mk_cola_AT_2022_2023", url=url)
    result = get_data("apro_mk_cola", filters={"GEO": "at", "time": ["2022", "2023"]})
    assert sent_urls(route) == [url]
    assert result.meta.request["filters"] == {"GEO": "at", "time": ["2022", "2023"]}
    assert result.meta.names == {"GEO": {"at": label("geo", "AT")}}


def test_get_data_checks_the_dimensions_that_one_codelist_of_its_base_feeds() -> None:
    """The keys checked before the request, by the base that serves the dataset: the twelve
    codelists of the main base, one for each of its dimensions, and of the Comext base
    ``reporter``, ``flow`` and ``indicators``. ``product``, which CXT_PRODCOM2_SOLD,
    CXT_PRODCOM2_TOTAL and CXT_NC feed, and ``partner``, the ``param`` of no packaged list,
    go unchecked, and so does a key of one base on a dataset of the other, ``freq`` on a
    ``DS-`` dataset among them, whose CXT_FREQ is not packaged (conventions §5: "A code
    sent under a coding system the packaged list does not hold goes unchecked")."""
    main = {
        origin.param: codelist
        for codelist, origin in params.CODELISTS.items()
        if origin.base_url == BASE_URL
    }
    assert len(main) == 12
    checked = tasks.CHECKED_FILTERS
    assert checked == {
        BASE_URL: main,
        COMEXT_BASE_URL: {
            "indicators": "CXT_INDICATORS",
            "reporter": "CXT_FREE_ISO",
            "flow": "CXT_EU_FLUX",
        },
    }


def test_get_data_sends_a_product_unchecked(replay_fixture: ReplayFixture) -> None:
    """``product`` is the ``param`` of three packaged codelists, so its code is sent
    unchecked, and a cube without a cell answers it with ``NotFoundError``, after the
    request. NOT RECORDED: the recorded empty cube of ``DS-059358_unknown_code`` served at
    the URL of an unlisted product with the reporter AT, which Eurostat answers alike, since
    it answers a code that matches nothing with an empty cube, as that recording holds for
    ``reporter=XX`` (conventions §10, kind 3)."""
    url = recorded_url("DS-059358_unknown_code").replace(
        "&reporter=XX&product=10411200&", "&reporter=AT&product=NO_SUCH_PRODUCT&"
    )
    route = replay_fixture(GET_DATA, "DS-059358_unknown_code", url=url)
    with pytest.raises(NotFoundError) as refused:
        get_data(
            "DS-059358",
            filters={"reporter": "AT", "product": "NO_SUCH_PRODUCT"},
            since_time_period="2022",
            until_time_period="2023",
        )
    assert sent_urls(route) == [url]
    assert not isinstance(refused.value, InvalidRequestError)


def test_get_data_answers_a_cube_without_a_cell_with_not_found(
    replay_fixture: ReplayFixture,
) -> None:
    """Recorded on the Comext base: DS-059359 for the reporter AT, the product 20158000 and
    the indicator PRODVAL, codes that CXT_FREE_ISO, CXT_PRODCOM2_TOTAL and CXT_INDICATORS
    hold, answered with a cube that holds no cell, size 0 on ``indicators``, since
    DS-059359 serves no PRODVAL (``docs/upstream/OBSERVED.md``, "A code that matches nothing
    answers an empty cube"). The check passes the codes, and a task of one record
    answers no data with ``NotFoundError``, which names the dataset and the filters sent
    (sdk-core ADR-0061, decision 6; conventions §5; the maintainer's decision of 2026-11-27
    on https://github.com/xippios/sdk-eurostat/issues/82)."""
    case = "DS-059359_AT_20158000_indicator_not_in_dataset"
    route = replay_fixture(GET_DATA, case)
    with pytest.raises(NotFoundError) as refused:
        get_data(
            "DS-059359",
            filters={"reporter": "AT", "product": "20158000", "indicators": "PRODVAL"},
            since_time_period="2022",
            until_time_period="2023",
        )
    assert sent_urls(route) == [recorded_url(case)]
    assert str(refused.value) == (
        "Eurostat holds no data for get_data(dataset_code='DS-059359', filters={'reporter': "
        "'AT', 'product': '20158000', 'indicators': 'PRODVAL'}, since_time_period='2022', "
        "until_time_period='2023'): the request was sent, and its cube has no cell with a "
        "value or a status. A code that the dataset does not use, or a period that Eurostat "
        "has not released, answers so, and the cube of a call without that filter lists the "
        "codes of each dimension."
    )
    assert UNSENT not in str(refused.value)


@pytest.mark.anyio
async def test_get_data_tool_answers_a_refused_code_as_text(respx_mock: respx.MockRouter) -> None:
    text = await mcp_call_text(
        server, "eurostat_get_data", {"dataset_code": "apro_mk_cola", "filters": {"geo": "XX"}}
    )
    assert text.startswith("error: UnknownCode: 'XX' is not a geo in the packaged GEO list")
    assert not respx_mock.calls


def test_get_data_unknown_dataset(replay_fixture: ReplayFixture) -> None:
    route = replay_fixture(GET_DATA, "unknown_dataset")
    with pytest.raises(NotFoundError, match="NO_SUCH_DATASET"):
        tasks.get_data("no_such_dataset")
    assert sent_urls(route) == [recorded_url("unknown_dataset")]


def test_get_data_unknown_dimension(replay_fixture: ReplayFixture) -> None:
    replay_fixture(GET_DATA, "unknown_dimension")
    with pytest.raises(InvalidRequestError, match="INVALID_QUERY_DIMENSION"):
        tasks.get_data("apro_mk_cola", filters={"nosuchdim": "AT"})


@pytest.mark.parametrize("level", [GeoLevel.COUNTRY, "country"], ids=["member", "plain"])
def test_get_data_geo_with_geo_level(replay_fixture: ReplayFixture, level: str) -> None:
    """A plain string is accepted where the enumeration is expected, and sent as it."""
    route = replay_fixture(GET_DATA, "geo_with_geo_level")
    with pytest.raises(InvalidRequestError, match="cannot be set at the same time"):
        tasks.get_data("apro_mk_cola", filters={"geo": "AT"}, geo_level=cast(GeoLevel, level))
    assert sent_urls(route) == [recorded_url("geo_with_geo_level")]


def test_get_data_takes_lang_as_a_plain_string(replay_fixture: ReplayFixture) -> None:
    case = "apro_mk_cola_AT_2022_2023"
    route = replay_fixture(GET_DATA, case)
    result = tasks.get_data(
        "apro_mk_cola", filters={"geo": "AT", "time": ["2022", "2023"]}, lang=cast(Lang, "EN")
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
    with pytest.raises(InvalidRequestError, match=f"{argument}={value!r} is not one of") as refused:
        tasks.get_data("apro_mk_cola", filters={"geo": "AT"}, **{argument: cast(Any, value)})
    assert str(refused.value).endswith(f"'. {UNSENT}")
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
    untilTimePeriod." Refused before any request (sdk-core ADR-0007), so nothing is replayed,
    and the refusal says so (conventions §5)."""
    with pytest.raises(InvalidRequestError) as refused:
        tasks.get_data("apro_mk_cola", filters={"geo": "AT", **filters}, **times)
    assert str(refused.value) == (
        f"{named}: the Statistics API does not accept more than one time parameter in a "
        f"query; the one exception is since_time_period with until_time_period. {UNSENT}"
    )
    assert not respx_mock.calls, "refused before any request"


def test_documented_shape_get_data_refuses_an_asynchronous_answer(
    respx_mock: respx.MockRouter,
) -> None:
    """Documented shape, read verbatim from the snapshot at test time; neither recorded nor
    hand-written: the asynchronous answer of api-statistics.md. Eurostat answers it as an
    ``error`` array (``tests/test_client.py``,
    ``test_statistics_api_asynchronous_answer_is_refused_as_recorded``;
    ``docs/upstream/OBSERVED.md``, "The asynchronous answer comes as an `error` array");
    this test stays for the documented ``warning`` (conventions §10, kind 1)."""
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
    with pytest.raises(
        InvalidRequestError, match="is a parameter of the Statistics API"
    ) as refused:
        tasks.get_data("apro_mk_cola", filters=filters)
    assert str(refused.value).endswith(f"are arguments of get_data. {UNSENT}")
    assert not respx_mock.calls, "refused before any request"


def test_get_data_refuses_an_empty_list_of_codes(respx_mock: respx.MockRouter) -> None:
    with pytest.raises(InvalidRequestError, match="lists no code") as refused:
        tasks.get_data("apro_mk_cola", filters={"geo": []})
    assert str(refused.value) == (
        "filters['geo'] lists no code: give one code or several, or leave the dimension out "
        f"to get all of its codes. {UNSENT}"
    )
    assert not respx_mock.calls


def test_get_data_keeps_an_updated_without_zone_as_a_naive_published_at(
    respx_mock: respx.MockRouter,
) -> None:
    """NOT RECORDED: the recorded cube with ``updated`` stripped of its zone in memory, a
    form Eurostat was not seen to send; ``published_at`` keeps it as printed, no zone invented, with
    ``published_at_naive`` set, and the text stays the vintage (sdk-core ADR-0041 decision 2;
    conventions §10, kind 4)."""
    fixture = load_fixture(FIXTURES / GET_DATA / "apro_mk_cola_AT_2022_2023.json")
    body: dict[str, Any] = json.loads(fixture.response.body)
    body["updated"] = "2026-10-05T23:00:00"
    respx_mock.route(method="GET", host="ec.europa.eu").mock(
        return_value=httpx.Response(200, json=body)
    )
    result = tasks.get_data("apro_mk_cola", filters={"geo": "AT", "time": ["2022", "2023"]})
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
            "dataset_code": "apro_mk_cola",
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
    agent sees the valid values; the tool validates a string against them. Each argument's
    text under ``Args:`` stands in its property, and the tool's description stops before
    ``Args:`` (sdk-core ADR-0063, decision 9)."""
    tools = {tool.name: tool for tool in await server.list_tools()}
    schema = tools["eurostat_get_data"].input_schema
    assert schema["properties"]["lang"] == {
        "$ref": "#/$defs/Lang",
        "default": "EN",
        "description": 'Language of the labels: ``"EN"`` (the default), ``"FR"`` or ``"DE"``.',
    }
    assert "Language of the labels" not in (tools["eurostat_get_data"].description or "")
    assert schema["$defs"]["Lang"]["enum"] == ["EN", "FR", "DE"]
    assert schema["$defs"]["GeoLevel"]["enum"] == [
        "aggregate",
        "country",
        "nuts1",
        "nuts2",
        "nuts3",
        "city",
    ]


def test_get_data_route_end_to_end(replay_fixture: ReplayFixture) -> None:
    """A mapping parameter makes the route a POST with a JSON body (sdk-core ADR-0007)."""
    case = "apro_mk_cola_AT_2022_2023"
    route = replay_fixture(GET_DATA, case)
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as http:
        answer = http.post(
            "/eurostat/get_data",
            json={
                "dataset_code": "apro_mk_cola",
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
            "/eurostat/get_data",
            json={"dataset_code": "apro_mk_cola", "filters": {"nosuchdim": "AT"}},
        )
    assert answer.status_code == 422
    assert "INVALID_QUERY_DIMENSION" in answer.text


# The Comext base: a DS- dataset is requested on COMEXT_BASE_URL (prefixed-datasets.md),
# through the same client; the fixtures mirror the main base's.

PRODCOM = "DS-059358_AT_10411200_2022_2023"
FISH_OIL = {"reporter": "AT", "product": "10411200"}
"""DS-059358 (Prodcom: sold production, exports and imports) for Austria and product
10411200, fats and oils of fish or marine mammals (NACE 10.41)."""
COMEXT_STATISTICS = f"{COMEXT_BASE_URL}/statistics/1.0/data"


def test_get_data_ds_059358_on_the_comext_base(replay_fixture: ReplayFixture) -> None:
    route = replay_fixture(GET_DATA, PRODCOM)
    before = datetime.now(UTC)
    result = tasks.get_data(
        "DS-059358", filters=FISH_OIL, since_time_period="2022", until_time_period="2023"
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
        "dataset_code": "DS-059358",
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
    route = replay_fixture(GET_DATA, "DS-000000_unknown_dataset")
    with pytest.raises(NotFoundError, match=r"DS-000000 \(DATA_FLOW:ALL,1\.0\) is not available"):
        tasks.get_data("DS-000000")
    assert sent_urls(route) == [recorded_url("DS-000000_unknown_dataset")]
    assert recorded_url("DS-000000_unknown_dataset").startswith(f"{COMEXT_STATISTICS}/DS-000000?")


def test_get_data_ds_059358_unknown_dimension_is_too_large(replay_fixture: ReplayFixture) -> None:
    """The Comext base does not refuse a filter on a dimension the dataset lacks as the
    main base does (fault 150 at HTTP 400), but as too large: HTTP 413 with an ``error``
    array, whose fault reaches the caller. The estimate, 151,971,120 rows, is that of an
    unfiltered query, so the unknown filter seems to be ignored. It is core's
    ``QueryTooLarge`` (conventions §5)."""
    route = replay_fixture(GET_DATA, "DS-059358_unknown_dimension_too_big")
    with pytest.raises(QueryTooLarge) as refused:
        tasks.get_data("DS-059358", filters={"geo": "AT"})
    assert sent_urls(route) == [recorded_url("DS-059358_unknown_dimension_too_big")]
    assert (refused.value.count, refused.value.limit) == (151_971_120, 5_000_000)
    assert str(refused.value) == (
        "GET /eurostat/api/comext/dissemination/statistics/1.0/data/DS-059358 would return "
        "151,971,120 records; upstream serves at most 5,000,000 per call. Eurostat estimates "
        "an extraction in cells and refuses one over its limit: narrow the query with fewer "
        "codes per dimension or a shorter period."
    )


@pytest.mark.anyio
async def test_get_data_ds_059358_tool_end_to_end(replay_fixture: ReplayFixture) -> None:
    route = replay_fixture(GET_DATA, PRODCOM)
    payload = await mcp_call(
        server,
        "eurostat_get_data",
        {
            "dataset_code": "DS-059358",
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
    assert payload["meta"]["request"]["dataset_code"] == "DS-059358"
    assert payload["meta"]["names"] == {"reporter": {"AT": label("cxt_free_iso", "AT")}}, (
        "product, which three codelists feed, names no code"
    )


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


TOC_DATE = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})")
"""How the table of contents prints ``lastUpdate`` and ``lastModified``, ``"02.10.2026"``."""


def toc_date(text: str) -> date:
    """A packaged leaf's date: the table of contents' print, day first, or an ISO date, the
    form ``dump_upstream`` writes a ``date`` in, which a refresh on this model packages."""
    printed = TOC_DATE.fullmatch(text)
    if printed is None:
        return date.fromisoformat(text)
    day, month, year = printed.groups()
    return date(int(year), int(month), int(day))


def toc_record(record: dict[str, Any]) -> dict[str, Any]:
    """A packaged leaf as ``Dataset.dump_upstream`` gives it back: its dates in ISO."""
    return record | {
        name: toc_date(record[name]).isoformat() for name in ("lastUpdate", "lastModified")
    }


def test_list_datasets_answers_the_whole_table_of_contents() -> None:
    result = list_datasets()
    raw = packaged_file("toc")
    assert len(result.data) == len(raw["records"]) == index_record("toc")["count"]
    assert all(isinstance(leaf, Dataset) for leaf in result.data)
    assert [leaf.dump_upstream() for leaf in result.data[:50]] == [
        toc_record(record) for record in raw["records"][:50]
    ]
    assert {leaf.type for leaf in result.data} == {LeafType.DATASET, LeafType.TABLE}
    assert all(leaf.path for leaf in result.data), "every leaf sits in a folder"


def test_list_datasets_meta_is_the_packaged_answer() -> None:
    """sdk-core ADR-0041 decision 1 and decision D4 of
    https://github.com/xippios/sdk-eurostat/pull/6: the file's fetched, the operation,
    creationDate as vintage and its naive time as published_at."""
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
    assert [leaf.dump_upstream() for leaf in result.data] == [
        toc_record(record) for record in expected
    ]
    assert "apro_mk_cola" in {leaf.code for leaf in result.data}
    assert result.meta.request == {"search": "MILK"}


def test_list_datasets_search_by_code() -> None:
    result = list_datasets(search="apro_mk_cola")
    assert [leaf.code for leaf in result.data] == ["apro_mk_cola"]
    cola = result.data[0]
    assert cola.type == LeafType.DATASET
    assert cola.path.endswith(" > Milk and milk products")
    record = next(
        record for record in packaged_file("toc")["records"] if record["code"] == cola.code
    )
    assert cola.last_update == toc_date(record["lastUpdate"])
    assert cola.last_modified == toc_date(record["lastModified"])


def test_list_datasets_reads_the_dates_day_first() -> None:
    """A leaf's ``lastUpdate`` and ``lastModified``, printed ``"02.10.2026"``, are read into
    a ``date``, the type that keeps all that upstream sends, with no text beside it
    (https://github.com/xippios/sdk-usda-esr/issues/60, part 3; conventions §3). The
    samples of the table of contents fix the order (``tests/test_refresh_reference.py``),
    and the packaged table is read in it, or in the ISO form a refresh on this model
    packages."""
    leaves = list_datasets().data
    records = packaged_file("toc")["records"]
    assert all(isinstance(leaf.last_update, date) for leaf in leaves)
    assert all(isinstance(leaf.last_modified, date) for leaf in leaves)
    assert [leaf.last_update for leaf in leaves] == [toc_date(r["lastUpdate"]) for r in records]
    assert [leaf.last_modified for leaf in leaves] == [toc_date(r["lastModified"]) for r in records]


def test_list_datasets_search_without_a_match_is_empty() -> None:
    assert list_datasets(search="no dataset is called this").data == []


def test_list_datasets_returns_a_new_list_each_call() -> None:
    first = list_datasets(search="apro_mk_cola")
    first.data.clear()
    assert list_datasets(search="apro_mk_cola").data


@pytest.mark.parametrize("name", ["GEO", "geo", "Geo"])
def test_list_codes_geo(name: str) -> None:
    """The codelist's name is matched without case and recorded in ``meta.request`` as the
    caller gave it (sdk-core ``docs/conventions.md`` §5)."""
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
    assert result.meta.request == {"codelist": name}
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
    last_updated = index_record(codelist.lower())["LAST_UPDATED"]
    assert result.meta.published_at == (
        None if last_updated is None else datetime.fromisoformat(last_updated)
    ), "CXT_EU_FLUX carries no LAST_UPDATED"
    assert result.meta.request == {"codelist": codelist.lower()}


def test_list_codes_serves_the_comext_codelists() -> None:
    """CXT_INDICATORS whole, CXT_PRODCOM2_TOTAL and CXT_FREE_ISO searched, CXT_EU_FLUX
    whole: the Comext base's codelists are served as the main base's are, their endpoint
    the full URL; one without LAST_UPDATED has no published_at."""
    indicators = list_codes("CXT_INDICATORS")
    assert Code(code="PRODVAL", label="Sold production value, euro") in indicators.data
    assert indicators.meta.endpoint == (f"{COMEXT_BASE_URL}/sdmx/2.1/codelist/ESTAT/CXT_INDICATORS")
    assert indicators.meta.published_at == datetime.fromisoformat(
        index_record("cxt_indicators")["LAST_UPDATED"]
    )
    fertilisers = list_codes("cxt_prodcom2_total", search="Animal or vegetable fertilisers")
    assert [code.code for code in fertilisers.data] == ["20158000"]
    assert fertilisers.meta.request == {
        "codelist": "cxt_prodcom2_total",
        "search": "Animal or vegetable fertilisers",
    }
    austria = list_codes("cxt_free_iso", search="austria")
    assert Code(code="AT", label="Austria") in austria.data
    assert austria.meta.endpoint == f"{COMEXT_BASE_URL}/sdmx/2.1/codelist/ESTAT/CXT_FREE_ISO"
    flows = list_codes("CXT_EU_FLUX")
    assert [code.dump_upstream() for code in flows.data] == packaged_file("cxt_eu_flux")["records"]
    assert Code(code="1", label="IMPORT") in flows.data
    assert flows.meta.vintage == index_record("cxt_eu_flux")["version"]
    assert flows.meta.published_at is None
    assert flows.meta.published_at_naive is False


def test_list_codes_search_keeps_code_or_label_ignoring_case() -> None:
    result = list_codes("geo", search="austria")
    assert Code(code="AT", label="Austria") in result.data
    assert all("austria" in (code.label or "").casefold() for code in result.data)
    assert result.meta.request == {"codelist": "geo", "search": "austria"}
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
        f"'goe' is not a codelist in the packaged codelist list (fetched {day}). {UNSENT} "
        "Did you mean GEO (Geopolitical entity (reporting))"
    )
    assert tasks.UNPACKAGED_CODELIST in message
    assert "get_data (over MCP, the tool eurostat_get_data)" in message


def test_list_codes_refuses_a_codelist_the_package_does_not_carry() -> None:
    with pytest.raises(UnknownCode, match=r"^'nace_r2' is not a codelist") as refused:
        list_codes("nace_r2")
    assert "the dimensions of apro_cpnh1, apro_mk_cola and ef_m_farmleg" in str(refused.value)
    assert "DS-059358 and DS-059359" in str(refused.value)
    assert "DS-045409 and DS-059341" in str(refused.value)


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
    assert cap.paged, "a packaged table: a continuation sends upstream no request"
    assert payload["note"] == (
        f"showing {shown} of {total} rows (cap: {cap.max_rows} rows or {cap.max_bytes} bytes); "
        "pass search, a word of the title or a part of the code (milk, apro_mk), to see the "
        f"rest; continue with offset={shown}"
    )
    assert payload["meta"]["vintage"] == index_record("toc")["creationDate"]
    assert payload["meta"]["published_at_naive"] is True


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("tool", "arguments", "record"),
    [
        ("eurostat_list_datasets", {}, "toc"),
        ("eurostat_list_codes", {"codelist": "geo"}, "geo"),
    ],
)
async def test_a_list_tool_continues_at_its_offset_without_a_request(
    respx_mock: respx.MockRouter, tool: str, arguments: dict[str, Any], record: str
) -> None:
    """Both list tools answer from packaged tables, so their caps are paged (sdk-core
    ADR-0047): the note of a cut answer names the ``offset`` to continue with, and the
    next page runs the task again and sends nothing."""
    first = await mcp_call(server, tool, arguments)
    shown = len(first["data"])
    second = await mcp_call(server, tool, {**arguments, "offset": shown})
    total = index_record(record)["count"]
    assert second["note"].startswith(f"showing rows {shown + 1} to ")
    assert f" of {total}" in second["note"]
    assert second["data"][0] != first["data"][0]
    assert not respx_mock.calls, "a continuation sends upstream no request"


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
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", payload["data"][0]["last_update"]), "an ISO date"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", payload["data"][0]["last_modified"])
    assert payload["meta"]["endpoint"] == "catalogue/toc/xml"
    assert payload["meta"]["request"] == {"search": "apro_mk_cola"}


@pytest.mark.anyio
async def test_list_codes_tool_cuts_geo_with_its_note() -> None:
    payload = await mcp_call(server, "eurostat_list_codes", {"codelist": "geo"})
    cap = tasks.MCP_CAPS["list_codes"]
    shown = len(payload["data"])
    total = index_record("geo")["count"]
    assert 0 < shown <= cap.max_rows < total
    assert cap.paged, "a packaged table: a continuation sends upstream no request"
    assert payload["note"] == (
        f"showing {shown} of {total} rows (cap: {cap.max_rows} rows or {cap.max_bytes} bytes); "
        "pass search, a part of the code or of the label (AT, austria), to see the rest; "
        f"continue with offset={shown}"
    )
    assert payload["meta"]["vintage"] == index_record("geo")["version"]
    assert payload["meta"]["request"] == {"codelist": "geo"}


@pytest.mark.anyio
async def test_list_codes_tool_answers_unit_whole() -> None:
    """UNIT, the largest codelist of the main base but GEO, fits the cap: 1,000 rows
    within 64 KB."""
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
    """Scalar parameters make the route a GET with query parameters (sdk-core ADR-0007)."""
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
    result = download_dataset(
        "apro_mk_cola", MILK_KEY, start_period="2022", end_period="2023", dest=dest
    )
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
    assert meta.vintage == "05/10/26 23:00:00", "LAST UPDATE as printed"
    assert meta.published_at == datetime(2026, 10, 5, 23, 0)
    assert meta.published_at == next(parse_sdmx_csv(dest)).last_update
    assert meta.published_at.tzinfo is None
    assert meta.published_at_naive is True
    assert meta.request == {
        "flow_ref": "apro_mk_cola",
        "key": MILK_KEY,
        "start_period": "2022",
        "end_period": "2023",
        "format": "SDMX-CSV",
        "compressed": True,
    }
    assert meta.request["key"] != REDACTED, (
        "the SDMX series key is data (sdk-core ADR-0040 decision 6)"
    )
    assert meta.total is None


@pytest.mark.parametrize(
    ("cube", "sample"),
    [
        ("apro_mk_cola_AT_2022_2023", MILK_SLICE),
        (PRODCOM, PRODCOM_SLICE),
        ("DS-045409_AT_DE_15071090_2023", "DS-045409_M_AT_DE_15071090_2023"),
    ],
    ids=["main", "comext", "comext-trade"],
)
def test_download_dataset_reads_last_update_day_first(cube: str, sample: str) -> None:
    """The recorded pairs fix the order: the JSON-stat answer's ``updated`` and the
    SDMX-CSV answer's ``LAST UPDATE`` of one dataset, recorded the same day, are one time,
    the CSV's printed day first and without the zone, on either base (apro_mk_cola's
    05/10/26, DS-059358's 20/10/26, DS-045409's 16/10/26)."""
    updated = datetime.fromisoformat(recorded_updated(cube))
    printed = next(parse_sdmx_csv(FIXTURES / "files" / "sdmx-csv" / f"{sample}.csv"))
    assert printed.last_update == updated.replace(tzinfo=None)


def test_download_dataset_ds_059358_on_the_comext_base(
    replay_fixture: ReplayFixture, tmp_path: Path
) -> None:
    route = replay_fixture(DATA_QUERY, PRODCOM_SLICE_GZ)
    recorded = recorded_data(PRODCOM_SLICE_GZ)
    dest = tmp_path / "fish_oil.csv.gz"
    result = download_dataset(
        "DS-059358", PRODCOM_KEY, start_period="2022", end_period="2023", dest=dest
    )
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
    values = {(row.dimensions["indicators"], row.time_period): row for row in rows}
    assert values[("QNTUNIT", "2022")].obs_value == "KG", "a unit among the measures, as printed"
    assert values[("SCQNTFLAG", "2023")].obs_value == values[("SCVALFLAG", "2023")].obs_value
    assert values[("SCQNTFLAG", "2023")].obs_value == ":E"
    texts = {row.obs_value for row in rows if row.obs_value_number is None}
    assert texts == {"KG", ":E"}, "the texts that read as no number"
    assert values[("EXPVAL", "2022")].obs_value == "349477"
    assert values[("EXPVAL", "2022")].obs_value_number == Decimal("349477")
    meta = result.meta
    assert meta.endpoint == "dataQuery"
    assert meta.vintage == "20/10/26 11:00:00", "LAST UPDATE as printed"
    assert meta.published_at == datetime(2026, 10, 20, 11, 0) == rows[0].last_update
    assert meta.published_at_naive is True
    assert meta.request == {
        "flow_ref": "DS-059358",
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
    moved, not written by hand, for a test that asserts only what was sent (conventions
    §10, kind 3). ``key`` is recorded as the empty string sent."""
    url = f"{DATA_URL}/apro_mk_cola?format=SDMX-CSV&compressed=true"
    route = replay_fixture(DATA_QUERY, MILK_SLICE_GZ, url=url)
    result = download_dataset("apro_mk_cola", dest=tmp_path / "all.csv.gz")
    assert sent_urls(route) == [url]
    assert result.meta.request == {
        "flow_ref": "apro_mk_cola",
        "key": "",
        "format": "SDMX-CSV",
        "compressed": True,
    }


def test_download_dataset_sends_last_n_observations_and_quotes_the_key(
    replay_fixture: ReplayFixture, tmp_path: Path
) -> None:
    """The recorded answer moved to the URL of another request, for a test that asserts
    only what was sent (conventions §10, kind 3): ``+`` and the dots stay in the key,
    ``lastNObservations`` follows ``format``."""
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
    with its recorded headers: a file without a row has no ``LAST UPDATE`` to read
    (conventions §10, kind 4)."""
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
    memory, served with its recorded headers (conventions §10, kind 4). The file is written
    and stays at ``dest``; the parser's refusal names the row and the form expected, never
    the text."""
    recorded = recorded_data(MILK_SLICE)
    body = recorded.response.content.replace(b"05/10/26 23:00:00", b"2026-10-05 23:00:00")
    respx_mock.route(method="GET", host="ec.europa.eu").mock(
        return_value=httpx.Response(200, headers=recorded.response.headers, content=body)
    )
    dest = tmp_path / "milk.csv"
    with pytest.raises(ValidationError) as refused:
        download_dataset("apro_mk_cola", MILK_KEY, dest=dest)
    assert str(refused.value).startswith("eurostat sdmx-csv line 2: ")
    assert "LAST UPDATE is not printed as dd/mm/yy HH:MM:SS" in str(refused.value)
    assert "2026-10-05" not in str(refused.value), "no value in the text"
    assert dest.read_bytes() == body, "the file stays at dest"
    assert leftovers(tmp_path) == ["milk.csv"]


@pytest.mark.parametrize("key", [".", ".."])
def test_download_dataset_refuses_a_dot_segment_key(
    respx_mock: respx.MockRouter, tmp_path: Path, key: str
) -> None:
    with pytest.raises(InvalidRequestError, match='pass key="" for every code') as refused:
        download_dataset("apro_mk_cola", key, dest=tmp_path / "f.csv.gz")
    assert str(refused.value).endswith(f'pass key="" for every code of every dimension. {UNSENT}')
    assert not respx_mock.calls, "refused before any request"


def test_download_dataset_refuses_a_directory_or_a_missing_one(
    respx_mock: respx.MockRouter, tmp_path: Path
) -> None:
    """Core's own text (``check_dest``, which ``AsyncClient.download`` calls), as the
    taxonomy's refusal, saying that nothing was sent (conventions §5)."""
    with pytest.raises(InvalidRequestError) as directory:
        download_dataset("apro_mk_cola", MILK_KEY, dest=tmp_path)
    assert str(directory.value) == f"dest is a directory; name the file to write. {UNSENT}"
    with pytest.raises(InvalidRequestError) as missing:
        download_dataset("apro_mk_cola", MILK_KEY, dest=tmp_path / "no" / "f.csv.gz")
    assert str(missing.value) == f"dest's directory does not exist; create it first. {UNSENT}"
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
    the test of the user guide's documented body (conventions §10). It queued one
    extraction on Eurostat's side that nobody fetches
    (https://github.com/xippios/sdk-eurostat/pull/12)."""
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
    reads an error's body for the error's text, and it is core's ``QueryTooLarge``
    (conventions §5). The recording replaces the test of the user guide's documented body
    (conventions §10)."""
    route = replay_fixture(DATA_QUERY, TOO_BIG)
    key = "M.AT+DE+FR+IT+NL.US..."
    with pytest.raises(QueryTooLarge) as refused:
        download_dataset(
            "DS-045409", key, start_period="2023", end_period="2023", dest=tmp_path / "t.csv.gz"
        )
    assert sent_urls(route) == [recorded_data(TOO_BIG).request.url]
    assert recorded_data(TOO_BIG).request.url == (
        f"{COMEXT_DATA_URL}/DS-045409/{key}?format=SDMX-CSV&startPeriod=2023&endPeriod=2023"
        "&compressed=true"
    ), "the plus signs and dots of the key as sent"
    assert str(refused.value) == (
        f"GET /eurostat/api/comext/dissemination/sdmx/2.1/data/DS-045409/{key} would return "
        "13,344,840 records; upstream serves at most 5,000,000 per call. Eurostat estimates an "
        "extraction in cells and refuses one over its limit: narrow the query with fewer codes "
        "per dimension or a shorter period."
    )
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
async def test_code_list_query_takes_the_comext_base(respx_mock: respx.MockRouter) -> None:
    """``base_url`` sends the codelist query to the Comext base: only the URL sent is
    asserted. NOT RECORDED: the answer is the main base's STATINFO sample
    (``tests/fixtures/files/codelist/statinfo.json``) served at the Comext base's codelist
    path, an exchange upstream never had, so that the call completes, for a test that
    asserts only what was sent (conventions §10, kind 3)."""
    sample = (FIXTURES / "files" / "codelist" / "statinfo.json").read_bytes()
    route = respx_mock.route(
        method="GET",
        host="ec.europa.eu",
        path="/eurostat/api/comext/dissemination/sdmx/2.1/codelist/ESTAT/STATINFO",
    ).mock(
        return_value=httpx.Response(
            200, headers={"content-type": "application/json"}, content=sample
        )
    )
    await api.sdmx.code_list_query("ESTAT", "STATINFO", lang="en", base_url=COMEXT_BASE_URL)
    assert sent_urls(route) == [
        f"{COMEXT_BASE_URL}/sdmx/2.1/codelist/ESTAT/STATINFO?format=JSON&lang=en"
    ]


@pytest.mark.anyio
async def test_code_list_query_answers_the_parsed_codelist(respx_mock: respx.MockRouter) -> None:
    """``api.sdmx.code_list_query`` answers core's ``Answer`` of the parsed codelist. NOT
    RECORDED as served: the main base's STATINFO sample
    (``tests/fixtures/files/codelist/statinfo.json``), the whole answer of the operation as
    decoded, served in memory at its own URL, where upstream answers alike (conventions §10,
    kind 3)."""
    sample = (FIXTURES / "files" / "codelist" / "statinfo.json").read_bytes()
    respx_mock.get(f"{BASE_URL}/sdmx/2.1/codelist/ESTAT/STATINFO").mock(
        return_value=httpx.Response(
            200, headers={"content-type": "application/json"}, content=sample
        )
    )
    answer = await api.sdmx.code_list_query("ESTAT", "STATINFO", lang="en")
    assert isinstance(answer, Answer)
    assert isinstance(answer.payload, models.Codelist)


TASKS = ["download_dataset", "get_data", "list_codes", "list_datasets"]
"""The four tasks that the boundary of a source package leaves this one."""

TOOLS = {"eurostat_get_data", "eurostat_list_codes", "eurostat_list_datasets"}
"""The tools of the three tasks that are not bulk tasks."""


@pytest.mark.anyio
async def test_the_package_serves_four_tasks_and_three_tools() -> None:
    """The slices (``get_series``, ``get_latest_period``, ``get_cross_section``), the
    production and trade tasks (``get_sold_production``, ``get_total_production``,
    ``get_trade``, ``get_trade_hs``, ``download_trade``) and the lists cut from one codelist
    (``list_cn8``, ``list_hs``, ``list_products``) left with their caps and ``models.Freq``,
    each a task that fixes filters over one upstream operation (sdk-core ADR-0060, decision
    8). The package re-exports exactly the tasks, and the MCP server lists their tools."""
    assert sorted(tasks.__all__) == TASKS
    assert sorted(set(xippios.eurostat.__all__) - {"__version__"}) == TASKS
    assert set(tasks.MCP_CAPS) == {"list_codes", "list_datasets"}
    assert {tool.name for tool in await server.list_tools()} == TOOLS
    assert "Freq" not in models.__all__
    assert not hasattr(models, "Freq")


ARGUMENTS: dict[str, tuple[list[str], list[str]]] = {
    "get_data": (
        ["dataset_code"],
        [
            "filters",
            "lang",
            "since_time_period",
            "until_time_period",
            "last_time_period",
            "geo_level",
        ],
    ),
    "download_dataset": (
        ["flow_ref", "key"],
        ["start_period", "end_period", "last_n_observations", "dest"],
    ),
    "list_codes": (["codelist"], ["search"]),
    "list_datasets": ([], ["search"]),
}
"""Each task's arguments by position, in the order of upstream's path, then those by name."""


@pytest.mark.parametrize("name", TASKS)
def test_a_task_takes_upstreams_names_the_record_first_and_the_filters_by_name(name: str) -> None:
    """An argument that upstream takes keeps the name of the parameter the task sends:
    ``getData``'s ``datasetCode``, ``dataQuery``'s ``flowRef``, ``startPeriod`` and
    ``endPeriod``, snake-cased, and ``list_codes`` keeps ``codelist``, the name under which
    it looks up its packaged lists (sdk-core ADR-0061, decision 4; the maintainer's decision
    of 2026-11-27 on https://github.com/xippios/sdk-eurostat/issues/82). The arguments that
    identify a record stand first, by position, in the order of upstream's path, and every
    optional filter and every argument of the package's own is keyword-only (decision 5;
    https://github.com/xippios/sdk-usda-esr/issues/60, part 1). A task and its async twin
    take the same."""
    positional, named = ARGUMENTS[name]
    for fn in (getattr(tasks, name), getattr(tasks, f"{name}_async")):
        parameters = list(inspect.signature(fn).parameters.values())
        assert [
            p.name for p in parameters if p.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
        ] == (positional)
        assert [p.name for p in parameters if p.kind is inspect.Parameter.KEYWORD_ONLY] == named
        assert len(parameters) == len(positional) + len(named), "no other kind of argument"


def test_get_data_refuses_filters_by_position(respx_mock: respx.MockRouter) -> None:
    """A call of 0.3.0 that passes ``filters`` second, by position, fails before anything is
    sent: ``filters`` is an optional filter, so it is keyword-only (sdk-core ADR-0061,
    decision 5)."""
    with pytest.raises(TypeError, match="positional argument"):
        cast(Any, tasks.get_data)("apro_mk_cola", {"geo": "AT"})
    with pytest.raises(TypeError, match="positional argument"):
        cast(Any, tasks.list_codes)("geo", "austria")
    assert not respx_mock.calls


@pytest.mark.anyio
async def test_get_data_tool_takes_dataset_code() -> None:
    """Over MCP a tool takes its arguments by name, so its schema carries the new name and
    no other: ``dataset_code``, required, and ``dataset`` no longer (sdk-core ADR-0061,
    decision 5: "Over MCP and HTTP nothing changes" but the names)."""
    tools = {tool.name: tool for tool in await server.list_tools()}
    schema = tools["eurostat_get_data"].input_schema
    assert schema["required"] == ["dataset_code"]
    assert list(schema["properties"])[:2] == ["dataset_code", "filters"]
    assert "dataset" not in schema["properties"]
    text = await mcp_call_text(server, "eurostat_get_data", {"dataset": "apro_mk_cola"})
    assert text.startswith("error: ")
    assert "dataset_code" in text


BULK = ["download_dataset"]


def test_bulk_tasks_are_no_tool_and_no_route() -> None:
    """Bulk tasks: ``BULK_TASKS`` names them, so core's adapters skip them (sdk-core ADR-0040
    decision 4); the family check (``tests/test_family.py``) serves ``tasks.__all__``
    minus them."""
    assert set(BULK) <= set(tasks.__all__)
    assert set(BULK) == set(tasks.BULK_TASKS)
    paths = {route.path for route in router.routes if isinstance(route, APIRoute)}
    assert "/eurostat/get_data" in paths
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as http:
        for name in BULK:
            assert f"/eurostat/{name}" not in paths
            assert http.post(f"/eurostat/{name}", json={}).status_code == 404
            assert http.get(f"/eurostat/{name}").status_code == 404


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("name", "arguments"),
    [("download_dataset", {"flow_ref": "apro_mk_cola"})],
)
async def test_bulk_tasks_are_no_mcp_tool(
    respx_mock: respx.MockRouter, name: str, arguments: dict[str, Any]
) -> None:
    names = {tool.name for tool in await server.list_tools()}
    assert f"eurostat_{name}" not in names
    assert "eurostat_get_data" in names
    with pytest.raises(AssertionError, match=f"Unknown tool: eurostat_{name}"):
        await mcp_call(server, f"eurostat_{name}", arguments)
    assert not respx_mock.calls


@pytest.mark.anyio
async def test_get_data_wrapper_answers_the_cube_with_its_printed_update(
    replay_fixture: ReplayFixture,
) -> None:
    """``api.statistics.get_data`` answers core's ``Answer``: the cube with its ``updated`` as
    Eurostat printed it, which ``meta.vintage`` holds, and when it was retrieved."""
    case = "apro_mk_cola_AT_2022_2023"
    replay_fixture(GET_DATA, case)
    answer = await api.statistics.get_data(
        "apro_mk_cola", lang=Lang.EN, filters={"geo": "AT", "time": ["2022", "2023"]}
    )
    assert isinstance(answer, Answer)
    assert isinstance(answer.payload, api.statistics.PrintedCube)
    assert isinstance(answer.payload.cube, Cube)
    assert answer.payload.updated == recorded_updated(case)
    assert answer.retrieved_at.tzinfo is not None


def test_the_api_keeps_no_pair_of_its_own() -> None:
    """Core's ``Answer`` takes the place of the wrappers' own pairs (conventions §15)."""
    assert not hasattr(api.statistics, "DataAnswer")
    assert not hasattr(api.sdmx, "CodelistAnswer")


def test_the_server_takes_its_instructions_from_the_tasks_module() -> None:
    """The rendered ``mcp.py`` holds no line of the package: core builds the server from
    ``tasks.py``, its ``MCP_INSTRUCTIONS`` among what it declares (sdk-core ADR-0063,
    decision 7)."""
    assert server.instructions == tasks.MCP_INSTRUCTIONS
    assert tasks.MCP_INSTRUCTIONS.startswith("Eurostat dissemination API via xippios.")


def test_the_package_holds_no_empty_stub() -> None:
    """``enums.py`` held the scaffold's ``__all__ = []`` and no enum, since every packaged
    list is a table, and leaves (https://github.com/xippios/sdk-template/issues/300)."""
    assert importlib.util.find_spec("xippios.eurostat.enums") is None
