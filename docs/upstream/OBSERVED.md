# What Eurostat does but never documents

Notes, written by hand, on what the Eurostat dissemination API does that no page of this
snapshot states (sdk-core's conventions §3). `scripts/refresh_upstream.py` neither writes
nor checks this file, and its next run lists the file in `FETCHED.md` in a row of its own.

Each note ends with its probe: the date, the operation and the sample. A sample kept
under `tests/fixtures/files/` is named by its path there, and its row in that folder's
`README.md` gives the release, URL, bytes and sha256 of the full answer.

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
