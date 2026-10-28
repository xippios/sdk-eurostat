"""``GET sdmx/2.1/codelist/{agencyID}/{resourceID}``: one codelist, ``codeListQuery``.

Reference: ``docs/upstream/api/sdmx-rest.wadl``, resource
``codelist/{agencyID}/{resourceID}`` under ``dissemination/sdmx/2.1/``, method ``GET``
with the id ``codeListQuery``, whose query takes ``format``, ``lang``, ``compressed``,
``detail``, ``completestub`` and ``references``. The request's grammar is
``docs/upstream/user-guide/api-detailed-guidelines/sdmx2-1/structure-queries.md``:
``format`` "JSON for JSON-stat" (supported for codelists and dataflows only) and ``lang``
``en``, ``fr`` or ``de`` "Used for JSON or TSV response format", ``en`` by default; the
version, a path segment, is "latest" when left out. This wrapper sends ``format=JSON``
always, since the package reads no SDMX-ML (D44; design round Q3, 2026-10-27), and
leaves the version out, for the latest: the guide's other sentence, that a query
without a version returns "all existing versions", is not what a JSON-stat answer does,
which carries one version (``UNIT`` answered with 84.0 on 2026-10-27, newer than the
82.0 and 75.0 that the data structures of apro_mk_cola and ef_m_farmleg name).

The answer is one JSON-stat dimension (``models.Codelist``). Only
``scripts/refresh_reference.py`` calls this operation; ``list_codes`` answers from the
packaged codelists.
"""

from datetime import datetime
from typing import Any, NamedTuple
from urllib.parse import quote

from xippios.core import parse

from xippios.eurostat._client import SOURCE, client
from xippios.eurostat.models import Codelist

__all__ = ["ENDPOINT", "CodelistAnswer", "codeListQuery", "codelist_path"]

ENDPOINT = "codeListQuery"
"""The operation's name, the WADL's method id."""


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
    codelist = parse(Codelist, answer.payload, source=SOURCE, endpoint=ENDPOINT)
    return CodelistAnswer(
        codelist=codelist, payload=answer.payload, retrieved_at=answer.retrieved_at
    )
