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
Statistics API (`statistics/1.0/data/{datasetCode}`). A `DS-` dataset, Comext trade or
Prodcom production, is requested on Eurostat's Comext base, every other on the main
base; the call and its answer are the same, and a value is the text Eurostat prints where
a Prodcom indicator is a unit or a flag:

```python
oil = get_data(
    "DS-059358",  # Prodcom: sold production, exports and imports
    {"reporter": "AT", "product": "10411200"},  # fish and marine oils, NACE 10.41
    since_time_period="2022",
    until_time_period="2023",
)
oil.data.id  # ["freq", "reporter", "product", "indicators", "time"]
oil.data.value["6"], oil.data.value["12"]  # 349477 (EXPVAL 2022), "KG" (QNTUNIT 2022)
```

`filters` maps any dimension of the dataset to one code or a list of codes (`{"geo": "AT",
"milkitem": "PRD"}`); a `time` filter selects periods, and so do `since_time_period`,
`until_time_period` and `last_time_period`. Eurostat accepts one time parameter per query,
the one exception being `since_time_period` with `until_time_period`; any other
combination is refused before sending. `lang` takes `Lang.EN`, `Lang.FR` or `Lang.DE` and
`geo_level` a `GeoLevel` (`aggregate`, `country`, `nuts1`, `nuts2`, `nuts3`, `city`), both
in `xippios.eurostat.models`; a plain string such as `"FR"` works too. A code that matches
nothing gives an empty cube, size 0 on that dimension. `meta.published_at` is the cube's
`updated` with Eurostat's zone; one printed without a zone, never seen, is kept as printed
with `meta.published_at_naive` set, and `meta.vintage` holds the text either way. An
unknown dataset, and Eurostat's "No results found", raise `NotFoundError`; a query
Eurostat refuses or judges too large raises `InvalidRequestError` with Eurostat's message
and how to narrow it. A query Eurostat would answer asynchronously raises it too: this
package does not poll asynchronous answers, and the Statistics API's own route is to send
the same request again later. Ask for small slices: the cube comes back whole, and over
MCP a result above 64 KB is replaced by a preview and a note.

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
refuses a `time` filter before sending, since it selects the periods itself, and
`get_cross_section` an empty `period`. A code that matches nothing gives an empty list.
Over MCP each slice keeps the family's cap, 200 rows or 64 KB, with a note of its own on
how to see the rest.

### Prodcom production

```python
from xippios.eurostat import get_sold_production, get_total_production, list_products

soya = list_products(search="soya")  # the PRODCOM products, without a request
soya.data[0]  # Code(code="10412100", label="Crude soya-bean oil and its fractions ...")
oil = get_sold_production("10411200", reporters=["AT"], since="2022", until="2023")
values = {(o.codes["indicators"], o.codes["time"]): o.value for o in oil.data}
values["EXPVAL", "2023"], values["QNTUNIT", "2023"]  # 415790 (euro), "KG"
oil.meta.request  # {"dataset": "DS-059358", "filters": {"reporter": ["AT"], ...}, ...}
manure = get_total_production("20158000", reporters=["AT"], since="2022", until="2023")
[(o.codes["indicators"], o.codes["time"], o.value) for o in manure.data][:2]
# [("APRODQNT", "2022", 84470389), ("APRODQNT", "2023", 14769157)], in QNTUNIT "KG"
```

