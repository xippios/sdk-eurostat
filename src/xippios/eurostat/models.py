"""Pydantic models mirroring Eurostat dissemination API payloads.

One model per upstream object, subclassing ``xippios.core.UpstreamModel``, with fields
named as upstream names them in snake_case. Where upstream spells a field differently,
``Field(validation_alias=...)`` accepts that spelling on input; never ``alias=``, which the
adapters would serialise, handing agents the upstream spelling. Within-source hygiene only:
dates become ``datetime.date``, numbers become numbers, upstream enumerations become
``StrEnum``, and an enumeration of integer ids ``IntEnum``. No cross-source normalisation
(ADR-0003): an upstream concept stays an upstream concept.

These read models stay faithful, documented personal identifiers included (``ssn``,
``iban`` and their like). The projections tasks return leave those out, a write task does
not echo one in ``meta.request``, and fixtures never carry their values (ADR-0017).

The Statistics API answers with one JSON-stat 2.0 dataset (https://json-stat.org/format/,
cited, not snapshotted), which ``Cube`` mirrors member by member as Eurostat serves it
(``docs/upstream/user-guide/api-getting-started/api.md``, "Understanding response
metadata"; the sample ``docs/upstream/samples/apro_mk_cola-json-stat.json``). A cube is a
list of dimensions (``id``, ``size``), each with its categories, Eurostat's codes, in
order (``dimension``), and one cell for every combination of codes; ``value`` and
``status`` hold the cells that have one, keyed by the cell's index. ``Observation`` is one
cell read out of a cube with its codes and labels (``Cube.observations``); nothing in it
is computed beyond that reading. No dataframe type (ADR-0002, ADR-0003).
"""

import math
from collections.abc import Iterator
from datetime import datetime
from typing import Any, Self

from pydantic import Field, model_validator
from xippios.core import UpstreamModel

__all__ = ["Category", "Cube", "Dimension", "Observation"]


class Category(UpstreamModel):
    """``dimension.<code>.category``: the dimension's codes, their positions and labels.

    Attributes:
        index: Each code's position in the dimension, from 0, e.g.
            ``{"PTEN": 0, "PRD": 1, "FAT": 2}``.
        label: Each code's label, e.g. ``{"PRD": "Product obtained"}``; ``None`` when
            upstream sends none.
    """

    index: dict[str, int]
    label: dict[str, str] | None = None


class Dimension(UpstreamModel):
    """``dimension.<code>``: one dimension of a cube.

    Attributes:
        label: The dimension's label, e.g. ``"Item of milk"``.
        category: Its codes, their positions and labels.
    """

    label: str | None = None
    category: Category


class Observation(UpstreamModel):
    """One cell of a cube: its code and label on every dimension, its value and status.

    Read out of a ``Cube`` by ``Cube.observations``; no upstream object of its own.

    Attributes:
        codes: The cell's code on each dimension, in the cube's dimension order, e.g.
            ``{"freq": "A", "milkitem": "PRD", "dairyprod": "D1110D", "unit": "THS_T",
            "geo": "AT", "time": "2022"}``.
        labels: The label of each of those codes, e.g. ``{"freq": "Annual", ...,
            "geo": "Austria", "time": "2022"}``; ``None`` where upstream gives none.
        value: The cell's value as upstream's JSON number, an ``int`` for an integer
            (``110780``) and a ``float`` otherwise (``3247.05``); ``None`` when the cell
            carries a status only (a confidential value, say).
        status: The cell's status as upstream writes it, e.g. ``"|C"`` or ``"n"``;
            ``None`` when it has none. The cube's ``extension["status"]["label"]`` names
            them (``"|C"``: ``"|confidential"``).
    """

    codes: dict[str, str]
    labels: dict[str, str | None]
    value: int | float | None
    status: str | None


