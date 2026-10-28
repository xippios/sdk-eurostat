"""``GET statistics/1.0/data/{datasetCode}``: the Statistics API's data query, ``getData``.

Reference: ``docs/upstream/api/statistics-rest.wadl``, resource ``1.0/data/{datasetCode}``
under ``dissemination/statistics/``, method ``GET`` with the id ``getData``, answering
``application/json``: the operation's only name upstream gives (the OpenAPI document
``docs/upstream/api/sdmx-rest.yaml`` lists the path without an ``operationId``). The same
operation on the second base, for the ``DS-`` datasets of Comext and Prodcom, is
``docs/upstream/api/comext/statistics-rest.wadl``, the main one's but for its
``resources base`` (``comext/dissemination/statistics/``): a ``DS-`` code is requested
there, every other on the main base (``_client.url_for``;
``docs/upstream/user-guide/api-detailed-guidelines/prefixed-datasets.md``). The
request's grammar is ``docs/upstream/user-guide/api-detailed-guidelines/api-statistics.md``:
``{host_url}/statistics/1.0/data/{datasetCode}?{format}&{lang}&{filters}``, where

- ``format`` takes ``JSON`` only, sent always;
- ``lang`` is ``EN``, ``FR`` or ``DE``, ``EN`` when left out;
- a filter is ``DIMENSION_CODE=VALUE`` for any dimension of the dataset, in any order,
  case-insensitive, repeated for several values (``time=2022&time=2023``); ``time`` and
  ``time_period`` both address the time dimension;
- ``sinceTimePeriod``, ``untilTimePeriod`` and ``lastTimePeriod`` select time periods;
  only ``sinceTimePeriod`` and ``untilTimePeriod`` combine;
- ``geoLevel`` (``aggregate``, ``country``, ``nuts1``, ``nuts2``, ``nuts3``, ``city``)
  selects geo codes by level and excludes a ``geo`` filter.

The answer is one JSON-stat 2.0 dataset (``models.Cube``;
``docs/upstream/user-guide/api-getting-started/api.md``). Refusals are mapped once in
``_client.classify``; this wrapper inspects no status.
"""

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import NamedTuple
from urllib.parse import quote

from xippios.core import parse

from xippios.eurostat._client import SOURCE, client, url_for
from xippios.eurostat.models import Cube, GeoLevel, Lang

__all__ = ["DataAnswer", "get_data"]

ENDPOINT = "getData"
"""The operation's name, the WADL's method id."""


class DataAnswer(NamedTuple):
    """What ``get_data`` returns: the cube and what the task's ``meta`` needs.

    Attributes:
        cube: The answer, parsed.
        updated: The ``updated`` member as upstream printed it, e.g.
            ``"2026-10-05T23:00:00+0200"``; ``None`` when the answer has none.
        retrieved_at: When the answer was retrieved, timezone-aware UTC: on a cache hit
            the time the entry was stored, else the time the answer arrived
            (``AsyncClient.get_answer``); the task's ``meta.retrieved_at``.
    """

    cube: Cube
    updated: str | None
    retrieved_at: datetime


async def get_data(
    dataset_code: str,
    *,
    lang: Lang | None = None,
    filters: Mapping[str, str | Sequence[str]] | None = None,
    since_time_period: str | None = None,
    until_time_period: str | None = None,
    last_time_period: int | None = None,
    geo_level: GeoLevel | None = None,
) -> DataAnswer:
    """Call ``getData``: one dataset, or a slice of it, as a JSON-stat cube.

    Args:
        dataset_code: ``datasetCode``, the dataset's online data code, e.g.
            ``"apro_mk_cola"``, or a Comext or Prodcom code, requested on the Comext
            base, e.g. ``"DS-059358"``.
        lang: ``lang``, e.g. ``Lang.FR``; ``None`` leaves it out (upstream: ``EN``).
        filters: ``DIMENSION_CODE=VALUE`` filters, a dimension code to one code or a
            sequence of codes, each sent as a parameter of its own, e.g.
            ``{"geo": "AT", "time": ["2022", "2023"]}``.
        since_time_period: ``sinceTimePeriod``, e.g. ``"2022"``.
        until_time_period: ``untilTimePeriod``, e.g. ``"2023"``.
        last_time_period: ``lastTimePeriod``, e.g. ``2``.
        geo_level: ``geoLevel``, e.g. ``GeoLevel.COUNTRY``.

    Returns:
        The cube, the ``updated`` text as printed and when the answer was retrieved.

    Raises:
        NotFoundError: No such dataset (HTTP 404).
        InvalidRequestError: Upstream refused the query (HTTP 400), will answer it
            asynchronously, or judged it too large (HTTP 413).
    """
    params: dict[str, str | int | list[str]] = {"format": "JSON"}
    if lang is not None:
        params["lang"] = str(lang)
    for code, values in (filters or {}).items():
        params[code] = values if isinstance(values, str) else list(values)
    if since_time_period is not None:
        params["sinceTimePeriod"] = since_time_period
    if until_time_period is not None:
        params["untilTimePeriod"] = until_time_period
    if last_time_period is not None:
        params["lastTimePeriod"] = last_time_period
    if geo_level is not None:
        params["geoLevel"] = str(geo_level)
    path = f"/statistics/1.0/data/{quote(dataset_code, safe='')}"
    answer = await client.get_answer(url_for(dataset_code, path), params=params)
    updated = answer.payload.get("updated") if isinstance(answer.payload, dict) else None
    cube = parse(Cube, answer.payload, source=SOURCE, endpoint=ENDPOINT)
    return DataAnswer(
        cube=cube,
        updated=updated if isinstance(updated, str) else None,
        retrieved_at=answer.retrieved_at,
    )
