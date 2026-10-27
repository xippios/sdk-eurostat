# xippios-eurostat

Typed Python client, MCP server and FastAPI routes for
[Eurostat dissemination API](https://ec.europa.eu/eurostat/web/main/data/database), part of the
[xippios SDK family](https://github.com/xippios). Names and semantics follow the
upstream documentation; every response carries release metadata (source, endpoint,
retrieved_at, published_at, vintage).

## Install

```bash
uv add xippios-eurostat            # client only
uv add "xippios-eurostat[mcp]"     # + MCP server
uv add "xippios-eurostat[http]"    # + FastAPI router
```

No API key is needed.

## 30-second example

```python
from xippios.eurostat import get_data

milk = get_data("apro_mk_cola", {"geo": "AT", "time": ["2022", "2023"]})
cube = milk.data  # the JSON-stat 2.0 dataset, member by member
cube.id  # ["freq", "milkitem", "dairyprod", "unit", "geo", "time"]
cube.size  # [1, 3, 10, 2, 1, 2]: codes per dimension
cube.value["40"]  # 3247.05: cell 40, row-major over size, the last dimension fastest
cube.status["64"]  # "|C": confidential, as cube.extension["status"]["label"] names it
first = next(cube.observations())  # one cell with its codes and labels
first.codes  # {"freq": "A", "milkitem": "PRD", "dairyprod": "D1110D", "unit": "THS_T", ...}
first.labels["dairyprod"], first.value  # "Raw cows' milk delivered to dairies", 3247.05
milk.meta.published_at  # 2026-10-05 23:00+02:00: the dataset's last update, `updated`
milk.meta.vintage  # "2026-10-05T23:00:00+0200": the same, as Eurostat prints it
milk.meta.request  # {"dataset": "apro_mk_cola", "filters": {...}, "lang": "EN"}
```

`get_data(dataset, filters=None, *, lang=Lang.EN, since_time_period=None,
until_time_period=None, last_time_period=None, geo_level=None)` sends one request to the
Statistics API (`statistics/1.0/data/{datasetCode}`). `filters` maps any dimension of the
dataset to one code or a list of codes (`{"geo": "AT", "milkitem": "PRD"}`); a `time`
filter selects periods, and so do `since_time_period`, `until_time_period` and
`last_time_period`. Eurostat accepts one time parameter per query, the one exception
being `since_time_period` with `until_time_period`; any other combination is refused
before sending. `lang` takes `Lang.EN`, `Lang.FR` or `Lang.DE` and `geo_level` a
`GeoLevel` (`aggregate`, `country`, `nuts1`, `nuts2`, `nuts3`, `city`), both in
`xippios.eurostat.models`; a plain string such as `"FR"` works too. A code that matches
nothing gives an empty cube, size 0 on that dimension. `meta.published_at` is the cube's
`updated` with Eurostat's zone; one printed without a zone, never seen, is kept as
printed with `meta.published_at_naive` set, and `meta.vintage` holds the text either
way. An unknown dataset, and Eurostat's "No results found", raise `NotFoundError`; a
query Eurostat refuses or judges too large raises `InvalidRequestError` with Eurostat's
message and how to narrow it. A query Eurostat would answer asynchronously raises it
too: this package does not poll asynchronous answers, and the Statistics API's own route
is to send the same request again later. Ask for small slices: the cube comes back
whole, and over MCP a result above 64 KB is replaced by a preview and a note.

### Slices

```python
from xippios.eurostat import get_cross_section, get_latest_period, get_series

milk = {"milkitem": "PRD", "dairyprod": "D1110D", "unit": "THS_T"}
series = get_series("apro_mk_cola", {**milk, "geo": "AT"}, since="2015", until="2023")
[(o.codes["time"], o.value) for o in series.data]  # [("2015", 3102.56), ..., ("2023", 3242.85)]
latest = get_latest_period("apro_mk_cola", {**milk, "geo": "AT"})
latest.data[0].codes["time"], latest.data[0].value  # ("2025", 3503.31)
section = get_cross_section("apro_mk_cola", "2023", milk)  # every geo code the dataset holds
len(section.data)  # 36: the geo codes with a value or a status in 2023
section.meta.request  # {"dataset": "apro_mk_cola", "filters": {..., "time": "2023"}, "lang": "EN"}
```

Each slice sends one `get_data` request and returns the cube's observations as a list
of `Observation`, with `get_data`'s `meta`: `meta.request` names what was sent
(`since_time_period`, `last_time_period`, the `time` filter).
`get_series(dataset, filters, *, since=None, until=None, lang=Lang.EN)` wants every
dimension but time pinned to one code; an answer that spans more than one series raises
`InvalidRequestError` naming each dimension still open and its codes.
`get_latest_period(dataset, filters=None, *, lang=Lang.EN)` asks for `lastTimePeriod=1`,
the most recent period, and `get_cross_section(dataset, period, filters=None, *,
lang=Lang.EN)` for `time=<period>`; both return any number of series in cube order. Each
refuses a `time` filter before sending, since it selects the periods itself. A code that
matches nothing gives an empty list. Over MCP each slice keeps the family's cap, 200
rows or 64 KB, with a note of its own on how to see the rest.

## MCP

```json
{
  "mcpServers": {
    "eurostat": {
      "command": "uvx",
      "args": ["--from", "xippios-eurostat[mcp]", "xippios-eurostat-mcp"]    }
  }
}
```

Tools are read-only and named `eurostat_<verb>_<noun>`. Results are capped, at
200 rows or 64 KB unless a tool has a cap of its own, with a note on how to see the rest.
`--http` serves streamable HTTP instead of stdio.

## Status

<!-- Core's family check (tests/test_family.py) reads this table: keep the "## Status"
heading and the "Task function" column. Each row's Task function cell starts with the
task's name in backticks, alone or as its call (`get_data(code, year)`); several tasks in
one row are backticked names separated by commas; prose may follow. The tables list
exactly tasks.__all__ and tasks_write.__all__. -->

| Upstream operation | Task function | MCP tool | Status |
| --- | --- | --- | --- |
| `getData` (`statistics/1.0/data/{datasetCode}`) | `get_data(dataset, filters)`, a JSON-stat cube | `eurostat_get_data` | alpha |
| `getData` with `sinceTimePeriod` and `untilTimePeriod` | `get_series(dataset, filters, since, until)`, one series as observations ordered by period | `eurostat_get_series` | alpha |
| `getData` with `lastTimePeriod=1` | `get_latest_period(dataset, filters)`, the observations of the most recent period | `eurostat_get_latest_period` | alpha |
| `getData` with `time` | `get_cross_section(dataset, period, filters)`, the observations of one period | `eurostat_get_cross_section` | alpha |

## Upstream terms and attribution

Data comes from Eurostat dissemination API (https://ec.europa.eu/eurostat/web/main/data/database) under its own terms of use;
this package adds no rights to it. Documentation snapshot: `docs/upstream/`.

## Licence

Apache-2.0. See [LICENSE](LICENSE).
