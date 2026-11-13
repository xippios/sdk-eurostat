- Adopted sdk-template v0.3.3 and conventions 1.27 (conventions §15), with no new core
  minor: the floor stays `xippios-core~=0.3.0`, since core 0.3.1 changed documents only.
  The README lists the package's documents under `## Documents` and links its license by
  URL, and `CLAUDE.md` holds the rules that `.claude/family.md` carried, which leaves with
  `/adopt-release`. Changelog entries are fragments under `changelog/`, the package's own
  decisions go into `docs/adr/` with the index that `scripts/adr_index.py` writes, and a
  pull request runs the organization's checks from `organization.yml`, where `gates.yml`
  was. (https://github.com/xippios/sdk-eurostat/issues/20)
