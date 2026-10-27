"""``parse_sdmx_csv``: an SDMX-CSV 1.0 file, plain or gzip-compressed, one row at a time.

The file kind ``sdmx-csv``: the SDMX 2.1 API's answer to ``format=SDMX-CSV``, "SDMX-CSV
1.0 flat format" (the user guide's ``sdmx2-1/data-query.md``), as ``download_dataset``
writes it. The layout, from the guide's examples and the sample
``docs/upstream/samples/apro_mk_cola-sdmx-csv.csv``: a header row, then one row per
observation, comma-separated, lines ending in CRLF::

    DATAFLOW,LAST UPDATE,freq,milkitem,dairyprod,unit,geo,TIME_PERIOD,OBS_VALUE,...
    ESTAT:APRO_MK_COLA(1.0),05/10/26 23:00:00,A,PRD,D1110D,THS_T,AT,2022,3247.05,,

``DATAFLOW`` and ``LAST UPDATE`` come first, the dataset's dimensions in structure order
up to ``TIME_PERIOD``, then ``OBS_VALUE`` and the observation's attributes, which differ
by dataset (``OBS_FLAG`` and ``CONF_STATUS`` in apro_mk_cola; ``OBS_FLAG``,
``LTAA_FLAG`` and ``LTAA`` in the guide's ENV_WAT_RES). Each row becomes a
``models.SdmxCsvRow`` with nothing renamed or computed (ADR-0020 decision 2);
``OBS_VALUE`` is parsed as a ``Decimal``.

A plain file is read through core's ``decode_csv`` (ADR-0019 decision 2). A file that
starts with gzip's magic bytes, as ``compressed=true`` answers, is opened with the
standard library's ``gzip`` and read with its ``csv.DictReader`` as ``decode_csv`` reads
a path (UTF-8, a byte order mark stripped, headers as printed), since ``decode_csv``
takes a path or a response, not an open stream: a decompressed copy on disk would write
the whole file again before its first row could be read. Either way the rows are read
lazily, never the whole file at once.
"""

import csv
import gzip
import os
import zlib
from collections.abc import Generator, Iterator
from pathlib import Path
from typing import Any

import pydantic
from xippios.core import ValidationError, parse
from xippios.core.client import decode_csv

from xippios.eurostat._client import SOURCE
from xippios.eurostat.models import SdmxCsvRow

__all__ = ["FILE_KIND", "parse_sdmx_csv"]

FILE_KIND = "sdmx-csv"
"""The file kind, named in a parse error."""

GZIP_MAGIC = b"\x1f\x8b"
"""The first two bytes of a gzip file (RFC 1952)."""

LEADING = ("DATAFLOW", "LAST UPDATE")
"""The columns that open every SDMX-CSV header, in order."""

TIME_PERIOD = "TIME_PERIOD"
OBS_VALUE = "OBS_VALUE"
NAMED_ATTRIBUTES = ("OBS_FLAG", "CONF_STATUS")
"""The attribute columns ``SdmxCsvRow`` has a field for; any other goes to ``attributes``."""


def _refuse(path: Path, reason: str) -> ValidationError:
    return ValidationError(f"{SOURCE} {FILE_KIND}: {path.name} {reason}", raw="", source=SOURCE)


def _gzip_records(path: Path) -> Iterator[dict[str, str]]:
    """The rows of a gzip-compressed CSV file, as ``decode_csv`` gives a plain file's."""
    try:
        with gzip.open(path, "rt", encoding="utf-8-sig", newline="") as text:
            yield from csv.DictReader(text)
    except UnicodeDecodeError as exc:
        raise _refuse(path, f"is not UTF-8 text once decompressed: {exc.reason}") from None
    except csv.Error as exc:
        raise _refuse(path, f"is not CSV the csv module reads: {exc}") from None
    except (gzip.BadGzipFile, EOFError, zlib.error) as exc:
        raise _refuse(path, f"is not a whole gzip file: {exc}") from None


def _records(path: Path) -> Iterator[dict[str, str]]:
    """The rows of ``path`` as text mappings, gzip told by its first two bytes."""
    with path.open("rb") as handle:
        packed = handle.read(len(GZIP_MAGIC)) == GZIP_MAGIC
    return _gzip_records(path) if packed else decode_csv(path, source=SOURCE)


class _Layout:
    """Where a header puts the dimensions and the attributes, read from the first row."""

    def __init__(self, path: Path, columns: list[str]) -> None:
        if (
            tuple(columns[: len(LEADING)]) != LEADING
            or TIME_PERIOD not in columns
            or OBS_VALUE not in columns
            or columns.index(OBS_VALUE) != columns.index(TIME_PERIOD) + 1
        ):
            raise _refuse(
                path,
                "does not have SDMX-CSV's columns: DATAFLOW, LAST UPDATE, the dimensions, "
                f"TIME_PERIOD, OBS_VALUE, the attributes; its header is {', '.join(columns)}",
            )
        time = columns.index(TIME_PERIOD)
        self.dimensions = columns[len(LEADING) : time]
        self.named = [name for name in NAMED_ATTRIBUTES if name in columns]
        self.attributes = [name for name in columns[time + 2 :] if name not in NAMED_ATTRIBUTES]

    def raw(self, record: dict[str, Any]) -> dict[str, Any]:
        """The row as ``SdmxCsvRow`` validates it, under upstream's headers."""
        return {
            "DATAFLOW": record["DATAFLOW"],
            "LAST UPDATE": record["LAST UPDATE"],
            "dimensions": {name: record[name] for name in self.dimensions},
            TIME_PERIOD: record[TIME_PERIOD],
            OBS_VALUE: record[OBS_VALUE] or None,
            **{name: record[name] or None for name in self.named},
            "attributes": {name: record[name] or None for name in self.attributes},
        }


def parse_sdmx_csv(path: str | os.PathLike[str]) -> Generator[SdmxCsvRow, None, None]:
    """Read an SDMX-CSV file row by row, each row one ``SdmxCsvRow``.

    Plain or gzip-compressed, told by the file's first two bytes, not by its name. A
    generator: the file is read as the rows are taken and closed when the generator ends
    or is closed; ``list(parse_sdmx_csv(path))`` reads it all. A file with a header and
    no row yields nothing.

    Args:
        path: The file, e.g. ``result.data.path`` of ``download_dataset``, or
            ``"apro_mk_cola.csv.gz"``.

    Raises:
        ValidationError: The file is not SDMX-CSV: its header lacks the columns above in
            their order, a row has more or fewer values than the header, a value of
            ``OBS_VALUE`` is not a number, the text is not UTF-8 or not CSV, or a gzip
            file is cut short or damaged. Raised at the row where it is found.
    """
    file = Path(path)
    layout: _Layout | None = None
    for line, record in enumerate(_records(file), start=2):
        if None in record or None in record.values():
            raise _refuse(file, f"has a row, line {line}, whose values do not match its header")
        if layout is None:
            layout = _Layout(file, list(record))
        raw = layout.raw(record)
        try:
            yield SdmxCsvRow.model_validate(raw)
        except pydantic.ValidationError:
            yield parse(SdmxCsvRow, raw, source=SOURCE, endpoint=f"{FILE_KIND} line {line}")
