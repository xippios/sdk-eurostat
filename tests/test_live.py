"""Live smoke tests, one per task, skipped unless XIPPIOS_LIVE_TESTS=1 (conventions §10).

``/add-endpoint`` adds them, next to the reachability check.

``get_data`` has one per dataset of the design round's question 6 (2026-10-27), each the
small slice its fixture holds: ``apro_mk_cola`` (milk collection), ``apro_cpnh1`` (crop
production) and ``ef_m_farmleg`` (farm indicators by legal status), Austria, two periods.
The slices have one each, on the slices their first fixtures hold: ``get_series`` and
``get_cross_section`` on ``apro_mk_cola``, ``get_latest_period`` on ``apro_cpnh1``.
The list tasks answer from the packaged lists, so theirs check upstream's side: that the
answers ``scripts/refresh_reference.py`` packages still read as it reads them, through
the script's own functions; ``list_datasets``'s reads the start of the table of contents
only (its test says why), ``list_codes``'s fetches the STATINFO codelist.
``download_dataset``'s downloads the slice its fixture holds, apro_mk_cola for Austria in
thousand tonnes, 2022 and 2023, to a temporary file and reads it with ``parse_sdmx_csv``,
the live parser test of the file kind ``sdmx-csv`` (ADR-0020 decision 6).
``get_data`` has one more on the Comext base, the smallest slice of the Prodcom dataset
``DS-059358`` (Austria, one product, the latest period), which is also the nightly's
check that the Comext base answers. The production tasks have one each there, on the
smallest slice their parameters allow, one product for Austria in one year (2023):
``get_sold_production`` on ``DS-059358``, ``get_total_production`` on ``DS-059359``;
``list_products``'s fetches the CXT_PRODCOM2_SOLD codelist from the Comext base through
the refresh script, as ``list_codes``'s fetches STATINFO.
A run sends fourteen keyless requests, the reachability check included. The tests assert
shape and release metadata, never values, which Eurostat revises twice a day, nor which
period is the latest.
"""

import importlib.util
import re
from datetime import datetime
from pathlib import Path
from types import ModuleType

import httpx
import pytest
from xippios.core import Result

from xippios.eurostat import params, tasks
from xippios.eurostat._client import BASE_URL, COMEXT_BASE_URL, config
from xippios.eurostat.api import catalogue
from xippios.eurostat.models import Code, Cube, Dataset, Observation, SdmxCsvRow
from xippios.eurostat.parse import parse_sdmx_csv

pytestmark = [pytest.mark.live, pytest.mark.anyio]

UPDATED = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{4}$")
"""``updated`` as Eurostat prints it, e.g. ``2026-10-05T23:00:00+0200``."""

LAST_UPDATE = re.compile(r"^\d{2}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}$")
"""SDMX-CSV's ``LAST UPDATE`` as Eurostat prints it, e.g. ``05/10/26 23:00:00``."""


async def test_upstream_answers() -> None:
    """The base URL answers without a server error.

    A plain request, not the package's client; any answer below 500 (a 404 at the
    root, say) shows the host is up.
    """
    async with httpx.AsyncClient(
        headers={"User-Agent": config.user_agent},
        timeout=config.timeouts.to_httpx(),
        follow_redirects=True,
    ) as http:
        response = await http.get(BASE_URL)
    assert response.status_code < 500


def _check(result: Result[Cube], *, periods: int) -> None:
    cube = result.data
    assert cube.class_ == "dataset"
    assert cube.size[cube.id.index("geo")] == 1
    assert cube.size[cube.id.index("time")] == periods
    assert cube.dimension["geo"].category.index == {"AT": 0}
    assert list(cube.observations()), "the slice has cells"
    assert result.meta.endpoint == "getData"
    assert result.meta.vintage is not None
    assert UPDATED.fullmatch(result.meta.vintage)
    assert result.meta.published_at is not None
    assert result.meta.published_at.tzinfo is not None
    assert result.meta.published_at == cube.updated


async def test_get_data_apro_mk_cola() -> None:
    result = await tasks.get_data_async("apro_mk_cola", {"geo": "AT", "time": ["2022", "2023"]})
    _check(result, periods=2)


async def test_get_data_apro_cpnh1() -> None:
    result = await tasks.get_data_async(
        "apro_cpnh1", {"geo": "AT"}, since_time_period="2022", until_time_period="2023"
    )
    _check(result, periods=2)


async def test_get_data_ef_m_farmleg() -> None:
    result = await tasks.get_data_async(
        "ef_m_farmleg", {"geo": "AT", "unit": "HLD"}, last_time_period=2
    )
    _check(result, periods=2)


