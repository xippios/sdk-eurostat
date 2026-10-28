"""``parse_sdmx_csv`` on the SDMX-CSV samples and on the user guide's documented layouts.

The samples under ``tests/fixtures/files/sdmx-csv/`` are the response bodies of the
recorded ``dataQuery`` exchanges (``tests/fixtures/data_query/``), plain and
``compressed=true``, byte for byte, which the first test checks: apro_mk_cola on the main
base, and Prodcom's DS-059358 on the Comext base, whose ``OBS_VALUE`` is text where the
indicator is a unit or a flag (``KG``, ``:E``) and which has no attribute column;
``tests/fixtures/files/README.md`` gives their provenance (ADR-0020 decision 6). The
tests assert the parser's shape against the sample's own text, read here with the
standard library's ``csv``, never values or sizes typed into a test (conventions §10).
``test_documented_shape_*`` read the user guide's SDMX-CSV examples verbatim from the
snapshot at test time, neither recorded nor hand-written: a dataset whose attributes
differ from apro_mk_cola's. ``NOT RECORDED`` marks a sample changed in memory to show a
refusal.
"""

import csv
import gzip
import hashlib
import inspect
import io
import re
from decimal import Decimal
from pathlib import Path

import pytest
from xippios.core import ValidationError
from xippios.core.testing import load_fixture

from xippios.eurostat.models import SdmxCsvRow
from xippios.eurostat.parse import parse_sdmx_csv

TESTS = Path(__file__).parent
FIXTURES = TESTS / "fixtures"
SAMPLES = FIXTURES / "files" / "sdmx-csv"
PLAIN = SAMPLES / "apro_mk_cola_AT_THS_T_2022_2023.csv"
PACKED = SAMPLES / "apro_mk_cola_AT_THS_T_2022_2023.csv.gz"
PRODCOM_PLAIN = SAMPLES / "DS-059358_A_AT_10411200_2022_2023.csv"
PRODCOM_PACKED = SAMPLES / "DS-059358_A_AT_10411200_2022_2023.csv.gz"
RECORDED = {
    PLAIN: FIXTURES / "data_query" / "apro_mk_cola_AT_THS_T_2022_2023.json",
    PACKED: FIXTURES / "data_query" / "apro_mk_cola_AT_THS_T_2022_2023_compressed.json",
    PRODCOM_PLAIN: FIXTURES / "data_query" / "DS-059358_A_AT_10411200_2022_2023.json",
    PRODCOM_PACKED: FIXTURES / "data_query" / "DS-059358_A_AT_10411200_2022_2023_compressed.json",
}
PAIRS = [(PLAIN, PACKED), (PRODCOM_PLAIN, PRODCOM_PACKED)]
DATA_QUERY = TESTS.parents[0] / "docs/upstream/user-guide/api-detailed-guidelines/sdmx2-1"


def text_of(sample: Path) -> str:
    """The sample's text, decompressed when it is the gzip file."""
    data = sample.read_bytes()
    return (gzip.decompress(data) if sample.suffix == ".gz" else data).decode("utf-8")


def table_of(text: str) -> tuple[list[str], list[list[str]]]:
    """The header and the rows of an SDMX-CSV text, as the standard library reads them."""
    header, *rows = csv.reader(io.StringIO(text, newline=""))
    return header, rows


def test_samples_are_the_recorded_bodies() -> None:
    readme = (FIXTURES / "files" / "README.md").read_text(encoding="utf-8")
    for sample, fixture in RECORDED.items():
        body = load_fixture(fixture).response.content
        assert sample.read_bytes() == body, "the sample is the recorded body, byte for byte"
        row = f"| `{sample.relative_to(FIXTURES / 'files')}` |"
        assert row in readme
        line = next(line for line in readme.splitlines() if line.startswith(row))
        assert f"| {len(body)} | `{hashlib.sha256(body).hexdigest()}` |" in line
        assert f"| {load_fixture(fixture).request.url} |" in line
    for plain, packed in PAIRS:
        assert load_fixture(RECORDED[packed]).response.body_base64 is True
        assert packed.read_bytes()[:2] == b"\x1f\x8b", "a gzip file, as compressed=true sends it"
        assert gzip.decompress(packed.read_bytes()) == plain.read_bytes()