Eurostat's Prodcom statistics, production of manufactured goods, food and agricultural
inputs among them, are served on the Comext base. `get_sold_production(product,
reporters=None, since=None, until=None, indicators=None)` reads DS-059358, sold
production, exports and imports, and `get_total_production(...)` DS-059359, total
production, one product at a time: each sends one `get_data` request and returns the
cube's observations in cube order with `get_data`'s `meta`. `reporters` are country codes
(`["AT"]`), `since` and `until` years, and `indicators` the measures (`PRODVAL`,
`PRODQNT` in `QNTUNIT`, `EXPVAL`, `EXPQNT`, `IMPVAL`, `IMPQNT` for DS-059358; `APRODQNT`
in `QNTUNIT` for DS-059359), `None` for every one. A value is a number, or the text
Eurostat prints for a unit or a flag (`"KG"`, `":E"`). The product is checked against the
dataset's product list packaged with this version, each reporter against CXT_FREE_ISO,
Comext's list of reporters and partners, and each indicator against CXT_INDICATORS,
before sending: a code they lack raises `UnknownCode` naming the closest, and a reporter
the list holds and the dataset lacks gives an empty list.
`list_products(search=None)` lists DS-059358's products (CXT_PRODCOM2_SOLD), eight-digit
codes that start with their NACE class (`1041` oils and fats, `2015` fertilisers);
DS-059359 covers a few hundred of them, chiefly chemicals, fertilisers and metals, which
`list_codes("cxt_prodcom2_total")` lists. Over MCP the production tasks keep the family's
cap, 200 rows or 64 KB, with a note naming `reporters`, `indicators` and `since`, and
`eurostat_list_products` takes up to 1,000 rows within 64 KB, with a note naming
`search`.

### Comext trade

```python
from xippios.eurostat import get_trade, get_trade_hs, list_cn8, list_hs

list_cn8(search="crude soya-bean oil").data[1]
# Code(code="15071090", label="Crude soya-bean oil, whether or not degummed (excl. for ...")
list_hs(search="soya").data[0]  # Code(code="1201", label="Soya beans, whether or not broken")
oil = get_trade("15071090", reporters=["AT"], partners=["DE"], since="2023-01", until="2023-12")
values = {(o.codes["flow"], o.codes["indicators"], o.codes["time"]): o.value for o in oil.data}
values["2", "VALUE_IN_EUROS", "2023-12"]  # 305451: Austria's exports to Germany, in euro
values["2", "QUANTITY_IN_100KG", "2023-12"]  # 3372.15, in 100 kg
oil.meta.request  # {"dataset": "DS-045409", "filters": {"freq": "M", "reporter": ["AT"], ...}, ...}
heading = get_trade_hs("1507", reporters=["AT"], partners=["DE"], since="2023-12", until="2023-12")
[(o.codes["flow"], o.codes["indicators"], o.value) for o in heading.data][:2]
# [("1", "VALUE_EUR", 1222), ("1", "VALUE_NAC", 1222)]: imports of soya-bean oil, HS 1507
```

Eurostat's Comext trade statistics, the EU side of the trade picture, are served on the
Comext base. `get_trade(product, reporters=None, partners=None, flow=None, since=None,
until=None, freq="M", indicators=None)` reads DS-045409, EU trade since 1988 by HS2-4-6
and CN8, and `get_trade_hs(...)`, with the same parameters, DS-059341, international trade
of EU and non-EU countries since 2002 by HS2-4-6, one product at a time: each sends one
`get_data` request and returns the cube's observations in cube order (reporter, partner,
flow, indicator, oldest period first) with `get_data`'s `meta`. `product` is an
eight-digit CN code (`"15071090"`, crude soya-bean oil) or an HS chapter, heading or
subheading (`"15"`, `"1507"`, `"150710"`); `reporters` and `partners` are country codes of
CXT_FREE_ISO (`["AT"]`, `["DE", "US"]`), which holds aggregates too (`"EU27_2020_EXTRA"`,
`"WORLD"`); `flow` is `"1"` for imports and `"2"` for exports, `None` for both; `freq`
`"M"` for monthly periods (`since="2023-01"`) or `"A"` for annual ones (`since="2023"`),
`Freq.M` and `Freq.A` in `xippios.eurostat.models`; `indicators` the measures,
`VALUE_IN_EUROS`, `QUANTITY_IN_100KG` and `SUPPLEMENTARY_QUANTITY` in DS-045409,
`VALUE_EUR`, `VALUE_NAC` and `QUANTITY_KG` in DS-059341, `None` for every one. Every code
is checked against the lists packaged with this version before sending, the product
against CXT_NC, the reporters and partners against CXT_FREE_ISO, the flow against
CXT_EU_FLUX and the indicators against CXT_INDICATORS: a code they lack raises
`UnknownCode` naming the closest. DS-059341's product list is CXT_NC too, so a CN8 code
passes the check for `get_trade_hs`, and DS-059341 answers one asynchronously (HTTP 413
`ASYNCHRONOUS_RESPONSE`), which this package does not poll: `InvalidRequestError`; give it
an HS code.
`list_cn8(search=None)` and `list_hs(search=None)` list CXT_NC's codes by length, the
eight-character ones and the two-, four- and six-character ones, without a request
(`list_codes("cxt_nc")` lists them all, `TOTAL` with them); a code with letters in it
(`"1507XXXX"`, `"15SSS421"`) is Eurostat's position for trade no regular code holds (not
elsewhere specified, confidential), as its label says. Over MCP the trade tasks keep the
family's cap, 200 rows or 64 KB, with a note naming `partners`, `indicators`, `since` and
`freq`, and `eurostat_list_cn8` and `eurostat_list_hs` take up to 1,000 rows within 64 KB,
with a note naming `search`.