async def test_get_data_ds_059358() -> None:
    """Prodcom's DS-059358 on the Comext base: Austria, product 10411200 (fats and oils of
    fish or marine mammals, NACE 10.41), the latest period."""
    result = await tasks.get_data_async(
        "DS-059358", {"reporter": "AT", "product": "10411200"}, last_time_period=1
    )
    cube = result.data
    assert cube.class_ == "dataset"
    assert cube.id[-1] == "time"
    assert cube.size[-1] == 1, "the latest period"
    assert cube.dimension["reporter"].category.index == {"AT": 0}
    assert cube.dimension["product"].category.index == {"10411200": 0}
    assert {"reporter", "product", "indicators"} <= set(cube.id), (
        "Prodcom's dimensions, which only the Comext base serves"
    )
    assert result.meta.endpoint == "getData"
    assert result.meta.vintage is not None
    assert UPDATED.fullmatch(result.meta.vintage)
    assert result.meta.published_at is not None
    assert result.meta.published_at.tzinfo is not None
    assert result.meta.published_at == cube.updated


MILK = {"milkitem": "PRD", "dairyprod": "D1110D", "unit": "THS_T"}


def _check_slice(result: Result[list[Observation]]) -> None:
    assert result.data, "the slice has observations"
    assert all(isinstance(observation, Observation) for observation in result.data)
    assert result.meta.endpoint == "getData"
    assert result.meta.vintage is not None
    assert UPDATED.fullmatch(result.meta.vintage)
    assert result.meta.published_at is not None
    assert result.meta.published_at.tzinfo is not None


async def test_get_series_apro_mk_cola() -> None:
    result = await tasks.get_series_async(
        "apro_mk_cola", {**MILK, "geo": "AT"}, since="2015", until="2023"
    )
    _check_slice(result)
    periods = [observation.codes["time"] for observation in result.data]
    assert periods == sorted(periods), "annual periods, oldest first"
    assert set(periods) <= {str(year) for year in range(2015, 2024)}
    assert {observation.codes["geo"] for observation in result.data} == {"AT"}


async def test_get_latest_period_apro_cpnh1() -> None:
    result = await tasks.get_latest_period_async("apro_cpnh1", {"crops": "C1110", "geo": "AT"})
    _check_slice(result)
    assert len({observation.codes["time"] for observation in result.data}) == 1, "one period"


async def test_get_cross_section_apro_mk_cola() -> None:
    result = await tasks.get_cross_section_async("apro_mk_cola", "2023", MILK)
    _check_slice(result)
    assert {observation.codes["time"] for observation in result.data} == {"2023"}
    assert len({observation.codes["geo"] for observation in result.data}) > 1, "every geo code"


