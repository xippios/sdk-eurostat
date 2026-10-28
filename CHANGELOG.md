# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/) (pre-1.0: breaking changes bump the minor).

## [Unreleased]

### Added

- Scaffold from [sdk-template](https://github.com/xippios/sdk-template): configured
  client for Eurostat dissemination API, empty task layer, MCP server and FastAPI router
  wired to it, test harness with core's family check, CI, the nightly live tests and
  the release train, in which a release PR's merge tags and publishes.
- Upstream documentation snapshot of 2026-10-27 in `docs/upstream/`: 17 pages of
  Eurostat's user guide "Data access via API" as Markdown, the WADL files of the
  Statistics, SDMX 2.1, Catalogue and asynchronous APIs and the consolidated OpenAPI
  document verbatim, and one JSON-stat and one SDMX-CSV answer as structural samples;
  written by `scripts/refresh_upstream.py` (standard library only, no key), whose
  `FETCHED.md` records each file's URL, fetch time, size and sha256, the pages not
  fetched and why, and Eurostat's licence and reuse lines, its exceptions to commercial
  reuse, its clause on modified reuse with the snapshot's disclaimer, and its citation
  form.
- `get_data(dataset, filters=None, *, lang=Lang.EN, since_time_period=None,
  until_time_period=None, last_time_period=None, geo_level=None)`: one Statistics API
  request (`getData`, `statistics/1.0/data/{datasetCode}`) answered as a `Cube`, the
  JSON-stat 2.0 dataset member by member, with `Cube.observations()` reading out the
  cells that have a value or a status, each an `Observation` with its codes and labels;
  `meta.published_at` is the cube's `updated`, with `meta.published_at_naive` set should
  Eurostat print it without a zone (never seen; ADR-0022 rule 2), and `meta.vintage` its
  text as printed. The StrEnums `Lang` and `GeoLevel` type `lang` and `geo_level`; more
  than one time parameter, other than `since_time_period` with `until_time_period`, is
  refused before sending. The MCP tool `eurostat_get_data` and the route
  `POST /eurostat/get_data`.
- `classify` for the Statistics API's refusals (`errors.py`): an unknown dataset, and an
  HTTP 400 whose faults are all 100 ("No results found"), are `NotFoundError`; any other
  HTTP 400 `error`, as an array or as one object, is `InvalidRequestError` with
  Eurostat's label; the asynchronous answer is `InvalidRequestError` saying to send the
  request again later or to narrow it, and an HTTP 413 `InvalidRequestError` naming how
  to narrow it. An unknown code is an empty cube, not an error.
- `get_series(dataset, filters, *, since=None, until=None, lang=Lang.EN)`,
  `get_latest_period(dataset, filters=None, *, lang=Lang.EN)` and
  `get_cross_section(dataset, period, filters=None, *, lang=Lang.EN)`: the task-shaped
  slices, each one `getData` request through `get_data` (`sinceTimePeriod` and
  `untilTimePeriod`, `lastTimePeriod=1`, `time=<period>`) answered as a list of
  `Observation` with `get_data`'s `meta`. `get_series` refuses, after the request, an
  answer that spans more than one series, naming the dimensions to pin and their codes;
  each slice refuses a `time` filter before sending, and `get_cross_section` an empty
  `period`; a code that matches nothing gives an empty list. The MCP tools
  `eurostat_get_series`, `eurostat_get_latest_period` and `eurostat_get_cross_section`,
  each with a result cap of its own in `MCP_CAPS` (the family's 200 rows or 64 KB, with
  a note on how to see the rest), and the routes `POST /eurostat/get_series`,
  `/eurostat/get_latest_period` and `/eurostat/get_cross_section`.
- `list_datasets(search=None)` and `list_codes(codelist, search=None)`: packaged answers
  (ADR-0022) without a request. `list_datasets` reads the Catalogue API's table of
  contents (`catalogue/toc/xml`, 10,375 leaves on 2026-10-27), each leaf a `Dataset`
  with its code, type (`LeafType`), English title, the folders above it as `path`,
  `lastUpdate`, `lastModified`, `dataStart`, `dataEnd` and `values` as printed;
  `meta.vintage` is the TOC's `creationDate` as printed and `meta.published_at` its
  time without a zone, `published_at_naive` set. `list_codes` reads one of the twelve
  codelists of the dimensions of apro_cpnh1, apro_mk_cola and ef_m_farmleg (FREQ, GEO,
  UNIT, CROPS, STRUCPRO, MILKITEM, DAIRYPROD, STATINFO, LEG_FORM, FARMTYPE, SO_EUR,
  UAAREA; `sdmx/2.1/codelist/ESTAT/<ID>`, latest version, English labels), each code a
  `Code`; the name is case-insensitive, an unknown one raises `UnknownCode` naming the
  closest; `meta.vintage` is the codelist's version and `meta.published_at` its
  `LAST_UPDATED`. `search` keeps the records whose code or title (label) contains the
  text, ignoring case. `meta.retrieved_at` is the list's fetch time. The MCP tools
  `eurostat_list_datasets` (the family's cap) and `eurostat_list_codes` (1,000 rows
  within the family's 64 KB), each with a note naming `search`, and the routes
  `GET /eurostat/list_datasets` and `/eurostat/list_codes`.
- `scripts/refresh_reference.py` fetches the table of contents (downloaded whole to a
  temporary file with core's `download`, which streams the body to disk, then read from
  that file a megabyte at a time with the standard library's ElementTree pull parser;
  the script is the only code that parses XML, the package parses none) and the twelve
  codelists as JSON-stat through the new endpoint wrappers `api.catalogue.getTocXml`
  and `api.sdmx.codeListQuery`. It writes `reference/toc.json` and one
  `reference/<codelist>.json` each with `PackagedList.write`, and `reference/lists.json`,
  a derived index in plain JSON (`fetched` and `lists`) that holds upstream's release
  identifiers of every list; `--samples` cuts the parser tests' samples under
  `tests/fixtures/files/` from the same run. Thirteen keyless requests.

### Changed

- `xippios-core` 0.3.0 from PyPI (`core_version` 0.3.0: `~=0.3.0` and its `mcp`, `http`
  and `testing` extras likewise), with no git pin; the template stays v0.2.2, and the
  adoption of template v0.3.0 follows as a PR of its own. Core 0.3.0 keeps the SDMX
  series `key` of this keyless source as data, not as a credential (ADR-0019,
  decision 6), and brings `AsyncClient.download`, `decode_text` and `decode_csv` for
  bulk files (ADR-0019, decisions 1 and 2); `pydantic-settings`, which core no longer
  depends on, and `python-dotenv` with it leave `uv.lock`.
- `scripts/refresh_reference.py` renders `enums.py` with one `render_enums` call, value
  lists and id lists in one module, each list with its own fetch date, and formats it
  with `ruff format` and `ruff check --fix`, since core 0.3.0 removed `render_str_enums`
  and `render_int_enums` (ADR-0008, amendment 2026-10-27): the port of core 0.3.0's
  Hand-apply entry; `scripts/` is the package's, so template v0.3.0 reaches it only
  through its Hand-apply list. `enums.py` is re-rendered by the script's first run, the
  renderer's empty module, since Eurostat's packaged lists are tables and none is an
  enum; the reference README and `/refresh-reference-data` name the new call.
- The client caches answers of HTTP 200 in core's `MemoryCache`, five minutes each, up
  to core's `cache_max_bytes` of 8 MiB a body, so a larger cube is fetched again
  (ADR-0019 decision 3); `getData` reads its answer with core 0.3.0's
  `AsyncClient.get_answer`, so `get_data`'s `meta.retrieved_at` on a cache hit is the
  time the answer was stored (conventions §4, ADR-0015 decision 5).
