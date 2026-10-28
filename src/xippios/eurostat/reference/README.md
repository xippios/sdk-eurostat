# Reference data for Eurostat dissemination API

The lists `list_datasets`, `list_codes`, `list_products`, `list_cn8` and `list_hs` answer
from, and the production and trade tasks check their codes against, ship here as JSON,
versioned with the package: the nineteen lists are packaged-list files (conventions §3,
ADR-0022) that `xippios.core.PackagedList.load` reads through `params.py`, and
`lists.json` beside them is a plain derived index, read with `load_json`:

```python
from xippios.core import PackagedList

geo = PackagedList.load("xippios.eurostat", "geo")
geo.records[0]  # {"code": "EUR", "label": "Europe"}
```

- `toc.json`: every leaf of the Catalogue API's table of contents, datasets and
  pre-defined tables, with its code, type, English title, the folders above it
  (`path`, their English titles joined with ` > `), `lastUpdate`, `lastModified`,
  `dataStart`, `dataEnd` and `values` as printed.
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
  them (ADR-0022, amendment 8; gap, row 111). It is derived from the nineteen answers
  the packaged lists come from and names no upstream operation, so it has no origin and
  no row in the table below.

The script, not the package, parses the TOC's XML, the only XML parsed anywhere (D44),
and it reads the codelists as JSON-stat. A record's fields are upstream's (`lastUpdate`,
`dataStart`), and `path`, `code` and `label` name what the package reads out of the
tree's nesting and a codelist's `category`. No enum is generated from these lists, too
large for one; `enums.py` is the renderer's empty module.

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
| `toc.json` | `catalogue/toc/xml` | 2026-10-27T19:55:14Z |
| `freq.json` | `sdmx/2.1/codelist/ESTAT/FREQ` | 2026-10-27T19:55:17Z |
| `geo.json` | `sdmx/2.1/codelist/ESTAT/GEO` | 2026-10-27T19:55:19Z |
| `unit.json` | `sdmx/2.1/codelist/ESTAT/UNIT` | 2026-10-27T19:55:21Z |
| `crops.json` | `sdmx/2.1/codelist/ESTAT/CROPS` | 2026-10-27T19:55:23Z |
| `strucpro.json` | `sdmx/2.1/codelist/ESTAT/STRUCPRO` | 2026-10-27T19:55:25Z |
| `milkitem.json` | `sdmx/2.1/codelist/ESTAT/MILKITEM` | 2026-10-27T19:55:27Z |
| `dairyprod.json` | `sdmx/2.1/codelist/ESTAT/DAIRYPROD` | 2026-10-27T19:55:26Z |
| `statinfo.json` | `sdmx/2.1/codelist/ESTAT/STATINFO` | 2026-10-27T19:55:28Z |
| `leg_form.json` | `sdmx/2.1/codelist/ESTAT/LEG_FORM` | 2026-10-27T19:55:30Z |
| `farmtype.json` | `sdmx/2.1/codelist/ESTAT/FARMTYPE` | 2026-10-27T19:55:32Z |
| `so_eur.json` | `sdmx/2.1/codelist/ESTAT/SO_EUR` | 2026-10-27T19:55:34Z |
| `uaarea.json` | `sdmx/2.1/codelist/ESTAT/UAAREA` | 2026-10-27T19:55:36Z |
| `cxt_prodcom2_sold.json` | `https://ec.europa.eu/eurostat/api/comext/dissemination/sdmx/2.1/codelist/ESTAT/CXT_PRODCOM2_SOLD` | 2026-10-28T14:25:01Z |
| `cxt_prodcom2_total.json` | `https://ec.europa.eu/eurostat/api/comext/dissemination/sdmx/2.1/codelist/ESTAT/CXT_PRODCOM2_TOTAL` | 2026-10-28T14:25:02Z |
| `cxt_indicators.json` | `https://ec.europa.eu/eurostat/api/comext/dissemination/sdmx/2.1/codelist/ESTAT/CXT_INDICATORS` | 2026-10-28T14:25:04Z |
| `cxt_nc.json` | `https://ec.europa.eu/eurostat/api/comext/dissemination/sdmx/2.1/codelist/ESTAT/CXT_NC` | 2026-10-28T15:13:49Z |
| `cxt_free_iso.json` | `https://ec.europa.eu/eurostat/api/comext/dissemination/sdmx/2.1/codelist/ESTAT/CXT_FREE_ISO` | 2026-10-28T15:13:49Z |
| `cxt_eu_flux.json` | `https://ec.europa.eu/eurostat/api/comext/dissemination/sdmx/2.1/codelist/ESTAT/CXT_EU_FLUX` | 2026-10-28T15:13:51Z |
