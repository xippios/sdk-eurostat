# API - Detailed guidelines - SDMX2.1 API - data query

## Overview

Data queries allow **retrieving statistical data**. Entire datasets, individual observations, or anything in between, can be retrieved using filters on dimensions (including time).

The data retrieved can be retrieved in a variety of formats (JSON, XML, CSV, etc.).

Depending on the request, a data query can result in a (potentially very) large response in which case data is delivered asynchronously. For more information please read the page [‘API - Detailed guidelines - Asynchronous API’](https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-detailed-guidelines/asynchronous-api)

It is important to remember that only the last version of each statistical observation is made available in the system. When a statistical observation is being updated, the previous value of the observation is lost and cannot be returned.

## Query URL syntax

Generic SDMX2.1 syntax is the following

`protocol://ws-entry-point/data/{resourceID}/{key}?{format}&{startPeriod}&{endPeriod}&{firstNObservations}&{lastNObservations}&{detail}&{compressed}&{returnData}`

| Parameter | Description |
| --- | --- |
| resourceID | The id of the artefact for which data have been reported. |
| key | The combination of dimension values identifying the slice of the cube for which data should be returned. Wildcarding is supported via entering no value. For example, if the following key identifies the bilateral exchange rates for the daily US dollar exchange rate against the euro, D.USD.EUR.SP00.A, then the following key can be used to retrieve the data for all currencies against the euro: D..EUR.SP00.A. |
| format | format=\<value><br>To get responses in other format than SDMX-ML 2.1 Generic, which is supported by default.<br>Supported values are:<br>**SDMX_2.1_STRUCTURED** for SDMX-ML 2.1 Structure Specific Data<br>**SDMX-CSV** for SDMX-CSV 1.0 flat format<br>**JSON** for JSON-stat<br>**TSV** for Tab Separated Value |
| startPeriod<br>endPeriod | **Data filtering on time**<br>startPeriod=\<value>&endPeriod=\<value> |
| firstNObservations | The maximum number of observations to be returned for each of the matching series, starting from the first observation |
| lastNObservations | The maximum number of observations to be returned for each of the matching series, counting back from the most recent observation |
| detail | Supported values are:<br>**dataonly** for each series, only the observations are returned, no attributes are returned<br>**serieskeysonly** for each series, only the series key are returned, no data or attributes are returned<br>**nodata** for each series, only the series level attributes are returned |
| compressed | To get responses in .gz compressed format |
| returnData | Only available for the TSV and SDMX-CSV formats.<br>Supported values are:<br>ALL All time-series are returned in the output, including the ones having no data / flag.<br>DATA_ONLY (default value) Only the time-series for which data or flag exists are returned in the output. |

### Key parameter - Data filtering on dimension

The key parameter defines values of the dimensions **in the order of structure**.

The **key** is constructed as a dot ('.') separated list of dimension filtered values.

To build the key for a selected dataflow (taking NAMA_10_GDP as example below), you must know beforehand:

- the structure and order of the dimensions as described in the DSD

href="https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/datastructure/ESTAT/NAMA_10_GDP/latest">https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/datastructure/ESTAT/NAMA_10_GDP/latest

- the available positions in the dataset as described in the Content Constraint

href="https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/contentconstraint/ESTAT/NAMA_10_GDP/latest">https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/contentconstraint/ESTAT/NAMA_10_GDP/latest

- If needed you can download the codelist definition referenced for each DSD dimension

href="https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/codelist/ESTAT/FREQ/latest">https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/codelist/ESTAT/FREQ/latest

href="https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/codelist/ESTAT/UNIT/latest">https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/codelist/ESTAT/UNIT/latest

href="https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/codelist/ESTAT/NA_ITEM/latest">https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/codelist/ESTAT/NA_ITEM/latest

href="https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/codelist/ESTAT/GEO/latest">https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/codelist/ESTAT/GEO/latest

- Alternatively it could help to work on filtered code lists that can be retrieved with the special query:

href="https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/dataflow/ESTAT/NAMA_10_GDP/1.0?references=descendants&detail=referencepartial">https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/dataflow/ESTAT/NAMA_10_GDP/1.0?references=descendants&detail=referencepartial

