- `api.statistics.get_data` and `api.sdmx.code_list_query` return core's `Answer` in place
  of `DataAnswer` and `CodelistAnswer`, with when the answer was retrieved as
  `retrieved_at`. The `payload` of `get_data` is a `PrintedCube`, the cube with its
  `updated` as Eurostat printed it, which `meta.vintage` holds, and that of
  `code_list_query` the parsed `Codelist`.
  (https://github.com/xippios/sdk-core/issues/479, https://github.com/xippios/sdk-eurostat/issues/82)
