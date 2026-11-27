- `list_codes` and `list_datasets` take `search` by name alone, as in `list_codes("geo",
  search="austria")`. A call that passes it by position fails with `TypeError`, and over MCP
  and HTTP, which take every argument by name, nothing changes.
  (sdk-core ADR-0061, https://github.com/xippios/sdk-usda-esr/issues/60,
  https://github.com/xippios/sdk-eurostat/issues/80)
