- The MCP server's instructions say what each tool lists, `eurostat_list_datasets` the
  datasets' codes and `eurostat_list_codes` the codes of eighteen codelists, and that the
  cube of `eurostat_get_data` lists the codes of any other dimension, where they promised a
  list tool for every value. The text of `get_data`'s `filters` names Eurostat's two
  country lists, GEO for `geo` with Greece `EL` and the United Kingdom `UK`, and
  CXT_FREE_ISO for `reporter` and `partner` with `GR` and `GB`.
  (https://github.com/xippios/sdk-eurostat/issues/52, https://github.com/xippios/sdk-eurostat/issues/82)
