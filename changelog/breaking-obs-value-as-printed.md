- `SdmxCsvRow.obs_value` keeps the text that Eurostat prints, `"3247.05"` or `"KG"`, and
  `obs_value_number` beside it reads it as a `Decimal`, `None` where the text is no number,
  where 0.3.0 held a `Decimal` or the text in `obs_value`. A caller that reads the number
  takes `obs_value_number`.
  (sdk-core ADR-0060, https://github.com/xippios/sdk-eurostat/issues/80)
