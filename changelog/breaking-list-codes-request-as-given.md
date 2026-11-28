- `list_codes` records `codelist` in `meta.request` as the caller gave it, `"geo"` for
  `list_codes("geo")`, where it recorded the packaged id, `"GEO"`. A caller that compares
  `meta.request["codelist"]` with the id reads it from `meta.endpoint`, which ends in the id.
  (https://github.com/xippios/sdk-eurostat/issues/96)
