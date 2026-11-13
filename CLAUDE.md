# sdk-eurostat — instructions for Claude Code

`xippios-eurostat` wraps Eurostat dissemination API as a typed Python client, an MCP server
and FastAPI routes, built on `xippios-core`. This file holds what an agent needs to work on
the package: what it wraps, its layout, its commands and its code rules. The documents it
follows, sdk-core's conventions among them, are listed under
[`## Documents` in the README](README.md#documents); read them before you change a file.

## What this package wraps

| | |
| --- | --- |
| Upstream | Eurostat dissemination API, https://ec.europa.eu/eurostat/web/main/data/database |
| API base URL | `https://ec.europa.eu/eurostat/api/dissemination`, and `https://ec.europa.eu/eurostat/api/comext/dissemination` for the Comext and Prodcom datasets: a dataset or flow code that starts with `DS-` is requested on the Comext base, every other on the main one (`docs/upstream/user-guide/api-detailed-guidelines/prefixed-datasets.md`); one client serves both, `_client.url_for` applies the rule |
| Documentation | https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-introduction, snapshotted in `docs/upstream/` |
| Credentials | none; the API is open |
| Rate limit | 30 requests per minute, burst 1; a self-imposed pace, upstream documents no rate in numbers (ADR-0010); the user guide states a fair-use rule without a number: past thresholds it does not give on concurrent requests, requests and extraction cost per day, 7 and 30 days, requests are answered asynchronously (`docs/upstream/user-guide/api-detailed-guidelines/asynchronous-api.md`, "Fair use of the service"); enforced client-side in `_client.py` |
| Write tools | no, this package is read-only |

The snapshot listed in `docs/upstream/FETCHED.md` is the reference for names, parameters and
semantics; a wrapper is never written from memory of the API.

## Layout

```
src/xippios/eurostat/
  __init__.py      public surface: __version__ and re-exported task functions
  py.typed         PEP 561 marker; consumers' mypy --strict needs it
  _version.py      __version__ from distribution metadata
  _client.py       the one configured AsyncClient (the two base URLs, url_for, rate
                   limit, cache) and classify, upstream's documented error shapes; no key
  errors.py        the Statistics API's fault model and its parsing, for classify
  models.py        pydantic models mirroring upstream payloads (UpstreamModel); by the
                   family's precedent also an enumeration written by hand, for a value set
                   upstream documents and no packaged list renders
  api/             endpoint wrappers, one module per upstream service, named after it,
                   since the API's operation ids repeat across its services: statistics,
                   sdmx and catalogue, one function per operation (conventions §2)
  tasks.py         task functions; __all__ is what the adapters register, MCP_CAPS any
                   per-tool result caps, BULK_TASKS the Python-only tasks they skip
                   (download_dataset, download_trade)
  parse/           file parsers, one module per file kind (ADR-0020): sdmx_csv.py,
                   parse_sdmx_csv for the SDMX-CSV files download_dataset and
                   download_trade write
  mcp.py           xippios-eurostat-mcp entry point
  http.py          FastAPI router
  params.py        packaged lists: CODELISTS (each codelist's base and dimension),
                   PACKAGED_LISTS, packaged(), list_info() (lists.json), datasets() (the
                   TOC), codes() (a codelist)
  enums.py         StrEnums (IntEnums for integer ids) generated from the packaged lists;
                   never edited by hand
  reference/       packaged lists as JSON plus README with provenance: the TOC, twelve
                   codelists of the main base and six of the Comext base
                   (CXT_PRODCOM2_SOLD, CXT_PRODCOM2_TOTAL, CXT_INDICATORS, CXT_NC,
                   CXT_FREE_ISO, CXT_EU_FLUX), and the index lists.json
scripts/
  refresh_reference.py   fetches the packaged lists through api/, every one or those
                         --only names, and regenerates enums.py
  refresh_upstream.py    writes docs/upstream/ and FETCHED.md (/refresh-upstream)
  adr_index.py           writes docs/adr.md and docs/adr.json from the records in docs/adr/;
                         --check fails while either is stale
tests/
  conftest.py      enables xippios.core.testing.plugin, which keeps the run offline
  fixtures/        recorded responses, <wrapper>/<case>.json, never hand-written;
                   files/<kind>/ the parser tests' samples, provenance in its README
  test_family.py   core's family check, one line: namespace levels, py.typed, __version__,
                   the adapters serving exactly the tasks, task shapes and docstrings, the
                   README status table, the template tag, the core bound
  test_client.py   classify against the recorded refusals and the documented ones
  test_models.py   Cube against the recorded answers
  test_tasks.py    per-task replay tests
  test_refresh_reference.py  the refresh script's readers on tests/fixtures/files/, and
                   its --only merge, offline
  test_parse.py    parse_sdmx_csv on the samples under tests/fixtures/files/sdmx-csv/
  test_live.py     @pytest.mark.live smoke tests, one per task and more for get_data
                   (one per dataset, the Comext base's among them); a run sends eighteen
                   requests, as its docstring counts
docs/
  upstream/        documentation snapshot and FETCHED.md
  adr/             this package's design decisions, one NNNN-<slug>.md record each, laid
                   out in its README.md
  adr.md           the index of the decisions, written by scripts/adr_index.py, never by hand
  adr.json         the same index, for machines
  reports/         dated reports, the evidence a decision cites, laid out in its README.md
changelog/         the next release's changelog entries, one fragment per change, laid out
                   in its README.md
CHANGELOG.md       the releases, each section assembled from the fragments
.github/workflows/ ci.yml (the required ci check, with the changelog and fixture-size steps),
                   publish.yml (the release train: tag, build, PyPI), live.yml (nightly live
                   tests), organization.yml (the organization's checks from xippios/.github:
                   conventions, a review of a pull request against the documents the README
                   lists, and adr-index, which runs scripts/adr_index.py --check)
.claude/commands/  add-endpoint, record-fixture, refresh-upstream, refresh-reference-data, release-prep
```

The import path is `xippios.eurostat` (ADR-0006); `src/xippios/` is a namespace
package.
Where the API's operation ids repeat across its services, `api/` keeps one module per service
instead, named after the service, and this Layout says so (conventions §2).

## Commands

```bash
uv sync --all-extras
uv run pytest                      # offline, replays the fixtures
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pre-commit run --all-files
python3 scripts/adr_index.py --check   # the index matches the records in docs/adr/
uv run pytest -m live --tb=short --assert=plain   # needs XIPPIOS_LIVE_TESTS=1

uv run xippios-eurostat-mcp   # stdio; add --http for streamable HTTP
```

`uv run pytest` is offline: core's plugin refuses the network and skips the rate limiter's
waits in every test not marked `live` (conventions §10, ADR-0013). A test that asserts a
limiter wait or a quota pause is marked `rate_limited`, one that must reach the network
`network`.

`.github/workflows/live.yml` runs the live tests nightly at 04:59 UTC, a time derived from
the slug, and on demand; a pull request never runs them.
Its `uv run pytest -m live --tb=short --assert=plain` step reads no secret: the API needs no
key. A live run sends eighteen keyless requests, one per test (`tests/test_live.py`); the
one for `list_cn8` and `list_hs` fetches the CXT_NC codelist, about 6 MB, once for both.
Every live run takes `--tb=short --assert=plain`, since the log of `live.yml` is public:
the first keeps a failing test's frame arguments out of it, a raw upstream payload among
them, and the second the values a failed `assert` compares. A live test asserts on shapes
and counts, never on a raw payload.

## Code rules

- Three layers (ADR-0001, conventions §2): endpoint wrappers in `api/`, task functions in
  `tasks.py`, adapters in `mcp.py` and `http.py`. The adapters register `tasks.__all__` and
  call only tasks, the tasks call only wrappers and reference data, and a wrapper returns
  models.
- Upstream's documented error shapes go into `classify` in `_client.py`, once, and an error
  class of the package's own into `errors.py`; a wrapper never inspects a status code
  (conventions §5, §6).
- A change brings its tests, written before the code, and passes the offline checks above;
  its changelog entry is a fragment under `changelog/`, one file holding its bullet, as
  `changelog/README.md` lays it out (conventions §12). Commit subjects follow Conventional
  Commits (conventions §13).
- `ruff` leaves `docs/` and `.claude/` alone (`pyproject.toml`), so the upstream snapshot
  keeps its bytes: never reformat it.
- A convention that seems wrong is followed anyway and said in the pull request; changing
  it is a change of sdk-core's `docs/conventions.md` with an ADR.

## Never

- Never hand-write a fixture, and never commit one without grepping it for key patterns
  (conventions §10).
- Never read or print `.envrc`, `.env`, or any variable ending in `_API_KEY`,
  `_REFRESH_TOKEN` or `_SECRET`.
- Never write a key, a token or another credential into a file or a commit.
- Never put logic in `mcp.py` or `http.py`, and never add a route or a tool by hand: the
  adapters register `tasks.__all__` (ADR-0001).
- Never rename or re-map an upstream concept to another source's (ADR-0003).
- Never return a documented personal identifier in a task's projection, echo one in
  `meta.request`, or commit one in a fixture (ADR-0017).
- Never edit `docs/upstream/` by hand: `/refresh-upstream` fetches it, and the pull request
  shows its diff (conventions §3).
- Never add `src/xippios/__init__.py`, nor an `__init__.py` at a level between it and the
  package (ADR-0006).
- Never push a tag by hand: a release's tag comes from `publish.yml` alone (conventions §12).

## Template updates

This repository is generated from sdk-template, at the tag `.copier-answers.yml` records. A
template release reaches it in a pull request of its own, with
`uvx --from 'copier>=9.19' copier update --defaults --vcs-ref=<tag>` (conventions §15): the
update renders the template's files again and never overwrites the files this package
fills, `__init__.py`, `_client.py`, `errors.py`, `models.py`, `api/`, `parse/`, `tasks.py`,
`params.py`, `enums.py`, `reference/`, `scripts/refresh_reference.py`,
`scripts/refresh_upstream.py`, `tests/test_tasks.py`, `tests/test_live.py`,
`tests/fixtures/`, `docs/upstream/`, `docs/adr.md`, `docs/adr.json`, `README.md`,
`CHANGELOG.md` and `CLAUDE.md`. sdk-template's
[CHANGELOG](https://github.com/xippios/sdk-template/blob/main/CHANGELOG.md) says, per
release, what to port into those by hand in the same pull request.

## When something is unclear

Prefer the smallest change that satisfies the documents the README lists, state the
assumption in the pull request's description, and stop rather than guess at upstream
semantics or the shape of the public API.

## Eurostat dissemination API specifics

The packaged codelists come from both bases: `params.CODELISTS` names each one's base and
the dimension it feeds, the packaged file's `param`. The twelve of the main base keep the
path they were fetched from as `endpoint` (`sdmx/2.1/codelist/ESTAT/GEO`); the six of the
Comext base, the Prodcom datasets' `product` and `indicators` lists and the trade
datasets' `product`, `reporter` and `flow` lists, the full URL
(`https://ec.europa.eu/eurostat/api/comext/dissemination/sdmx/2.1/codelist/ESTAT/CXT_INDICATORS`),
since the path alone names the main base's operation (Johannes, 2026-10-28; gap, row 172).
CXT_FREE_ISO feeds `partner` too; its `param` is `reporter`, the first of the two in the
data structures' order.
`scripts/refresh_reference.py --only <name> [<name> ...]` refreshes the named lists and
keeps every other list's file, `lists.json` record and provenance row; the index's
`fetched` is the latest among all lists. The production tasks check a product against the
dataset's own product list before sending: DS-059358's is CXT_PRODCOM2_SOLD, DS-059359's
CXT_PRODCOM2_TOTAL, 822 of the first list's 4,788 codes (chiefly chemicals, fertilisers
and metals) on 2026-10-28; each indicator is checked against CXT_INDICATORS, which
Comext's trade datasets share, and each reporter against CXT_FREE_ISO. What Eurostat
answers a code a list holds and the dataset lacks is its own, as recorded: an empty cube
for an indicator DS-059359 lacks (`PRODVAL`,
`DS-059359_AT_20158000_indicator_not_in_dataset`), the asynchronous answer for a CN8 code
on DS-059341 (`DS-059341_AT_DE_15071090_cn8_on_hs_flow`); a code no list holds (`XX`,
which Eurostat answered with an empty cube, `DS-059358_unknown_code`) the package refuses
before sending.

The trade tasks read DS-045409 (EU trade since 1988 by HS2-4-6 and CN8, data structure
6.6) and DS-059341 (international trade of EU and non-EU countries since 2002 by HS2-4-6,
3.7), whose data structures name the same codelists, read on 2026-10-28: CXT_FREQ (`A`,
`M`; not packaged: `models.Freq`, written by hand as `Lang` and `GeoLevel` are, and
unexported from `__init__`), CXT_FREE_ISO for `reporter` and `partner`, CXT_NC for
`product`, CXT_EU_FLUX for `flow` and CXT_INDICATORS, in the positional order
freq.reporter.partner.product.flow.indicators (`tasks.TRADE_DIMENSIONS`), the order of
their filters and of `download_trade`'s key. DS-045409 serves VALUE_IN_EUROS,
QUANTITY_IN_100KG and SUPPLEMENTARY_QUANTITY, DS-059341 VALUE_EUR, VALUE_NAC and
QUANTITY_KG (the recorded cubes). A CN8 code passes the product check for DS-059341, whose
product list is CXT_NC, and DS-059341 answered one (`15071090`) with HTTP 413 and an
`error` array labelled `ASYNCHRONOUS_RESPONSE`
(`tests/fixtures/get_data/DS-059341_AT_DE_15071090_cn8_on_hs_flow.json`): the Statistics
API's asynchronous answer, recorded on 2026-10-28 in another shape than the user guide's
`warning`, which was never seen. `classify` refuses it by its label
(`errors.asynchronous_fault`), before its HTTP 413 refusal of `EXTRACTION_TOO_BIG`, which
shares its id and status: send the request again later, or narrow it; the package does not
poll. `list_cn8` and `list_hs` split CXT_NC by code length: eight characters, and two,
four or six; its lettered codes (`1507XXXX`, `15SSS421`) are Eurostat's positions for
trade no regular code holds and are served as listed, and its one code of five characters,
`TOTAL`, is in neither. A Comext trade dataset is served filtered only
(`prefixed-datasets.md`), so `download_trade` refuses a call with neither `product` nor
`reporters` before any request; Eurostat answers up to 500,000 estimated cells at once,
queues up to 5,000,000 (the asynchronous answer `classify` refuses) and refuses more with
HTTP 413 (`asynchronous-api.md`).

Two kinds of fixture beyond the recorded `<wrapper>/<case>.json`:

`tests/fixtures/data_query/*_compressed.json` holds a gzip file as its body, which no grep
reads: it is stored base64 (`body_base64`, recorded with `Scrub(allow_binary=True)`) and
decompresses to the plain recording beside it, byte for byte, which `tests/test_parse.py`
checks.

`tests/fixtures/files/<kind>/<case>.*` are the parser tests' samples, never written by
hand: `toc/` and `codelist/` of the answers `scripts/refresh_reference.py` reads, cut by
its `--samples` run from the answers it packaged; `sdmx-csv/` the response bodies of the
recorded `tests/fixtures/data_query/` exchanges, byte for byte.
`tests/fixtures/files/README.md` gives each one's release, URL, sha256 and fetch time
(ADR-0020 decision 6).
