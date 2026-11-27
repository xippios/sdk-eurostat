# What Eurostat does but never documents

Notes, written by hand, on what the Eurostat dissemination API does that no page of this
snapshot states (sdk-core's conventions §3). `scripts/refresh_upstream.py` neither writes
nor checks this file, and `FETCHED.md` lists it in a row of its own. `CLAUDE.md`, the
README and the package's modules say what the package does with a note and cite it by its
heading; none of them repeats its probe.

Each note ends with its probe: the date, the operation and the sample. A recording is named
by its path under `tests/fixtures/`, and its `recorded_at` gives the time; a sample kept
under `tests/fixtures/files/` is named by its path there, and its row in that folder's
`README.md` gives the release, URL, bytes and sha256 of the full answer. A probe that kept
no answer names its request.

## Statistics API

### A code that matches nothing answers an empty cube

The Statistics API answers a filter whose code matches nothing in the dataset with HTTP 200
and a cube in which that filter's dimension has size 0 and no cell has a value or a status,
where its fault table gives "No results found" for "The result from the query is empty"
(`docs/upstream/user-guide/api-detailed-guidelines/api-statistics.md`, "Error messages
returned in case of invalid queries"). It answers so a code that no codelist of the
dataset holds, `XX` for `geo` on the main base and for `reporter` on the Comext base, and
a code that the dataset's codelist holds and the dataset does not use: DS-059359 answered
the indicator `PRODVAL`, which CXT_INDICATORS holds, with the reporter `AT` and the product
`20158000`, which CXT_FREE_ISO and CXT_PRODCOM2_TOTAL hold, with its `indicators` of size 0.
`get_data` refuses the first kind before its request, by the check of a packaged codelist,
and answers the second with `NotFoundError` after it.

Probe: 2026-10-27 and 2026-10-28, `getData`: `geo=XX` on apro_mk_cola on the main base,
`tests/fixtures/get_data/unknown_code.json` (2026-10-27); on the Comext base `reporter=XX`
on DS-059358, `tests/fixtures/get_data/DS-059358_unknown_code.json`, and `PRODVAL` on
DS-059359, `tests/fixtures/get_data/DS-059359_AT_20158000_indicator_not_in_dataset.json`
(2026-10-28).

### The refusal of `geo` with `geoLevel` comes as an array

The user guide documents the refusal of a query with both as one fault, an object whose
status is text and which has no id:
`{"error":{"status":"400","label":"'geo' parameter and 'geoLevel' parameter cannot be set
at the same time. Please choose one or the other."}}`
(`docs/upstream/user-guide/api-detailed-guidelines/api-statistics.md`, "The geoLevel
parameter"). Eurostat answered with HTTP 400 and an `error` array of one fault under the
same label, its status a number and its id 400. `errors.error_faults` reads both shapes.

Probe: 2026-10-27, `getData`, `geo=AT` with `geoLevel=country` on apro_mk_cola,
`tests/fixtures/get_data/geo_with_geo_level.json`.

### The asynchronous answer comes as an `error` array

The user guide documents the Statistics API's answer to a request that it will treat
asynchronously as a `warning` member, `{"warning":{"status":413,
"label":"ASYNCHRONOUS_RESPONSE. ..."}}`, at an HTTP status it does not name
(`docs/upstream/user-guide/api-detailed-guidelines/api-statistics.md`, "Asynchronous
response in case of big extractions"). Eurostat answered with HTTP 413 and an `error` array
of one fault, its status and its id 413, labelled "ASYNCHRONOUS_RESPONSE. Your request will
be treated asynchronously. Please try again later.": the status and the id of its refusal
of an extraction too large, `EXTRACTION_TOO_BIG`, so the label alone tells the two apart
(`errors.asynchronous_fault`). The documented `warning` was never answered: four requests
without a filter on the main base, to the datasets apro_ec_poulm, ef_mp_digicr, ef_ah_pigt
and env_air_emis, were answered at once with HTTP 200, 9.9 to 19.2 MB in 3.0 to 5.5 s
(https://github.com/xippios/sdk-eurostat/pull/4, its live calls).

Probe: 2026-10-27 and 2026-10-28, `getData`: on the main base
`GET statistics/1.0/data/apro_ec_poulm`, `GET statistics/1.0/data/ef_mp_digicr`,
`GET statistics/1.0/data/ef_ah_pigt` and `GET statistics/1.0/data/env_air_emis`, each
without a filter as https://github.com/xippios/sdk-eurostat/pull/4 names them, the rest of
their query not recorded, kept no answer (2026-10-27); on the Comext base DS-059341, by
HS2-4-6, answered so the CN8 product `15071090` with the reporter `AT` and the partner `DE`,
`tests/fixtures/get_data/DS-059341_AT_DE_15071090_cn8_on_hs_flow.json` (2026-10-28).

### The Comext base reads a filter on a dimension the dataset lacks as none

On the main base a filter on a dimension the dataset lacks is refused with HTTP 400 and the
fault 150, "INVALID_QUERY_DIMENSION: Query is invalid as per its structure's definition".
On the Comext base `geo=AT` on DS-059358, whose dimensions are `freq`, `reporter`,
`product`, `indicators` and `time`, was refused with HTTP 413 and `EXTRACTION_TOO_BIG`,
"estimated 151971120 rows, max authorised is 5000000": the estimate of an unfiltered query,
so the filter seems to be ignored. `classify` maps the first to `InvalidRequestError` and
the second to core's `QueryTooLarge`.

Probe: 2026-10-27 and 2026-10-28, `getData`: `nosuchdim=AT` on apro_mk_cola on the main
base, `tests/fixtures/get_data/unknown_dimension.json` (2026-10-27), and `geo=AT` on
DS-059358 on the Comext base,
`tests/fixtures/get_data/DS-059358_unknown_dimension_too_big.json` (2026-10-28).

## SDMX 2.1 API

### A data query answers SDMX-CSV under one media type, compressed or not

`format=SDMX-CSV` is answered with HTTP 200 and the media type
`application/vnd.sdmx.data+csv;version=1.0.0`, which no page of the user guide names, and
Eurostat's file name in `Content-Disposition`, `estat_apro_mk_cola_filtered_en.csv`. With
`compressed=true` the media type stays the same, the file name ends in `.gz`, and the body
is a gzip file that decompresses to the plain answer byte for byte. `_client.SDMX_CSV` is
this media type, and `classify` refuses a data query's answer under any other.

Probe: 2026-10-27 and 2026-10-28, `dataQuery`: apro_mk_cola's key `A...THS_T.AT` for 2022
and 2023 on the main base, plain and compressed,
`tests/fixtures/data_query/apro_mk_cola_AT_THS_T_2022_2023.json` and
`tests/fixtures/data_query/apro_mk_cola_AT_THS_T_2022_2023_compressed.json` (2026-10-27),
and DS-059358's key `A.AT.10411200.` alike on the Comext base,
`tests/fixtures/data_query/DS-059358_A_AT_10411200_2022_2023_compressed.json`
(2026-10-28).

### A data query to be queued answers HTTP 200 with its envelope

The user guide documents the answer to a data query that the service treats asynchronously
as an XML envelope that queues it with the status `SUBMITTED`
(`docs/upstream/user-guide/api-detailed-guidelines/asynchronous-api.md`, "Step 1: Initial
request"), and names no HTTP status for it. Eurostat answered a request for SDMX-CSV so with
HTTP 200, the media type `application/xml` and a SOAP envelope whose `queued` element holds
the request's id and `SUBMITTED`. `classify` refuses it by its media type, since the
package does not poll.

Probe: 2026-10-28, `dataQuery`, DS-045409's whole monthly flow, the key `M.....`,
compressed, on the Comext base, `tests/fixtures/data_query/DS-045409_asynchronous.json`.

### A data query without a key answered a whole dataset at once

A data query without a key, `data/{flowRef}`, filters no dimension
(`docs/upstream/user-guide/api-detailed-guidelines/sdmx2-1/data-query.md`). Eurostat
answered one for ef_m_farmleg, 6.2 million values, with HTTP 200 and SDMX-CSV, at once.
`download_dataset` sends the key `""` so, for the whole dataset.

Probe: 2026-10-27, `dataQuery`, `GET sdmx/2.1/data/ef_m_farmleg?format=SDMX-CSV`, its
status and headers read and its body not kept
([fb9c058](https://github.com/xippios/sdk-eurostat/commit/fb9c0580106445b43bacb3c6b324711ea3a1192a)).

### A codelist in JSON-stat carries one version

The user guide says that a structure query without a version answers "all existing
versions" of the artefact
(`docs/upstream/user-guide/api-detailed-guidelines/sdmx2-1/structure-queries.md`, "About
versioned artefacts"). A codelist asked for in JSON-stat without a version answers one, its
latest, as the sample `tests/fixtures/files/codelist/statinfo.json` carries one: UNIT
answered with its version 84.0, newer than the 82.0 and 75.0 that the data structures of
apro_mk_cola and ef_m_farmleg name. `api.sdmx.code_list_query` leaves the version out for
the latest, and the reference refresh packages the version it answers.

Probe: 2026-10-27, `codeListQuery`, `GET sdmx/2.1/codelist/ESTAT/UNIT?format=JSON&lang=en`,
version 84.0, which kept no answer; the refresh of 2026-11-27 packaged UNIT at 84.0 again,
`src/xippios/eurostat/reference/lists.json`.

### The Comext base's datasets take these codelists

The data structures of the Comext base's datasets name the codelists of their dimensions,
which no page of the user guide lists. Prodcom's DS-059358 2.7 and DS-059359 2.7 take
CXT_FREE_ISO for `reporter`, CXT_PRODCOM2_SOLD and CXT_PRODCOM2_TOTAL for `product` and
CXT_INDICATORS for `indicators`. Comext's trade datasets DS-045409 6.6 and DS-059341 3.7
take CXT_FREQ for `freq` (`A`, `M`), CXT_FREE_ISO for `reporter` and `partner`, CXT_NC for
`product`, CXT_EU_FLUX for `flow` and CXT_INDICATORS for `indicators`, in the order
freq.reporter.partner.product.flow.indicators; DS-045409's cube holds the indicators
VALUE_IN_EUROS, QUANTITY_IN_100KG and SUPPLEMENTARY_QUANTITY, and DS-059341's VALUE_EUR,
VALUE_NAC and QUANTITY_KG. `params.CODELISTS` declares each packaged codelist's base and
dimension from them.

Probe: 2026-10-28, `dataStructureQuery` on the Comext base, one request for each data
structure in SDMX-ML, written here in the WADL's form
(`docs/upstream/api/comext/sdmx-rest.wadl:983`), since no record holds the requests as
sent:
`GET https://ec.europa.eu/eurostat/api/comext/dissemination/sdmx/2.1/datastructure/ESTAT/DS-059358/2.7`,
`GET https://ec.europa.eu/eurostat/api/comext/dissemination/sdmx/2.1/datastructure/ESTAT/DS-059359/2.7`,
`GET https://ec.europa.eu/eurostat/api/comext/dissemination/sdmx/2.1/datastructure/ESTAT/DS-045409/6.6`
and
`GET https://ec.europa.eu/eurostat/api/comext/dissemination/sdmx/2.1/datastructure/ESTAT/DS-059341/3.7`
kept no answer (https://github.com/xippios/sdk-eurostat/pull/14 counts DS-059341's read, and
[2362757](https://github.com/xippios/sdk-eurostat/commit/2362757ca9b7b70db177b5d10cfec9696efdc8e2)
states the versions 6.6 and 3.7); and `getData`, the cubes
`tests/fixtures/get_data/DS-045409_AT_DE_15071090_2023.json` and
DS-059341's for the reporter `AT`, the partner `DE` and the product `1507` in 2023,
recorded the same day and removed with the trade tasks in 0.4.0, as it stands at
https://github.com/xippios/sdk-eurostat/blob/1713cf7ff17283a012f1b40721140b10a82b54c3/tests/fixtures/get_data/DS-059341_AT_DE_1507_2023.json.

## Catalogue API

### A leaf may print its number of values empty

A leaf of the table of contents may print its `values` element empty, `<nt:values/>`,
where the user guide describes the number of values as the "Number of actual values
included in the dataset" and marks only the data start and the data end "(if
available)" (`user-guide/api-detailed-guidelines/catalogue-api/toc.md`). The element is
present, as on every other leaf, and the leaf's other elements are printed as on any
other leaf. A data start or end that is not available is printed the same way, as an
empty `dataStart` and `dataEnd`. The package reads an empty `values` as `None`
(`Dataset.values`). The XML schema the file names, `TableOfContent.xsd`, is not in this
snapshot.

Probe: 2026-11-20, `getTocXml` (`catalogue/toc/xml`), one download, creationDate
`20261120T1004`. Of its 10,454 leaves, one pre-defined table, `tai13` ("Share of
agricultural holdings by type of manure storage facilities"), listed at two places of
the tree, printed `values` empty, and five leaves printed `dataStart` and `dataEnd`
empty; no leaf left any of the three elements out. Sample
`tests/fixtures/files/toc/ai.xml`. The table of contents fetched on 2026-10-28,
creationDate `20261028T1000`, printed a number on each of its 10,379 leaves and did not
list `tai13`.

### The Comext base answers the table of contents with HTTP 404

The Comext base's Catalogue WADL lists `getTocXml` at `catalogue/toc/xml`
(`docs/upstream/api/comext/catalogue.wadl`), as the main base's does, and the user guide
gives the Comext base as the base of the `DS-` datasets
(`docs/upstream/user-guide/api-detailed-guidelines/prefixed-datasets.md`). The Comext base
answered the table of contents with HTTP 404, so no table of contents lists its datasets,
and `list_datasets` lists the main base's alone.

Probe: 2026-10-28, `getTocXml`,
`GET https://ec.europa.eu/eurostat/api/comext/dissemination/catalogue/toc/xml`, which kept
no answer.

## Eurostat's website

### The website's request budget runs out within a few requests

The pages of the user guide are served by Eurostat's website, for which no page of the
snapshot gives a rate, and the API's fair-use rule names no number
(`docs/upstream/user-guide/api-detailed-guidelines/asynchronous-api.md`, "Fair use of the
service"). The website reports a small request budget in `X-Rate-Limit-Remaining`, which a
series of requests a few seconds apart drains, and then answers HTTP 429 "Quota Exhausted",
naming the wait in `X-Rate-Limit-Retry-After-Seconds` or `Retry-After`. Five seconds apart,
`scripts/refresh_upstream.py`'s pace, a capture of its 33 pages met three 429s, each
answered at the one retry after the wait the website named. The script's `PAUSE`,
`QUOTA_PAUSE` and `MAX_QUOTA_WAIT` follow from it.

Probe: 2026-10-27 and 2026-11-27, the website's pages: the first runs of the capture
script, whose requests were the snapshot's pages from
`GET https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-introduction`
on, kept no answer, and the budget, its header and the 429 stand in the script's text since
[564652c](https://github.com/xippios/sdk-eurostat/commit/564652ceb5bb7591564e12308e67c29998d7ac35)
(2026-10-27); the capture of 2026-11-27 met a 429 once at each of
`GET https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-detailed-guidelines`,
`GET https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-detailed-guidelines/catalogue-api/dcat`
and `GET https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-faq`,
retried after 25, 28 and 29 s, and kept no answer
(https://github.com/xippios/sdk-eurostat/pull/91, its live calls).
