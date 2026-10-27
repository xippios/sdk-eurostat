"""Live smoke tests: skipped unless XIPPIOS_LIVE_TESTS=1 (conventions §10).

Every task function gets one live smoke test here, next to the reachability check.
``get_data`` has one per dataset of the design round's question 6 (2026-10-27), each the
small slice its fixture holds: ``apro_mk_cola`` (milk collection), ``apro_cpnh1`` (crop
production) and ``ef_m_farmleg`` (farm indicators by legal status), Austria, two periods.
A run sends four keyless requests, the reachability check included. The tests assert
shape and release metadata, never values, which Eurostat revises twice a day.
"""

import re

import httpx
import pytest
from xippios.core import Result

from xippios.eurostat import tasks
from xippios.eurostat._client import BASE_URL, config
from xippios.eurostat.models import Cube

pytestmark = [pytest.mark.live, pytest.mark.anyio]

UPDATED = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{4}$")
"""``updated`` as Eurostat prints it, e.g. ``2026-10-05T23:00:00+0200``."""


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
