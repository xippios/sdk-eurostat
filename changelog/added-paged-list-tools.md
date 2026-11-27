- `eurostat_list_datasets` and `eurostat_list_codes` take `offset`, the rows of a cut
  answer already shown, and answer the rows after them by running the task again on its
  packaged table, which sends no request. The note of every page but the last names
  `search` and the `offset` to continue with, so an answer without a note is whole.
  (https://github.com/xippios/sdk-core/issues/314, https://github.com/xippios/sdk-eurostat/issues/82)