@pytest.mark.parametrize("sample", [PLAIN, PACKED], ids=["plain", "gzip"])
def test_parse_sdmx_csv_reads_every_row_as_printed(sample: Path) -> None:
    header, table = table_of(text_of(sample))
    time = header.index("TIME_PERIOD")
    rows = list(parse_sdmx_csv(sample))
    assert len(rows) == len(table), "one row per data line, none dropped"
    for row, cells in zip(rows, table, strict=True):
        record = dict(zip(header, cells, strict=True))
        assert isinstance(row, SdmxCsvRow)
        assert row.dataflow == record["DATAFLOW"]
        assert row.last_update == record["LAST UPDATE"]
        assert list(row.dimensions) == header[2:time], "the dimensions in column order"
        assert list(row.dimensions.values()) == cells[2:time]
        assert row.time_period == record["TIME_PERIOD"]
        if record["OBS_VALUE"]:
            assert isinstance(row.obs_value, Decimal)
            assert row.obs_value == Decimal(record["OBS_VALUE"])
            assert str(row.obs_value) == record["OBS_VALUE"], "the number as printed"
        else:
            assert row.obs_value is None
        assert row.obs_flag == (record["OBS_FLAG"] or None)
        assert row.conf_status == (record["CONF_STATUS"] or None)
        assert row.attributes == {}, "apro_mk_cola's attributes are OBS_FLAG and CONF_STATUS"
    empty = [row for row in rows if row.obs_value is None]
    assert empty, "the sample holds a cell without a value"
    assert all(row.conf_status for row in empty), "each with its confidentiality status"


@pytest.mark.parametrize(("plain", "packed"), PAIRS, ids=["main", "comext"])
def test_parse_sdmx_csv_reads_gzip_and_plain_alike(plain: Path, packed: Path) -> None:
    assert list(parse_sdmx_csv(packed)) == list(parse_sdmx_csv(plain))


@pytest.mark.parametrize("sample", [PRODCOM_PLAIN, PRODCOM_PACKED], ids=["plain", "gzip"])
def test_parse_sdmx_csv_keeps_prodcom_text_values_as_printed(sample: Path) -> None:
    """DS-059358's ``indicators`` mix measures with units and flags, and ``OBS_VALUE``
    prints them as text: a number is parsed, a text is kept as printed. Its header ends
    at ``OBS_VALUE``: no attribute column."""
    header, table = table_of(text_of(sample))
    assert header[-1] == "OBS_VALUE"
    time = header.index("TIME_PERIOD")
    rows = list(parse_sdmx_csv(sample))
    assert len(rows) == len(table)
    texts = 0
    for row, cells in zip(rows, table, strict=True):
        record = dict(zip(header, cells, strict=True))
        assert row.dataflow == record["DATAFLOW"]
        assert (
            list(row.dimensions) == header[2:time] == ["freq", "reporter", "product", "indicators"]
        )
        assert list(row.dimensions.values()) == cells[2:time]
        assert (row.obs_flag, row.conf_status, row.attributes) == (None, None, {})
        printed = record["OBS_VALUE"]
        try:
            number = Decimal(printed)
        except ArithmeticError:
            assert row.obs_value == printed, "a text kept as printed"
            texts += 1
        else:
            assert isinstance(row.obs_value, Decimal)
            assert row.obs_value == number
            assert str(row.obs_value) == printed, "the number as printed"
    assert texts, "the sample holds a text value"
    shown = {row.obs_value for row in rows if isinstance(row.obs_value, str)}
    units = {row.obs_value for row in rows if row.dimensions["indicators"] == "QNTUNIT"}
    assert units <= shown, "QNTUNIT, the quantity's unit, is text"


