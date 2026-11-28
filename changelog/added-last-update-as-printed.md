- `xippios.eurostat.parse.sdmx_csv` exports `last_update_as_printed(path)`, the first row's
  `LAST UPDATE` of a downloaded SDMX-CSV file as Eurostat prints it, `"05/10/26 23:00:00"`,
  the text that `download_dataset` keeps as `meta.vintage`; `None` for a file without a row.
  (https://github.com/xippios/sdk-eurostat/issues/99)
