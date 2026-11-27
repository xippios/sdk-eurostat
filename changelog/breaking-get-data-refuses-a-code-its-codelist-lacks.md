- `get_data` refuses before its request a filter's code that the one packaged codelist of
  its dimension lacks, `filters={"geo": "XX"}` say, with core's `UnknownCode`, which names
  the closest codes and says that nothing was sent, where 0.3.0 sent it and returned an empty
  cube. The twelve dimensions of the main base's codelists and `reporter`, `flow` and
  `indicators` of the Comext base are checked, and `product` and `partner` are sent
  unchecked.
  (sdk-core ADR-0061, https://github.com/xippios/sdk-eurostat/issues/43,
  https://github.com/xippios/sdk-eurostat/issues/82)
