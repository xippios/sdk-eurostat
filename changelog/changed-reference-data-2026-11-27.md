- The packaged reference data are those of 2026-11-27, and `list_codes` no longer lists the
  codes Eurostat removed or renamed: MILKITEM 4.0 drops `FCA`, `PCA` and `PAT` and the units
  in the labels of `FAT`, `USM` and `UWM`, and STRUCPRO 11.0 writes `HLD_THS_NR` and
  `ANI_THS_NR` where 9.0 wrote `HOL` and `ANI`. GEO 29.0 labels `EUR` "Europe*" and lists
  `AM`, `AM_CAP`, `AZ` and `AZ_CAP` after `AD`, and the other fifteen codelists keep their
  records and versions. The table of contents that `list_datasets` reads, `creationDate`
  `20261126T2200`, holds 10,461 leaves, 7 more than on 2026-11-20 (34 added, 27 removed and
  1,066 changed in place, counted leaf by leaf at each code and folder path): its seven new
  codes are house price and rent datasets, `prc_hpi_reg_a` among them, and `road_if_rchtrat`
  is gone.
  (https://github.com/xippios/sdk-eurostat/issues/90)
