"""The SDMX 2.1 API's operations: ``codeListQuery`` (one codelist) and ``dataQuery`` (data).

Reference: ``docs/upstream/api/sdmx-rest.wadl``, resources under
``dissemination/sdmx/2.1/``.

``GET sdmx/2.1/codelist/{agencyID}/{resourceID}``: the resource
``codelist/{agencyID}/{resourceID}``, method ``GET`` with the id ``codeListQuery``, whose
query takes ``format``, ``lang``, ``compressed``, ``detail``, ``completestub`` and
``references``. The request's grammar is
``docs/upstream/user-guide/api-detailed-guidelines/sdmx2-1/structure-queries.md``:
``format`` "JSON for JSON-stat" (supported for codelists and dataflows only) and ``lang``
``en``, ``fr`` or ``de`` "Used for JSON or TSV response format", ``en`` by default; the
version, a path segment, is "latest" when left out. This wrapper sends ``format=JSON``
always, since the package reads no SDMX-ML (D44; design round Q3, 2026-10-27), and
leaves the version out, for the latest: the guide's other sentence, that a query
without a version returns "all existing versions", is not what a JSON-stat answer does,
which carries one version (``UNIT`` answered with 84.0 on 2026-10-27, newer than the
82.0 and 75.0 that the data structures of apro_mk_cola and ef_m_farmleg name). The
answer is one JSON-stat dimension (``models.Codelist``). Only
``scripts/refresh_reference.py`` calls this operation; ``list_codes`` answers from the
packaged codelists.

``GET sdmx/2.1/data/{flowRef}/{key}``: the resources ``data/{flowRef}`` and
``data/{flowRef}/{key}``, method ``GET`` with the id ``dataQuery`` on both, whose query
takes ``firstNObservations``, ``lastNObservations``, ``detail``, ``format``, ``lang``,
``compressed``, ``label`` and ``returnData``. The request's grammar is
``docs/upstream/user-guide/api-detailed-guidelines/sdmx2-1/data-query.md``:
``data/{resourceID}/{key}?{format}&{startPeriod}&{endPeriod}&{firstNObservations}&``
``{lastNObservations}&{detail}&{compressed}&{returnData}``, where

- the key "defines values of the dimensions in the order of structure", "a dot ('.')
  separated list of dimension filtered values": a dimension left empty is not filtered,
  and "Explicit listing of values for a dimension is done using the plus '+' character"
  (``A.CP_MEUR.B1GQ.BE+LU``); without a key, ``data/{flowRef}``, every dimension is
  unfiltered (``data/ef_m_farmleg`` answered the whole dataset on 2026-10-27);
- ``startPeriod`` and ``endPeriod`` filter on time (the guide's; the WADL lists
  neither), and ``lastNObservations`` is "The maximum number of observations to be
  returned for each of the matching series, counting back from the most recent
  observation";
- ``format`` ``SDMX-CSV`` is "SDMX-CSV 1.0 flat format", sent always, since the package
  reads no SDMX-ML (D44; design round Q2, 2026-10-27);
- ``compressed`` gives "responses in .gz compressed format": ``compressed=true``
  answered on 2026-10-27 with the same ``Content-Type``,
  ``application/vnd.sdmx.data+csv;version=1.0.0``, and a gzip file
  (``estat_apro_mk_cola_filtered_en.csv.gz``) that decompresses to the plain answer
  byte for byte (``tests/fixtures/dataQuery/``).

The answer is a file, streamed to disk with core's ``download`` and never held in
memory (ADR-0019); ``parse.sdmx_csv`` reads it. A large request is answered
asynchronously or refused with HTTP 413 (``asynchronous-api.md``), which
``_client.classify`` maps.
"""

import os
from datetime import datetime
from typing import Any, NamedTuple
from urllib.parse import quote

import httpx
from xippios.core import Downloaded, parse

from xippios.eurostat._client import SOURCE, client
from xippios.eurostat.models import Codelist

__all__ = [
    "CODELIST_ENDPOINT",
    "DATA_ENDPOINT",
    "DATA_FORMAT",
    "CodelistAnswer",
    "codeListQuery",
    "codelist_path",
    "dataQuery",
    "data_path",
]

CODELIST_ENDPOINT = "codeListQuery"
"""The codelist operation's name, the WADL's method id."""

DATA_ENDPOINT = "dataQuery"
"""The data operation's name, the WADL's method id."""

DATA_FORMAT = "SDMX-CSV"
"""The ``format`` ``dataQuery`` sends: "SDMX-CSV for SDMX-CSV 1.0 flat format"."""


