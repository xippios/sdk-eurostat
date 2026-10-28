"""``Cube`` against the recorded answers: every member kept, the cells read out right.

The cubes are the recorded answers under ``tests/fixtures/get_data/``. Where a test needs
a shape the service did not send (JSON-stat's dense ``value`` array, an incoherent
cube), it derives it in memory from a recorded body and says so; no fixture is written.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from xippios.core import ValidationError, parse
from xippios.core.testing import load_fixture

from xippios.eurostat.models import Cube, Observation

FIXTURES = Path(__file__).parent / "fixtures" / "get_data"
CUBES = [
    "apro_mk_cola_AT_2022_2023",
    "apro_cpnh1_AT_2022_2023",
    "ef_m_farmleg_AT_HLD_last_2",
    "unknown_code",
]


def raw(case: str) -> dict[str, Any]:
    body: dict[str, Any] = json.loads(load_fixture(FIXTURES / f"{case}.json").response.body)
    return body


def cube(case: str) -> Cube:
    return parse(Cube, raw(case), source="eurostat", endpoint="getData")


@pytest.mark.parametrize("case", CUBES)
def test_cube_keeps_every_member(case: str) -> None:
    sent = raw(case)
    kept = cube(case).model_dump(mode="json")
    kept["class"] = kept.pop("class_")
    for member, value in sent.items():
        if member == "updated":
            assert datetime.fromisoformat(kept[member]) == datetime.fromisoformat(value)
        else:
            assert kept[member] == value, member
    assert all(kept[member] is None for member in kept.keys() - sent.keys()), (
        "a member the model has and the answer lacks is empty"
    )


def test_cube_mirrors_json_stat() -> None:
    milk = cube("apro_mk_cola_AT_2022_2023")
    assert (milk.version, milk.class_, milk.source) == ("2.0", "dataset", "ESTAT")
    assert milk.label == "Production of main cows' milk products - annual data"
    assert milk.updated is not None
    assert milk.updated.isoformat() == "2026-10-05T23:00:00+02:00"
    assert milk.id == ["freq", "milkitem", "dairyprod", "unit", "geo", "time"]
    assert milk.size == [1, 3, 10, 2, 1, 2]
    assert milk.dimension["milkitem"].label == "Item of milk"
    assert milk.dimension["milkitem"].category.index == {"PTEN": 0, "PRD": 1, "FAT": 2}
    assert milk.status == {"64": "|C", "65": "|C"}
    assert isinstance(milk.value, dict)
    assert len(milk.value) == 18
    assert milk.value["44"] == 0
    assert isinstance(milk.value["44"], int), "an integer stays an integer"
    assert isinstance(milk.value["40"], float)
    assert milk.extension is not None
    assert milk.extension["status"] == {"label": {"|C": "|confidential"}}


def test_empty_cube_has_no_status_member() -> None:
    empty = cube("unknown_code")
    assert empty.size[empty.id.index("geo")] == 0
    assert empty.value == {}
    assert empty.status is None
    assert list(empty.observations()) == []


def test_observations_read_every_cell_with_a_value_or_a_status() -> None:
    milk = cube("apro_mk_cola_AT_2022_2023")
    observations = list(milk.observations())
    assert isinstance(milk.value, dict)
    assert len(observations) == len(milk.value.keys() | (milk.status or {}).keys()) == 20


def test_observation_codes_labels_and_value_of_known_cells() -> None:
    """Cell 40 of size [1, 3, 10, 2, 1, 2] is positions 0, 1, 0, 0, 0, 0 (strides 120,
    40, 4, 2, 2, 1); cell 64 is 0, 1, 6, 0, 0, 0 and carries a status only."""
    milk = cube("apro_mk_cola_AT_2022_2023")
    by_codes = {tuple(o.codes.values()): o for o in milk.observations()}
    assert by_codes[("A", "PRD", "D1110D", "THS_T", "AT", "2022")] == Observation(
        codes={
            "freq": "A",
            "milkitem": "PRD",
            "dairyprod": "D1110D",
            "unit": "THS_T",
            "geo": "AT",
            "time": "2022",
        },
        labels={
            "freq": "Annual",
            "milkitem": "Product obtained",
            "dairyprod": "Raw cows' milk delivered to dairies",
            "unit": "Thousand tonnes",
            "geo": "Austria",
            "time": "2022",
        },
        value=raw("apro_mk_cola_AT_2022_2023")["value"]["40"],
        status=None,
    )
    cream = by_codes[("A", "PRD", "D1200DME", "THS_T", "AT", "2022")]  # cell 44
    assert cream.value == 0
    assert isinstance(cream.value, int), "an integer stays an integer"
    confidential = by_codes[("A", "PRD", "D3200", "THS_T", "AT", "2022")]
    assert (confidential.value, confidential.status) == (None, "|C")
    assert confidential.labels["dairyprod"] == "Concentrated milk"


@pytest.mark.parametrize("case", CUBES)
def test_observations_come_in_cube_order(case: str) -> None:
    """Row-major over ``size``, the last dimension varying fastest: the positions of the
    cells yielded increase."""
    data = cube(case)
    positions = [
        tuple(data.dimension[name].category.index[code] for name, code in o.codes.items())
        for o in data.observations()
    ]
    assert positions == sorted(positions)
    assert len(set(positions)) == len(positions)


def test_dense_value_reads_like_the_sparse_one() -> None:
    """NOT RECORDED as such: the recorded cube with ``value`` and ``status`` in
    JSON-stat's dense array form, built in memory; Eurostat serves the sparse form."""
    sparse = raw("apro_mk_cola_AT_2022_2023")
    cells = 1
    for count in sparse["size"]:
        cells *= count
    dense = dict(sparse, value=[sparse["value"].get(str(i)) for i in range(cells)])
    assert list(parse(Cube, dense, source="eurostat", endpoint="getData").observations()) == list(
        cube("apro_mk_cola_AT_2022_2023").observations()
    )


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"size": [1, 3, 10, 2, 1]}, "id names 6 dimensions, size 5"),
        (
            {"size": [1, 3, 10, 2, 1, 3]},
            "dimension 'time': category.index does not hold the positions 0 to 2 that size gives",
        ),
        ({"value": {"120": 1.0}}, "cell index '120' is not one of the 120 cells"),
        ({"status": {"x": "|C"}}, "cell index 'x' is not one of the 120 cells"),
        ({"value": [1.0, 2.0]}, "value lists 2 cells, size gives 120"),
    ],
)
def test_incoherent_cube_is_refused(change: dict[str, Any], message: str) -> None:
    """NOT RECORDED: the recorded cube with one member changed in memory. Core's text
    names the first error's location, type and message, and chains no pydantic error,
    whose text would quote the input."""
    broken = dict(raw("apro_mk_cola_AT_2022_2023"), **change)
    with pytest.raises(ValidationError) as refused:
        parse(Cube, broken, source="eurostat", endpoint="getData")
    assert str(refused.value) == (
        "eurostat getData: 1 validation error(s); first at <root> (value_error): "
        f"Value error, {message}"
    )
    assert refused.value.__cause__ is None
