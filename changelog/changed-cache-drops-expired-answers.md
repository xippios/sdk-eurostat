- The answers of `get_data` are kept in core's cache for five minutes, the lifetime of every
  path, an expired answer dropped and the bodies held under core's bound of 64 MiB in all.
  (https://github.com/xippios/sdk-core/issues/479, https://github.com/xippios/sdk-eurostat/issues/82)
