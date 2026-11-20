- `Dataset.values`, the number of values of a leaf that `list_datasets` returns, may be
  `None`, as `data_start` and `data_end` already may: the table of contents of 2026-11-20
  prints it empty for a pre-defined table, which stopped the reference refresh. A caller
  that reads it as an integer checks for `None` first.
  (https://github.com/xippios/sdk-eurostat/issues/72)
