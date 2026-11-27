# Layout

The files that every source of the family holds are laid out once, in the tree of
sdk-template's README,
[What gets generated](https://github.com/xippios/sdk-template/blob/main/README.md#what-gets-generated).
This file holds what `xippios-eurostat` adds to that tree, a module, a task file, a
script or a test of its own, each with what it holds, and the change that adds one updates it.

The import path is `xippios.eurostat` (sdk-core ADR-0006); `src/xippios/` is a
namespace package.
Where the API's operation ids repeat across its services, `api/` keeps one module per service
instead, named after the service, and this file says so (conventions §2).

```
src/xippios/eurostat/
  _client.py       the one client of both base URLs, url_for, which sends a DS- code to the
                   Comext base, and classify, which maps EXTRACTION_TOO_BIG to core's
                   QueryTooLarge
  errors.py        the Statistics API's fault model and its parsing, for classify
  models.py        Cube, the JSON-stat 2.0 dataset, Codelist, Code, Dataset and SdmxCsvRow,
                   and the value sets written by hand, Lang, GeoLevel and LeafType
  api/
    statistics.py  getData, statistics/1.0/data/{datasetCode}: the cube with its updated
                   as printed, a PrintedCube
    sdmx.py        codeListQuery, one codelist, and dataQuery, a data query streamed as
                   SDMX-CSV to a file
    catalogue.py   getTocXml, the table of contents streamed to a file, which the reference
                   script alone reads
  parse/
    sdmx_csv.py    parse_sdmx_csv, the SDMX-CSV 1.0 file that download_dataset writes, gzip
                   or plain, row by row
  params.py        CODELISTS, each codelist's base and dimension, and the readers of the
                   packaged lists: datasets(), the table of contents, codes(), a codelist,
                   list_info(), the index lists.json
  reference/       the table of contents, twelve codelists of the main base and six of the
                   Comext base (CXT_PRODCOM2_SOLD, CXT_PRODCOM2_TOTAL, CXT_INDICATORS, CXT_NC,
                   CXT_FREE_ISO, CXT_EU_FLUX), and the index lists.json
scripts/
  refresh_reference.py   declares LISTS, the nineteen lists, with the reader of the table of
                         contents and the cut of the samples; --samples writes the samples
                         under tests/fixtures/files/
  refresh_upstream.py    declares SNAPSHOT, its client of the website, the converter of the
                         user-guide pages and the rule that keeps a WADL file as recorded
tests/
  fixtures/        recorded responses, <wrapper>/<case>.json; data_query/*_compressed.json
                   holds a gzip body, stored base64
  fixtures/files/  a sample of each file kind the parsers and the reference script read,
                   <kind>/<case>.*: toc/, codelist/ and sdmx-csv/
  test_client.py   classify against the recorded refusals and the documented ones
  test_models.py   Cube against the recorded answers
  test_parse.py    parse_sdmx_csv on the samples under tests/fixtures/files/sdmx-csv/
  test_refresh_reference.py  the reference script's declaration, readers and cuts, and the
                   frame's run of it, offline
  test_refresh_upstream.py   the snapshot's declaration and hooks, offline
docs/upstream/
  OBSERVED.md      what upstream does but never documents, each note with its evidence
```
