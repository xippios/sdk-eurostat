# API - Detailed guidelines - API Statistics

API Statistics is a web service for data query where parameters don’t have to respect a specific order opposed to API SDMX 2.1.

This web service:

- provides data in JSON-stat 2.0 format;
- supports only representation State Transfer (REST) protocol;
- delivers responses in English, French or German.

## The structure of the REST request

The structure to build the REST request is a URL: {host_url}/{service}/{version}/{response_type}/{datasetCode}?{format}&{lang}&{filters}

@A3: Please add an Alt tex for the screenshot below

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

## The parameters defined in the REST request

### The Filter parameters

The Filter parameters defined in the URL are optional. Any dimension present in the data product can be used as filter parameter.

Filters start after the question mark ("?") in the URL. They are separated by an ampersand ("&") if there are several filters.

The structure of a filter parameter is **`DIMENSION_CODE=VALUE`**

- **DIMENSION_CODE**: the code of the dimension used to filter data
  - the dimension code must be present in the data product
  - it is not necessary that the order of the filters corresponds to the order of the dimensions in the data product
- **VALUE**: value of the filter is the position in the dimension i.e.
  - time=2019
  - geo=FR
- **DIMENSION_CODE** and **VALUE** are case-insensitive; they can be written in lower or uppercase in the URL request.
- if several **VALUE** are required for a dimension several filter must be used **`DIMENSION_CODE=VALUE_1&DIMENSION_CODE=VALUE_2`**

### The Time parameter

Both "time" and "time_period" parameters are accepted in the URL to address the TIME_PERIOD dimension.

Below are other Time parameters that can be used:

- untilTimePeriod – the specific TIME_PERIOD value to filter the returned file until this value
- sinceTimePeriod – the specific TIME_PERIOD value to filter the returned file since this value
- lastTimePeriod – a numeric value counting down until the TIME_PERIOD dimension values are included in the returned file

Using more than one Time parameter in the same query is not accepted.

The only exception is using both sinceTimePeriod and untilTimePeriod. This will return the filtered file based on the specific values for the two Time parameters.

### The geoLevel parameter

The geoLevel” parameter allows retrieving a list of "GEO" codes according to their level in the NUTS classification or if they are considered aggretates :

- **geoLevel=aggregate** : European aggregates based on a white list - EU15, EU25, EU27_2007, EU27_2019, EU28, EA19, etc.
- **geoLevel=country** : any country code (EU Member States, or EFTA, or Candidate Countries or other countries) - any 2 digits - i.e. FR
- geoLevel=nuts1: NUTS code level 1: major socio-economic regions - 3 digits - i.e. FR4
- geoLevel=nuts2: NUTS code level 2: basic regions for the application of regional policies - 4 digits - i.e. FR41
- geoLevel=nuts3: NUTS code level 3: small regions for specific diagnoses - 5 digits - i.e. FR413
- geoLevel= city: code at city level - 7 digits - i.e. DE_DEL1 (Karlsruhe)

The "geo" dimension parameter filter and the "geoLevel" parameter are mutually exclusive.

A request must not contain both at the same time. If such a query is sent, the Statistics endpoint should return an error without trying to provide any data:

`{"error":{"status":"400","label":"'geo' parameter and 'geoLevel' parameter cannot be set at the same time. Please choose one or the other."}}`

### The Format and Language parameters

The “format” parameter’s only possible value is "JSON".

The Language parameter (“lang”) can have only three values: “EN”, “FR”, and “DE”. In case the parameter isn’t specified, the default value “EN” is taken.

## Error messages returned in case of invalid queries

| Fault Code | HTTP Status | Description |
| --- | --- | --- |
| 100 No results found | 400 Bad request | The result from the query is empty. |
| 100 No results found | 404 Not Found | The requested resource is not available. |
| 140 Syntax error | 400 Bad request | The query is invalid. |
| 150 Semantic error | 400 Bad request | The request is syntactically correct but fails a semantic validation, business rules. |
| 500 Internal Server error | 500 Internal server error | The web service should return this error code when none of the other error codes better describe the reason for the failure of the service to provide a meaningful response. |
| **Client Errors** | | |
| **Server errors** | | |

## Asynchronous response in case of big extractions

When receiving a request, API can determine if the response can be returned immediately or asynchronously.

In case of an asynchronous response, API will return the following JSON response:

{"warning":{"status":413, "label":"ASYNCHRONOUS_RESPONSE. Your request will be treated asynchronously. Please try again later."}}

API Statistics will not notify the user when the file is ready, the request must be made again to check its status.
