"""Live smoke tests, one per task, skipped unless XIPPIOS_LIVE_TESTS=1 (conventions §10).

``/add-endpoint`` adds them.

``get_data`` has one per dataset chosen when the package started
(https://github.com/xippios/sdk-eurostat/pull/1), each the small slice its fixture holds:
``apro_mk_cola`` (milk collection), ``apro_cpnh1`` (crop production) and
``ef_m_farmleg`` (farm indicators by legal status), Austria, two periods.
The list tasks answer from the packaged lists, so theirs check upstream's side: that the
answers ``scripts/refresh_reference.py`` packages still read as it reads them, through
the script's own functions; ``list_datasets``'s reads the start of the table of contents
only (its test says why), ``list_codes``'s fetches the STATINFO codelist through the
script's declared fetch.
``download_dataset``'s downloads the slice its fixture holds, apro_mk_cola for Austria in
thousand tonnes, 2022 and 2023, to a temporary file and reads it with ``parse_sdmx_csv``,
the live parser test of the file kind ``sdmx-csv`` (sdk-core ADR-0020 decision 6).
``get_data`` has one more on the Comext base, the smallest slice of the Prodcom dataset
``DS-059358`` (Austria, one product, the latest period), which is also the nightly's
check that the Comext base answers.

Core's nightly comparison, collected by the star import below, compares each of the
eighteen packaged codelists, declared in ``LIVE_LISTS``, with the codelist that
``codeListQuery`` serves now, through the script's declared fetch, one request each
(sdk-core ADR-0055); the table of contents stands in ``NO_LIVE_LIST`` with its reason.
Core's testing plugin prints the run's requests as ``requests sent by the live run: <n>``,
the count that ``live.yml``'s log holds. The tests send no key. They assert shape and
release metadata, never values, which Eurostat revises twice a day, nor which period is
the latest.
"""

import importlib.util
import re
from collections.abc import Awaitable, Callable
from datetime import date, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import httpx
import pytest
from xippios.core import PackagedCodes, Result
from xippios.core.testing.live import *  # noqa: F403

from xippios.eurostat import params, tasks
from xippios.eurostat._client import BASE_URL, config
from xippios.eurostat.api import catalogue
from xippios.eurostat.models import Code, Cube, Dataset, SdmxCsvRow
from xippios.eurostat.parse import parse_sdmx_csv

pytestmark = [pytest.mark.live, pytest.mark.anyio]

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "refresh_reference.py"


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("refresh_reference", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


script = load_script()


def _live_codes(resource_id: str) -> Callable[[], Awaitable[list[dict[str, Any]]]]:
    """The records of ``resource_id`` as the refresh packages them from its answer now."""

    async def fetch() -> list[dict[str, Any]]:
        packaged = await script.fetch_codelist(resource_id)
        records: list[dict[str, Any]] = packaged.records
        return records

    return fetch


LIVE_LISTS: dict[str, tuple[PackagedCodes, Callable[[], Awaitable[list[dict[str, Any]]]]]] = {
    resource_id.lower(): (
        params.packaged(resource_id.lower()).codes("code", "label"),
        _live_codes(resource_id),
    )
    for resource_id in params.CODELISTS
}
"""The eighteen packaged codelists, each compared with upstream's codelist each night by
its codes and their labels (sdk-core ADR-0055)."""
NO_LIVE_LIST: dict[str, str] = {
    params.TOC: (
        "Each leaf of the table of contents carries its dataset's lastUpdate, dataEnd and "
        "values, which change whenever Eurostat updates the data, twice a day, so a nightly "
        "comparison of it would fail every night."
    ),
}
"""The table of contents, not compared: its start is read by
``test_list_datasets_upstream_toc_still_reads``."""

UPDATED = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{4}$")
"""``updated`` as Eurostat prints it, e.g. ``2026-10-05T23:00:00+0200``."""

LAST_UPDATE = re.compile(r"^\d{2}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}$")
"""SDMX-CSV's ``LAST UPDATE`` as Eurostat prints it, e.g. ``05/10/26 23:00:00``."""


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
    result = await tasks.get_data_async(
        "apro_mk_cola", filters={"geo": "AT", "time": ["2022", "2023"]}
    )
    _check(result, periods=2)


async def test_get_data_apro_cpnh1() -> None:
    result = await tasks.get_data_async(
        "apro_cpnh1", filters={"geo": "AT"}, since_time_period="2022", until_time_period="2023"
    )
    _check(result, periods=2)


async def test_get_data_ef_m_farmleg() -> None:
    result = await tasks.get_data_async(
        "ef_m_farmleg", filters={"geo": "AT", "unit": "HLD"}, last_time_period=2
    )
    _check(result, periods=2)


async def test_get_data_ds_059358() -> None:
    """Prodcom's DS-059358 on the Comext base: Austria, product 10411200 (fats and oils of
    fish or marine mammals, NACE 10.41), the latest period."""
    result = await tasks.get_data_async(
        "DS-059358", filters={"reporter": "AT", "product": "10411200"}, last_time_period=1
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


async def test_download_dataset_apro_mk_cola(tmp_path: Path) -> None:
    dest = tmp_path / "milk.csv.gz"
    result = await tasks.download_dataset_async(
        "apro_mk_cola", "A...THS_T.AT", start_period="2022", end_period="2023", dest=dest
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
    assert result.meta.vintage is not None
    assert LAST_UPDATE.fullmatch(result.meta.vintage)
    assert result.meta.published_at is not None
    assert result.meta.published_at == rows[0].last_update
    assert result.meta.published_at.tzinfo is None
    assert result.meta.published_at_naive is True
    assert result.meta.request["key"] == "A...THS_T.AT"


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
    parser = script.TocParser()
    async with (
        httpx.AsyncClient(
            headers={"User-Agent": config.user_agent},
            timeout=httpx.Timeout(10.0, read=config.read_timeout),
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
    assert isinstance(first.last_update, date), "printed day first, read into a date"
    result = await tasks.list_datasets_async(search="apro_mk_cola")
    assert result.data
    assert result.meta.published_at_naive is True


async def test_list_codes_upstream_statinfo_still_reads() -> None:
    """The STATINFO codelist upstream serves still reads as the refresh script reads it.

    One request through the package's client and the script's ``fetch_codelist``, the
    fetch its declaration hands core's frame: the codes in order with their labels, the
    version and a ``LAST_UPDATED`` with a zone, which the script keeps for ``lists.json``.
    """
    script.RUN.start(samples=False)
    packaged = await script.fetch_codelist("STATINFO")
    info = script.RUN.infos["statinfo"]
    script.RUN.start(samples=False)
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
