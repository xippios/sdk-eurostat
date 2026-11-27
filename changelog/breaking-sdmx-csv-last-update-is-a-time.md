- `SdmxCsvRow.last_update` is a naive `datetime` read day first from `LAST UPDATE`, as in
  `"05/10/26 23:00:00"`, where 0.3.0 held the text, and `meta.vintage` of
  `download_dataset` keeps the text. A `LAST UPDATE` printed in another form is refused by
  `parse_sdmx_csv` at its row with `ValidationError`.
  (https://github.com/xippios/sdk-usda-esr/issues/60, https://github.com/xippios/sdk-eurostat/issues/82)
