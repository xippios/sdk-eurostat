# Handover — xippios-eurostat 0.1.0

Date: 2026-10-28 · Written in the release PR (`chore/release-0.1.0`) for the next
session on sdk-eurostat · Decisions cite the coordination log of session `sdk-eurostat`
by its time, CET: `coordination/log/sdk-eurostat.md` in the coordination root
(`~/github/sdk`), whose `scripts/coord.py` is the root's script, not this repository's;
its `log show sdk-eurostat` prints the last 20 entries by default, so read the
2026-10-27 lines from the file.

## State

- 0.1.0 is the first release. The release PR's merge runs `publish.yml`, which tags
  `v0.1.0` on the merge commit and waits at the `pypi` environment until Johannes
  approves the run; the first upload needs the PyPI pending publisher (owner xippios,
  repository sdk-eurostat, workflow `publish.yml`, environment `pypi`). Confirm the
  release at `https://pypi.org/pypi/xippios-eurostat/json` afterwards.
- Floor: `xippios-core~=0.3.0` from PyPI with its `mcp`, `http` and `testing` extras, no
  git pin; sdk-template v0.3.0 (`.copier-answers.yml`, `_commit: v0.3.0`, keyless and
  flat, `has_files: false`); conventions 1.21.
- Merged before the release, in order: #1 the scaffold, #2 the upstream snapshot of
  2026-10-27, #3 core 0.3.0 from PyPI and the refresh script on `render_enums`, #4
  `get_data`, #5 the three slices, #6 the packaged TOC and codelists, #7 the bulk task
  and its parser, #8 the template v0.3.0 adoption.

## What 0.1.0 covers

One base URL, `https://ec.europa.eu/eurostat/api/dissemination`, keyless; seven tasks:

- `get_data(dataset, filters=None, ...)`: one Statistics API `getData` request answered
  as a JSON-stat 2.0 `Cube` with `observations()`; `published_at` is the cube's
  `updated`, `vintage` its text.
- `get_series`, `get_latest_period`, `get_cross_section`: one `getData` request each
  through `get_data`, answered as a list of `Observation`.
- `list_datasets(search=None)` and `list_codes(codelist, search=None)`: packaged answers
  without a request, the table of contents (10,375 leaves) and twelve SDMX codelists
  (FREQ, GEO, UNIT, CROPS, STRUCPRO, MILKITEM, DAIRYPROD, STATINFO, LEG_FORM, FARMTYPE,
  SO_EUR, UAAREA, the dimensions of apro_cpnh1, apro_mk_cola and ef_m_farmleg), every
  codelist at its latest version, fetched on 2026-10-27 between 19:55:14Z and 19:55:36Z
  by `scripts/refresh_reference.py` (13 keyless requests a run; the only code that
  parses XML); each file keeps its own `fetched`, which is its `meta.retrieved_at`.
- `download_dataset(dataset, key="", *, since=None, until=None,
  last_n_observations=None, dest)`: one SDMX 2.1 `dataQuery` as gzip-compressed SDMX-CSV
  streamed to disk, named in `BULK_TASKS`, so Python only; `parse.parse_sdmx_csv(path)`
  reads the file lazily.

The six others are MCP tools and HTTP routes. `MCP_CAPS`: the slices 200 rows with a
note each, `list_datasets` the family's cap with a note naming `search`, `list_codes`
1,000 rows within the family's 64 KB, `get_data` the default cap.

## What 0.1.0 leaves out

- Comext and Prodcom datasets (`DS-` codes, served from
  `https://ec.europa.eu/eurostat/api/comext/dissemination`): 0.2.0 (D44).
- Polling an asynchronous answer: 0.2.0 if a consumer needs it (design round Q4). Today
  `classify` refuses the asynchronous answer, the HTTP 413 and a non-SDMX-CSV 200 on the
  data path with `InvalidRequestError` naming how to narrow the query. No asynchronous
  answer was ever provoked on either API (log 2026-10-27 13:50, 21:15); the tests read
  the documented bodies from `docs/upstream/` (row 83), and the first real one seen is
  recorded and replaces them (log 2026-10-27 14:15).
- Codelists beyond the twelve: `params.CODELISTS` names the twelve, which the refresh
  script fetches and `list_codes` serves; another is a change of its own, then a
  `/refresh-reference-data` run.
- TSV and SDMX-ML are never read (design round Q2); no comparison across datasets or
  sources (ADR-0003).

## Pace, cache, live budget

- Pace: 30 requests per minute, burst 1, self-imposed (ADR-0010); Eurostat documents a
  fair-use rule without a number (design round Q7, log 2026-10-27 12:15).
- Cache: answers of HTTP 200 in core's `MemoryCache` at its defaults, five minutes,
  256 entries, up to `cache_max_bytes` 8 MiB a body, so a larger cube is fetched again
  (Johannes, log 2026-10-27 19:49; ADR-0019 decision 3); `getData` reads through
  `get_answer`, so `retrieved_at` on a hit is the time the answer was stored (ADR-0015
  decision 5); a download streamed to disk never touches the cache.
