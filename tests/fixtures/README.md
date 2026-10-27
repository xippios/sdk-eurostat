# Recorded fixtures

`<endpoint>/<case>.json`, written by `/record-fixture` through
`xippios.core.testing.record`, never by hand. Credentials are scrubbed on write; still
grep before committing:

```bash
grep -rniE 'api[_-]?key|token|secret' tests/fixtures
```

`dataQuery/*_compressed.json` holds a gzip file as its body, which no grep reads: it is
stored base64 (`body_base64`, recorded with `Scrub(allow_binary=True)`) and decompresses
to the plain recording beside it, byte for byte, which `tests/test_parse.py` checks.

`files/<kind>/<case>.*` are the parser tests' samples, never written by hand: `toc/`
and `codelist/` of the answers `scripts/refresh_reference.py` reads, cut by its
`--samples` run from the answers it packaged; `sdmx-csv/` the response bodies of the
recorded `dataQuery/` exchanges, byte for byte. `files/README.md` gives each one's
release, URL, sha256 and fetch time (ADR-0020 decision 6).
