"""``Cube`` against the recorded answers, and the value sets written by hand against the
snapshot's pages.

The cubes are the recorded answers under ``tests/fixtures/get_data/``, of the main base
and of the Comext base (``DS-059358``, Prodcom, whose ``indicators`` dimension carries
units and flags as text among its measures). Where a test needs a shape the service did
not send (JSON-stat's dense ``value`` array, an incoherent cube), it derives it in memory
from a recorded body and says so; no fixture is written. ``Lang``, ``GeoLevel`` and
``LeafType`` are read against the user guide's pages under ``docs/upstream/`` at test time
(sdk-core ADR-0061, decision 12).
"""

import inspect
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from xippios.core import ValidationError, parse
from xippios.core.testing import load_fixture

from xippios.eurostat import tasks
from xippios.eurostat.models import Cube, GeoLevel, Lang, LeafType, Observation

FIXTURES = Path(__file__).parent / "fixtures" / "get_data"
GUIDE = Path(__file__).parents[1] / "docs" / "upstream" / "user-guide" / "api-detailed-guidelines"
PRODCOM = "DS-059358_AT_10411200_2022_2023"
CUBES = [
    "apro_mk_cola_AT_2022_2023",
    "apro_cpnh1_AT_2022_2023",
    "ef_m_farmleg_AT_HLD_last_2",
    "unknown_code",
    PRODCOM,
    "DS-059358_unknown_code",
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


def test_cube_keeps_a_text_value_as_printed() -> None:
    """DS-059358's ``value`` holds numbers and, where the indicator is a unit or a flag,
    upstream's text: ``"KG"`` for QNTUNIT and ``":E"`` for SCQNTFLAG and SCVALFLAG.
    Cell 12 of size [1, 1, 1, 23, 2] is QNTUNIT (position 6) in 2022; cell 43 SCQNTFLAG
    (position 21) in 2023."""
    prodcom = cube(PRODCOM)
    sent = raw(PRODCOM)["value"]
    assert isinstance(prodcom.value, dict)
    assert prodcom.value == sent, "every value as upstream's JSON has it"
    assert prodcom.value["12"] == "KG"
    assert prodcom.value["43"] == ":E"
    assert isinstance(prodcom.value["6"], int), "an integer stays an integer"
    assert {type(value) for value in prodcom.value.values()} == {int, str}
    by_codes = {(o.codes["indicators"], o.codes["time"]): o for o in prodcom.observations()}
    unit = by_codes[("QNTUNIT", "2022")]
    assert (unit.value, unit.status) == ("KG", None)
    assert unit.labels["indicators"] == "Quantity unit"
    flag = by_codes[("SCQNTFLAG", "2023")]
    assert flag.value == ":E"
    assert flag.labels["indicators"] == "Sub-contracted production quantity flag"
    texts = [o for o in prodcom.observations() if isinstance(o.value, str)]
    assert len(texts) == sum(isinstance(value, str) for value in sent.values()) == 4
    dumped = unit.model_dump(mode="json")
    assert dumped["value"] == "KG", "text in the adapters' JSON too"


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


def test_lang_holds_the_values_of_the_user_guide() -> None:
    """``Lang``, written by hand, holds the three values that api-statistics.md gives
    ``lang``, in its order, and ``get_data`` takes its default: "The Language parameter
    ("lang") can have only three values: "EN", "FR", and "DE". In case the parameter isn't
    specified, the default value "EN" is taken." (sdk-core ADR-0061, decision 12)."""
    page = (GUIDE / "api-statistics.md").read_text(encoding="utf-8")
    sentence = next(line for line in page.splitlines() if line.startswith("The Language parameter"))
    values = re.search(r"only three values: (.*?)\. ", sentence)
    default = re.search(r"the default value \W(\w+)\W is taken", sentence)
    assert values is not None
    assert default is not None
    assert [member.value for member in Lang] == re.findall(r"\W([A-Z]{2})\W", values[1])
    assert inspect.signature(tasks.get_data).parameters["lang"].default == default[1]


def test_geo_level_holds_the_values_of_the_user_guide() -> None:
    """``GeoLevel``, written by hand, holds the values of api-statistics.md's section "The
    geoLevel parameter", in its order, ``geoLevel= city`` with its space among them
    (sdk-core ADR-0061, decision 12)."""
    page = (GUIDE / "api-statistics.md").read_text(encoding="utf-8")
    section = page.split("### The geoLevel parameter\n", 1)[1].split("\n### ", 1)[0]
    documented = re.findall(r"^- \**geoLevel=\s*(\w+)", section, flags=re.MULTILINE)
    assert len(documented) == 6
    assert [member.value for member in GeoLevel] == documented


def test_leaf_type_holds_the_types_of_a_leaf_in_the_user_guide() -> None:
    """``LeafType``, written by hand, holds the types that toc.md's row "type (dataset,
    table, folder)" names but ``folder``, a branch of the tree and never a leaf, which the
    package does not list (sdk-core ADR-0061, decision 12)."""
    page = (GUIDE / "catalogue-api" / "toc.md").read_text(encoding="utf-8")
    row = next(line for line in page.splitlines() if line.startswith("| type ("))
    named = re.match(r"\| type \(([^)]*)\)", row)
    assert named is not None
    types = named[1].split(", ")
    assert "folder" in types
    assert [member.value for member in LeafType] == [kind for kind in types if kind != "folder"]
