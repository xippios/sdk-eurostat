# Recorded fixtures

`<endpoint>/<case>.json`, written by `/record-fixture` through
`xippios.core.testing.record`, never by hand. Credentials are scrubbed on write; still
grep before committing:

```bash
grep -rniE 'api[_-]?key|token|secret' tests/fixtures
```

`files/<kind>/<case>.*` are the parser tests' samples of the answers
`scripts/refresh_reference.py` reads, cut by its `--samples` run from the answers it
packaged, never by hand; `files/README.md` gives each one's release, URL, sha256 and
fetch time (ADR-0020 decision 6).
