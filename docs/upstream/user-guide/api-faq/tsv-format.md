# API - FAQ - TSV data format

## Overview

The TSV format available in the SDMX 2.1 and 3.0 APIs is a format specific to Eurostat.

This format originates from the tab-delimited data files provided by Eurostat via Bulk Download Facility.

While usage of standard format issued from SDMX standard is recommended, this format is kept for compatibility with existing clients and ease of use.

## Details on the format

TSV API responses are flat files that include a ‘tab delimited’ time-series in each line
instead of one value per line/record as in SDMX-CSV.

- Contains one Header line then one or more Data lines
- The columns (or fields or cells) of the records are ‘tab delimited’.
- Time series lines are sorted in ascending alphabetical order on their seriesKeys identifier, i.e on the first column,
- ATTENTION: time-series for which there is "no data available" at all are NOT present in the tsv file

**In below examples,**

- orange dot represents a space
- orange arrow represents a tabulation

### Header line

First line of the TSV file, for example from the header line of <https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/ei_isin_m?format=TSV>

![](https://ec.europa.eu/eurostat/documents/19009692/20115120/image-2023-11-14_15-49-59.png/9238b64c-456f-b947-9fda-d6a8b55e2e7f?t=1728053980935)

#### SeriesKeys column (first column)

sequence of dimension codes separated by a comma providing the format of the time-series **seriesKeys** **identifier** used in data lines followed by a back slash and the time dimension code that is always TIME_PERIOD in SDMX standard ***\\TIME_PERIOD***

`freq,unit,s_adj,nace_r2,indic,geo\TIME_PERIOD`

For each of these dimension code there is a corresponding SDMX codelist **with the same code** available also in TSV format

| Dimension code | Corresponding codelist download link in TSV |
| --- | --- |
| freq | <https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/codelist/ESTAT/freq?format=TSV> |
| unit | <https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/codelist/ESTAT/unit?format=TSV> |
| s_adj | <https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/codelist/ESTAT/s_adj?format=TSV> |
| nace_r2 | <https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/codelist/ESTAT/nace_r2?format=TSV> |
| indic | <https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/codelist/ESTAT/indic?format=TSV> |
| geo | <https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/codelist/ESTAT/geo?format=TSV> |

#### Observation column(s)

In the header line, other columns contains the observation time period

Observation columns are sorted in ascending order. The notation follows SDMX and ISO8601 standards characters in bold are fixed)

There is a trailing space in each column that correspond to the separator between observation value and abservation statuses, it is important to align columns when considering both tab and space as column separator

| Period | Format | Example |
| --- | --- | --- |
| year | YYYY | 2015 |
| semester | YYYY**-S**N | 2015**-S**1 |
| quarter | YYYY**-Q**N | 2015**-Q**4 |
| month | YYYY**-**MM | 2015**-**02 |
| week | YYYY**-W**NN | 2015**-W**01 |
| day | YYYY**-**MM**-**DD | 2015**-**12**-**31 |

### Data line(s)

#### SeriesKeys column (first column)

sequence of dimension codes separated by a comma providing the **seriesKeys** **identifier** for the data time series for the current line.

`M,I2015,CA,B,IS-IP,AT`

This information uniquely identify the time-series of the dataset.

| Dimension code | Position code | Position label |
| --- | --- | --- |
| freq | M | Monthly |
| unit | I2015 | Index, 2015=100 |
| s_adj | CA | Calendar adjusted data, not seasonally adjusted data |
| nace_r2 | B | Mining and quarrying |
| indic | IS-IP | Production index |
| geo | AT | Austria |

#### Observation column(s)

All other columns but the first line represent the sequence of observation value and statuses corresponding to the time period in the header line.

When an observation value is not available a special character colon is displayed instead **":"**

**Where available, status flags are attached to values. The separator used between values and statuses is a simple space.**

When an observation have not statuses, there remains a trailing space in the column to keep columns aligned when considering both tab and space as column separator

Following excerpt show two time-series for which there are data since the first available time position

![](https://ec.europa.eu/eurostat/documents/19009692/20115120/image-2023-11-28_11-45-31.png/9cf9b904-48ee-15a7-3468-1e570a624e80?t=1728053981172)

For Ireland (IE) there are observation values without statuses, so the extra space character.

For Netherlands (NL) the observalue values have a "provisional" status so the **p** status flag is attached to the value, separated by a space

### Special case : datasets with multiple time frequencies

When a dataset contains time series of different frequencies, the data file contains one row for each frequency respecting the general rule of alphabetical order.

The columns will be ordered according to the relevant frequency code alphabetical order, so for a same year and a dataset with Annual, Quarterly and Monthly data, the order will be

**A**nnual, then **M**onthly and finally **Q**uarterly observations, please see below example come from [AVIA_GOR_ME](https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/AVIA_GOR_ME?format=TSV) dataset

<table>
<thead>
<tr>
<th>freq</th>
<th>unit</th>
<th>tra_meas</th>
<th>airp_pr\TIME_PERIOD</th>
<th>...</th>
<th>2019</th>
<th>2019-01</th>
<th>2019-02</th>
<th>...</th>
<th>2019-11</th>
<th>2019-12</th>
<th>2019-Q1</th>
<th>2019-Q2</th>
<th>2019-Q3</th>
<th>2019-Q4</th>
<th>...</th>
</tr>
</thead>
<tbody>
<tr>
<td>A</td>
<td>T</td>
<td>FRM_BRD</td>
<td>ME_LYPG_AT_LOWW</td>
<td>...</td>
<td>70.6</td>
<td>:</td>
<td>:</td>
<td>...</td>
<td>:</td>
<td>:</td>
<td>:</td>
<td>:</td>
<td>:</td>
<td>:</td>
<td>...</td>
</tr>
<tr>
<td colspan="16">[ ... ]</td>
</tr>
<tr>
<td>M</td>
<td>T</td>
<td>FRM_BRD</td>
<td>ME_LYPG_AT_LOWW</td>
<td>...</td>
<td>:</td>
<td>5.1</td>
<td>4.4</td>
<td>...</td>
<td>6.7</td>
<td>5.8</td>
<td>:</td>
<td>:</td>
<td>:</td>
<td>:</td>
<td>...</td>
</tr>
<tr>
<td colspan="16">[ ... ]</td>
</tr>
<tr>
<td>Q</td>
<td>T</td>
<td>FRM_BRD</td>
<td>ME_LYPG_AT_LOWW</td>
<td>...</td>
<td>:</td>
<td>:</td>
<td>:</td>
<td>...</td>
<td>:</td>
<td>:</td>
<td>14.7</td>
<td>15.2</td>
<td>19.2</td>
<td>21.4</td>
<td>...</td>
</tr>
</tbody>
</table>

Due to this format, this situation must extend the meaning of the ':' special character from "not available" to "not applicable" as it is logically that there cannot be data for 2019 on the **monthly** time-serie.
