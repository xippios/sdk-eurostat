- `xippios.eurostat.enums` is removed: it held the template's empty `__all__` and no enum,
  since the package generates no enum from its nineteen packaged lists.
  `xippios.eurostat._client` no longer declares `API_KEY_ENV`, a key variable that no code
  read, and `ENV_VARS` names none. (https://github.com/xippios/sdk-template/issues/300)
