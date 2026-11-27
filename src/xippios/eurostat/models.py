"""Pydantic models mirroring upstream's payloads, one ``UpstreamModel`` per object.

Conventions §3 and ``/add-endpoint`` give the rules.

The Statistics API answers with one JSON-stat 2.0 dataset (https://json-stat.org/format/,
cited, not snapshotted), which ``Cube`` mirrors member by member as Eurostat serves it
(``docs/upstream/user-guide/api-getting-started/api.md``, "Understanding response
metadata"; the sample ``docs/upstream/samples/apro_mk_cola-json-stat.json``). A cube is a
list of dimensions (``id``, ``size``), each with its categories, Eurostat's codes, in
order (``dimension``), and one cell for every combination of codes; ``value`` and
``status`` hold the cells that have one, keyed by the cell's index. ``Observation`` is one
cell read out of a cube with its codes and labels (``Cube.observations``); nothing in it
is computed beyond that reading. No dataframe type (sdk-core ADR-0002, sdk-core ADR-0028).

The packaged lists have models of their own. ``Dataset`` is one leaf of the Catalogue
API's table of contents (``catalogue/toc/xml``,
``docs/upstream/user-guide/api-detailed-guidelines/catalogue-api/toc.md``), ``Code`` one
code of an SDMX codelist; both are what ``scripts/refresh_reference.py`` packages and the
list tasks return. ``Codelist`` mirrors the SDMX 2.1 API's codelist answer in JSON-stat
(``sdmx/2.1/codelist/{agencyID}/{resourceID}?format=JSON``,
``docs/upstream/user-guide/api-detailed-guidelines/sdmx2-1/structure-queries.md``), which
only the refresh script reads; the TOC's XML is parsed in that script alone (decision D1
of https://github.com/xippios/sdk-eurostat/pull/6).

``SdmxCsvRow`` is one row of an SDMX-CSV 1.0 file, the SDMX 2.1 API's
``format=SDMX-CSV`` answer that ``download_dataset`` writes to disk and
``parse.parse_sdmx_csv`` reads (the user guide's ``sdmx2-1/data-query.md`` and the
sample ``docs/upstream/samples/apro_mk_cola-sdmx-csv.csv``): one observation, its
columns under their headers snake_cased, the dimensions and the other attributes kept
by their column names (sdk-core ADR-0020 decision 2).

A value that Eurostat prints as text and that may be no number, a row's ``OBS_VALUE``,
stays the text under upstream's name with its reading beside it, ``obs_value_number``
(sdk-core ADR-0060, decisions 1 and 7). A date or a time that Eurostat prints is read
into the type that keeps all that it sends, naive where it states no zone, with no text
beside it (https://github.com/xippios/sdk-usda-esr/issues/60, part 3): a leaf's
``lastUpdate`` and ``lastModified``, ``TOC_DATE``, and a row's ``LAST UPDATE``,
``LAST_UPDATE``, both printed day first.
"""

import math
from collections.abc import Iterator, Mapping
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Self

from pydantic import Field, computed_field, field_validator, model_validator
from xippios.core import UpstreamModel, parse_decimal

__all__ = [
    "Annotation",
    "Category",
    "Code",
    "Codelist",
    "CodelistCategory",
    "CodelistExtension",
    "Cube",
    "Dataset",
    "Dimension",
    "GeoLevel",
    "Lang",
    "LeafType",
    "Observation",
    "SdmxCsvRow",
]

TOC_DATE = "%d.%m.%Y"
"""How the table of contents prints a leaf's ``lastUpdate`` and ``lastModified``:
``"02.10.2026"``, day first, the order that a day past 12 among the packaged leaves fixes
(``"19.11.2026"``)."""

