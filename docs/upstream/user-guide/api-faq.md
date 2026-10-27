# API - Frequently asked questions

This section will be enriched on base of received questions, to be submitted through the Eurostat user support.

[Contact Eurostat user support](https://ec.europa.eu/eurostat/web/main/contact-us/user-support)

## Guides

Some information would not fit in the short Q&A section below, a dedicated page is proposed for the following topics:

- [API - Examples - periodic data download](https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-faq/examples)
- [API - FAQ - TSV data format](https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-faq/tsv-format)
- [API - FAQ - Usage in Excel Power Query](https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-faq/excel-power-query)

## Questions and answers

### How can I get information about the structural metadata?

The API provides every available information about the structural metadata. More information is available on [this page](https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-detailed-guidelines/sdmx2-1/structure-queries).

### Does the API provide versioned information?

The API provides:

Following structural artefacts are versioned and final following SDMX specification: code lists, concept schemes and data structure definitions: each version of each item is available and can be downloaded via the API.

For statistical dataset, corresponding SDMX artefacts are non-final and always with version=1.0.

There is no history available on data.

### Why does SDMX API reject my data query with 400 error code

HTTP 400 Bad Request is a generic error status to inform that the requested URL could not be processed by the server. It can happens in several cases

#### Case 1 : Invalid request

Network appliance receiving HTTP requests may reject them with the following information

![](https://ec.europa.eu/eurostat/documents/19009692/20069370/invalid-request.png/83827aaa-a116-ce69-3bd9-e9c92639ccd8?t=1727442375747)

Main case is when a URL would exceed the character size limit supported by the network appliance.

A simple example is when building an explicit query for a NUTS3 regional datas for API statistics, the URL would contains a lot of &geo= parameters

![](https://ec.europa.eu/eurostat/documents/19009692/20069370/query.png/52ecea75-9597-5b22-2573-ed5ff23fd718?t=1727444901047)

In most case, it would be recommended to leave such dimension unfiltered in the query URL and filter the received data or use the dedicated geoLevel parameter in this particular example:

<https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/DEMO_R_GIND3?format=JSON&lang=en&freq=A&indic_de=JAN&time=2018&time=2019&time=2020&time=2021&time=2022&geoLevel=nuts3>

<https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/DEMO_R_GIND3?format=JSON&lang=en&freq=A&indic_de=JAN&time=2018&time=2019&time=2020&time=2021&time=2022>

#### Case 2: Invalid query

SDMX API REST URLs are validated that they contain dimension codes and position codes actually declared in the dataset definition. In other words validation ensures that the codes present in the query are present in the SDMX Constraint of the dataset.

Example REST URL:

<https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/ISOC_CI_ID_H/A.H_IPC.PC_HH.TOTAL.EU27>

This URL would not pass validation and an HTTP 400 Bad Request response would be issued with following content

```xml
<S:Fault xmlns:S="http://schemas.xmlsoap.org/soap/envelope/">
    <faultcode>150</faultcode>
    <faultstring>INVALID_QUERY_DIMENSION_VALUE: Query is invalid as per its structure's definition. The following values for dimension are not allowed: GEO=EU27.</faultstring>
</S:Fault>
```

This error message is reporting that **EU27** cannot be found in the list of position actually present in the GEO dimension of the dataset.

The valid code to use in this case is **EU27_2020**

The SDMX Constraint can be retrieved to allow client side query validation. It can be retrieved from the SDMX API as follow :

<https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/contentconstraint/ESTAT/ISOC_CI_ID_H>

#### Why does TSV data file contains extra whitespace ?

As dataset may contains attributes flags attached to an observation value, the TSV format is adding them next to the value separated by.

In case of data results without such flags, these extra spaces could look like as unnecessary but they always be present to ensure format consistency.

In below example, space are visible as a dot and tabulation as an arrow.

![](https://ec.europa.eu/eurostat/documents/19009692/20069370/tsv-file.png/11e8a538-01ca-e522-de72-78a20c4ee752?t=1727447479967)

The space is present in all data columns to ensure generic processing, for example separating by both tabulation and whitespace will result in having the attributes in an extra column next to the value.

Please consult the format description page for more details : [API - FAQ - TSV data format](https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-faq/tsv-format)

#### Why does SDMX API reject my data query with lastNObservations with EXTRACTION_TOO_BIG error code

To better understand why this specific query is rejected as being too costly to perform is because the **lastNObservation** cannot help in reducing the overall cost of the data extraction.
From SDMX API definition, lastNObservation means "The maximum number of observations to be returned **for each of the matching series**, counting back from the most recent observation."
as this is the only parameter, no data filtering is done, so **the full data need to be extracted** and then scanned to confirm a observation value is available or not.

One possibility to actually reduce the data extraction is to express a filter on the time dimension to only search in recent year values
<https://ec.europa.eu/eurostat/api/dissemination/sdmx/3.0/data/dataflow/ESTAT/STS_INPR_M/1.0?compress=false&format=TSV&lastNObservations=1&c[TIME_PERIOD]=ge:2024>

Please note that first call to this may receive an asynchronous statement, waiting a few minutes and recalling the same URL should be enough under normal operation of the API.

We can see in the resulting data several time columns (2024-3 being the most recent one) that where scanned for data.

![](https://ec.europa.eu/eurostat/documents/19009692/20069370/lastnobservation.png/6d1ba1ed-6d50-be21-fdfc-affb81bbe6c3?t=1727680873202)If the user is in fact interested only in the most recent time position, sadly there is no direct SDMX data query to represent this.
It must be done in 2 different queries :

1. retrieve the data constraints of the dataset: <https://ec.europa.eu/eurostat/api/dissemination/sdmx/3.0/structure/dataconstraint/ESTAT/STS_INPR_M?compress=false>
2. lookup the last value of the TIME_PERIOD dimension and use it in the data query below
3. retrieve data for this specific time position <https://ec.europa.eu/eurostat/api/dissemination/sdmx/3.0/data/dataflow/ESTAT/STS_INPR_M/1.0?compress=false&format=TSV&c[TIME_PERIOD]=eq:2024-03>
