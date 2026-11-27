"""``parse_sdmx_csv``: an SDMX-CSV 1.0 file, plain or gzip-compressed, one row at a time.

The file kind ``sdmx-csv``: the SDMX 2.1 API's answer to ``format=SDMX-CSV``, "SDMX-CSV
1.0 flat format" (the user guide's ``sdmx2-1/data-query.md``), as ``download_dataset``
writes it. The layout, from the guide's examples and the sample
``docs/upstream/samples/apro_mk_cola-sdmx-csv.csv``: a header row, then one row per
observation, comma-separated, lines ending in CRLF::

    DATAFLOW,LAST UPDATE,freq,milkitem,dairyprod,unit,geo,TIME_PERIOD,OBS_VALUE,...
    ESTAT:APRO_MK_COLA(1.0),05/11/26 11:00:00,A,PRD,D1110D,THS_T,AT,2022,3247.05,,

``DATAFLOW`` and ``LAST UPDATE`` come first, the dataset's dimensions in structure order
up to ``TIME_PERIOD``, then ``OBS_VALUE`` and the observation's attributes, which differ
by dataset (``OBS_FLAG`` and ``CONF_STATUS`` in apro_mk_cola; ``OBS_FLAG``,
``LTAA_FLAG`` and ``LTAA`` in the guide's ENV_WAT_RES; none in Prodcom's DS-059358).
Each row becomes a ``models.SdmxCsvRow`` with nothing renamed (sdk-core ADR-0020
decision 2); ``OBS_VALUE`` is kept as printed, a number or a text such as Prodcom's units
and flags (``"KG"``, ``":E"``, ``docs/upstream/samples/DS-059358-sdmx-csv.csv``), with its
reading as a number beside it, and ``LAST UPDATE`` is read into a naive time, whose text
``last_update_as_printed`` gives for ``meta.vintage``.

The header row is read first, with the standard library's ``csv``, and checked before
any row, so a file of another layout is refused even without rows. The rows of both files
are then read through core's ``decode_csv`` (sdk-core ADR-0040 decision 2): a plain file by its
path, and a file that starts with gzip's magic bytes, as ``compressed=true`` answers, as
the text stream the standard library's ``gzip`` opens on it (UTF-8, a byte order mark
stripped, headers as printed), never as a decompressed copy on disk, which would write the
whole file again before its first row could be read (the gzip branch of
https://github.com/xippios/sdk-eurostat/pull/7). Either way the rows are read lazily,
never the whole file at once.
"""

import csv
import gzip
import os
import zlib
from collections.abc import Generator, Iterator
from contextlib import closing, contextmanager
from pathlib import Path
from typing import IO, Any

import pydantic
from xippios.core import ValidationError, parse
from xippios.core.client import decode_csv

from xippios.eurostat._client import SOURCE
from xippios.eurostat.models import SdmxCsvRow

__all__ = ["FILE_KIND", "last_update_as_printed", "parse_sdmx_csv"]

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
    """A refusal worded as ``decode_csv`` words its own: ``"eurostat: <file> <reason>"``."""
    return ValidationError(f"{SOURCE}: {path.name} {reason}", raw="", source=SOURCE)


def _is_gzip(path: Path) -> bool:
    with path.open("rb") as handle:
        return handle.read(len(GZIP_MAGIC)) == GZIP_MAGIC


def _text(path: Path, packed: bool) -> IO[str]:
    """The file as text, UTF-8 with a byte order mark stripped, decompressed if ``packed``."""
    if packed:
        return gzip.open(path, "rt", encoding="utf-8-sig", newline="")
    return path.open(encoding="utf-8-sig", newline="")


