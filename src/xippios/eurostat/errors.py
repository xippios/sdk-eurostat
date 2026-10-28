"""Eurostat's refusals on the Statistics API: the fault model and its parsing.

``_client.classify`` maps them onto the family's taxonomy (conventions §5, ADR-0008); this
module only reads them. The shapes, from the user guide
(``docs/upstream/user-guide/api-detailed-guidelines/api-statistics.md``, "Error messages
returned in case of invalid queries", "The geoLevel parameter" and "Asynchronous response
in case of big extractions"; ``asynchronous-api.md`` beside it for the SOAP fault) and
from the answers recorded under ``tests/fixtures/get_data/``, on the main base on
2026-10-27 and on the Comext base on 2026-10-28:

- ``{"error": [{"status": 404, "id": 100, "label": "ERR_NOT_FOUND_4: ..."}]}``, an array
  of faults: recorded for an unknown dataset (HTTP 404, ``unknown_dataset.json``, and
  ``DS_unknown_dataset.json`` on the Comext base), an unknown dimension (HTTP 400, id
  150, ``unknown_dimension.json``) and ``geo`` together with ``geoLevel`` (HTTP 400, id
  400, ``geo_with_geo_level.json``).
- ``{"error": [{"status": 413, "id": 413, "label": "EXTRACTION_TOO_BIG: ..."}]}``, the
  same array at HTTP 413: recorded on the Comext base for a filter on a dimension the
  dataset lacks, which it counts unfiltered and judges too large, "estimated 151971120
  rows, max authorised is 5000000" (``DS-059358_unknown_dimension_too_big.json``), where
  the main base answers fault 150 at HTTP 400.
- ``{"error": {"status": "400", "label": "'geo' parameter and 'geoLevel' parameter ..."}}``,
  one fault as an object, its status as text and without an id: how the user guide
  documents the answer to ``geo`` with ``geoLevel``; the service answered that request
  with the array above when recorded, and both shapes are read.
- ``{"error": [{"status": 413, "id": 413, "label": "ASYNCHRONOUS_RESPONSE. Your request
  will be treated asynchronously. Please try again later."}]}``, the same array at HTTP
  413: the Statistics API's answer to a request the service will treat asynchronously,
  recorded on the Comext base on 2026-10-28 for DS-059341 and a CN8 code the dataset
  does not serve (``DS-059341_AT_DE_15071090_cn8_on_hs_flow.json``); its label, not its
  id or status, tells it from ``EXTRACTION_TOO_BIG``.
- ``{"warning": {"status": 413, "label": "ASYNCHRONOUS_RESPONSE. ..."}}``: the
  asynchronous answer as the user guide documents it, at an HTTP status the guide does
  not name; never seen. Four unfiltered requests on 2026-10-27 to datasets of 624,554 to
  853,146 values all answered synchronously, and probing stopped there (Johannes,
  2026-10-27); the answer recorded on 2026-10-28 came as the ``error`` array above. The
  SDMX API's asynchronous answer, an XML envelope, is recorded too (``_client.classify``).
- ``<S:Fault>`` with ``<faultcode>413</faultcode>`` and a ``<faultstring>`` such as
  ``EXTRACTION_TOO_BIG: The requested extraction is too big, ...``: the SOAP fault the
  guide documents for an SDMX request over the maximum extraction, recorded on the
  Comext base for one (``tests/fixtures/data_query/DS-045409_too_big_413.json``); read
  in case the Statistics API sends it too. Only the ``faultstring`` text is taken, with
  a regular expression on the body text: the package parses no XML at run time (D44).

The fault table's codes (``id``): 100 no results found (HTTP 400, "The result from the
query is empty", or HTTP 404, "The requested resource is not available"), 140 syntax
error and 150 semantic error (HTTP 400), 500 internal server error (HTTP 500).
"""

import json
import re
from typing import Any

import httpx
from pydantic import ValidationError as PydanticValidationError
from xippios.core import UpstreamModel

__all__ = [
    "AGAIN_LATER",
    "ASYNCHRONOUS_LABEL",
    "NARROW_HINT",
    "NO_RESULTS",
    "Fault",
    "asynchronous_fault",
    "error_faults",
    "fault_payload",
    "soap_faultstring",
    "warning_fault",
]

ASYNCHRONOUS_LABEL = "ASYNCHRONOUS_RESPONSE"
"""How the label of the asynchronous answer begins (api-statistics.md), in the documented
``warning`` and in the recorded ``error`` array alike."""

NO_RESULTS = 100
"""The fault code of "No results found" (the fault table)."""