### Datasets and codes

```python
from xippios.eurostat import list_codes, list_datasets

milk = list_datasets(search="milk")  # 18 leaves of the table of contents
cola = list_datasets(search="apro_mk_cola").data[0]
cola.code, cola.type  # ("apro_mk_cola", "dataset")
cola.title  # "Production of main cows' milk products - annual data"
cola.path  # "Database by themes > Agriculture, forestry and fisheries > ... > Milk and milk products"
cola.last_update, cola.data_start, cola.data_end  # ("05.10.2026", "1968", "2025"), as printed
milk.meta.vintage, milk.meta.published_at  # "20261027T1000", 2026-10-27 10:00 without a zone
austria = list_codes("geo", search="austria")
austria.data  # [Code(code="AT", label="Austria")]
austria.meta.vintage, austria.meta.published_at  # "28.0", 2026-03-25 23:00+01:00
list_codes("unit", search="THS_T").data[0]  # Code(code="THS_T", label="Thousand tonnes")
```

Both answer from lists packaged with this version, without a request: `meta.retrieved_at`
is when the package fetched the list, `meta.endpoint` the operation it came from.
`list_datasets(search=None)` reads Eurostat's table of contents (`catalogue/toc/xml`):
every dataset and pre-defined table of the navigation tree, over 10,000 leaves, one per
listing in the tree, each with its code, type, English title, the folders above it
(`path`, joined with `" > "`), its last update and structure change, its first and last
period and its number of values as Eurostat prints them. `meta.vintage` is the table of
contents' `creationDate` as printed and `meta.published_at` the same time, which
Eurostat prints without a zone, so `meta.published_at_naive` is set.
`list_codes(codelist, search=None)` reads one of eighteen SDMX codelists
(`sdmx/2.1/codelist/ESTAT/<ID>`, English labels): FREQ, GEO, UNIT, CROPS, STRUCPRO,
MILKITEM, DAIRYPROD, STATINFO, LEG_FORM, FARMTYPE, SO_EUR and UAAREA, the codelists of
the dimensions of apro_cpnh1, apro_mk_cola and ef_m_farmleg, named as the dimension is
(`"geo"`, case-insensitive); and from the Comext base CXT_PRODCOM2_SOLD,
CXT_PRODCOM2_TOTAL and CXT_INDICATORS, the `product` and `indicators` codes of the
Prodcom datasets, and CXT_NC, CXT_FREE_ISO and CXT_EU_FLUX, the `product`, `reporter`
and `partner`, and `flow` codes of the Comext trade datasets, whose `meta.endpoint` is
the codelist's full URL there. `meta.vintage` is the codelist's version and
`meta.published_at` its last update, `None` for CXT_EU_FLUX, which names none.
Another name raises `UnknownCode` naming the closest packaged codelists. `search` keeps
the records whose code or title (label) contains the text, ignoring case. Over MCP
`eurostat_list_datasets` keeps the family's cap and `eurostat_list_codes` takes up to
1,000 codes within the family's 64 KB, so every packaged codelist but GEO, the two
PRODCOM product lists and CXT_NC comes whole; both notes name `search`.

### Bulk download