@contextmanager
def _reading(path: Path) -> Iterator[None]:
    """Map what reading the file as CSV can raise to ``ValidationError``, as ``decode_csv``."""
    try:
        yield
    except UnicodeDecodeError as exc:
        raise _refuse(path, f"is not UTF-8 text: {exc.reason}") from None
    except csv.Error as exc:
        raise _refuse(path, f"is not CSV the csv module reads: {exc}") from None
    except (gzip.BadGzipFile, EOFError, zlib.error) as exc:
        raise _refuse(path, f"is not a whole gzip file: {exc}") from None


def _header(path: Path, packed: bool) -> list[str] | None:
    """The header row as printed, or ``None`` for an empty file."""
    with _reading(path), _text(path, packed) as text:
        return next(csv.reader(text), None)


def _gzip_records(path: Path) -> Iterator[dict[str, str]]:
    """The rows of a gzip-compressed CSV file, read by ``decode_csv`` from its open stream.

    ``_reading`` maps what the gzip stream raises, a cut or damaged file; ``decode_csv``
    words the text's and the CSV's errors by the file's name, as for a plain file.
    """
    with _reading(path), _text(path, packed=True) as text:
        yield from decode_csv(text, source=SOURCE)


class _Layout:
    """Where a header puts the dimensions and the attributes, checked before any row."""

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


def _rows(file: Path) -> Generator[tuple[int, dict[str, Any]], None, None]:
    """Each row with its line, as ``SdmxCsvRow`` validates it, under upstream's headers.

    The header is checked first, before any row; an empty file, or one with a header and
    no row, yields nothing.

    Raises:
        ValidationError: As ``parse_sdmx_csv`` raises it, but for a row that ``SdmxCsvRow``
            refuses.
    """
    packed = _is_gzip(file)
    columns = _header(file, packed)
    if columns is None:
        return
    layout = _Layout(file, columns)
    records = _gzip_records(file) if packed else decode_csv(file, source=SOURCE)
    for line, record in enumerate(records, start=2):
        if None in record or None in record.values():
            raise _refuse(file, f"has a row, line {line}, whose values do not match its header")
        yield line, layout.raw(record)


def parse_sdmx_csv(path: str | os.PathLike[str]) -> Generator[SdmxCsvRow, None, None]:
    """Read an SDMX-CSV file row by row, each row one ``SdmxCsvRow``.

    Plain or gzip-compressed, told by the file's first two bytes, not by its name. A
    generator: the file is read as the rows are taken and closed when the generator ends
    or is closed; ``list(parse_sdmx_csv(path))`` reads it all. The header is checked
    first, before any row; a file with a header and no row, or an empty one, yields
    nothing.

    Args:
        path: The file, e.g. ``result.data.path`` of ``download_dataset``, or
            ``"apro_mk_cola.csv.gz"``.

    Raises:
        ValidationError: The file is not SDMX-CSV: its header lacks the columns above in
            their order, a row has more or fewer values than the header or prints its
            ``LAST UPDATE`` in another form than ``models.LAST_UPDATE``, the text is not
            UTF-8 or not CSV, or a gzip file is cut short or damaged. Raised when the
            header is read, or at the row where it is found.
    """
    for line, raw in _rows(Path(path)):
        try:
            yield SdmxCsvRow.model_validate(raw)
        except pydantic.ValidationError:
            yield parse(SdmxCsvRow, raw, source=SOURCE, endpoint=f"{FILE_KIND} line {line}")


def last_update_as_printed(path: str | os.PathLike[str]) -> str | None:
    """The first row's ``LAST UPDATE`` as Eurostat printed it, e.g. ``"05/10/26 23:00:00"``.

    ``SdmxCsvRow.last_update`` reads it into a time and keeps no text beside it, while
    ``meta.vintage`` of ``download_dataset`` is the release as upstream states it
    (conventions §4), so the text is read from the row as the file holds it. ``None`` for
    a file without a row.

    Raises:
        ValidationError: As ``parse_sdmx_csv`` raises it for the header and the first row.
    """
    with closing(_rows(Path(path))) as rows:
        first = next(rows, None)
    return None if first is None else str(first[1]["LAST UPDATE"])