In NAMA_10_GDP example, the structure of seriesKey is **[FREQ].[UNIT].[NA_ITEM].[GEO]**

An example seriesKey would be **A.CP_MEUR.B1GQ.LU**, where:

| Position | 1 | 2 | 3 | 4 |
| --- | --- | --- | --- | --- |
| Dimension | FREQ | UNIT | NA_ITEM | GEO |
| Key value | A | CP_MEUR | B1GQ | LU |
| Meaning | Data aggregated annually | Current prices, million euro | Gross domestic product at market prices | Luxembourg |

Dimensions which should not be filtered are left empty in the query. Extending above example all NA_ITEM for Luxembourg could be retrieved with key **A.CP_MEUR..LU**

Explicit listing of values for a dimension is done using the plus '+' character. For example, retrieving value for a Luxembourg and Belgium would be done with key = A.CP_MEUR.B1GQ.**BE+LU**

**Examples**
<https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/NAMA_10_GDP/A.CP_MEUR.B1GQ.LU>
<https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/NAMA_10_GDP/A.CP_MEUR..LU>
<https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/NAMA_10_GDP/A.CP_MEUR.B1GQ.BE+LU>

### Detail parameter - examples

ENV_WAT_RES is a dataset that define series attributes to hold the LTAA value and flags, that is a good example for the detail parameter values.

#### Request FULL

`protocol://ws-entry-point/sdmx/2.1/data/ENV_WAT_RES?format=SDMX-CSV&detail=full`

All data is returned (default)

`DATAFLOW,LAST UPDATE,freq,wat_proc,unit,geo,TIME_PERIOD,OBS_VALUE,OBS_FLAG,LTAA_FLAG,LTAA`

`ESTAT:ENV_WAT_RES(1.0),10/08/22 23:00:00,A,AQUI,M3_HAB,AL,2013,124.17,e,,`

`ESTAT:ENV_WAT_RES(1.0),10/08/22 23:00:00,A,AQUI,M3_HAB,AL,2014,128.81,e,,`

`ESTAT:ENV_WAT_RES(1.0),10/08/22 23:00:00,A,AQUI,M3_HAB,AL,2015,135.02,,,`

`ESTAT:ENV_WAT_RES(1.0),10/08/22 23:00:00,A,AQUI,M3_HAB,AL,2016,134.86,e,,`

`ESTAT:ENV_WAT_RES(1.0),10/08/22 23:00:00,A,AQUI,M3_HAB,AL,2017,111.71,e,,`

`ESTAT:ENV_WAT_RES(1.0),10/08/22 23:00:00,A,AQUI,M3_HAB,AL,2018,120.99,e,,`

`ESTAT:ENV_WAT_RES(1.0),10/08/22 23:00:00,A,AQUI,M3_HAB,AL,2019,105.63,e,,`

`ESTAT:ENV_WAT_RES(1.0),10/08/22 23:00:00,A,AQUI,M3_HAB,AL,2020,118.47,e,,`

`ESTAT:ENV_WAT_RES(1.0),10/08/22 23:00:00,A,AQUI,M3_HAB,BG,2012,742.00,,,715.53`

`ESTAT:ENV_WAT_RES(1.0),10/08/22 23:00:00,A,AQUI,M3_HAB,BG,2013,746.17,,,715.53`

`ESTAT:ENV_WAT_RES(1.0),10/08/22 23:00:00,A,AQUI,M3_HAB,BG,2014,764.96,,,715.53`

`ESTAT:ENV_WAT_RES(1.0),10/08/22 23:00:00,A,AQUI,M3_HAB,BG,2015,772.22,,,715.53`

`ESTAT:ENV_WAT_RES(1.0),10/08/22 23:00:00,A,AQUI,M3_HAB,BG,2016,764.75,,,715.53`

`ESTAT:ENV_WAT_RES(1.0),10/08/22 23:00:00,A,AQUI,M3_HAB,BG,2017,826.60,,,715.53`

`[...]`

#### Request DataOnly

`protocol://ws-entry-point/sdmx/2.1/data/ENV_WAT_RES?format=SDMX-CSV&detail=dataonly`

The observations (OBS_VAL only) are returned for each series, but not the attributes