NARROW_HINT = "narrow the query with fewer codes per dimension or a shorter period"
"""What a refusal of a too-large request tells the caller to do, in no task's terms:
``classify`` serves every task, whose parameters differ. It names no other task:
``download_dataset`` goes through the SDMX 2.1 data API, whose thresholds bind it as well
(``asynchronous-api.md``: asynchronous from 500,000 cells, refused over 5,000,000), and it
is Python-only, no tool an agent could be pointed to (conventions §8). The user guide's
advice for large extractions, the bulk download facility ("Fair use of the service"), is
another service this package does not wrap."""

AGAIN_LATER = (
    "the Statistics API prepares the answer meanwhile and does not say when it is ready: "
    "send the same request again later"
)
"""The Statistics API's own route for an asynchronous answer (``api-statistics.md``, its
last line: "the request must be made again to check its status")."""

_JSON_FAULT = re.compile(rb'\A\s*\{\s*"(?:error|warning)"')
"""A body that opens with an ``error`` or ``warning`` member; a JSON-stat answer opens
with ``version``, so a large cube is never decoded twice."""

_FAULTSTRING = re.compile(r"<faultstring>(.*?)</faultstring>", re.DOTALL)


class Fault(UpstreamModel):
    """One fault of an ``error`` or ``warning`` member.

    Attributes:
        status: The HTTP status the fault states, e.g. ``404``; upstream writes it as a
            number or as text (``"400"``), read as a number; ``None`` when absent.
        id: Eurostat's fault code, e.g. ``150`` (semantic error); ``None`` when the
            fault carries none, as in the documented single-object form.
        label: Upstream's text, e.g. ``"ERR_NOT_FOUND_4: NO_SUCH_DATASET
            (DATA_FLOW:ALL,1.0) is not available for dissemination."``.
    """

    status: int | None = None
    id: int | None = None
    label: str

    def describe(self) -> str:
        """The fault as one line: ``"fault 150: INVALID_QUERY_DIMENSION: ..."``."""
        return self.label if self.id is None else f"fault {self.id}: {self.label}"


def fault_payload(response: httpx.Response) -> dict[str, Any] | None:
    """The decoded body when it is an ``error`` or ``warning`` object, else ``None``.

    Only a body that opens with one of the two members is decoded; a cube, a body that
    is not JSON and a JSON value that is not an object give ``None``.
    """
    try:
        content = response.content
    except httpx.ResponseNotRead:
        return None
    if _JSON_FAULT.match(content[:256]) is None:
        return None
    try:
        payload = json.loads(content)
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None


def _fault(item: object) -> Fault | None:
    try:
        return Fault.model_validate(item)
    except PydanticValidationError:
        return None


def error_faults(payload: dict[str, Any]) -> list[Fault]:
    """The faults of the payload's ``error`` member, an array or one object; ``[]`` if none.

    An item that is not a fault (no ``label``) is left out.
    """
    error = payload.get("error")
    items = error if isinstance(error, list) else [error] if isinstance(error, dict) else []
    return [fault for fault in map(_fault, items) if fault is not None]


def warning_fault(payload: dict[str, Any]) -> Fault | None:
    """The payload's ``warning`` member as a fault, or ``None``."""
    warning = payload.get("warning")
    return _fault(warning) if isinstance(warning, dict) else None


def asynchronous_fault(payload: dict[str, Any]) -> Fault | None:
    """The fault saying the service will treat the request asynchronously, else ``None``.

    The ``warning`` member, as the user guide documents the answer, when its status is 413
    or its label starts ``ASYNCHRONOUS_LABEL``; else the first fault of the ``error``
    member whose label starts so, as the answer was recorded on 2026-10-28 (an ``error``
    array at HTTP 413, id 413). The label, not the id or the status, tells it from
    ``EXTRACTION_TOO_BIG``, which shares them.
    """
    warning = warning_fault(payload)
    if warning is not None and (
        warning.status == 413 or warning.label.startswith(ASYNCHRONOUS_LABEL)
    ):
        return warning
    return next(
        (fault for fault in error_faults(payload) if fault.label.startswith(ASYNCHRONOUS_LABEL)),
        None,
    )


def soap_faultstring(response: httpx.Response) -> str | None:
    """The ``faultstring`` of a SOAP fault body, whitespace collapsed, or ``None``."""
    try:
        text = response.text
    except (httpx.ResponseNotRead, UnicodeDecodeError):
        return None
    match = _FAULTSTRING.search(text)
    return " ".join(match.group(1).split()) if match else None