```python
from pathlib import Path

from xippios.eurostat import download_dataset
from xippios.eurostat.parse import parse_sdmx_csv

milk = download_dataset(
    "apro_mk_cola", "A...THS_T.AT", since="2022", until="2023", dest=Path("milk.csv.gz")
)
milk.data.path  # PosixPath("milk.csv.gz"): the gzip-compressed SDMX-CSV file
milk.data.bytes  # 335
milk.data.filename  # "estat_apro_mk_cola_filtered_en.csv.gz", Eurostat's name for it
milk.meta.vintage  # "05/10/26 23:00:00": LAST UPDATE as printed, day first
milk.meta.published_at  # 2026-10-05 23:00 without a zone, meta.published_at_naive set
rows = parse_sdmx_csv(milk.data.path)  # one SdmxCsvRow per observation, read lazily
first = next(rows)
first.dimensions  # {"freq": "A", "milkitem": "PRD", "dairyprod": "D1110D", ...}
first.time_period, first.obs_value  # ("2022", Decimal("3247.05"))
```

`download_dataset(dataset, key="", *, since=None, until=None, last_n_observations=None,
dest)` sends one SDMX 2.1 data query (`dataQuery`, `sdmx/2.1/data/{flowRef}/{key}`) with
`format=SDMX-CSV` and `compressed=true` and streams the answer to `dest`, never holding
it in memory or caching it; it returns core's `Downloaded` (path, size, content type,
Eurostat's file name, retrieval time). It is a bulk task: Python only, so the MCP server
and the router skip it and no agent is handed a file path. `key` is Eurostat's series
key, the dimensions but time in the dataset's order, dot-separated, empty for every code
of a dimension, `+` between codes (`"A...THS_T.AT+DE"`); `""` downloads the whole
dataset.
`since`, `until` and `last_n_observations` are Eurostat's `startPeriod`, `endPeriod` and
`lastNObservations`. `meta.vintage` is the file's `LAST UPDATE` as printed and
`meta.published_at` the same time, which Eurostat prints without a zone; both are `None`
for a file without a row. A query Eurostat would answer asynchronously, or refuses as
too large, raises `InvalidRequestError` naming how to narrow it. `parse_sdmx_csv(path)`
reads the file, gzip-compressed or plain, row by row: each `SdmxCsvRow` has the
`dataflow`, the `last_update`, the `dimensions` in column order, the `time_period`, the
`obs_value` as a `Decimal`, or as the text printed where it is no number (Prodcom's
`"KG"`, `":E"`), `None` when empty, `obs_flag`, `conf_status` and any other `attributes`
of the dataset, as Eurostat prints them. A `DS-` dataset is downloaded from the Comext
base, `key` in its own dimensions' order (`"A.AT.10411200."` for DS-059358); a Comext
trade dataset is served filtered only, a Prodcom dataset whole as well.

```python
from xippios.eurostat import download_trade

oil = download_trade(
    "15071090", reporters=["AT"], since="2023-01", until="2023-12", dest=Path("oil.csv.gz")
)
oil.meta.request["key"]  # "M.AT..15071090..": every partner, both flows, every indicator
```

`download_trade(product=None, reporters=None, partners=None, flow=None, since=None,
until=None, freq="M", indicators=None, *, dest)` is the second bulk task, Python only as
well: it builds DS-045409's series key from `get_trade`'s arguments in the dataset's
order, freq.reporter.partner.product.flow.indicators, `+` between codes and an empty
position for an argument left `None`, checks every code as `get_trade` does, and
downloads the file as `download_dataset` does; `meta.request` records the arguments and
the key sent. `product` or `reporters` is required, since Eurostat serves no Comext trade
dataset whole; a query too large for Eurostat to answer at once (500,000 cells, the
product of the codes each position matches) raises `InvalidRequestError` naming how to
narrow it. `download_dataset("DS-045409", key)` takes a key of your own.

## MCP

