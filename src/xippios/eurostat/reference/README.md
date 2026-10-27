# Reference data for Eurostat dissemination API

The lists `list_datasets` and `list_codes` answer from ship here as JSON, versioned with
the package, each a packaged-list file (conventions §3, ADR-0022) that
`xippios.core.PackagedList.load` reads through `params.py`:

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
  SDMX codelist, the latest version, in upstream's order; the twelve codelists of the
  dimensions of apro_cpnh1, apro_mk_cola and ef_m_farmleg.
- `lists.json`: one record per packaged list with upstream's release identifiers, the
  TOC's `creationDate` and a codelist's `version` and `LAST_UPDATED`, which the list
  tasks read for `meta.vintage` and `meta.published_at`; a packaged-list file has no key
  for them (ADR-0022, amendment 8).

Rules:

- Files come from the upstream through `scripts/refresh_reference.py`
  (`/refresh-reference-data`), never typed in by hand; the script rewrites the table
  below. It parses the TOC's XML, the only XML the package reads (D44), and reads the
  codelists as JSON-stat.
- Files keep upstream's names: a record's fields are upstream's (`lastUpdate`,
  `dataStart`), and `path`, `code` and `label` name what the package reads out of the
  tree's nesting and a codelist's `category`.
- No enum is generated from these lists, too large for one; `enums.py` is the
  renderer's empty module.
- Every file has a row below naming the upstream operation it came from and when it
  was fetched.

| File | Origin | Fetched |
| --- | --- | --- |
| `lists.json` | `sdmx/2.1/codelist/ESTAT` | 2026-10-27T19:55:36Z |
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
