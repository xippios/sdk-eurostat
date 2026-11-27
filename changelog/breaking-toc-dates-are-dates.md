- `Dataset.last_update` and `Dataset.last_modified`, a leaf's `lastUpdate` and
  `lastModified` in the table of contents, are dates read day first from `"05.11.2026"`,
  where 0.3.0 held the text. `eurostat_list_datasets` answers them as ISO dates,
  `"2026-11-05"`.
  (https://github.com/xippios/sdk-usda-esr/issues/60, https://github.com/xippios/sdk-eurostat/issues/82)