class Cube(UpstreamModel):
    """A JSON-stat 2.0 dataset as the Statistics API serves it.

    Every member upstream sends is kept, under its own name (``class`` as ``class_``).
    A cell's index counts row-major over ``size``, the last dimension varying fastest:
    with ``size`` ``[1, 3, 10, 2, 1, 2]``, cell 40 is position 0, 1, 0, 0, 0, 0. A cell
    absent from ``value`` is a JSON-stat null. A code that matches nothing in a filter
    gives a dimension of size 0 and an empty ``value``: an empty cube, not an error.

    Attributes:
        version: The JSON-stat version, ``"2.0"``.
        class_: The JSON-stat class, ``"dataset"``; upstream's ``class``.
        label: The dataset's title, e.g. ``"Production of main cows' milk products -
            annual data"``.
        source: The producer, ``"ESTAT"``.
        updated: The dataset's last update, with its zone, e.g. 2026-10-05 23:00 +02:00
            for upstream's ``"2026-10-05T23:00:00+0200"``.
        value: The cells that have a value, by cell index as upstream prints it, each
            number as upstream's JSON has it, an integer staying an ``int``, e.g.
            ``{"40": 3247.05, "44": 0}``; JSON-stat's dense form, one entry per cell with
            ``None`` for a null, is read too.
        status: The cells that have a status, by cell index, e.g. ``{"64": "|C"}``;
            ``None`` when upstream sends no ``status`` member (the empty cube).
        id: The dimension codes in order, e.g. ``["freq", "milkitem", "dairyprod",
            "unit", "geo", "time"]``.
        size: The number of codes of each dimension, in the same order, e.g.
            ``[1, 3, 10, 2, 1, 2]``.
        dimension: Each dimension by its code.
        extension: Eurostat's additions as sent, unmodelled: ``annotation`` (the
            dataset's update and dissemination times, ``OBS_COUNT`` and the like),
            ``status.label`` (what each status means), ``positions-with-no-data``,
            ``datastructure`` and others.
    """

    version: str
    class_: str = Field(validation_alias="class")
    label: str | None = None
    source: str | None = None
    updated: datetime | None = None
    value: dict[str, int | float | None] | list[int | float | None]
    status: dict[str, str] | None = None
    id: list[str]
    size: list[int]
    dimension: dict[str, Dimension]
    extension: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        """Refuse a cube whose cells could not be read: ``id``, ``size`` and the indexes agree."""
        if len(self.id) != len(self.size):
            raise ValueError(f"id names {len(self.id)} dimensions, size {len(self.size)}")
        for code, count in zip(self.id, self.size, strict=True):
            dimension = self.dimension.get(code)
            if dimension is None:
                raise ValueError(f"dimension {code!r} is named in id but not described")
            if sorted(dimension.category.index.values()) != list(range(count)):
                raise ValueError(
                    f"dimension {code!r}: category.index does not hold the positions 0 to "
                    f"{count - 1} that size gives"
                )
        cells = math.prod(self.size)
        if isinstance(self.value, list):
            if len(self.value) != cells:
                raise ValueError(f"value lists {len(self.value)} cells, size gives {cells}")
            keys: set[str] = set()
        else:
            keys = set(self.value)
        keys |= set(self.status or {})
        for key in keys:
            if not (key.isascii() and key.isdigit()) or int(key) >= cells:
                raise ValueError(f"cell index {key!r} is not one of the {cells} cells")
        return self

    def observations(self) -> Iterator[Observation]:
        """One ``Observation`` per cell that has a value or a status, in cube order.

        Cells absent from ``value`` and ``status`` are JSON-stat nulls and are not
        yielded; a cell with a status and no value is, with ``value`` ``None``. The
        cube keeps everything, so nothing is lost.
        """
        if isinstance(self.value, list):
            valued = {i: v for i, v in enumerate(self.value) if v is not None}
        else:
            valued = {int(key): v for key, v in self.value.items() if v is not None}
        flagged = {int(key): text for key, text in (self.status or {}).items()}
        codes: list[list[str]] = []
        labels: list[dict[str, str]] = []
        for name in self.id:
            category = self.dimension[name].category
            ordered = sorted(category.index, key=category.index.__getitem__)
            codes.append(ordered)
            labels.append(category.label or {})
        strides = [math.prod(self.size[k + 1 :]) for k in range(len(self.size))]
        for cell in sorted(valued.keys() | flagged.keys()):
            at = [
                codes[k][(cell // stride) % count]
                for k, (stride, count) in enumerate(zip(strides, self.size, strict=True))
            ]
            yield Observation(
                codes=dict(zip(self.id, at, strict=True)),
                labels={
                    name: labels[k].get(code)
                    for k, (name, code) in enumerate(zip(self.id, at, strict=True))
                },
                value=valued.get(cell),
                status=flagged.get(cell),
            )