`DATAFLOW,LAST UPDATE,freq,wat_proc,unit,geo,TIME_PERIOD,OBS_VALUE`

`ESTAT:ENV_WAT_RES(1.0),10/08/22 23:00:00,A,AQUI,M3_HAB,AL,2013,124.17`

`ESTAT:ENV_WAT_RES(1.0),10/08/22 23:00:00,A,AQUI,M3_HAB,AL,2014,128.81`

`ESTAT:ENV_WAT_RES(1.0),10/08/22 23:00:00,A,AQUI,M3_HAB,AL,2015,135.02`

`ESTAT:ENV_WAT_RES(1.0),10/08/22 23:00:00,A,AQUI,M3_HAB,AL,2016,134.86`

`ESTAT:ENV_WAT_RES(1.0),10/08/22 23:00:00,A,AQUI,M3_HAB,AL,2017,111.71`

`ESTAT:ENV_WAT_RES(1.0),10/08/22 23:00:00,A,AQUI,M3_HAB,AL,2018,120.99`

`ESTAT:ENV_WAT_RES(1.0),10/08/22 23:00:00,A,AQUI,M3_HAB,AL,2019,105.63`

`ESTAT:ENV_WAT_RES(1.0),10/08/22 23:00:00,A,AQUI,M3_HAB,AL,2020,118.47`

`ESTAT:ENV_WAT_RES(1.0),10/08/22 23:00:00,A,AQUI,M3_HAB,BG,2012,742.00`

`ESTAT:ENV_WAT_RES(1.0),10/08/22 23:00:00,A,AQUI,M3_HAB,BG,2013,746.17`

`ESTAT:ENV_WAT_RES(1.0),10/08/22 23:00:00,A,AQUI,M3_HAB,BG,2014,764.96`

`ESTAT:ENV_WAT_RES(1.0),10/08/22 23:00:00,A,AQUI,M3_HAB,BG,2015,772.22`

`ESTAT:ENV_WAT_RES(1.0),10/08/22 23:00:00,A,AQUI,M3_HAB,BG,2016,764.75`

`ESTAT:ENV_WAT_RES(1.0),10/08/22 23:00:00,A,AQUI,M3_HAB,BG,2017,826.60`

`ESTAT:ENV_WAT_RES(1.0),10/08/22 23:00:00,A,AQUI,M3_HAB,CH,2000,2572.29`

`[...]`

#### Request NoData

`protocol://ws-entry-point/sdmx/2.1/data/ENV_WAT_RES?format=SDMX-CSV&detail=nodata`

Only the series level attributes are returned for each series

`DATAFLOW,LAST UPDATE,freq,wat_proc,unit,geo,LTAA_FLAG,LTAA`

`ESTAT:ENV_WAT_RES(1.0),10/08/22 23:00:00,A,AQUI,M3_HAB,AL,,`

`ESTAT:ENV_WAT_RES(1.0),10/08/22 23:00:00,A,AQUI,M3_HAB,BG,,715.53`

`ESTAT:ENV_WAT_RES(1.0),10/08/22 23:00:00,A,AQUI,M3_HAB,CH,,2531.09`

`ESTAT:ENV_WAT_RES(1.0),10/08/22 23:00:00,A,AQUI,M3_HAB,CY,e,314.43`

`ESTAT:ENV_WAT_RES(1.0),10/08/22 23:00:00,A,AQUI,M3_HAB,CZ,,527.25`

`ESTAT:ENV_WAT_RES(1.0),10/08/22 23:00:00,A,AQUI,M3_HAB,DE,,583.86`

`ESTAT:ENV_WAT_RES(1.0),10/08/22 23:00:00,A,AQUI,M3_HAB,DK,,885.83`

`ESTAT:ENV_WAT_RES(1.0),10/08/22 23:00:00,A,AQUI,M3_HAB,EE,,2077.19`

`ESTAT:ENV_WAT_RES(1.0),10/08/22 23:00:00,A,AQUI,M3_HAB,ES,,1126.01`

`ESTAT:ENV_WAT_RES(1.0),10/08/22 23:00:00,A,AQUI,M3_HAB,FI,,`

#### Request SeriesKeysOnly

`protocol://ws-entry-point/sdmx/2.1/data/ENV_WAT_RES?`**detail=seriesKeysOnly**

