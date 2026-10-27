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
  through its Hand-apply list. `enums.py` is not re-rendered, since no list is packaged
  yet; the reference README and `/refresh-reference-data` name the new call.
