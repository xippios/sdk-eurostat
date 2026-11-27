# xippios-eurostat

Typed Python client, MCP server and FastAPI routes for
[Eurostat dissemination API](https://ec.europa.eu/eurostat/web/main/data/database), part of the
[xippios SDK family](https://github.com/xippios). Names and semantics follow the
upstream documentation; every response carries its metadata (source, endpoint,
retrieved_at, request), and the release Eurostat states, in `published_at` and `vintage`,
where it states one.

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

milk = get_data("apro_mk_cola", filters={"geo": "AT", "time": ["2022", "2023"]})
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
milk.meta.request  # {"dataset_code": "apro_mk_cola", "filters": {...}, "lang": "EN"}
```

`get_data(dataset_code, *, filters=None, lang=Lang.EN, since_time_period=None,
until_time_period=None, last_time_period=None, geo_level=None)` sends one request to the
Statistics API (`statistics/1.0/data/{datasetCode}`); `dataset_code` is its first
argument, and every other is passed by name. A `DS-` dataset, Comext trade or
Prodcom production, is requested on Eurostat's Comext base, every other on the main
base; the call and its answer are the same, and a value is the text Eurostat prints where
a Prodcom indicator is a unit or a flag:

```python
oil = get_data(
    "DS-059358",  # Prodcom: sold production, exports and imports
    filters={"reporter": "AT", "product": "10411200"},  # fish and marine oils, NACE 10.41
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
in `xippios.eurostat.models`; a plain string such as `"FR"` works too.

The codes of a dimension that one packaged codelist feeds are checked against it before
the request, on the dataset's base: `geo`, `unit` and the other ten dimensions of the
main base's codelists, and `reporter`, `flow` and `indicators` of the Comext base, as
`list_codes` lists them. A code the codelist lacks raises core's `UnknownCode`, which says
that nothing was sent and names the closest codes, and `meta.names` names each checked
code with its label (`{"geo": {"AT": "Austria"}}`). `product`, which three codelists
feed, and `partner` are sent unchecked, and so is a dimension of one base on a dataset of
the other. A cube that holds no cell, a code the dataset does not use or a period not yet
released, raises `NotFoundError` naming the dataset and the filters sent.

`meta.published_at` is the cube's `updated` with Eurostat's zone; one printed without a
zone, never seen, is kept as printed with `meta.published_at_naive` set, and
`meta.vintage` holds the text either way. An unknown dataset, and Eurostat's "No results
found", raise `NotFoundError` too; a query Eurostat refuses raises `InvalidRequestError`
with Eurostat's message, and one it judges too large core's `QueryTooLarge`, with
Eurostat's estimate and limit and how to narrow it. A query Eurostat would answer
asynchronously raises `InvalidRequestError`: this package does not poll asynchronous
answers, and the Statistics API's own route is to send the same request again later. Ask
for small slices: the cube comes back whole, and over MCP a result above 64 KB is replaced
by a preview and a note.

### Datasets and codes

```python
from xippios.eurostat import list_codes, list_datasets

milk = list_datasets(search="milk")  # 18 leaves of the table of contents
cola = list_datasets(search="apro_mk_cola").data[0]
cola.code, cola.type  # ("apro_mk_cola", "dataset")
cola.title  # "Production of main cows' milk products - annual data"
cola.path  # "Database by themes > Agriculture, forestry and fisheries > ... > Milk and milk products"
cola.last_update, cola.data_start, cola.data_end  # ("05.11.2026", "1968", "2025"), as printed
milk.meta.vintage, milk.meta.published_at  # "20261120T1004", 2026-11-20 10:04 without a zone
austria = list_codes("geo", search="austria")
austria.data  # [Code(code="AT", label="Austria")]
austria.meta.vintage, austria.meta.published_at  # "28.1", 2026-11-16 23:00+01:00
list_codes("unit", search="THS_T").data[0]  # Code(code="THS_T", label="Thousand tonnes")
```

Both answer from lists packaged with this version, without a request: `meta.retrieved_at`
is when the package fetched the list, `meta.endpoint` the operation it came from.
`list_datasets(*, search=None)` reads Eurostat's table of contents (`catalogue/toc/xml`):
every dataset and pre-defined table of the navigation tree, over 10,000 leaves, one per
listing in the tree, each with its code, type, English title, the folders above it
(`path`, joined with `" > "`), its last update and structure change, its first and last
period and its number of values as Eurostat prints them, each `None` where it prints
none. `meta.vintage` is the table of contents' `creationDate` as printed and
`meta.published_at` the same time, which Eurostat prints without a zone, so
`meta.published_at_naive` is set.
`list_codes(codelist, *, search=None)` reads one of eighteen SDMX codelists
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
PRODCOM product lists and CXT_NC comes whole. Both tools take `offset`, the rows already
shown, and the note of a cut answer names `search` and the `offset` to continue with; the
next page sends no request.

### Bulk download

```python
from pathlib import Path

from xippios.eurostat import download_dataset
from xippios.eurostat.parse import parse_sdmx_csv

milk = download_dataset(
    "apro_mk_cola",
    "A...THS_T.AT",
    start_period="2022",
    end_period="2023",
    dest=Path("milk.csv.gz"),
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

`download_dataset(flow_ref, key="", *, start_period=None, end_period=None,
last_n_observations=None, dest)` sends one SDMX 2.1 data query (`dataQuery`, `sdmx/2.1/data/{flowRef}/{key}`) with
`format=SDMX-CSV` and `compressed=true` and streams the answer to `dest`, never holding
it in memory or caching it; it returns core's `Downloaded` (path, size, content type,
Eurostat's file name, retrieval time). It is a bulk task: Python only, so the MCP server
and the router skip it and no agent is handed a file path. `key` is Eurostat's series
key, the dimensions but time in the dataset's order, dot-separated, empty for every code
of a dimension, `+` between codes (`"A...THS_T.AT+DE"`); `""` downloads the whole
dataset.
`start_period`, `end_period` and `last_n_observations` are Eurostat's `startPeriod`,
`endPeriod` and `lastNObservations`. `meta.vintage` is the file's `LAST UPDATE` as printed and
`meta.published_at` the same time, which Eurostat prints without a zone; both are `None`
for a file without a row. A query Eurostat would answer asynchronously raises
`InvalidRequestError`, and one it refuses as too large `QueryTooLarge`, each naming how to
narrow it. `parse_sdmx_csv(path)`
reads the file, gzip-compressed or plain, row by row: each `SdmxCsvRow` has the
`dataflow`, the `last_update`, the `dimensions` in column order, the `time_period`, the
`obs_value` as a `Decimal`, or as the text printed where it is no number (Prodcom's
`"KG"`, `":E"`), `None` when empty, `obs_flag`, `conf_status` and any other `attributes`
of the dataset, as Eurostat prints them. A `DS-` dataset is downloaded from the Comext
base, `key` in its own dimensions' order (`"A.AT.10411200."` for DS-059358); a Comext
trade dataset is served filtered only, a Prodcom dataset whole as well.

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
exactly tasks.__all__, and tasks_write.__all__ where the package has write tasks. -->

| Upstream operation | Task function | MCP tool | Status |
| --- | --- | --- | --- |
| `getData` (`statistics/1.0/data/{datasetCode}`) | `get_data(dataset_code, filters)`, a JSON-stat cube | `eurostat_get_data` | alpha |
| `getTocXml` (`catalogue/toc/xml`), packaged | `list_datasets(search)`, the datasets and tables of the table of contents | `eurostat_list_datasets` | alpha |
| `codeListQuery` (`sdmx/2.1/codelist/ESTAT/{resourceID}`), packaged | `list_codes(codelist, search)`, the codes of one of eighteen codelists, six of them the Comext base's | `eurostat_list_codes` | alpha |
| `dataQuery` (`sdmx/2.1/data/{flowRef}/{key}`), SDMX-CSV | `download_dataset(flow_ref, key, dest)`, a gzip-compressed SDMX-CSV file on disk | none: a bulk task, Python only, which the adapters skip | alpha |

Two of these four tasks choose the base URL by the dataset's code: `get_data` and
`download_dataset` request a dataset whose code starts with `DS-`, Eurostat's Comext and
Prodcom datasets, on `https://ec.europa.eu/eurostat/api/comext/dissemination`, and every
other on the main base URL, `https://ec.europa.eu/eurostat/api/dissemination`. The
Comext base serves Prodcom's DS-059358 and DS-059359 and Comext's DS-045409 and
DS-059341. `list_codes` lists eighteen packaged codelists, twelve of the main base and
six of the Comext base, CXT_PRODCOM2_SOLD and CXT_NC among them, the products of the
Prodcom and trade datasets. `list_datasets` lists the main base's table of contents only, and does not list the
Comext or Prodcom datasets: the Comext base answers `catalogue/toc/xml` with HTTP 404
(probed 2026-10-28), though its WADL lists it. Not covered: polling an asynchronous
answer, which is refused with how to narrow the query; SDMX-ML and TSV; codelists other
than the eighteen packaged ones, which `list_codes` refuses naming the closest.

## Upstream terms and attribution

Data comes from Eurostat dissemination API (https://ec.europa.eu/eurostat/web/main/data/database) under its own terms of use;
this package adds no rights to it. Documentation snapshot and its attribution,
Eurostat's reuse and citation lines among them: `docs/upstream/FETCHED.md`.

## Workflows

`ci.yml` runs ruff, its format check, mypy, pytest and pre-commit on Python 3.12, 3.13 and
3.14, requires a changelog entry of every pull request but Dependabot's and refuses a
fixture file over 256 KiB that a pull request adds or changes. It runs on every pull request and,
called by `publish.yml`, once for a release, and its job `ci` is the check the
organization's ruleset requires. It is handed no secret, and no variable switches it off.

`publish.yml` is the release train (conventions §12): on a push to `main` whose
`pyproject.toml` names a version that has no tag yet and has its section in `CHANGELOG.md`,
it runs `ci.yml`, refuses a core pinned to git, tags the merge commit, builds the package
and, once a reviewer of the environment `pypi` approves the run, publishes it to PyPI by
trusted publishing. Every push to `main` and a dispatch start it, and a push that brings no
release ends quietly. It is handed no secret: the step that tells a release is handed the
job's token as `GH_TOKEN`, the tag goes with the job's token and PyPI trusts the workflow
itself. Its job `tag` holds the one checkout of the repository that keeps its credentials,
since it pushes the tag with the job's token; every other checkout sets
`persist-credentials: false` (conventions §13). No variable switches it off.

`live.yml` runs every `live` test against the upstream with `--tb=short --assert=plain`, so
its public log holds neither a failing test's arguments nor the values an assertion compared.
It runs every night at 04:59 UTC and on demand, never on a pull request.
Its pytest step alone is handed `XIPPIOS_LIVE_TESTS`, and no secret.
A variable `WORKFLOW_LIVE` of `off`, the repository's over the organization's, switches it off.

`conventions.yml` calls the organization's review of a pull request against the documents
listed under Documents below, the check `conventions / conventions`, when a pull request
opens, is pushed to, reopens or is edited, and on a push to `main` or a dispatch the review
of the range of commits, `range / range`. It hands the review the organization's
secret of the model's key, by name. A variable `WORKFLOW_CONVENTIONS` of `off`, the
repository's over the organization's, switches both off.

`adr-index.yml` calls the organization's check of the ADR index, `adr-index / adr-index`,
which runs `scripts/adr_index.py --check`, when a pull request opens, is pushed to or
reopens. It hands over nothing, and the called workflow reads its switch itself: a variable
`WORKFLOW_ADR_INDEX` of `off`, the repository's over the organization's, skips the check.

## Documents

- sdk-core: [docs/conventions.md](https://github.com/xippios/sdk-core/blob/main/docs/conventions.md) — the conventions every xippios source package follows: its layout, names, results, tests and releases.
- sdk-core: [docs/adr.md](https://github.com/xippios/sdk-core/blob/main/docs/adr.md) — the index of the family's architecture decisions, which the conventions cite.
- sdk-core: [docs/definition-of-done.md](https://github.com/xippios/sdk-core/blob/main/docs/definition-of-done.md) — what a change satisfies before its pull request is opened.
- sdk-core: [docs/review-checklist.md](https://github.com/xippios/sdk-core/blob/main/docs/review-checklist.md) — what the review of a pull request checks, in order.
- sdk-eurostat: [docs/adr.md](https://github.com/xippios/sdk-eurostat/blob/main/docs/adr.md) — the index of this package's own decisions, generated from the records in `docs/adr/`.
- sdk-eurostat: [docs/upstream/FETCHED.md](https://github.com/xippios/sdk-eurostat/blob/main/docs/upstream/FETCHED.md) — the snapshot of the upstream documentation, the reference for names, parameters and semantics.

## Licence

Apache-2.0. See [LICENSE](https://github.com/xippios/sdk-eurostat/blob/main/LICENSE).
