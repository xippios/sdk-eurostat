# Parser-test samples

Small real samples of the answers the package and its refresh script read, under
`<kind>/<case>.*`, never written by hand (ADR-0020 decision 6, conventions §10): `toc/`
and `codelist/` cut by `scripts/refresh_reference.py --samples` from the answers of its
run, which rewrites their rows and keeps the others; `sdmx-csv/` the response bodies of
the recorded `tests/fixtures/data_query/` exchanges, byte for byte, which
`tests/test_parse.py` checks. One row per file: the release (upstream's identifier of
it), the URL, the bytes and sha256 of the full answer, and when it was fetched. The
parser tests in `tests/test_refresh_reference.py` and `tests/test_parse.py` read them;
they assert shape, never values or sizes.

| File | Release | URL | Bytes | sha256 | Fetched | What |
| --- | --- | --- | --- | --- | --- | --- |
| `toc/apro_mk.xml` | `20261027T1000` (creationDate) | https://ec.europa.eu/eurostat/api/dissemination/catalogue/toc/xml | 23310491 | `40043970a6ecd003df517d839d0322d2d7a108b04a962bde58bd944b2b491768` | 2026-10-27T19:55:14Z | the folder `apro_mk` with the leaves `apro_mk_cola`, `apro_mk_farm` and the folders above it, written again by ElementTree |
| `codelist/statinfo.json` | `16.0` (version) | https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/codelist/ESTAT/STATINFO?format=JSON&lang=en | 18494 | `5d9fb944ba53fe7a8e0ecba22c189da04098192961d7eed567c76d98239c86e7` | 2026-10-27T19:55:28Z | the whole answer, decoded and written again as compact JSON |
| `sdmx-csv/apro_mk_cola_AT_THS_T_2022_2023.csv` | `05/10/26 23:00:00` (LAST UPDATE) | https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/apro_mk_cola/A...THS_T.AT?format=SDMX-CSV&startPeriod=2022&endPeriod=2023 | 1652 | `6f541935c29cea0f9c995f9303479f1b43696c008cf5a1c567894eac9678d901` | 2026-10-27T21:44:01Z | the whole answer, the response body of `data_query/apro_mk_cola_AT_THS_T_2022_2023.json` byte for byte |
| `sdmx-csv/apro_mk_cola_AT_THS_T_2022_2023.csv.gz` | `05/10/26 23:00:00` (LAST UPDATE) | https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/apro_mk_cola/A...THS_T.AT?format=SDMX-CSV&startPeriod=2022&endPeriod=2023&compressed=true | 335 | `06a3171aee98f5455e68d90b32d07e97ba9c8e9309d562f26e3fb3a213fd732b` | 2026-10-27T21:44:07Z | the whole gzip file, the response body of `data_query/apro_mk_cola_AT_THS_T_2022_2023_compressed.json` byte for byte; it decompresses to the plain sample |
