# Handover — xippios-eurostat 0.2.0

Date: 2026-10-28 · Written in the release PR (`chore/release-0.2.0`) for the next
session on sdk-eurostat · Decisions cite the coordination log of session `sdk-eurostat`
by its time, CET: `coordination/log/sdk-eurostat.md` in the coordination root
(`~/github/sdk`), whose `scripts/coord.py` is the root's script, not this repository's;
its `log show sdk-eurostat` prints the last 20 entries by default, so read the
2026-10-28 lines from 11:30 on from the file. "PR N" below is the 0.2.0 briefing's
package number; the GitHub number follows where there is one.

## State

- 0.2.0 is the second release; 0.1.0 (#9) has been on PyPI since 2026-10-28, tagged
  `v0.1.0` on f484709. The release PR's merge runs `publish.yml`, which tags `v0.2.0` on
  the merge commit and waits at the `pypi` environment until Johannes approves the run;
  the trusted publisher (owner xippios, repository sdk-eurostat, workflow `publish.yml`,
  environment `pypi`) took 0.1.0's upload, so no pending publisher is needed. 0.1.0's
  first publish attempt failed before any upload on a transient HTTP 502 from
  Sigstore's Rekor; re-running the failed job, which Johannes approves again, uploaded
  it. Confirm the release at `https://pypi.org/pypi/xippios-eurostat/json` afterwards.
- Floor: core 0.3.0 and template v0.3.0, unchanged since 0.1.0; conventions 1.22
  (0.1.0: 1.21), whose naming rule #10 applied. That is `xippios-core~=0.3.0` from PyPI
  with its `mcp`, `http` and `testing` extras, no git pin, and sdk-template v0.3.0
  (`.copier-answers.yml`, `_commit: v0.3.0`, keyless and flat, `has_files: false`).
- Merged before the release, in order: #10 the wrapper rename (`chore/wrapper-names`,
  PR 1), #11 the upstream snapshot of 2026-10-28 with the Comext base
  (`docs/upstream-2026-10-28`, PR 2), #12 the Comext client (`feature/comext-client`,
  PR 3), then PR 4, Prodcom production (`feature/prodcom`, opened as #<n>), PR 5,
  Comext trade (`feature/comext-trade`, opened as #<n>), and PR 6, the routine
  reference refresh (`chore/reference-refresh`, opened as #<n>); this release PR
  (`chore/release-0.2.0`, PR 7) last. #10 and #11 were cut from 0.1.0's `main`, each
  later branch from the one before it; a branch behind `main` merged it forward, never
  rebased.

## What 0.2.0 covers

Two base URLs, keyless: the main base, `https://ec.europa.eu/eurostat/api/dissemination`,
and the Comext base, `https://ec.europa.eu/eurostat/api/comext/dissemination`, where
Eurostat serves its Comext trade and Prodcom production datasets, whose codes start with
`DS-`. One client serves both (`_client.url_for`, `_client.COMEXT_BASE_URL`): a `DS-`
code goes to the Comext base, every other to the main base, with one pace, one cache and
one `classify`. Fifteen tasks:

- `get_data(dataset, filters=None, *, lang=Lang.EN, since_time_period=None,
  until_time_period=None, last_time_period=None, geo_level=None)`: one Statistics API
  `getData` request answered as a JSON-stat 2.0 `Cube` with `observations()`;
  `published_at` is the cube's `updated`, `vintage` its text. A value is a number, or
  the text Eurostat prints (`"KG"`, `":E"` among Prodcom's measures), and so is
  `SdmxCsvRow.obs_value`.
- `get_series`, `get_latest_period`, `get_cross_section`: one `getData` request each
  through `get_data`, answered as a list of `Observation`.
- `list_datasets(search=None)`: the packaged table of contents of the main base, a list
  of `Dataset`; the Comext base has none to package (below).
- `list_codes(codelist, search=None)`: one of the eighteen packaged codelists, a list of
  `Code`.
- `list_products(search=None)`: DS-059358's products, CXT_PRODCOM2_SOLD, a list of
  `Code`.
- `get_sold_production(product, reporters=None, since=None, until=None,
  indicators=None)` on DS-059358 and `get_total_production(...)`, the same parameters,
  on DS-059359: one `getData` request each through `get_data`, a list of
  `Observation`. The product is checked against the dataset's own product list
  (CXT_PRODCOM2_SOLD, CXT_PRODCOM2_TOTAL), each reporter against CXT_FREE_ISO and each
  indicator against CXT_INDICATORS before sending (`UnknownCode` naming the closest); a
  code a list holds and the dataset lacks is Eurostat's to answer (an empty cube,
  recorded for `PRODVAL` on DS-059359; no reporter case is recorded).
- `list_cn8(search=None)` and `list_hs(search=None)`: CXT_NC's eight-character codes,
  and its two-, four- and six-character ones, each a list of `Code`; `TOTAL` is in
  neither.
- `get_trade(product, reporters=None, partners=None, flow=None, since=None, until=None,
  freq=Freq.M, indicators=None)` on DS-045409 and `get_trade_hs(...)`, the same
  parameters, on DS-059341: one `getData` request each through `get_data`, a list of
  `Observation`, filters in the data structures' order
  (`tasks.TRADE_DIMENSIONS`), every code checked against CXT_NC, CXT_FREE_ISO,
  CXT_EU_FLUX and CXT_INDICATORS before sending, `freq` against `models.Freq` (`A`,
  `M`). DS-059341 answers a CN8 code asynchronously (recorded), which is refused.
- `download_dataset(dataset, key="", *, since=None, until=None,
  last_n_observations=None, dest)` and `download_trade(product=None, reporters=None,
  partners=None, flow=None, since=None, until=None, freq=Freq.M, indicators=None, *,
  dest)`: one SDMX 2.1 `dataQuery` each, gzip-compressed SDMX-CSV streamed to disk, a
  `Downloaded`; `download_trade` builds DS-045409's key from `get_trade`'s arguments and
  refuses a call with neither `product` nor `reporters` before any request. Both are
  named in `BULK_TASKS`, so Python only; `parse.parse_sdmx_csv(path)` reads the file
  lazily.

The thirteen others are MCP tools and HTTP routes.

The packaged lists, fetched by one `scripts/refresh_reference.py` run on 2026-10-28
between 16:08:00Z and 16:08:37Z (`lists.json`'s `fetched` is 2026-10-28T16:08:37Z),
each file keeping its own `fetched`, which is its `meta.retrieved_at`:

| List | Base | Version | Last update | Entries | Fetched (UTC) |
| --- | --- | --- | --- | --- | --- |
| TOC (`toc.json`) | main | `creationDate` 20261028T1000 | | 10,379 leaves | 16:08:00 |
| FREQ | main | 3.9 | 2025-11-07T23:00:00+0100 | 12 | 16:08:05 |
| GEO | main | 28.0 | 2026-03-25T23:00:00+0100 | 4,292 | 16:08:08 |
| UNIT | main | 84.0 | 2026-10-21T23:00:00+0200 | 773 | 16:08:09 |
| CROPS | main | 17.0 | 2026-09-21T23:00:00+0200 | 725 | 16:08:11 |
| STRUCPRO | main | 9.0 | 2026-06-29T11:00:00+0200 | 24 | 16:08:13 |
| MILKITEM | main | 3.0 | 2025-09-09T23:00:00+0200 | 17 | 16:08:15 |
| DAIRYPROD | main | 4.1 | 2026-04-27T23:00:00+0200 | 166 | 16:08:17 |
| STATINFO | main | 16.0 | 2026-05-11T23:00:00+0200 | 109 | 16:08:19 |
| LEG_FORM | main | 2.0 | 2026-10-26T23:00:00+0100 | 28 | 16:08:21 |
| FARMTYPE | main | 3.3 | 2025-07-07T23:00:00+0200 | 113 | 16:08:23 |
| SO_EUR | main | 8.0 | 2025-04-28T23:00:00+0200 | 68 | 16:08:25 |
| UAAREA | main | 5.0 | 2025-04-28T23:00:00+0200 | 21 | 16:08:27 |
| CXT_PRODCOM2_SOLD | Comext | 6.0 | 2025-01-13T23:00:00+0100 | 4,788 | 16:08:26 |
| CXT_PRODCOM2_TOTAL | Comext | 4.0 | 2025-01-13T23:00:00+0100 | 822 | 16:08:28 |
| CXT_INDICATORS | Comext | 49.0 | 2026-10-19T11:00:00+0200 | 44 | 16:08:30 |
| CXT_NC | Comext | 11.0 | 2025-01-19T11:00:00+0100 | 40,409 | 16:08:34 |
| CXT_FREE_ISO | Comext | 10.0 | 2026-01-13T23:00:00+0100 | 313 | 16:08:35 |
| CXT_EU_FLUX | Comext | 1.0 | none | 3 | 16:08:37 |

The twelve of the main base keep the path they were fetched from as `endpoint`, the six
of the Comext base the codelist's full URL there. `cxt_nc.json` is about 7 MB, the
largest packaged file. `scripts/refresh_reference.py --only <name> ...` fetches the
named lists alone; without it the run is the whole refresh, nineteen keyless requests.

`MCP_CAPS`: the slices 200 rows with a note each; the production tasks 200 rows with a
note naming `reporters`, `indicators` and `since`; the trade tasks 200 rows with a note
naming `reporters`, `partners`, `indicators`, one `flow`, `since` and `freq`;
`list_datasets` the family's cap with a note naming `search`; `list_codes`,
`list_products`, `list_cn8` and `list_hs` 1,000 rows within the family's 64 KB with a
note naming `search`; `get_data` the default cap.

## What 0.2.0 leaves out

- Polling an asynchronous answer (G5 Q3; 0.1.0's design round Q4, in the log's
  2026-10-27 lines and `git show v0.1.0:docs/handover.md`). `classify` refuses it, in
  both recorded shapes and in the one the user guide documents, with
  `InvalidRequestError` naming how to narrow the query; the Statistics API's refusal
  also says to send the request again later, that API's own route.
- CPA 2.2 lists: they wait for a consumer (G5 Q4).
- The Comext base's catalogue: its `catalogue/toc/xml` answers HTTP 404 (probe 5, log
  13:37), though its WADL lists it, so `list_datasets` lists the main base's table of
  contents only and no `DS-` dataset.
- `list_products` over the total list: it lists CXT_PRODCOM2_SOLD, DS-059358's products;
  DS-059359's CXT_PRODCOM2_TOTAL, 822 of them, is read through
  `list_codes("cxt_prodcom2_total")`.
- Narrowing `get_trade_hs` by HS length: DS-059341's structure names CXT_NC, so a CN8
  code passes its check and Eurostat answers it asynchronously (the session, log 16:49).
- SDMX 3.0 and TSV: the Comext base's SDMX 3.0 WADL is in the snapshot and nothing reads
  it; TSV and SDMX-ML are never read (0.1.0's design round Q2, in the log's 2026-10-27
  lines and `git show v0.1.0:docs/handover.md`). No comparison across datasets or
  sources (ADR-0003).

## Pace, cache, live budget

- Pace: 30 requests per minute, burst 1, self-imposed (ADR-0010), one limiter for both
  bases, since core builds one bucket per client (G5 Q1); Eurostat documents a fair-use
  rule without a number.
- Cache: answers of HTTP 200 in core's `MemoryCache` at its defaults, five minutes, 256
  entries, up to `cache_max_bytes` 8 MiB a body, one cache for both bases, keyed on the
  full URL; a download streamed to disk never touches it.
- Live budget: no key, no keyed call ever. The nightly `live.yml` (04:59 UTC) sends
  eighteen keyless requests: one smoke test per task, `list_cn8` and `list_hs` sharing
  one fetch of CXT_NC (about 6 MB); four for `get_data`, one per dataset of 0.1.0's
  design round and one on DS-059358, which is the Comext base's reachability check; and
  the main base's reachability check (G5 Q7 said about 17). Each tasks PR's live run
  spends at most 10, counted in its body (G5 Q7, the briefing's budget line); the
  release PR runs the whole live suite once, eighteen requests, by the release-prep
  command's step 8.
- This version's PRs, all keyless: #10 none; #11 74 requests (three probes and two
  snapshot runs); #12 19 (the ten probes of 13:37, eight recordings, one live run); PR 4
  9; PR 5 13; PR 6 19 (one whole refresh with `--samples`); this release PR 18 (the live
  suite, once).

## Decisions, by date

2026-10-28

- 11:30, Johannes: after 0.1.0, the wrapper rename first, the routine reference
  refresh, and 0.2.0 as Comext trade plus Prodcom production with an agricultural
  focus.
- 13:37, the session's probes, ten keyless requests on the Comext base, counted in #12:
  DS-059358 answers JSON-stat 2.0 with a zoned `updated` and an `indicators` dimension
  of 23 codes that mixes measures with units and flags; DS-045409's structure (freq,
  reporter, partner, product, flow, indicators); SDMX-CSV on the Comext base in the
  main base's form; CXT_FREE_ISO (313 codes) and CXT_NC (40,409); the Comext base's
  `catalogue/toc/xml` HTTP 404; DS-045409's whole monthly flow answered asynchronously,
  the first real asynchronous answer seen; five reporters against one partner in every
  product for 2023 HTTP 413, the SOAP fault `EXTRACTION_TOO_BIG`.
- 13:55, G5, the 0.2.0 design round, Johannes, seven answers: Q1 one client, two base
  URLs, one pace, cache and `classify`, so 0.1.0's seven tasks serve `DS-` datasets at
  once (five, as built: `get_data`, the three slices and `download_dataset`); Q2 the
  production and trade tasks read JSON-stat cubes through `getData` on the
  Comext base, one request each, composing `get_data` as the slices do; Q3 no polling,
  the real asynchronous answer recorded in place of the documented-body test; Q4
  CXT_PRODCOM2_SOLD and CXT_INDICATORS packaged at latest, DS-059359's list only if it
  differs (it does), CPA 2.2 waits for a consumer; Q5 CXT_NC packaged whole, `list_cn8`
  and `list_hs` by code length and search, a 1,000-row cap with a note; Q6 release
  times as in 0.1.0; Q7 a nightly of about 17 requests, a PR's live run within 10.
- 14:06, the PR 3 interview (#12), Johannes: (1) the real asynchronous answer recorded
  once, replacing the documented-body test, the single-object SOAP-fault tests staying
  documented where no real answer exists; (2) the Comext base mirrors the main base's
  fixtures for DS-059358 (a cube, an unknown `DS-` dataset, an unknown dimension, an
  unknown code, the data query plain and compressed with the audited
  `.secrets.baseline` entry), plus the asynchronous answer and the HTTP 413 fault (on
  DS-045409); (3) one live test on DS-059358, the Comext reachability check; (4) the
  docstrings, CLAUDE.md and the README say that 0.1.0's seven tasks serve `DS-`
  datasets (five, as built: `get_data`, the three slices and `download_dataset`),
  through one documented routing helper in `_client.py`.
- 14:19, the PR 3 interview's fifth answer, Johannes: the text values. A value is a
  number where it parses, else the text as Eurostat printed it: `Observation.value` and
  `Cube.value` take a `str`, `SdmxCsvRow.obs_value` is `Decimal | str | None`
  (conventions §3, units and footnote markers kept as text; a type widened in a minor,
  §12).
- 15:16, the PR 4 interview (Prodcom), Johannes: (1) a packaged list of the Comext base
  names the codelist's full URL as its `endpoint`, the main base's twelve keep their
  path; (2) two tasks, `get_sold_production` on DS-059358 and `get_total_production` on
  DS-059359, one request each through `get_data`, observations under a 200-row cap;
  (3) `indicators=None` sends no filter, every indicator, and the cap's note names
  `indicators`; (4) the Comext lists join `list_codes` and `lists.json`, with
  `list_products(search)` over CXT_PRODCOM2_SOLD; (5) the selector: the refresh script
  gains `--only <name> ...`, so a feature PR fetches only the lists it adds and the
  routine refresh stays a PR of its own (row 179).
- 16:09, the PR 5 interview (Comext trade), Johannes: (1) two trade tasks as for
  Prodcom, `get_trade` on DS-045409 and `get_trade_hs` on DS-059341; (2)
  `download_trade`, task-shaped on DS-045409, its positional key built from the
  structure, `product` or `reporters` required, compressed SDMX-CSV to disk; (3)
  CXT_NC, CXT_FREE_ISO and CXT_EU_FLUX packaged, and DS-059341's product list if it
  differs (it does not: its structure names CXT_NC); reporters, partners and the flow
  checked before sending, the Prodcom tasks' reporters too; (4) `freq` defaults to `M`.
- 16:49, the session's answers to the PR 5 worker's questions: one more recording, of
  what DS-059341 answers to a CN8 code, and no narrowing by code length, since the
  structure names CXT_NC; `freq` a hand-written StrEnum `models.Freq` (`A`, `M`) in
  `models.py`, as `Lang` is (row 85), so the MCP schema lists the values; the CHANGELOG
  records 0.2.0's final behaviour only; `TO` in `list_hs`, `ZZZZZZZZ` in `list_cn8`,
  `TOTAL` in neither, as upstream's codes split by length.
- The asynchronous answer's two recorded shapes (rows 59, 83): the SDMX 2.1 data API's,
  recorded in #12 (log 15:16), HTTP 200, `application/xml`, a SOAP envelope with status
  `SUBMITTED`, DS-045409's answer to its whole monthly flow
  (`tests/fixtures/data_query/DS-045409_asynchronous.json`); and the Statistics API's,
  recorded in PR 5 (log 17:05), HTTP 413 with an `error` array labelled
  `ASYNCHRONOUS_RESPONSE`, DS-059341's answer to a CN8 code
  (`tests/fixtures/get_data/DS-059341_AT_DE_15071090_cn8_on_hs_flow.json`), not the
  user guide's `warning`, which was never seen and keeps its documented-body test.
  `classify` refuses the first by its content type and the second by its label
  (`errors.asynchronous_fault`), before the HTTP 413 refusal of `EXTRACTION_TOO_BIG`,
  which shares its status and id.
- 17:05 and 17:21, the session: the routine refresh becomes a PR only if it changes
  more than fetch times; the table of contents gained four leaves (10,375 to 10,379),
  so it is PR 6.

## Next

- The leaves above, each when a consumer needs it: polling the asynchronous answer, the
  CPA 2.2 lists, the Comext base's catalogue should Eurostat serve it, `list_products`
  over the total list, narrowing `get_trade_hs` by HS length, SDMX 3.0 and TSV.
- The routine reference refresh after the release (`/refresh-reference-data`).
- The `family-review` check gave no verdict anywhere in the family on 2026-10-28 (log
  15:37): sdk-eurostat #11 at 14:31 and on its re-run at 14:34, sdk-comtrade and
  sdk-usda-gats as well, in two modes, no structured output after a full run and, from
  14:31 on, an immediate model-call error. The session stopped re-running it; the
  repository's ruleset requires `ci` alone. Check whether it gives verdicts again
  before reading anything into its result.
- A core minor or template release that takes up the rows below arrives through
  `/adopt-release`, in one adoption PR before the next release.

## Queue rows this package filed or extended

Titles as `python3 scripts/coord.py queue show N` gives them; status as of 2026-10-28.
A row's "PR N" counts the packages of the briefing it was written under: an entry
dated 2026-10-28 from 13:29 on the 0.2.0 briefing's, as above; an earlier one the 0.1.0
briefing's, whose PRs 1 to 4 and 6 are #1 to #4 and #6, PR 7 (the slices) #5, PR 8
(the bulk task) #7 and PR 9 (the template v0.3.0 adoption) #8.

Filed during 0.2.0, all open:

| Row | Repository | Title |
| --- | --- | --- |
| 145 | sdk-template | record-fixture.md and family.md still name the fixture directory by <endpoint> and the api/ layer by <operation>; conventions 1.22 names both by the wrapper (from sdk-eurostat 0.2.0 PR 1) |
| 155 | sdk-core | gap: conventions §3 names neither the not-fetched table of FETCHED.md (linked resources deliberately not requested, each with a reason) nor structural answer samples under docs/upstream/samples/ (from the sdk-eurostat 0.2.0 PR 2 review) |
| 172 | sdk-core | gap: an upstream that serves part of its data from a second base URL on the same host (Eurostat's Comext base): one client, an absolute URL per routed call, one limiter, cache and classify (from sdk-eurostat 0.2.0 PR 3) |
| 173 | sdk-template | record-fixture.md says the request path is relative to the base URL; a recording on a second base of the same upstream passes an absolute URL (from sdk-eurostat 0.2.0 PR 3) |
| 177 | sdk-core | gap: conventions §3's packaged-file name rule (the parameter, or a name of the list's own where two lists feed one parameter) does not cover naming by upstream's list id, nor one list feeding two parameters (from the sdk-eurostat 0.2.0 PR 4 review) |
| 178 | sdk-core | UnknownCode builds its message's article from param, so a plural parameter name (indicators, reporters) reads badly; a noun argument separate from param (from sdk-eurostat 0.2.0 PR 4) |
| 179 | sdk-template | the refresh_reference.py skeleton could carry a selector (--only <name> ...) so a feature PR fetches only the lists it adds and the routine refresh stays its own PR (from sdk-eurostat 0.2.0 PR 4) |

Extended during 0.2.0, all open:

| Row | Repository | Title | Extended with |
| --- | --- | --- | --- |
| 59 | sdk-core | gap: an upstream that defers a large synchronous request (Eurostat's asynchronous answer) is refused in classify with InvalidRequestError (eurostat design round Q4) | the two recorded asynchronous answers |
| 69 | sdk-core | gap: an upstream document regenerated per request in an unstable order (Eurostat WADL files) and the keep-if-same-lines rule (from sdk-eurostat PR 2) | six reordered WADLs in #11's run, four of the Comext base |
| 75 | sdk-core | gap: live-call accounting for a session orchestrator own probes (from sdk-eurostat PR 2 review) | a briefing's budget line naming the reference refresh's requests |
| 83 | sdk-core | gap: a test that reads an upstream-documented body verbatim from docs/upstream/ when the shape cannot be recorded (conventions §10; from sdk-eurostat PR 4) | the documented SDMX bodies replaced by recordings; a third kind of not-recorded test; a documented shape never seen keeps its test when the recorded one differs |
| 99 | sdk-core | stale sentences outside the release subset after core 0.3.0 (sdk-gates name; roadmap state) | item (h), conventions 1.22 §2's sentence on `api/catalogue.py` |
| 128 | sdk-core | two bulk-task gaps: core download refuses a bad dest with ValueError outside the taxonomy, and meta.endpoint for a task that downloads through an API operation (from the sdk-eurostat PR 8 review) | a download wrapper passes no `endpoint=` |

0.1.0's other rows, still open:

| Row | Repository | Title |
| --- | --- | --- |
| 58 | sdk-core | gap: the family's first multi-dimensional answer, a JSON-stat cube stated under ADR-0003 (eurostat design round Q1) |
| 62 | sdk-template | live.yml: actions by mutable tag and a checkout that persists credentials (from the sdk-eurostat scaffold review) |
| 71 | sdk-template | PULL_REQUEST_TEMPLATE.md still names the organisation .github repository for the merge classes (renamed sdk-gates; from sdk-eurostat PR 2) |
| 76 | sdk-core | gap: a publisher own conditions on modified text, such as Eurostat disclaimer on modifications (conventions §3 attribution; from sdk-eurostat PR 2 review) |
| 77 | sdk-core | gap: a documentation page behind a login is recorded as not fetched, no credentials, no browser automation (conventions §3; from sdk-eurostat PR 2) |
| 80 | sdk-template | CLAUDE.md says api/ holds one module per upstream operation; Eurostat needs one per service, since WADL method ids repeat (from sdk-eurostat PR 4) |
| 81 | sdk-core | a public helper for the request description classify implementations rebuild (errors._where), and a refuse-above-N-bytes option on record() (from sdk-eurostat PR 4) |
| 85 | sdk-template | no stated home for a hand-written upstream enumeration: enums.py is generated and rewritten whole (from sdk-eurostat PR 4) |
| 86 | sdk-core | a value refused by a typed parameter (StrEnum, int) bypasses the family error format in both adapters (from sdk-eurostat PR 4 review) |
| 89 | sdk-core | gap: a bound on a refusal text that lists codes (eurostat get_series lists at most 20 codes per unpinned dimension; from sdk-eurostat PR 7) |
| 90 | sdk-core | gap: a task that composes another task of the same package (eurostat slices call get_data async); conventions §2 says tasks compose endpoint wrappers (from sdk-eurostat PR 7) |
| 91 | sdk-core | ResultCap: an option to keep the last rows of a cut list, for time series ordered oldest first (from sdk-eurostat PR 7) |
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
| 137 | sdk-core | gap: a first release (version unchanged at 0.1.0) is recognised by neither review-checklist item 13 nor sdk-gates merge-class rule 5, and the definition-of-done Docs item 7 (an entry under Unreleased) is untrue for every release PR (from the sdk-eurostat 0.1.0 release review) |

Row 135, this package's own wrapper rename, reads done since 2026-10-28 20:31: it
landed in sdk-eurostat#10.
