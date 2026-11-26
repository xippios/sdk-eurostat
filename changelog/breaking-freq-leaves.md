- `xippios.eurostat.models.Freq` leaves with `get_trade`, `get_trade_hs` and
  `download_trade`, the tasks that took it. A `freq` filter of `get_data` takes the code
  itself, `"M"` or `"A"`, as the dataset's cube lists it.
  (sdk-core ADR-0060, https://github.com/xippios/sdk-core/issues/474,
  https://github.com/xippios/sdk-eurostat/issues/84)