def test_parse_sdmx_csv_is_a_generator(tmp_path: Path) -> None:
    rows = parse_sdmx_csv(PACKED)
    assert inspect.isgenerator(rows)
    first = next(rows)
    rows.close()
    assert first == next(parse_sdmx_csv(str(PLAIN))), "a path as text works too"
    header_only = tmp_path / "header.csv"
    header_only.write_bytes(PLAIN.read_bytes().split(b"\r\n", 1)[0] + b"\r\n")
    assert list(parse_sdmx_csv(header_only)) == [], "a header and no row yields nothing"
    empty = tmp_path / "empty.csv"
    empty.write_bytes(b"")
    assert list(parse_sdmx_csv(empty)) == [], "an empty file yields nothing"


def documented_lines(heading: str) -> str:
    """The SDMX-CSV lines under ``heading`` of the snapshot's data-query.md, as one text."""
    page = (DATA_QUERY / "data-query.md").read_text(encoding="utf-8")
    section = page.split(f"#### {heading}\n", 1)[1].split("\n#### ", 1)[0]
    lines = re.findall(r"^`((?:DATAFLOW|ESTAT:)[^`]*)`$", section, flags=re.MULTILINE)
    assert len(lines) > 1, f"{heading}: a header and rows"
    return "\r\n".join(lines) + "\r\n"


@pytest.mark.parametrize("heading", ["Request FULL", "Request DataOnly"])
def test_documented_shape_attributes_are_kept_by_their_headers(
    tmp_path: Path, heading: str
) -> None:
    """Documented shape, read verbatim from the snapshot at test time; neither recorded nor
    hand-written: ENV_WAT_RES with ``detail=full``, whose attributes are ``OBS_FLAG``,
    ``LTAA_FLAG`` and ``LTAA``, and with ``detail=dataonly``, which has none."""
    text = documented_lines(heading)
    header, table = table_of(text)
    path = tmp_path / "env_wat_res.csv"
    path.write_text(text, encoding="utf-8", newline="")
    rows = list(parse_sdmx_csv(path))
    assert len(rows) == len(table)
    others = header[header.index("OBS_VALUE") + 1 :]
    for row, cells in zip(rows, table, strict=True):
        record = dict(zip(header, cells, strict=True))
        assert list(row.dimensions) == ["freq", "wat_proc", "unit", "geo"]
        assert row.obs_value == Decimal(record["OBS_VALUE"])
        assert row.obs_flag == (record.get("OBS_FLAG") or None)
        assert row.conf_status is None, "ENV_WAT_RES has no CONF_STATUS column"
        assert row.attributes == {
            name: record[name] or None for name in others if name != "OBS_FLAG"
        }
    if heading == "Request FULL":
        assert list(rows[0].attributes) == ["LTAA_FLAG", "LTAA"]
        assert any(row.attributes["LTAA"] for row in rows), "a series attribute with a value"


