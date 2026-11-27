- `get_data` raises `NotFoundError` for a cube that holds no cell, Eurostat's answer to a
  code the dataset does not use or to a period not yet released, where 0.3.0 returned the
  empty cube. The error names the dataset and the filters sent, and says that the request
  was sent.
  (sdk-core ADR-0061, https://github.com/xippios/sdk-eurostat/issues/43,
  https://github.com/xippios/sdk-eurostat/issues/82)