LAST_UPDATE = "%d/%m/%y %H:%M:%S"
"""How SDMX-CSV prints ``LAST UPDATE``: ``"05/10/26 23:00:00"``, day first, no zone.

The order is fixed by the snapshot's two answers for apro_mk_cola of 2026-10-27: the
JSON-stat sample's ``updated`` is ``"2026-10-05T23:00:00+0200"`` and the SDMX-CSV
sample's ``LAST UPDATE`` ``"05/10/26 23:00:00"``, the same time without its zone. The
Comext base prints it alike: DS-059358's ``"2026-10-20T11:00:00+0200"`` is
``"20/10/26 11:00:00"`` (recorded 2026-10-28), whose day cannot be read as a month."""


# Lang and GeoLevel are written by hand from
# docs/upstream/user-guide/api-detailed-guidelines/api-statistics.md, since no endpoint
# lists them, and the package renders no enumeration from its packaged lists. The adapters
# publish each docstring as the schema's description.


class Lang(StrEnum):
    """The language of the labels: "EN" (English, the default), "FR" or "DE".

    "The Language parameter ("lang") can have only three values: "EN", "FR", and "DE".
    In case the parameter isn't specified, the default value "EN" is taken."
    """

    EN = "EN"
    """English, the default."""
    FR = "FR"
    """French."""
    DE = "DE"
    """German."""


class GeoLevel(StrEnum):
    """Geo codes by their level: "aggregate", "country", "nuts1", "nuts2", "nuts3", "city".

    aggregate: European aggregates based on a white list - EU15, EU25, EU27_2007,
    EU27_2019, EU28, EA19, etc. country: any country code (EU Member States, or EFTA, or
    Candidate Countries or other countries) - any 2 digits - i.e. FR. nuts1: NUTS code
    level 1: major socio-economic regions - 3 digits - i.e. FR4. nuts2: NUTS code level 2:
    basic regions for the application of regional policies - 4 digits - i.e. FR41. nuts3:
    NUTS code level 3: small regions for specific diagnoses - 5 digits - i.e. FR413. city:
    code at city level - 7 digits - i.e. DE_DEL1 (Karlsruhe). "The "geo" dimension
    parameter filter and the "geoLevel" parameter are mutually exclusive."
    """

    AGGREGATE = "aggregate"
    """European aggregates based on a white list - EU15, EU25, EU27_2007, EU27_2019, EU28,
    EA19, etc."""
    COUNTRY = "country"
    """Any country code (EU Member States, or EFTA, or Candidate Countries or other
    countries) - any 2 digits - i.e. FR."""
    NUTS1 = "nuts1"
    """NUTS code level 1: major socio-economic regions - 3 digits - i.e. FR4."""
    NUTS2 = "nuts2"
    """NUTS code level 2: basic regions for the application of regional policies - 4
    digits - i.e. FR41."""
    NUTS3 = "nuts3"
    """NUTS code level 3: small regions for specific diagnoses - 5 digits - i.e. FR413."""
    CITY = "city"
    """Code at city level - 7 digits - i.e. DE_DEL1 (Karlsruhe)."""


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
        value: The cell's value as upstream's JSON has it: a number, an ``int`` for an
            integer (``110780``) and a ``float`` otherwise (``3247.05``), or the text
            upstream prints in place of one, e.g. ``"KG"`` or ``":E"``, since the
            ``indicators`` dimension of Prodcom's datasets (``DS-059358``) carries units
            and flags among its measures (``QNTUNIT``, ``SCQNTFLAG``; the sample
            ``docs/upstream/samples/DS-059358-json-stat.json``); ``None`` when the cell
            carries a status only (a confidential value, say).
        status: The cell's status as upstream writes it, e.g. ``"|C"`` or ``"n"``;
            ``None`` when it has none. The cube's ``extension["status"]["label"]`` names
            them (``"|C"``: ``"|confidential"``).
    """

    codes: dict[str, str]
    labels: dict[str, str | None]
    value: int | float | str | None
    status: str | None


class Cube(UpstreamModel):
    """A JSON-stat 2.0 dataset as the Statistics API serves it.

    Every member upstream sends is kept, under its own name (``class`` as ``class_``).
    A cell's index counts row-major over ``size``, the last dimension varying fastest:
    with ``size`` ``[1, 3, 10, 2, 1, 2]``, cell 40 is position 0, 1, 0, 0, 0, 0. A cell
    absent from ``value`` is a JSON-stat null. A code that matches nothing in a filter
    gives a dimension of size 0 and an empty ``value``: an empty cube, which the model
    reads and ``get_data`` answers with ``NotFoundError``.

    Attributes:
        version: The JSON-stat version, ``"2.0"``.
        class_: The JSON-stat class, ``"dataset"``; upstream's ``class``.
        label: The dataset's title, e.g. ``"Production of main cows' milk products -
            annual data"``.
        source: The producer, ``"ESTAT"``.
        updated: The dataset's last update, with the zone upstream prints, e.g.
            2026-10-05 23:00 +02:00 for upstream's ``"2026-10-05T23:00:00+0200"``; naive
            if upstream prints none (never seen).
        value: The cells that have a value, by cell index as upstream prints it, each
            value as upstream's JSON has it, an integer staying an ``int``, e.g.
            ``{"40": 3247.05, "44": 0}``, and a text staying a ``str``, e.g. ``{"12":
            "KG", "43": ":E"}`` in Prodcom's ``DS-059358``, whose ``indicators``
            dimension carries units and flags among its measures; JSON-stat's dense form,
            one entry per cell with ``None`` for a null, is read too.
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
    value: dict[str, int | float | str | None] | list[int | float | str | None]
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