```json
{
  "mcpServers": {
    "eurostat": {
      "command": "uvx",
      "args": ["--from", "xippios-eurostat[mcp]", "xippios-eurostat-mcp"]
    }
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
exactly tasks.__all__. -->

| Upstream operation | Task function | MCP tool | Status |
| --- | --- | --- | --- |
| `getData` (`statistics/1.0/data/{datasetCode}`) | `get_data(dataset, filters)`, a JSON-stat cube | `eurostat_get_data` | alpha |
| `getData` with `sinceTimePeriod` and `untilTimePeriod` | `get_series(dataset, filters, since, until)`, one series as observations in cube order, which runs oldest period first in every recorded cube | `eurostat_get_series` | alpha |
| `getData` with `lastTimePeriod=1` | `get_latest_period(dataset, filters)`, the observations of the most recent period | `eurostat_get_latest_period` | alpha |
| `getData` with `time` | `get_cross_section(dataset, period, filters)`, the observations of one period | `eurostat_get_cross_section` | alpha |
| `getTocXml` (`catalogue/toc/xml`), packaged | `list_datasets(search)`, the datasets and tables of the table of contents | `eurostat_list_datasets` | alpha |
| `codeListQuery` (`sdmx/2.1/codelist/ESTAT/{resourceID}`), packaged | `list_codes(codelist, search)`, the codes of one of eighteen codelists, six of them the Comext base's | `eurostat_list_codes` | alpha |
| `codeListQuery` (`sdmx/2.1/codelist/ESTAT/CXT_PRODCOM2_SOLD`, Comext base), packaged | `list_products(search)`, the PRODCOM products of DS-059358 | `eurostat_list_products` | alpha |
| `getData` on DS-059358 (Comext base) | `get_sold_production(product, reporters, since, until, indicators)`, Prodcom's sold production, exports and imports of one product as observations | `eurostat_get_sold_production` | alpha |
| `getData` on DS-059359 (Comext base) | `get_total_production(product, reporters, since, until, indicators)`, Prodcom's total production of one product as observations | `eurostat_get_total_production` | alpha |
| `dataQuery` (`sdmx/2.1/data/{flowRef}/{key}`), SDMX-CSV | `download_dataset(dataset, key, dest)`, a gzip-compressed SDMX-CSV file on disk | none: a bulk task, Python only, which the adapters skip | alpha |
| `codeListQuery` (`sdmx/2.1/codelist/ESTAT/CXT_NC`, Comext base), packaged | `list_cn8(search)`, the eight-digit CN codes of the trade datasets | `eurostat_list_cn8` | alpha |
| `codeListQuery` (`sdmx/2.1/codelist/ESTAT/CXT_NC`, Comext base), packaged | `list_hs(search)`, the HS chapters, headings and subheadings of the trade datasets | `eurostat_list_hs` | alpha |
| `getData` on DS-045409 (Comext base) | `get_trade(product, reporters, partners, flow, since, until, freq, indicators)`, EU trade in one CN8 or HS product as observations | `eurostat_get_trade` | alpha |
| `getData` on DS-059341 (Comext base) | `get_trade_hs(product, reporters, partners, flow, since, until, freq, indicators)`, trade of EU and non-EU countries in one HS product as observations | `eurostat_get_trade_hs` | alpha |
| `dataQuery` on DS-045409 (Comext base), SDMX-CSV | `download_trade(product, reporters, partners, flow, since, until, freq, indicators, dest)`, DS-045409's slice as a gzip-compressed SDMX-CSV file on disk | none: a bulk task, Python only, which the adapters skip | alpha |

These fifteen tasks cover Eurostat's dissemination API on its two base URLs: the main one,
`https://ec.europa.eu/eurostat/api/dissemination`, and
`https://ec.europa.eu/eurostat/api/comext/dissemination`, where Eurostat serves the
Comext and Prodcom datasets, whose codes start with `DS-`; the dataset's code chooses the
base. Not covered: polling an asynchronous answer, which is refused with how to narrow
the query; SDMX-ML and TSV; codelists other than the eighteen packaged ones, which
`list_codes` refuses naming the closest.

## Upstream terms and attribution

Data comes from Eurostat dissemination API (https://ec.europa.eu/eurostat/web/main/data/database) under its own terms of use;
this package adds no rights to it. Documentation snapshot and its attribution,
Eurostat's reuse and citation lines among them: `docs/upstream/FETCHED.md`.

## Licence

Apache-2.0. See [LICENSE](LICENSE).
