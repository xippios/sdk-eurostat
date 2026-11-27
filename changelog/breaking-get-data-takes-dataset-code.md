- `get_data` takes the dataset as `dataset_code`, upstream's `datasetCode`, in place of
  `dataset`, and so do its MCP tool `eurostat_get_data`, its route and `meta.request`. A call
  that names `dataset` fails, and one that passes the code first by position works as before.
  (sdk-core ADR-0061, https://github.com/xippios/sdk-eurostat/issues/80,
  https://github.com/xippios/sdk-eurostat/issues/82)