No data or attributes are returned for each series, only the series key

`DATAFLOW,LAST UPDATE,freq,wat_proc,unit,geo`

`ESTAT:ENV_WAT_RES(1.0),10/08/22 23:00:00,A,AQUI,M3_HAB,AL`

`ESTAT:ENV_WAT_RES(1.0),10/08/22 23:00:00,A,AQUI,M3_HAB,BG`

`ESTAT:ENV_WAT_RES(1.0),10/08/22 23:00:00,A,AQUI,M3_HAB,CH`

`ESTAT:ENV_WAT_RES(1.0),10/08/22 23:00:00,A,AQUI,M3_HAB,CY`

`ESTAT:ENV_WAT_RES(1.0),10/08/22 23:00:00,A,AQUI,M3_HAB,CZ`

`ESTAT:ENV_WAT_RES(1.0),10/08/22 23:00:00,A,AQUI,M3_HAB,DE`

`ESTAT:ENV_WAT_RES(1.0),10/08/22 23:00:00,A,AQUI,M3_HAB,DK`

`ESTAT:ENV_WAT_RES(1.0),10/08/22 23:00:00,A,AQUI,M3_HAB,EE`

`ESTAT:ENV_WAT_RES(1.0),10/08/22 23:00:00,A,AQUI,M3_HAB,ES`

`ESTAT:ENV_WAT_RES(1.0),10/08/22 23:00:00,A,AQUI,M3_HAB,FI`

`ESTAT:ENV_WAT_RES(1.0),10/08/22 23:00:00,A,AQUI,M3_HAB,FR`

`ESTAT:ENV_WAT_RES(1.0),10/08/22 23:00:00,A,AQUI,M3_HAB,HU`

`ESTAT:ENV_WAT_RES(1.0),10/08/22 23:00:00,A,AQUI,M3_HAB,IE`

`ESTAT:ENV_WAT_RES(1.0),10/08/22 23:00:00,A,AQUI,M3_HAB,LU`

`ESTAT:ENV_WAT_RES(1.0),10/08/22 23:00:00,A,AQUI,M3_HAB,LV`

`ESTAT:ENV_WAT_RES(1.0),10/08/22 23:00:00,A,AQUI,M3_HAB,MT`

#### Return data parameter

In SDMX, the dataset boundaries can be expressed as ContentConstraint describing the available positions for each dimension. It means that a position is used at least once in a data time-series.

This listing of positions for each dimension is used as the basis when building a data result for a received query.

For example, supposing a dataset exposing yearly since 2000 where data for Croatia is available only since 2004. The following query in TSV:

GEO = "Croatia" And TIME_PERIOD >= 1990 and TIME_PERIOD <= 2006

is returning a TSV file containing the (empty) columns 2000, 2001, 2002 and 2003 in addition to the columns 2004, 2005 and 2006.

Also, to be noted that in some specific filtered results some positions could be present while no actual data being present for them.

This information is encoded in the JSONSTAT format extension "positions-with-no-data". To retake the above example, the positions 2000, 2001, 2002 and 2003 for the TIME_PERIOD dimension are represented as positions which did not match any data.

This is enough to understand the boundaries defined for cube-oriented JSONSTAT format, however TSV as a time-series oriented format has the specific feature to not include lines for non-existing time-series.

For example, the following query

<https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/DEMO_GIND/A.NATT+POPTRT.FR+FX/?format=TSV&startPeriod=2012&endPeriod=2021>

Returns:

![](https://ec.europa.eu/eurostat/documents/19009692/21149086/return_data_parameter.png/a89783f2-d0c4-68b8-2f9b-30bf3a03c5c7?t=1741014533169)

Only the existing time-series are actually present in the output thus this TSV result contains only 3 lines because the time-series DEMO_GIND/A.POPTRT.FX does not exist.

This response is the default one to reduce the response size and be more accurate. It is expected from API client to be in power to process such results in general as it is how Eurostat is offering its content via the heavily used Bulk Download facilities.
In case this behavior proves itself blocking to some client applications, an extra parameter &returnData=ALL could be used to let the TSV contains these expected "missing" lines.
This option is also available for the SDMX-CSV format.
