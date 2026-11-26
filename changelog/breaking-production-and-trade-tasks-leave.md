- `get_sold_production`, `get_total_production`, `get_trade`, `get_trade_hs` and the bulk
  `download_trade` leave, with their MCP tools, their routes and their caps, by the boundary
  of a source package: each fixed one Prodcom or Comext dataset and the filters of
  `get_data` or the series key of `download_dataset`. `get_data("DS-059358", {"reporter":
  "AT", "product": "10411200"})` and `download_dataset("DS-045409", "M.AT.DE.15071090..",
  dest=...)` read the same records, and `list_codes` lists the codes that the five checked
  before sending.
  (sdk-core ADR-0060, https://github.com/xippios/sdk-core/issues/474,
  https://github.com/xippios/sdk-eurostat/issues/84)
