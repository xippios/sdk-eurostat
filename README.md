# xippios-eurostat

Typed Python client, MCP server and FastAPI routes for
[Eurostat dissemination API](https://ec.europa.eu/eurostat/web/main/data/database), part of the
[xippios SDK family](https://github.com/xippios). Names and semantics follow the
upstream documentation; every response carries release metadata (source, endpoint,
retrieved_at, published_at, vintage).

## Install

```bash
uv add xippios-eurostat            # client only
uv add "xippios-eurostat[mcp]"     # + MCP server
uv add "xippios-eurostat[http]"    # + FastAPI router
```

No API key is needed.

## 30-second example

```python
from xippios.eurostat import tasks

# result = tasks.<task>(...)
# result.data, result.meta.retrieved_at, result.meta.request
```

Task functions are listed in the status table below as they are added.

## MCP

```json
{
  "mcpServers": {
    "eurostat": {
      "command": "uvx",
      "args": ["--from", "xippios-eurostat[mcp]", "xippios-eurostat-mcp"]    }
  }
}
```

Tools are read-only and named `eurostat_<verb>_<noun>`. Results are capped, at
200 rows or 64 KB unless a tool has a cap of its own, with a note on how to see the rest.
`--http` serves streamable HTTP instead of stdio.

## Status

<!-- Core's family check (tests/test_family.py) reads this table: keep the "## Status"
heading and the "Task function" column. Each row's Task function cell starts with the
task's name in backticks, alone or as its call (`get_data(code, year)`); several tasks in
one row are backticked names separated by commas; prose may follow. The tables list
exactly tasks.__all__ and tasks_write.__all__. -->

| Upstream operation | Task function | MCP tool | Status |
| --- | --- | --- | --- |
| (none yet) | | | |

## Upstream terms and attribution

Data comes from Eurostat dissemination API (https://ec.europa.eu/eurostat/web/main/data/database) under its own terms of use;
this package adds no rights to it. Documentation snapshot: `docs/upstream/`.

## Licence

Apache-2.0. See [LICENSE](LICENSE).
