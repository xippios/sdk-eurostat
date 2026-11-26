- `get_series`, `get_latest_period` and `get_cross_section` leave, with their MCP tools, their
  routes and their caps, by the boundary of a source package: a task that fixes the filters
  of one upstream operation is not the package's. `get_data` sends the same requests, with
  `since_time_period` and `until_time_period`, `last_time_period=1` or a `time` filter, and
  `result.data.observations()` reads the cube's cells with their codes and labels.
  (sdk-core ADR-0060, https://github.com/xippios/sdk-core/issues/474,
  https://github.com/xippios/sdk-eurostat/issues/84)