async def test_download_dataset_apro_mk_cola(tmp_path: Path) -> None:
    dest = tmp_path / "milk.csv.gz"
    result = await tasks.download_dataset_async(
        "apro_mk_cola", "A...THS_T.AT", since="2022", until="2023", dest=dest
    )
    assert result.data.path == dest
    assert result.data.bytes == dest.stat().st_size
    assert dest.read_bytes()[:2] == b"\x1f\x8b", "gzip, as compressed=true answers"
    assert result.data.content_type is not None
    assert result.data.content_type.startswith("application/vnd.sdmx.data+csv")
    rows = list(parse_sdmx_csv(dest))
    assert rows, "the slice has rows"
    assert all(isinstance(row, SdmxCsvRow) for row in rows)
    assert {tuple(row.dimensions) for row in rows} == {
        ("freq", "milkitem", "dairyprod", "unit", "geo")
    }
    assert {row.dimensions["geo"] for row in rows} == {"AT"}
    assert {row.time_period for row in rows} <= {"2022", "2023"}
    assert result.meta.endpoint == "dataQuery"
    assert result.meta.vintage == rows[0].last_update
    assert LAST_UPDATE.fullmatch(result.meta.vintage)
    assert result.meta.published_at is not None
    assert result.meta.published_at.tzinfo is None
    assert result.meta.published_at_naive is True
    assert result.meta.request["key"] == "A...THS_T.AT"


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "refresh_reference.py"


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("refresh_reference", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def test_list_datasets_upstream_toc_still_reads() -> None:
    """The table of contents upstream serves still reads as the refresh script reads it.

    ``list_datasets`` answers from the packaged copy, so this checks upstream's side. The
    TOC is 23 MB, too much to fetch every night for a smoke test, so the test streams it
    and stops after the first complete leaf, a few kilobytes: one request, closed early,
    sent with a plain ``httpx`` client and the family's User-Agent, since core's client
    streams only to a file. It checks the root's ``creationDate`` and the first leaf's
    shape through the script's ``TocParser``; the packaged answer's metadata is checked
    on the way, without a request.
    """
    script = load_script()
    parser = script.TocParser()
    async with (
        httpx.AsyncClient(
            headers={"User-Agent": config.user_agent}, timeout=config.timeouts.to_httpx()
        ) as http,
        http.stream("GET", f"{BASE_URL}/{catalogue.PATH}") as response,
    ):
        assert response.status_code == 200
        async for chunk in response.aiter_bytes():
            parser.feed(chunk)
            if parser.completed:
                break
    assert parser.creation_date is not None
    assert re.fullmatch(r"\d{8}T\d{4}", parser.creation_date)
    datetime.strptime(parser.creation_date, tasks.CREATION_DATE)
    first = parser.leaves()[0]
    assert isinstance(first, Dataset)
    assert first.code
    assert first.title
    assert first.path
    result = await tasks.list_datasets_async(search="apro_mk_cola")
    assert result.data
    assert result.meta.published_at_naive is True


async def test_list_codes_upstream_statinfo_still_reads() -> None:
    """The STATINFO codelist upstream serves still reads as the refresh script reads it.

    One request through the package's client and the script's ``fetch_codelist``: the
    codes in order with their labels, the version and a ``LAST_UPDATED`` with a zone.
    """
    script = load_script()
    answer = await script.fetch_codelist("STATINFO")
    packaged = script.codelist_list(answer.codelist, answer.retrieved_at)
    info = script.codelist_info(answer.codelist)
    assert packaged.endpoint == "sdmx/2.1/codelist/ESTAT/STATINFO"
    assert packaged.records
    assert all(Code.model_validate(record).code for record in packaged.records)
    assert info.id == "STATINFO"
    assert info.version
    assert info.last_updated is not None
    assert datetime.fromisoformat(info.last_updated).utcoffset() is not None
    result = await tasks.list_codes_async("statinfo")
    assert result.data
    assert result.meta.vintage is not None


async def test_list_products_upstream_cxt_prodcom2_sold_still_reads() -> None:
    """The CXT_PRODCOM2_SOLD codelist still reads as the refresh script reads it.

    One request on the Comext base through the package's client and the script's
    ``fetch_codelist``: the codes in order with their labels, the full URL as
    ``endpoint``, ``product`` as ``param``, the version and a ``LAST_UPDATED`` with a zone.
    """
    script = load_script()
    answer = await script.fetch_codelist(params.PRODCOM_SOLD)
    packaged = script.codelist_list(answer.codelist, answer.retrieved_at)
    info = script.codelist_info(answer.codelist)
    assert packaged.endpoint == f"{COMEXT_BASE_URL}/sdmx/2.1/codelist/ESTAT/CXT_PRODCOM2_SOLD"
    assert packaged.param == "product"
    assert packaged.records
    assert all(Code.model_validate(record).code for record in packaged.records)
    assert info.id == params.PRODCOM_SOLD
    assert info.version
    assert info.last_updated is not None
    assert datetime.fromisoformat(info.last_updated).utcoffset() is not None
    result = await tasks.list_products_async(search="1041")
    assert result.data
    assert result.meta.vintage is not None


def _check_production(result: Result[list[Observation]], *, dataset: str, product: str) -> None:
    _check_slice(result)
    assert {observation.codes["reporter"] for observation in result.data} == {"AT"}
    assert {observation.codes["product"] for observation in result.data} == {product}
    assert {observation.codes["time"] for observation in result.data} == {"2023"}
    indicators = {code.code for code in params.codes(params.PRODCOM_INDICATORS.lower())}
    assert {observation.codes["indicators"] for observation in result.data} <= indicators
    assert result.meta.request["dataset"] == dataset


async def test_get_sold_production() -> None:
    """DS-059358 on the Comext base: Austria, product 10411200 (fish and marine oils), 2023."""
    result = await tasks.get_sold_production_async(
        "10411200", reporters=["AT"], since="2023", until="2023"
    )
    _check_production(result, dataset="DS-059358", product="10411200")


async def test_get_total_production() -> None:
    """DS-059359 on the Comext base: Austria, product 20158000 (animal or vegetable
    fertilisers), 2023."""
    result = await tasks.get_total_production_async(
        "20158000", reporters=["AT"], since="2023", until="2023"
    )
    _check_production(result, dataset="DS-059359", product="20158000")