def codelist_path(agency_id: str, resource_id: str) -> str:
    """The path of one codelist under the base URL, e.g. ``"sdmx/2.1/codelist/ESTAT/GEO"``.

    A packaged codelist's ``endpoint``.
    """
    return f"sdmx/2.1/codelist/{quote(agency_id, safe='')}/{quote(resource_id, safe='')}"


class CodelistAnswer(NamedTuple):
    """What ``codeListQuery`` returns.

    Attributes:
        codelist: The answer, parsed.
        payload: The answer as decoded, every member kept, for the refresh script's
            sample of it.
        retrieved_at: When the answer was retrieved, timezone-aware UTC: on a cache hit
            the time the entry was stored (``AsyncClient.get_answer``).
    """

    codelist: Codelist
    payload: dict[str, Any]
    retrieved_at: datetime


async def codeListQuery(
    agency_id: str, resource_id: str, *, lang: str | None = None
) -> CodelistAnswer:
    """Call ``codeListQuery``: the latest version of one codelist as JSON-stat.

    Args:
        agency_id: ``agencyID``, the maintaining agency, e.g. ``"ESTAT"``.
        resource_id: ``resourceID``, the codelist's id, e.g. ``"GEO"``.
        lang: ``lang``, the labels' language, e.g. ``"en"``; ``None`` leaves it out
            (upstream: ``en``).

    Returns:
        The codelist, the decoded answer and when it was retrieved.

    Raises:
        XippiosError: The taxonomy error for a refusal (an unknown codelist, say).
        ValidationError: The answer is not a JSON-stat dimension.
    """
    params: dict[str, str] = {"format": "JSON"}
    if lang is not None:
        params["lang"] = lang
    answer = await client.get_answer(f"/{codelist_path(agency_id, resource_id)}", params=params)
    codelist = parse(Codelist, answer.payload, source=SOURCE, endpoint=CODELIST_ENDPOINT)
    return CodelistAnswer(
        codelist=codelist, payload=answer.payload, retrieved_at=answer.retrieved_at
    )


def data_path(flow_ref: str, key: str = "") -> str:
    """The path of a data query under the base URL, its key segment as upstream takes it.

    E.g. ``"sdmx/2.1/data/apro_mk_cola/A...THS_T.AT"``: the key keeps its dots and plus
    signs, everything else in it percent-encoded; an empty key gives ``data/{flowRef}``
    without a key segment, e.g. ``"sdmx/2.1/data/ef_m_farmleg"``. A key that is a dot
    segment (``"."``, ``".."``) is a caller's to refuse: a URL resolves it away.
    """
    path = f"sdmx/2.1/data/{quote(flow_ref, safe='')}"
    return f"{path}/{quote(key, safe='.+')}" if key else path


async def dataQuery(
    flow_ref: str,
    dest: str | os.PathLike[str],
    *,
    key: str = "",
    start_period: str | None = None,
    end_period: str | None = None,
    last_n_observations: int | None = None,
    compressed: bool = False,
) -> Downloaded:
    """Call ``dataQuery``: stream a dataset, or a slice of it, as SDMX-CSV to ``dest``.

    Args:
        flow_ref: ``flowRef`` (the guide's ``resourceID``), the dataset's code, e.g.
            ``"apro_mk_cola"``.
        dest: The file to write, in a directory that exists, e.g.
            ``tmp_path / "apro_mk_cola.csv.gz"``.
        key: ``key``, the dimension values in structure order, dot-separated, ``+``
            between codes, e.g. ``"A...THS_T.AT"``; ``""`` sends none, for every code of
            every dimension.
        start_period: ``startPeriod``, e.g. ``"2022"``; ``None`` leaves it out.
        end_period: ``endPeriod``, e.g. ``"2023"``; ``None`` leaves it out.
        last_n_observations: ``lastNObservations``, e.g. ``2``; ``None`` leaves it out.
        compressed: ``compressed=true`` when set, for the answer as a gzip file; left
            out otherwise (upstream: uncompressed).

    Returns:
        The file written, with its size, content type, file name and when it was
        complete.

    Raises:
        ValueError: ``dest`` is a directory, or its directory does not exist; nothing is
            sent.
        XippiosError: The taxonomy error for a refusal, an asynchronous answer among
            them (``_client.classify``); ``dest`` is left untouched.
    """
    params: dict[str, str | int] = {"format": DATA_FORMAT}
    if start_period is not None:
        params["startPeriod"] = start_period
    if end_period is not None:
        params["endPeriod"] = end_period
    if last_n_observations is not None:
        params["lastNObservations"] = last_n_observations
    if compressed:
        params["compressed"] = "true"
    return await client.download(f"/{data_path(flow_ref, key)}?{httpx.QueryParams(params)}", dest)