def test_parse_sdmx_csv_refuses_a_cut_gzip_file(tmp_path: Path) -> None:
    """NOT RECORDED: the gzip sample cut to its first half in memory."""
    cut = tmp_path / "cut.csv.gz"
    data = PACKED.read_bytes()
    cut.write_bytes(data[: len(data) // 2])
    with pytest.raises(ValidationError, match=r"cut\.csv\.gz is not a whole gzip file"):
        list(parse_sdmx_csv(cut))


def test_parse_sdmx_csv_refuses_a_row_that_does_not_match_its_header(tmp_path: Path) -> None:
    """NOT RECORDED: the plain sample with its third line's last two cells cut in memory."""
    lines = PLAIN.read_bytes().split(b"\r\n")
    lines[2] = lines[2].rsplit(b",", 2)[0]
    path = tmp_path / "short.csv"
    path.write_bytes(b"\r\n".join(lines))
    rows = parse_sdmx_csv(path)
    next(rows)
    with pytest.raises(ValidationError, match=r"short\.csv has a row, line 3, whose values"):
        next(rows)


@pytest.mark.parametrize("sample", ["toc/apro_mk.xml", "codelist/statinfo.json"])
def test_parse_sdmx_csv_refuses_another_file_kind(sample: str) -> None:
    """The TOC sample, XML, and the codelist sample, JSON on one line, are no SDMX-CSV:
    refused at the header, before any row."""
    path = FIXTURES / "files" / sample
    with pytest.raises(ValidationError, match=rf"^eurostat: {re.escape(path.name)} does not "):
        next(parse_sdmx_csv(path))


def test_parse_sdmx_csv_refuses_a_header_out_of_order(tmp_path: Path) -> None:
    """NOT RECORDED: the plain sample with OBS_VALUE and TIME_PERIOD swapped in its header."""
    data = PLAIN.read_bytes().replace(b"TIME_PERIOD,OBS_VALUE", b"OBS_VALUE,TIME_PERIOD", 1)
    path = tmp_path / "swapped.csv"
    path.write_bytes(data)
    with pytest.raises(ValidationError, match="does not have SDMX-CSV's columns"):
        list(parse_sdmx_csv(path))


def write(path: Path, data: bytes, *, packed: bool) -> Path:
    """``data`` at ``path``, gzip-compressed when ``packed``, as ``compressed=true`` sends it."""
    path.write_bytes(gzip.compress(data) if packed else data)
    return path


@pytest.mark.parametrize("packed", [False, True], ids=["plain", "gzip"])
def test_parse_sdmx_csv_refuses_a_header_only_file_of_another_layout(
    tmp_path: Path, packed: bool
) -> None:
    """NOT RECORDED: the plain sample's header line alone, OBS_VALUE and TIME_PERIOD swapped
    in memory. The header is checked before any row, so a file without rows is refused
    too."""
    header = PLAIN.read_bytes().split(b"\r\n", 1)[0]
    swapped = header.replace(b"TIME_PERIOD,OBS_VALUE", b"OBS_VALUE,TIME_PERIOD")
    path = write(tmp_path / "swapped.csv", swapped + b"\r\n", packed=packed)
    with pytest.raises(ValidationError) as refused:
        list(parse_sdmx_csv(path))
    assert str(refused.value).startswith(
        "eurostat: swapped.csv does not have SDMX-CSV's columns: DATAFLOW, LAST UPDATE, the "
        "dimensions, TIME_PERIOD, OBS_VALUE, the attributes; its header is DATAFLOW, "
    )


@pytest.mark.parametrize("packed", [False, True], ids=["plain", "gzip"])
def test_parse_sdmx_csv_refuses_text_that_is_not_utf8(tmp_path: Path, packed: bool) -> None:
    """NOT RECORDED: the plain sample's rows repeated past 64 KiB, its last row with a byte
    that is no UTF-8, in memory. The header reads, so the rows' reader refuses it: the
    plain file's ``decode_csv``, the gzip file's standard library, worded alike."""
    header, rows = PLAIN.read_bytes().split(b"\r\n", 1)
    body = rows * (64 * 1024 // len(rows) + 1)
    last = body.rindex(b"ESTAT:")
    data = header + b"\r\n" + body[:last] + b"ESTAT\xff:" + body[last + len(b"ESTAT:") :]
    path = write(tmp_path / "latin.csv", data, packed=packed)
    rows_read = parse_sdmx_csv(path)
    assert next(rows_read).dataflow == "ESTAT:APRO_MK_COLA(1.0)", "the header and first rows read"
    with pytest.raises(ValidationError) as refused:
        list(rows_read)
    assert str(refused.value) == "eurostat: latin.csv is not UTF-8 text: invalid start byte"


@pytest.mark.parametrize("packed", [False, True], ids=["plain", "gzip"])
def test_parse_sdmx_csv_refuses_csv_the_csv_module_cannot_read(
    tmp_path: Path, packed: bool
) -> None:
    """NOT RECORDED: the plain sample with one OBS_FLAG cell made longer than the csv
    module's field limit (131,072 characters) in memory."""
    lines = PLAIN.read_bytes().split(b"\r\n")
    lines[1] = lines[1].replace(b",,", b"," + b"e" * (csv.field_size_limit() + 1) + b",", 1)
    path = write(tmp_path / "wide.csv", b"\r\n".join(lines), packed=packed)
    with pytest.raises(ValidationError) as refused:
        list(parse_sdmx_csv(path))
    assert str(refused.value) == (
        "eurostat: wide.csv is not CSV the csv module reads: field larger than field limit "
        f"({csv.field_size_limit()})"
    )
