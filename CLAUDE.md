# sdk-eurostat — instructions for Claude Code

`xippios-eurostat` wraps Eurostat dissemination API as a typed Python client, an MCP server
and FastAPI routes, built on `xippios-core`. This file holds what an agent needs to work on
the package: what it wraps, its layout, its commands and what only it knows. The documents it
follows, sdk-core's conventions among them, are listed under
[`## Documents` in the README](README.md#documents); read them before you change a file. The
rules that no change breaks stand in `.claude/rules/never.md`, which Claude Code loads with
this file.

## What this package wraps

| | |
| --- | --- |
| Upstream | Eurostat dissemination API, https://ec.europa.eu/eurostat/web/main/data/database |
| API base URL | `https://ec.europa.eu/eurostat/api/dissemination`, and `https://ec.europa.eu/eurostat/api/comext/dissemination` for the Comext and Prodcom datasets: a dataset or flow code that starts with `DS-` is requested on the Comext base, every other on the main one (`docs/upstream/user-guide/api-detailed-guidelines/prefixed-datasets.md`); one client serves both, `_client.url_for` applies the rule |
| Documentation | https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-introduction, snapshotted in `docs/upstream/` |
| Credentials | none; the API is open |
| Rate limit | 30 requests per minute, burst 1; a self-imposed pace, upstream documents no rate in numbers (sdk-core ADR-0033); the user guide states a fair-use rule without a number: past thresholds it does not give on concurrent requests, requests and extraction cost per day, 7 and 30 days, requests are answered asynchronously (`docs/upstream/user-guide/api-detailed-guidelines/asynchronous-api.md`, "Fair use of the service"); enforced client-side in `_client.py` |
| Write tools | no, this package is read-only |
| Files | parsed in `parse/`, one module per file kind: the SDMX-CSV 1.0 file that `download_dataset` writes gzip-compressed (`compressed=true`), the file kind `sdmx-csv`, read row by row by `parse/sdmx_csv.py` with the standard library's `gzip` and `csv` and core's `decode_csv`, the plain file too, as `api.sdmx.data_query` writes it without `compressed`; the parser tests read the samples under `tests/fixtures/files/`, these and the answers `scripts/refresh_reference.py` reads (`toc/`, `codelist/`), their provenance in its `README.md` (sdk-core ADR-0020) |

The snapshot listed in `docs/upstream/FETCHED.md` is the reference for names, parameters and
semantics; a wrapper is never written from memory of the API.

## Layout

What this package adds to the family's tree, and its import path, stand in `docs/layout.md`,
imported here:

@docs/layout.md

## Commands

```bash
uv sync --all-extras
uv run pytest                      # offline, replays the fixtures
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pre-commit run --all-files
python3 -I scripts/adr_index.py --check   # the index matches the records in docs/adr/
uv run pytest -m live --tb=short --assert=plain   # needs XIPPIOS_LIVE_TESTS=1

uv run xippios-eurostat-mcp   # stdio; add --http for streamable HTTP
```

`.github/workflows/live.yml` runs the live tests nightly at 04:59 UTC, a time derived from
the slug, and on demand; a pull request never runs them.
Its `uv run pytest -m live --tb=short --assert=plain` step reads no secret: the API needs no
key.
Every live run takes `--tb=short --assert=plain`, since the log of `live.yml` is public:
the first keeps a failing test's frame arguments out of it, a raw upstream payload among
them, and the second the values a failed `assert` compares. A live test asserts on shapes
and counts, never on a raw payload.

## Template updates

This repository is generated from sdk-template, at the tag `.copier-answers.yml` records. A
template release reaches it in a pull request of its own, with
`uvx --from 'copier>=9.19' copier update --defaults --vcs-ref=<tag>` (conventions §15). The
update never overwrites a file this package fills, those that `_skip_if_exists` lists in
sdk-template's [`copier.yml`](https://github.com/xippios/sdk-template/blob/main/copier.yml),
and sdk-template's
[CHANGELOG](https://github.com/xippios/sdk-template/blob/main/CHANGELOG.md) says, per
release, what to port into those by hand in the same pull request.

The update writes every other file it renders again, since they are the template's,
`.claude/rules/never.md` among them. This package keeps no text of its own in them, the
docstring of `mcp.py` included: its own words go into a file it fills. A line it has to
add to one, such as a dependency in `pyproject.toml`, the update carries into the new
render, silently where the release leaves the lines around it alone and as a conflict
where it changes them.

## Eurostat dissemination API specifics

The packaged codelists come from both bases: `params.CODELISTS` names each one's base and
the dimension it feeds, the packaged file's `param`. The twelve of the main base keep the
path they were fetched from as `endpoint` (`sdmx/2.1/codelist/ESTAT/GEO`); the six of the
Comext base, the Prodcom datasets' `product` and `indicators` lists and the trade
datasets' `product`, `reporter` and `flow` lists, the full URL
(`https://ec.europa.eu/eurostat/api/comext/dissemination/sdmx/2.1/codelist/ESTAT/CXT_INDICATORS`),
since the path alone names the main base's operation (conventions §4, as
https://github.com/xippios/sdk-eurostat/pull/13 decided).
CXT_FREE_ISO feeds `partner` too; its `param` is `reporter`, the first of the two in the
data structures' order.
`scripts/refresh_reference.py --only <file> [<file> ...]` refreshes the lists of those
files (`--only statinfo`) and keeps every other list's file, `lists.json` record and
provenance row; the index's `fetched` is the latest among all lists. No task checks a code
against a packaged list before sending: a code no list holds (`XX`) is sent, and Eurostat
answered it with an empty cube (`DS-059358_unknown_code`), as it answers a code that
matches nothing on the main base (`unknown_code`).

Comext's trade datasets DS-045409 (EU trade since 1988 by HS2-4-6 and CN8) and DS-059341
(international trade of EU and non-EU countries since 2002 by HS2-4-6) name the same
codelists, read on 2026-10-28: CXT_FREQ (`A`, `M`; not packaged), CXT_FREE_ISO for
`reporter` and `partner`, CXT_NC for `product`, CXT_EU_FLUX for `flow` and CXT_INDICATORS,
in the positional order freq.reporter.partner.product.flow.indicators, the order of
`download_dataset`'s key for them. DS-045409 serves VALUE_IN_EUROS, QUANTITY_IN_100KG and
SUPPLEMENTARY_QUANTITY, DS-059341 VALUE_EUR, VALUE_NAC and QUANTITY_KG (the recorded cubes).
DS-059341 answered a CN8 code (`15071090`) with HTTP 413 and an `error` array labelled
`ASYNCHRONOUS_RESPONSE`
(`tests/fixtures/get_data/DS-059341_AT_DE_15071090_cn8_on_hs_flow.json`): the Statistics
API's asynchronous answer, recorded on 2026-10-28 in another shape than the user guide's
`warning`, which was never seen. `classify` refuses it by its label
(`errors.asynchronous_fault`), before its HTTP 413 refusal of `EXTRACTION_TOO_BIG`, which
shares its id and status and is core's `QueryTooLarge`: send the request again later, or
narrow it; the package does not poll. A Comext trade dataset is served filtered only
(`prefixed-datasets.md`); Eurostat answers up to 500,000 estimated cells at once, queues up
to 5,000,000 (the asynchronous answer `classify` refuses) and refuses more with HTTP 413
(`asynchronous-api.md`), stating its estimate and its limit, which `QueryTooLarge` carries.
`list_codes` serves CXT_NC whole: its lettered codes (`1507XXXX`, `15SSS421`) are
Eurostat's positions for trade no regular code holds, and its one code of five characters is
`TOTAL`.

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
(sdk-core ADR-0020 decision 6).