class LeafType(StrEnum):
    """What a leaf of the table of contents is: "dataset" or "table".

    The TOC's "type (dataset, table, folder)": "Dataset: i.e. an "open dataset"",
    "Table: i.e. a "pre-defined table"", "Folder: i.e. a "section" or "chapter"". A folder
    is a ``branch`` of the tree, never a ``leaf``, and is not packaged.
    """

    DATASET = "dataset"
    """An open dataset."""
    TABLE = "table"
    """A pre-defined table."""


class Dataset(UpstreamModel):
    """One leaf of Eurostat's table of contents: a dataset or a pre-defined table.

    The leaf's elements as the TOC's XML prints them, the English title only, plus the
    folders it sits in. A code classified at several places of the navigation tree is
    one leaf per place, each with its own ``path``; the TOC also lists a few leaves twice
    under one folder, which are packaged twice, as listed.

    Attributes:
        code: The leaf's code, e.g. ``"apro_mk_cola"``.
        type: ``"dataset"`` or ``"table"``; upstream's ``type`` attribute of the leaf.
        title: The English title, e.g. ``"Production of main cows' milk products - annual
            data"``.
        path: The English titles of the folders above the leaf, from the top of the
            tree, joined with ``" > "``, e.g. ``"Database by themes > Agriculture,
            forestry and fisheries > Agriculture > Animal production > Milk and milk
            products"``; a table listed under a dataset ends with that dataset's title.
            The package's reading of the tree's nesting, nothing else.
        last_update: The last update of the data, a date, e.g. 2026-10-02 for upstream's
            ``"02.10.2026"``, printed day first; upstream's ``lastUpdate``.
        last_modified: The last change of the structure, a date, e.g. 2026-10-02 for
            ``"02.10.2026"``; upstream's ``lastModified``.
        data_start: The oldest period as printed, e.g. ``"1991-Q1"`` or ``"2000"``;
            ``None`` where the TOC prints none. Upstream's ``dataStart``.
        data_end: The most recent period as printed, e.g. ``"2026-Q2"``; ``None`` where
            the TOC prints none. Upstream's ``dataEnd``.
        values: The number of values the dataset holds, e.g. ``314789``; ``None`` where
            the TOC prints none (``docs/upstream/OBSERVED.md``). Upstream's ``values``.
    """

    code: str
    type: LeafType
    title: str
    path: str
    last_update: date = Field(validation_alias="lastUpdate")
    last_modified: date = Field(validation_alias="lastModified")
    data_start: str | None = Field(default=None, validation_alias="dataStart")
    data_end: str | None = Field(default=None, validation_alias="dataEnd")
    values: int | None = None

    @field_validator("last_update", "last_modified", mode="before")
    @classmethod
    def _printed_day_first(cls, value: object) -> object:
        """The table of contents' print, ``"02.10.2026"``, as a date, ``TOC_DATE``.

        Any other value is left to pydantic, which reads an ISO date, ``"2026-10-02"``: the
        form ``dump_upstream`` writes a ``date`` in, so a refresh packages a leaf so and the
        package reads it back.
        """
        if isinstance(value, str):
            try:
                return datetime.strptime(value, TOC_DATE).date()
            except ValueError:
                return value
        return value


