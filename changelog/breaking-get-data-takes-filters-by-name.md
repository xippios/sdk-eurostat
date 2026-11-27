- `get_data` takes `filters` by name alone, as in `get_data("apro_mk_cola", filters={"geo":
  "AT"})`, since every optional filter of a task is keyword-only. A call that passes the
  filters second, by position, fails with `TypeError`, and over MCP and HTTP, which take every
  argument by name, nothing changes.
  (sdk-core ADR-0061, https://github.com/xippios/sdk-usda-esr/issues/60,
  https://github.com/xippios/sdk-eurostat/issues/80)
