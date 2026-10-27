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
- Upstream documentation snapshot of 2026-10-27 in `docs/upstream/`: the 17 pages of
  Eurostat's user guide "Data access via API" as Markdown, the WADL files of the
  Statistics, SDMX 2.1, Catalogue and asynchronous APIs and the consolidated OpenAPI
  document verbatim, and one JSON-stat and one SDMX-CSV answer as structural samples;
  written by `scripts/refresh_upstream.py` (standard library only, no key), whose
  `FETCHED.md` records each file's URL, fetch time, size and sha256, the pages not
  fetched and why, and Eurostat's licence and reuse lines, its exceptions to commercial
  reuse and its citation form.