class Code(UpstreamModel):
    """One code of a codelist with its English label.

    Attributes:
        code: The code, as a dimension filter takes it, e.g. ``"AT"``.
        label: Its English label, e.g. ``"Austria"``; ``None`` when upstream gives none.
    """

    code: str
    label: str | None = None


class Annotation(UpstreamModel):
    """One annotation of a codelist answer's ``extension.annotation``.

    Attributes:
        type: What it says, e.g. ``"LAST_UPDATED"`` or ``"IS_STANDARD_CODE_LIST"``.
        title: Its value, e.g. ``"2026-03-25T23:00:00+0100"``; ``None`` when absent.
        text: Its text, e.g. ``"Standard code list"``; ``None`` when absent.
    """

    type: str
    title: str | None = None
    text: str | None = None


class CodelistExtension(UpstreamModel):
    """Eurostat's ``extension`` of a codelist answer, the members the package reads.

    ``code-annotation``, the notes on single codes, is not read.

    Attributes:
        lang: The labels' language, e.g. ``"EN"``.
        id: The codelist's id, e.g. ``"GEO"``.
        version: The codelist's version, e.g. ``"28.0"``.
        annotation: The codelist's annotations, ``LAST_UPDATED`` among them.
    """

    lang: str | None = None
    id: str
    version: str
    annotation: list[Annotation] = Field(default_factory=list)


class CodelistCategory(UpstreamModel):
    """``category`` of a codelist answer: its codes in order and their labels.

    Attributes:
        index: The codes in order, e.g. ``["EUR", "EU", ...]``; JSON-stat's other form, a
            code to its position (``{"EUR": 0, ...}``), is read too.
        label: Each code's label, e.g. ``{"AT": "Austria"}``; ``None`` when upstream
            sends none.
    """

    index: list[str] | dict[str, int]
    label: dict[str, str] | None = None


class Codelist(UpstreamModel):
    """A codelist as the SDMX 2.1 API serves it in JSON-stat: one JSON-stat dimension.

    Attributes:
        version: The JSON-stat version, ``"2.0"``.
        class_: The JSON-stat class, ``"dimension"``; upstream's ``class``.
        source: The maintainer, ``"ESTAT"``.
        label: The codelist's name, e.g. ``"Geopolitical entity (reporting)"``.
        category: Its codes and their labels.
        extension: Eurostat's id, version and annotations of the codelist.
    """

    version: str
    class_: str = Field(validation_alias="class")
    source: str | None = None
    label: str | None = None
    category: CodelistCategory
    extension: CodelistExtension

    def codes(self) -> list[Code]:
        """The codes in the codelist's order, each with its label."""
        index = self.category.index
        ordered = index if isinstance(index, list) else sorted(index, key=index.__getitem__)
        labels = self.category.label or {}
        return [Code(code=code, label=labels.get(code)) for code in ordered]

    def annotation(self, type_: str) -> str | None:
        """The ``title`` of the first annotation of ``type_``, e.g. ``"LAST_UPDATED"``.

        ``None`` when the codelist carries no such annotation.
        """
        return next((item.title for item in self.extension.annotation if item.type == type_), None)


