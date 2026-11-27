# Reference data for Eurostat dissemination API

The lists that `list_datasets` and `list_codes` answer from ship here as JSON, versioned
with the package: the nineteen lists are packaged-list files (conventions §3,
sdk-core ADR-0041) that `xippios.core.PackagedList.load` reads through `params.py`, and
`lists.json` beside them is a plain derived index, read with `load_json`:

```python
from xippios.core import PackagedList

geo = PackagedList.load("xippios.eurostat", "geo")
geo.records[0]  # {"code": "EUR", "label": "Europe*"}
```

- `toc.json`: every leaf of the Catalogue API's table of contents, datasets and
  pre-defined tables, with its code, type, English title, the folders above it
  (`path`, their English titles joined with ` > `), `lastUpdate` and `lastModified`,
  which the table of contents prints day first (`05.11.2026`) and the script, from 0.4.0
  on, writes as ISO dates (`2026-11-05`), the form `dump_upstream` writes a date in, and
  `dataStart`, `dataEnd` and `values` as printed. The package reads a date in either form,
  as the file written on 2026-11-27 holds the printed one.
- `<codelist>.json`, the codelist's id lower-cased: the codes and English labels of one
  SDMX codelist, the latest version, in upstream's order, its `param` the dimension it
  feeds (`params.CODELISTS`). Twelve come from the main base, the codelists of the
  dimensions of apro_cpnh1, apro_mk_cola and ef_m_farmleg, each feeding the dimension
  named as its id lower-cased; six from the Comext base,
  `https://ec.europa.eu/eurostat/api/comext/dissemination`. Three are the codelists of the
  Prodcom datasets DS-059358 and DS-059359: `cxt_prodcom2_sold.json` and
  `cxt_prodcom2_total.json`, their `product` codes (the second a part of the first), and
  `cxt_indicators.json`, the `indicators` codes of both, which Comext's trade datasets
  share. Three are the codelists of the Comext trade datasets DS-045409 and DS-059341:
  `cxt_nc.json`, their `product` codes, the Combined Nomenclature's eight-digit codes with
  the HS chapters, headings and subheadings (about 7 MB, the largest file here);
  `cxt_free_iso.json`, their `reporter` and `partner` codes, its `param` the first of the
  two, which the Prodcom datasets' `reporter` takes too; and `cxt_eu_flux.json`, their
  `flow` codes, a codelist without a `LAST_UPDATED` annotation.
- `lists.json`: not a packaged list but a derived index, plain JSON read with
  `load_json`: `fetched`, the latest `fetched` among the packaged lists, and `lists`,
  one record per packaged list with upstream's release identifiers, the TOC's
  `creationDate` and a codelist's `version` and `LAST_UPDATED`, which the list tasks
  read for `meta.vintage` and `meta.published_at`; a packaged-list file has no key for
  them (sdk-core ADR-0041, decision 5; https://github.com/xippios/sdk-core/issues/81). It
  is derived from the nineteen answers the packaged lists come from and names no upstream
  operation, so it has no origin and no row in the table below.

The script, not the package, parses the TOC's XML, the only XML parsed anywhere, and it
reads the codelists as JSON-stat (decision D1 of
https://github.com/xippios/sdk-eurostat/pull/6). A record's fields are upstream's
(`lastUpdate`, `dataStart`), and `path`, `code` and `label` name what the package reads
out of the tree's nesting and a codelist's `category`. No enum is generated from these lists, too
large for one, so the package holds no `enums.py`.

Each packaged-list file holds `{"param", "endpoint", "fetched", "records"}` and an
optional `"note"`, upstream's records under upstream's field names, written by
`/refresh-reference-data`'s script, `scripts/refresh_reference.py`, with
`PackagedList.write`, never by hand, and read with `PackagedList.load`; the script
rewrites the table below, a run with `--only` the rows of the lists it names and no
other. One row per packaged list: Origin is the endpoint it was fetched from, the path
on the main base and the full URL on the Comext base, as the file's `endpoint` records
it, none being rebuilt from a `docs/upstream/` file; Fetched is the UTC time of that
fetch.

| File | Origin | Fetched |
| --- | --- | --- |
| `toc.json` | `catalogue/toc/xml` | 2026-11-27T07:26:43Z |
| `freq.json` | `sdmx/2.1/codelist/ESTAT/FREQ` | 2026-11-27T07:26:45Z |
| `geo.json` | `sdmx/2.1/codelist/ESTAT/GEO` | 2026-11-27T07:26:47Z |
| `unit.json` | `sdmx/2.1/codelist/ESTAT/UNIT` | 2026-11-27T07:26:49Z |
| `crops.json` | `sdmx/2.1/codelist/ESTAT/CROPS` | 2026-11-27T07:26:51Z |
| `strucpro.json` | `sdmx/2.1/codelist/ESTAT/STRUCPRO` | 2026-11-27T07:26:53Z |
| `milkitem.json` | `sdmx/2.1/codelist/ESTAT/MILKITEM` | 2026-11-27T07:26:55Z |
| `dairyprod.json` | `sdmx/2.1/codelist/ESTAT/DAIRYPROD` | 2026-11-27T07:26:57Z |
| `statinfo.json` | `sdmx/2.1/codelist/ESTAT/STATINFO` | 2026-11-27T07:27:23Z |
| `leg_form.json` | `sdmx/2.1/codelist/ESTAT/LEG_FORM` | 2026-11-27T07:27:04Z |
| `farmtype.json` | `sdmx/2.1/codelist/ESTAT/FARMTYPE` | 2026-11-27T07:27:06Z |
| `so_eur.json` | `sdmx/2.1/codelist/ESTAT/SO_EUR` | 2026-11-27T07:27:08Z |
| `uaarea.json` | `sdmx/2.1/codelist/ESTAT/UAAREA` | 2026-11-27T07:27:10Z |
| `cxt_prodcom2_sold.json` | `https://ec.europa.eu/eurostat/api/comext/dissemination/sdmx/2.1/codelist/ESTAT/CXT_PRODCOM2_SOLD` | 2026-11-27T07:27:12Z |
| `cxt_prodcom2_total.json` | `https://ec.europa.eu/eurostat/api/comext/dissemination/sdmx/2.1/codelist/ESTAT/CXT_PRODCOM2_TOTAL` | 2026-11-27T07:27:14Z |
| `cxt_indicators.json` | `https://ec.europa.eu/eurostat/api/comext/dissemination/sdmx/2.1/codelist/ESTAT/CXT_INDICATORS` | 2026-11-27T07:27:16Z |
| `cxt_nc.json` | `https://ec.europa.eu/eurostat/api/comext/dissemination/sdmx/2.1/codelist/ESTAT/CXT_NC` | 2026-11-27T07:27:19Z |
| `cxt_free_iso.json` | `https://ec.europa.eu/eurostat/api/comext/dissemination/sdmx/2.1/codelist/ESTAT/CXT_FREE_ISO` | 2026-11-27T07:27:20Z |
| `cxt_eu_flux.json` | `https://ec.europa.eu/eurostat/api/comext/dissemination/sdmx/2.1/codelist/ESTAT/CXT_EU_FLUX` | 2026-11-27T07:27:22Z |
