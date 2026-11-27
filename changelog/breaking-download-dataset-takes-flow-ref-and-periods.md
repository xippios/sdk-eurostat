- `download_dataset` takes `flow_ref`, `start_period` and `end_period`, upstream's `flowRef`,
  `startPeriod` and `endPeriod`, in place of `dataset`, `since` and `until`, and its
  `meta.request` names `flow_ref`. A call that names `dataset`, `since` or `until` fails, and
  `key` stays second, by position or by name.
  (sdk-core ADR-0061, https://github.com/xippios/sdk-eurostat/issues/80,
  https://github.com/xippios/sdk-eurostat/issues/82)