class SdmxCsvRow(UpstreamModel):
    """One row of an SDMX-CSV file: one observation with its dimensions and attributes.

    The columns as Eurostat prints them, in order: ``DATAFLOW``, ``LAST UPDATE``, one
    column per dimension in structure order, ``TIME_PERIOD``, ``OBS_VALUE``, then the
    observation's attributes (``OBS_FLAG`` and ``CONF_STATUS`` in apro_mk_cola;
    ``OBS_FLAG``, ``LTAA_FLAG`` and ``LTAA`` in the user guide's ENV_WAT_RES). Nothing is
    renamed: each field is its column's header snake_cased, and the dimensions and the
    other attributes keep their headers as keys. Every value is text as printed but
    ``last_update``, a time; ``obs_value`` keeps its text too, with ``obs_value_number``
    beside it, its reading as a number. An empty cell is ``None`` except in a dimension.

    Attributes:
        dataflow: The dataflow and its version, e.g. ``"ESTAT:APRO_MK_COLA(1.0)"``;
            upstream's ``DATAFLOW``.
        last_update: The dataset's last update, a naive time, e.g. 2026-10-05 23:00 for
            upstream's ``"05/10/26 23:00:00"``, printed day first and without a zone
            (``LAST_UPDATE``); upstream's ``LAST UPDATE``. ``meta.vintage`` of
            ``download_dataset`` keeps the text.
        dimensions: The row's code on each dimension, in column order, e.g. ``{"freq":
            "A", "milkitem": "PRD", "dairyprod": "D1110D", "unit": "THS_T", "geo":
            "AT"}``: the columns between ``LAST UPDATE`` and ``TIME_PERIOD``.
        time_period: The period, as the dataset prints it, e.g. ``"2022"``; upstream's
            ``TIME_PERIOD``.
        obs_value: The value as upstream printed it, e.g. ``"3247.05"``, or a text that is
            no number, e.g. ``"KG"`` or ``":E"``: the ``indicators`` dimension of
            Prodcom's datasets (``DS-059358``) carries units and flags among its measures
            (``QNTUNIT``, ``SCQNTFLAG``; the sample
            ``docs/upstream/samples/DS-059358-sdmx-csv.csv``). ``None`` when the cell is
            empty (a confidential value, say). Upstream's ``OBS_VALUE``.
        obs_value_number: ``obs_value`` read as a number by core's ``parse_decimal``,
            e.g. ``Decimal("3247.05")``; ``None`` for a text that is no number and for an
            empty cell.
        obs_flag: The observation's flag, e.g. ``"e"`` (estimated); ``None`` when empty
            or when the file has no such column. Upstream's ``OBS_FLAG``.
        conf_status: The confidentiality status, e.g. ``"C"``; ``None`` when empty or
            when the file has no such column. Upstream's ``CONF_STATUS``.
        attributes: The other attribute columns after ``OBS_VALUE``, in column order,
            e.g. ``{"LTAA_FLAG": None, "LTAA": "715.53"}`` in ENV_WAT_RES; empty in
            apro_mk_cola, whose attributes are ``OBS_FLAG`` and ``CONF_STATUS``.
    """

    dataflow: str = Field(validation_alias="DATAFLOW")
    last_update: datetime = Field(validation_alias="LAST UPDATE")
    dimensions: Mapping[str, str]
    time_period: str = Field(validation_alias="TIME_PERIOD")
    obs_value: str | None = Field(validation_alias="OBS_VALUE")
    obs_flag: str | None = Field(default=None, validation_alias="OBS_FLAG")
    conf_status: str | None = Field(default=None, validation_alias="CONF_STATUS")
    attributes: Mapping[str, str | None] = Field(default_factory=dict)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def obs_value_number(self) -> Decimal | None:
        """``obs_value`` as a number, ``None`` for a text such as ``"KG"`` or for none."""
        return None if self.obs_value is None else parse_decimal(self.obs_value)

    @field_validator("last_update", mode="before")
    @classmethod
    def _printed_day_first(cls, value: object) -> object:
        """``LAST UPDATE`` as SDMX-CSV prints it, ``"05/10/26 23:00:00"``, as a naive time.

        Raises:
            ValueError: A text in another form, which the error names, never the text.
        """
        if isinstance(value, str):
            try:
                return datetime.strptime(value, LAST_UPDATE)
            except ValueError:
                raise ValueError(
                    "LAST UPDATE is not printed as dd/mm/yy HH:MM:SS, day first"
                ) from None
        return value
