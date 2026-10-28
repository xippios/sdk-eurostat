# sdk-eurostat — instructions for Claude Code

`xippios-eurostat` wraps Eurostat dissemination API as a typed Python client, an MCP server
and FastAPI routes, built on `xippios-core`. This file is the contract for every session
that works here; the family rules it points to apply as well.

@.claude/family.md

## What this package wraps

| | |
| --- | --- |
| Upstream | Eurostat dissemination API, https://ec.europa.eu/eurostat/web/main/data/database |
| API base URL | `https://ec.europa.eu/eurostat/api/dissemination` |
| Documentation | https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-introduction, snapshotted in `docs/upstream/` |
| Credentials | none; the API is open |
| Rate limit | 30 requests per minute, burst 1; a self-imposed pace, upstream documents no rate in numbers (ADR-0010); the user guide states a fair-use rule without a number: past thresholds it does not give on concurrent requests, requests and extraction cost per day, 7 and 30 days, requests are answered asynchronously (`docs/upstream/user-guide/api-detailed-guidelines/asynchronous-api.md`, "Fair use of the service"); enforced client-side in `_client.py` |
| Write tools | no, this package is read-only |

The snapshot in `docs/upstream/` is the reference for names, parameters and semantics.

## Layout

```
src/xippios/eurostat/
  __init__.py      public surface: __version__ and re-exported task functions
  py.typed         PEP 561 marker; consumers' mypy --strict needs it
  _version.py      __version__ from distribution metadata
  _client.py       the one configured AsyncClient (base URL, rate limit, cache) and
                   classify, upstream's documented error shapes; no key
  errors.py        the Statistics API's fault model and its parsing, for classify
  models.py        pydantic models mirroring upstream payloads (UpstreamModel)
  api/             endpoint wrappers, one module per upstream service (statistics,
                   catalogue, sdmx), one function per operation
  tasks.py         task functions; __all__ is what the adapters register, MCP_CAPS any
                   per-tool result caps, BULK_TASKS the Python-only tasks they skip
                   (download_dataset)
  parse/           file parsers, one module per file kind (ADR-0020): sdmx_csv.py,
                   parse_sdmx_csv for the SDMX-CSV file download_dataset writes
  mcp.py           xippios-eurostat-mcp entry point
  http.py          FastAPI router
  params.py        packaged lists: PACKAGED_LISTS, packaged(), list_info() (lists.json),
                   datasets() (the TOC), codes() (a codelist)
  enums.py         StrEnums (IntEnums for integer ids) generated from the packaged lists;
                   never edited by hand
  reference/       packaged code lists (CSV/JSON) plus README with provenance
scripts/
  refresh_reference.py   fetches the packaged lists through api/ and regenerates enums.py
  refresh_upstream.py    writes docs/upstream/ and FETCHED.md (/refresh-upstream)
tests/
  conftest.py      enables xippios.core.testing.plugin, which keeps the run offline
  fixtures/        recorded responses, <endpoint>/<case>.json, never hand-written;
                   files/<kind>/ the parser tests' samples, provenance in its README
  test_family.py   core's family check, one line: namespace levels, py.typed, __version__,
                   the adapters serving exactly the tasks, task shapes and docstrings, the
                   README status table, the template tag, the core bound
  test_client.py   classify against the recorded refusals and the documented ones
  test_models.py   Cube against the recorded answers
  test_tasks.py    per-task replay tests
  test_refresh_reference.py  the refresh script's readers on tests/fixtures/files/
  test_parse.py    parse_sdmx_csv on the samples under tests/fixtures/files/sdmx-csv/
  test_live.py     @pytest.mark.live smoke tests, one per task
docs/upstream/     documentation snapshot and FETCHED.md
.github/workflows/ ci.yml (the required ci check, with the CHANGELOG and fixture-size steps),
                   publish.yml (the release train: tag, build, PyPI), live.yml (nightly live
                   tests), gates.yml (the merge gates as jobs, off until GATES_CALLER is 1)
.claude/family.md  the family rules, the template's, imported above
.claude/commands/  add-endpoint, record-fixture, refresh-upstream, refresh-reference-data, release-prep,
                   adopt-release
```

`src/xippios/` has **no** `__init__.py`: it is a PEP 420 namespace package shared with
`xippios-core` and every other source package. The import path is `xippios.eurostat`
(ADR-0006).

## Commands

```bash
uv run pytest -m live --tb=short   # needs XIPPIOS_LIVE_TESTS=1

uv run xippios-eurostat-mcp   # stdio; add --http for streamable HTTP
```

`.github/workflows/live.yml` runs `uv run pytest -m live --tb=short` with
`XIPPIOS_LIVE_TESTS=1` nightly at 04:59 UTC, a time derived from the slug so that sources
sharing a key never start together, and on demand from the Actions tab; pull requests
never run live tests. The API needs no key, so the workflow uses no secret.

## Eurostat dissemination API specifics

Two kinds of fixture beyond the recorded `<endpoint>/<case>.json`:

`tests/fixtures/dataQuery/*_compressed.json` holds a gzip file as its body, which no grep
reads: it is stored base64 (`body_base64`, recorded with `Scrub(allow_binary=True)`) and
decompresses to the plain recording beside it, byte for byte, which `tests/test_parse.py`
checks.

`tests/fixtures/files/<kind>/<case>.*` are the parser tests' samples, never written by
hand: `toc/` and `codelist/` of the answers `scripts/refresh_reference.py` reads, cut by
its `--samples` run from the answers it packaged; `sdmx-csv/` the response bodies of the
recorded `tests/fixtures/dataQuery/` exchanges, byte for byte.
`tests/fixtures/files/README.md` gives each one's release, URL, sha256 and fetch time
(ADR-0020 decision 6).
