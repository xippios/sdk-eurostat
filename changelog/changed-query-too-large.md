- A query that Eurostat refuses as too large, `EXTRACTION_TOO_BIG` at HTTP 413, raises
  core's `QueryTooLarge`, a subclass of `InvalidRequestError`, with Eurostat's estimate as
  `count` and its limit as `limit`, in `get_data` and `download_dataset` alike. Its message
  names the request, the estimate and the limit in core's words, and how to narrow the
  query. (https://github.com/xippios/sdk-core/issues/481, https://github.com/xippios/sdk-eurostat/issues/82)
