# API - Getting started with statistics API

## Introduction

Statistics API is dedicated to support online visualisation built on Eurostat data thanks to the JSON-stat Toolkit

Pre-requisite

It is strongly recommended to read through the [introduction of the JSON-stat toolkit by its author](https://observablehq.com/@jsonstat/toolkit)

[JSON-stat.org](https://json-stat.org/) **describe the format** that is a simple lightweight JSON dissemination format best suited for data visualisation, mobile apps or open data initiatives.

It is based on a cube model that arises from the evidence that the most common form of data dissemination is the tabular form.

In this cube model, datasets are organised in dimensions. Dimensions are organised in categories.

The particularity of this format is that it intend to provide ready-to-use content for visualisations **from a single API call**

[JSON-stat.com](https://jsonstat.com/) **describe the toolkit(s)** to take full advantages of the JSON-stat format.

For further usage details of the toolkit, please consult the [README of the jsonstat-toolkit](https://www.npmjs.com/package/jsonstat-toolkit)

### The structure of the REST request

The structure to build the REST request is a URL: {host_url}/{service}/{version}/{response_type}/{datasetCode}?{format}&{lang}&{filters}

![](https://ec.europa.eu/eurostat/documents/19009692/20123432/structure-rest-request.png/0164d56d-495a-94ec-638d-1af93be0062d?t=1728057499783)

### Fixed part

| URL part | Example | Comment |
| --- | --- | --- |
| {host_url}/ | https://ec.europa.eu/eurostat/api/<br>dissemination/<br>https://ec.europa.eu/eurostat/api/<br>comext/dissemination (Comext and Prodcom datasets) | Fixed part of the request related to our website |
| {service}/ | statistics/ | Fixed part of the request related to the service |
| {version}/ | 1.0/ | Fixed part of the request related to the version of the service |

### Dynamic part

| URL part | Example | Comment |
| --- | --- | --- |
| {response_type}/ | data/ | Only statistical data are currently returned |
| {datasetCode} | nama_10_gdp | Unique code identifier of the queried data product (either a dataset or a predefined extraction) |
| ?{format} | ?format=JSON | Optional parameter |
| &{lang} | &lang=EN | Optional parameter |
| &{filters} | &time=2019 | Optional parameters |

## Retrieving your first content

Usage of API statistics starts when a dataset is selected for data retrieval, **knowing the dataset online data code**, that can be easily found.

In case the language of the response should be other than English (default language), a specific Query parameter should be added to the URL

`https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/DATASET_CODE?lang=EN`

`DATASET_CODE` in the URL above is a placeholder to be replaced with the dataset code of choice, for example :

`https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/DEMO_R_D3DENS?lang=EN`

### Finding the online data code

#### In Eurostat website navigation tree

The online data code is always next to the dataset title in between parentheses.

![](https://ec.europa.eu/eurostat/documents/19009692/20123432/databrowser+navigation+tree.png/9beb7c45-1c0a-57c1-4f70-f4966b3caa1a?t=1728466191870)

#### In Databrowser navigation tree

The online data code is present below the dataset title in between square brackets.

![](https://ec.europa.eu/eurostat/documents/19009692/20123432/databrowser.png/8c535b50-c9b7-0f5d-21eb-3e760c93c346?t=1728466193016)

#### In Databrowser dataset view

The online data code is present in the information panel about the dataset

![](https://ec.europa.eu/eurostat/documents/19009692/20123432/databrowser+view.png/1fec9963-88ae-1217-5319-eb76daea9b16?t=1728466192689)

Thus on this example, the JSON-stat data for this **DEMO_R_D3DENS** dataset can be retrieved via the URL

`https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/DEMO_R_D3DENS?lang=EN`

### Understanding response metadata

#### Dataset metadata

The first elements of the JSON-stat response are the metadata indicating the type of JSON-stat response, the title of the dataset its source and its last update data.

`"version":"2.0",`

`"class":"dataset",`

`"label":"Population density by NUTS 3 region",`

`"source":"ESTAT",`

`"updated":"2023-04-19T11:00:00+0200",`

#### Dimension metadata : id and size

Then the dimensional structure of the dataset is summarised in two arrays indicating the code and size of each dimension used by the dataset.

We can observe that the **GEO** dimension is quite large (2031 positions) as this dataset is one of Eurostat's **regional** datasets, meaning that it contains statistical data for countries and their subdivision in statistical regions also called NUTS regions ([see more information on NUTS classification](https://ec.europa.eu/eurostat/web/nuts))

`"id" : ["freq","unit","geo","time"],`

`"size": [1,1,2031,33],`

#### Dimension metadata : index and label

The **dimension** object in the response uses dimension code as keys to references objects with its title and for each position (called **category** in JSON-stat) a list of key-value pair of its code and corresponding order and a key-value pair of its code and corresponding label.

`"dimension":{`

`"freq":{`

`"label":"Time frequency",`

`"category":{`

`"index":{`

`"A":0`

`},`

`"label":{`

`"A":"Annual"`

`}`

`}`

`},`

`[...]`

[Preview this data on JSON-stat Explorer](https://jsonstat.com/explorer/#/https%3A%2F%2Fec.europa.eu%2Feurostat%2Fapi%2Fdissemination%2Fstatistics%2F1.0%2Fdata%2FDEMO_R_D3DENS)

( this can take up to one minute to preview the content as the JSON-stat is large, please see below for ways to filter the data)

## Filter data

### Filtering on geoLevel

As the above regional dataset have more than 2000 positions for the **GEO** dimension and is a **regional** dataset, it is interesting to make use of the special filter **geoLevel** to help retrieving content for a specific NUTS level. Following table list the possible value of this filter with example on DEMO_R_D3DENS dataset.

| Value | Description |
| --- | --- |
| aggregate | filter GEO dimension on European aggregates based on a white list (EU15, EU25, EU27_2007, EU27_2019, EU28, EA19, etc)<br>`https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/DEMO_R_D3DENS?lang=EN&geoLevel=aggregate` |
| country | filter GEO dimension on country code (EU Member States, or EFTA, or Candidate Countries or other countries)<br>`https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/DEMO_R_D3DENS?lang=EN&geoLevel=country` |
| nuts1 | filter GEO dimension on level-1 NUTS codes (major socio-economic regions)<br>`https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/DEMO_R_D3DENS?lang=EN&geoLevel=nuts1` |
| nuts2 | filter GEO dimension on level-2 NUTS code (basic regions for the application of regional policies)<br>`https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/DEMO_R_D3DENS?lang=EN&geoLevel=nuts2` |
| nuts3 | filter GEO dimension on level-3 NUTS code (small regions for specific diagnoses)<br>`https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/DEMO_R_D3DENS?lang=EN&geoLevel=nuts3` |

### Filtering on Time

It is possible to restrict the response to specific time values or a range of values.

| Value | Description |
| --- | --- |
| time=YYYY<br>or<br>time_period=YYYY | Filter TIME dimension on one or more specific time values (ie. time=2020)<br>`https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/DEMO_R_D3DENS?lang=EN&geoLevel=country&time=2020`<br>`https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/DEMO_R_D3DENS?lang=EN&geoLevel=country&time=2020&time=2019` |
| sinceTimePeriod=YYYY | Filter TIME dimension on all time values since the specified value included (for example **sinceTimePeriod=2020** means "all time values **since 2020, 2020 included**")<br>`https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/DEMO_R_D3DENS?lang=EN&geoLevel=country&sinceTimePeriod=2020` |
| untilTimePeriod=YYYY | Filter TIME dimension on all time values until the specified value included (for example **untilTimePeriod=2000** means "all time values **until 2000, 2000 included**")<br>`https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/DEMO_R_D3DENS?lang=EN&geoLevel=country&untilTimePeriod=2000` |
| sinceTimePeriod=YYYY<br>AND<br>untilTimePeriod=YYYY | Filter TIME dimension by combining both above filters to define a FROM-TO range<br>(for example sinceTimePeriod=2010&untilTimePeriod=2020 means "all time values **from** 2010 **to** 2020, both ends included")<br>`https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/DEMO_R_D3DENS?lang=EN&geoLevel=country&sinceTimePeriod=2010&untilTimePeriod=2020` |
| lastTimePeriod=N | Filter TIME dimension to always retrieve the N latest positions<br>(for example **lastTimePeriod=1** means 'most recent data" or lastTimePeriod=3 means "last 3 positions")<br>`https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/DEMO_R_D3DENS?lang=EN&geoLevel=country&lastTimePeriod=3` |

### Filtering on other dimensions

Any dimension present in the data product can be used as filter parameter with the syntax **&dimension_code=position_code**.

For example to retrieve only EU27 data for 2022 of our example dataset, the following query should be used

`https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/DEMO_R_D3DENS?lang=EN&geo=EU27_2020&time=2022`

## Need help in building your API query

### From Eurostat query builder

Eurostat website include a [Query Builder](https://ec.europa.eu/eurostat/web/query-builder/tool) on its website.

### From Eurostat Databrowser

The advanced menu for download in DataBrowser is providing a query based on the currently visualised data if you open the menu via Download > Advanced settings and then select the options below (as shown in below screenshot)

File format: JSON-stat (.json)

Data scope: Data on this page only

Endpoint: JSON

![](https://ec.europa.eu/eurostat/documents/19009692/20123432/databrowser+download-1.png/360938fa-f594-8879-c7e4-48809fec3e31?t=1728484315252)

![](https://ec.europa.eu/eurostat/documents/19009692/20123432/databrowser+download-2.png/4cae2e01-e8fc-ea12-e3c6-f0a99d2fb25d?t=1728484315613)

![](https://ec.europa.eu/eurostat/documents/19009692/20123432/databrowser+download-3.png/b6630cbe-cb8c-256d-5d57-7627efab1137?t=1728484315911)

### From JSON-stat community

JSON-stat community is maintaining a [showcase on Eurostat data](https://jsonstat.com/eurostat/) that could also be used as a query builder or a data previewer

### From detailed documentation

Please consult the [detailed documentation](https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-detailed-guidelines/api-statistics) for further details.