- Live budget: no key, no keyed call ever. The nightly `live.yml` (04:59 UTC) sends ten
  keyless requests: one smoke test per task, three for `get_data` (one per design-round
  dataset), and the reachability check (Johannes 2026-10-27, log 23:39, over the design
  round's "about 4 to 6"). A PR's live run spends at most 10, counted in its body
  (design round Q8).

## Decisions, by date

2026-10-27

- 12:15, design round (D44), Johannes: Q1 a `Cube` mirroring JSON-stat 2.0 with a
  lossless `observations()`, no dataframe; Q2 JSON-stat for what the adapters serve,
  SDMX-CSV 1.0 for bulk; Q3 the TOC and codelists packaged by the refresh script, XML
  parsed there only; Q4 the asynchronous answer refused; Q5 small real JSON-stat
  fixtures under 256 KiB; Q6 the datasets apro_cpnh1, apro_mk_cola, ef_m_farmleg; Q7 the
  pace above; Q8 the live budget.
- 14:15, Johannes: the documented-shape tests of the asynchronous answer and the SOAP
  fault stand; probing on the Statistics path stops (row 83).
- 14:21, the session (PR #4): `get_data` refuses more than one time parameter, except
  `since_time_period` with `until_time_period`, before sending (ADR-0007); `Lang` and
  `GeoLevel` StrEnums in `models.py`, since `enums.py` is generated whole (row 85; log
  correction 14:33).
- 14:53, the family session's answer on the caps: `ResultCap` keeps `max_rows` in core
  0.3.0, so the slices keep 200 rows with a note.
- 18:51, Johannes: core 0.3.0 from PyPI with no git pin (#3; the briefing's second
  re-pin, its PR 5, falls away), `get_data` and the slices ported to the 0.3.0 helpers.
- 19:49, Johannes: a naive JSON-stat `updated` goes into `published_at` with
  `published_at_naive` set and `vintage` the text (ADR-0022 rule 2); the cache at core's
  defaults.
- 20:37, Johannes (#6): codelists read as JSON-stat; the twelve codelists at latest; the
  whole TOC, datasets and tables, with English titles and the navigation path; release
  times by ADR-0022 (the TOC's `creationDate`, naive; a codelist's version and
  `LAST_UPDATED`).
- 22:25, Johannes (#7): `download_dataset` takes Eurostat's series `key` as given;
  `compressed=true`, the `.gz` stored as sent; a 200 on the data path that is not
  SDMX-CSV refused in `classify`; `vintage` the first row's `LAST UPDATE`, naive.
- 22:26, Johannes: `list_codes` takes the codelist name in any case, as upstream does
  (row 120); `parse_sdmx_csv` yields `SdmxCsvRow` lazily.
- 23:15, Johannes (#7): an audited `.secrets.baseline` entry for the gzip fixture's
  base64 body (row 124); `SdmxCsvRow.attributes` for columns beyond the documented set;
  the gzip branch through the standard library (rows 125, 126).
- 23:39, Johannes: the over-large-query hint without "or use the bulk task"; the
  nightly at ten requests; 0.1.0 after the template v0.3.0 adoption.

2026-10-28

- D91 and D92 (log 09:56), Johannes: the template v0.3.0 adoption before the release
  PR, `has_files: false` (the SDMX-CSV bulk is an API payload under ADR-0019).
- 10:26, Johannes: no reference refresh before 0.1.0; the lists of 2026-10-27 ship; the
  next refresh is a routine PR after the release.
- 10:48, Johannes: the wrapper rename of row 135 (D95, `getData` to `get_data`) lands
  after 0.1.0; the release ships the current names, and the rename is the first PR of
  the next version.

## Next

- The first PR of the next version, row 135 (family, for this repository; Johannes
  2026-10-28, log 10:48): the wrapper `getData` becomes `get_data` and
  `tests/fixtures/getData/` moves to `tests/fixtures/get_data/` (D95, conventions 1.22
  once core's docs PR merges); class `human` by sdk-gates rule 3, since the move re-keys
  the audited `.secrets.baseline` entry (row 124); no live call.
- The routine reference refresh after the release (`/refresh-reference-data`).
- 0.2.0: Comext and Prodcom; polling the asynchronous answer if a consumer needs it.

## Queue rows this package filed or extended

Titles as `python3 scripts/coord.py queue show N` gives them; status as of 2026-10-28.

Open:

| Row | Repository | Title |
| --- | --- | --- |
| 58 | sdk-core | gap: the family's first multi-dimensional answer, a JSON-stat cube stated under ADR-0003 (eurostat design round Q1) |
| 59 | sdk-core | gap: an upstream that defers a large synchronous request (Eurostat's asynchronous answer) is refused in classify with InvalidRequestError (eurostat design round Q4) |
| 62 | sdk-template | live.yml: actions by mutable tag and a checkout that persists credentials (from the sdk-eurostat scaffold review) |
| 69 | sdk-core | gap: an upstream document regenerated per request in an unstable order (Eurostat WADL files) and the keep-if-same-lines rule (from sdk-eurostat PR 2) |
| 71 | sdk-template | PULL_REQUEST_TEMPLATE.md still names the organisation .github repository for the merge classes (renamed sdk-gates; from sdk-eurostat PR 2) |
| 75 | sdk-core | gap: live-call accounting for a session orchestrator own probes (from sdk-eurostat PR 2 review) |
| 76 | sdk-core | gap: a publisher own conditions on modified text, such as Eurostat disclaimer on modifications (conventions §3 attribution; from sdk-eurostat PR 2 review) |
| 77 | sdk-core | gap: a documentation page behind a login is recorded as not fetched, no credentials, no browser automation (conventions §3; from sdk-eurostat PR 2) |
| 80 | sdk-template | CLAUDE.md says api/ holds one module per upstream operation; Eurostat needs one per service, since WADL method ids repeat (from sdk-eurostat PR 4) |
| 81 | sdk-core | a public helper for the request description classify implementations rebuild (errors._where), and a refuse-above-N-bytes option on record() (from sdk-eurostat PR 4) |
| 83 | sdk-core | gap: a test that reads an upstream-documented body verbatim from docs/upstream/ when the shape cannot be recorded (conventions §10; from sdk-eurostat PR 4) |
| 85 | sdk-template | no stated home for a hand-written upstream enumeration: enums.py is generated and rewritten whole (from sdk-eurostat PR 4) |
| 86 | sdk-core | a value refused by a typed parameter (StrEnum, int) bypasses the family error format in both adapters (from sdk-eurostat PR 4 review) |
| 89 | sdk-core | gap: a bound on a refusal text that lists codes (eurostat get_series lists at most 20 codes per unpinned dimension; from sdk-eurostat PR 7) |
| 90 | sdk-core | gap: a task that composes another task of the same package (eurostat slices call get_data async); conventions §2 says tasks compose endpoint wrappers (from sdk-eurostat PR 7) |
| 91 | sdk-core | ResultCap: an option to keep the last rows of a cut list, for time series ordered oldest first (from sdk-eurostat PR 7) |
| 99 | sdk-core | stale sentences outside the release subset after core 0.3.0 (sdk-gates name; roadmap state) |
| 103 | sdk-core | gap: which rules bind a source that pins core 0.3.0 from PyPI before its template v0.3.0 adoption (from sdk-eurostat PR 3 review) |
| 105 | sdk-core | gap: get_answer reports a later time on the miss that stores an entry than the hit reads back (from sdk-eurostat PR 4 on core 0.3.0) |
| 106 | sdk-template | two scaffold texts stale on core 0.3.0: the guarded ResultCap import in tasks.py.jinja and CLAUDE.md "wrappers use client.get_json" (from the sdk-eurostat PR 4 re-check) |
| 107 | sdk-core | docs: definition-of-done Adoption block still names the organisation .github repository for the merge classes (renamed sdk-gates on 2026-10-27; from the sdk-eurostat PR 4 re-check) |
| 111 | sdk-core | gap: where a packaged list own release identifier lives (version, LAST_UPDATED, the TOC creationDate) when a packaged file holds the four keys and an optional note only (from sdk-eurostat PR 6) |
| 112 | sdk-core | gap: a live parser test on a partial stream of a large upstream file, and a client read that can stop early (from sdk-eurostat PR 6) |
| 120 | sdk-core | gap: the case of a list-task name argument where upstream folds case (sdk-eurostat list_codes("geo") answers the GEO codelist; from the sdk-eurostat PR 6 review) |
| 124 | sdk-template | the secret scan flags a recorder body_base64 line as a high-entropy string: every binary fixture of ADR-0019 trips detect-secrets (from sdk-eurostat PR 8) |
| 125 | sdk-core | decode_csv over an open text stream, or opening a gzip path itself (from sdk-eurostat PR 8) |
| 126 | sdk-core | gap: conventions §2 and ADR-0020 decision 1 say parse_<kind>(path) -> list[Model]; a bulk file parser yields lazily (from sdk-eurostat PR 8) |
| 128 | sdk-core | two bulk-task gaps: core download refuses a bad dest with ValueError outside the taxonomy, and meta.endpoint for a task that downloads through an API operation (from the sdk-eurostat PR 8 review) |

Row 99 is the family's; this package extended it with item (g), from the sdk-eurostat
PR 9 review. The rows' "PR N" are the briefing's package numbers: PRs 1 to 4 and 6 are
#1 to #4 and #6; PR 7 (the slices) is #5, PR 8 (the bulk task) #7 and PR 9 (the
adoption) #8; PR 5 never ran.

Done in template v0.3.0: 61 (keyless render wording in template v0.2.2), 63 (the
CHANGELOG rule in CLAUDE.md and ci.yml exempts adoption PRs), 64 (adapters skip
BULK_TASKS by hand until v0.3.0), 70 (a shared HTML-to-Markdown helper for
scripts/refresh_upstream.py), 98 (refresh_reference.py and refresh-reference-data.md
call the renderers core removed; filed by usda-esmis, met by this package in #3).
