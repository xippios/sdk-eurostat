# Parser-test samples

Small real samples of the answers `scripts/refresh_reference.py` reads, under
`<kind>/<case>.*`, cut by `scripts/refresh_reference.py --samples` from the answers of
its run, never by hand (ADR-0020 decision 6, conventions §10). One row per file: the
release (upstream's identifier of it), the URL, the bytes and sha256 of the full answer,
and when it was fetched. The parser tests in `tests/test_refresh_reference.py` read
them; they assert shape, never values or sizes.

| File | Release | URL | Bytes | sha256 | Fetched | What |
| --- | --- | --- | --- | --- | --- | --- |
| `toc/apro_mk.xml` | `20261027T1000` (creationDate) | https://ec.europa.eu/eurostat/api/dissemination/catalogue/toc/xml | 23310491 | `40043970a6ecd003df517d839d0322d2d7a108b04a962bde58bd944b2b491768` | 2026-10-27T19:55:14Z | the folder `apro_mk` with the leaves `apro_mk_cola`, `apro_mk_farm` and the folders above it, written again by ElementTree |
| `codelist/statinfo.json` | `16.0` (version) | https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/codelist/ESTAT/STATINFO?format=JSON&lang=en | 18494 | `5d9fb944ba53fe7a8e0ecba22c189da04098192961d7eed567c76d98239c86e7` | 2026-10-27T19:55:28Z | the whole answer, decoded and written again as compact JSON |
