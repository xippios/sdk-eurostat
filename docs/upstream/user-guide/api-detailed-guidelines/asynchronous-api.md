# API - Detailed guidelines - Asynchronous API

## Purpose of ASYNC API

The ASYNC API is a programmatic access for asynchronous responses to large data requests.

For the SDMX APIs, data can be returned either synchronously or asynchronously:

- Synchronously: the data is returned directly in the response to the request. This is the default operation
- Asynchronously: the data is not returned directly in the response. Instead a key is returned in the response which allows to access the data through the async API to check for its availability and eventually retrieve it once available.

The decision whether to deliver the data synchronously or asynchronously is related to factors such as the complexity of the query and the volume of the data (number of rows) to be returned and the fair use of the service (see details in the section below).

In case the requested filtered data would be to important to be prepared, a client error code 413 is returned with a suggestion to apply more filtering to the request.

```xml
<S:Fault xmlns:S="http://schemas.xmlsoap.org/soap/envelope/">
    <faultcode>413</faultcode>
    <faultstring>EXTRACTION_TOO_BIG: The requested extraction is too big, estimated 420709314 rows, max authorised is 5000000, please change your filters to reduce the extraction size</faultstring>
</S:Fault>
```

### More details on asynchronous trigger and thresholds...

When a data request is initiated, the system first checks if the exact same request was already performed previously and if applicable lookup the data directly from an internal cache and return it as a response.

If the data is not cached, the data needs to be extracted and the system estimates the related "extraction cost" in term of potential number of data cells returned.

To compute this cost, the system resolves the **number of positions matched by each dimension filter**.

As an example, if a dataset has 3 dimensions with respectively 5, 10 and 20 positions available for each dimension, the dataset cardinality is 5 x 10 x 20 = 1000 cells.

An extraction request asking for:

- 3 positions for the first dimension
- 2 positions for the second dimension
- no filtering for the third dimension
  will potentially match 3 x 2 x 20 = 120 cells which is also the estimated cost of this request.

The decision whether to deliver the data synchronously or asynchronously is related to factors such as the complexity of the query and the volume of the data (number of cells) to be returned:

- if the data is cached -> the data is returned **synchronously**
- if the data has to be extracted, the "cost" of the request is estimated and:
  - if below 500 000 cells, the data is returned synchronously
  - if between 500 000 cells and 5 000 000 cells, the data is returned **asynchronously** (please see this page on how to deal with such requests: <https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-detailed-guidelines/asynchronous-api>)
  - if above 5 000 000 cells, **a client request error is returned** and more filters need to be added to the extraction query to reduce its estimated cost.

In order to know how many positions are available for the dimensions of a dataset, the API provides **an SDMX endpoint** which returns the SDMX data constraints artefact for the specified dataset.

Taking Eurostat Comext dataset DS-045409 as example, its data constraints can be retrieved using:

<https://ec.europa.eu/eurostat/api/comext/dissemination/sdmx/2.1/contentconstraint/estat/DS-045409>

In this dataset, the dimensions have the following number of positions:

- freq has 2 positions
- reporter has 33 positions
- partner has 282 positions
- product has 40321 positions
- flow has 2 positions
- time_period has 468 positions (36 years and 432 months)
- indicators has 3 positions

The dataset cardinality is then: 2 x 33 x 282 x 40321 x 2 x 468 x 3 = 2 107 276 101 216 cells.

### Examples queries

1 - Query in range for asynchronous extraction

Following query would be considered within limits and processed by the system

<http://ec.europa.eu/eurostat/api/comext/dissemination/sdmx/2.1/data/DS-045409/A.DK.US..1.SUPPLEMENTARY_QUANTITY?format=SDMX_2.1_STRUCTURED>

This query matches the following positions:

- freq -> 1 position ("A")
- reporter 1 position ("DK")
- partner -> 1 position ("US")
- product -> 40321 positions (there is no filter on this dimension)
- flow -> 1 position ("1")
- time_period -> 36 positions (there is no explicit filter on this dimension but the system will only return yearly data)
- indicators -> 1 position ("SUPPLEMENTARY_QUANTITY")

Estimated cost: 1 x 1 x 1 x 40321 x 1 x 36 x 1 = 1 451 556 which is above the synchronous limit but below the maximum extraction limit so this request is treated **asynchronously**.

2 -Query above range for asynchronous extraction

Following query would be considered off limits and not processed by the system

<https://ec.europa.eu/eurostat/api/comext/dissemination/sdmx/2.1/data/DS-045409/A.PT...2.QUANTITY_IN_100KG?format=SDMX_2.1_STRUCTURED1>

This query matches the following positions:

- freq -> 1 position ("A")
- reporter 1 position ("PT")
- partner -> 282 positions (there is no filter on this dimension)
- product -> 40321 positions (there is no filter on this dimension)
- flow -> 1 position ("2")
- time_period -> 36 positions (there is no explicit filter on this dimension but the system will only return yearly data as the frequency requested is annual)
- indicators -> 1 position ("QUANTITY_IN_100KG")

Estimated cost: 1 x 1 x 282 x 40321 x 1 x 36 x 1 = **409 338 792** which is **above the maximum extraction limit** of 5 000 000 cells and an error is returned.

## Fair use of the service

A request for data extraction will be forced to be processed asynchronously based on the evaluation of 3 main criteria:

- the number of concurrent data extraction requests
- the number of requests performed during a period
  - per day
  - during the last 7 days
  - during the last 30 days
- the cumulative "extraction cost" generated during a period
  - per day
  - during the last 7 days
  - during the last 30 days

If one of the above criteria exceeds some thresholds, further data extraction requests will be forced to be processed asynchronously and this as long as the rule is violated.

In order to avoid this, we recommend to:

- trigger 1 extraction request at a time
- in case of use of scripts, don't use parallelisation
- if applicable, get data from the [bulk download](https://ec.europa.eu/eurostat/databrowser/bulk?lang=en)

### How to implement asynchronous requests?

The asynchronous delivery process can be summarized as follows:

1. Step 1 A client issues a request to one of the SDMX data API. The API returns a response indicating asynchronous delivery pattern, with a unique key
2. [Step 2](https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-detailed-guidelines/asynchronous-api#Step2) The client issues to the asynchronous endpoint at regular interval a request with the unique key, to enquire about the readiness of the requested data
3. [Step 3](https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-detailed-guidelines/asynchronous-api#Step3) Once the data is available, the client can request the data for the provided unique key and receive it

### Example

#### Step 1: Initial request

For an initial data request for which asynchronous delivery pattern must be used, the response is similar to following XML:

```xml
<env:Envelope xmlns:env="http://schemas.xmlsoap.org/soap/envelope/">
    <env:Header />
    <env:Body>
        <ns0:syncResponse xmlns:ns0="http://estat.ec.europa.eu/disschain/soap/extraction">
            <processingTime>412</processingTime>
            <queued>
                <id>98de05ea-540a-43d3-903b-7c9e14faf808</id>
                <status>SUBMITTED</status>
            </queued>
        </ns0:syncResponse>
    </env:Body>
</env:Envelope>
```

The \<id> value, 98de05ea-540a-43d3-903b-7c9e14faf808 in this example is the key to use for checking data availability against the asynchronous API.

#### Step 2: Get the current status of the request

The status of a request that is processed asynchronously can be one of the following values:

| Value | Meaning |
| --- | --- |
| **SUBMITTED** | The request is submitted for processing |
| **PROCESSING** | The request is currently being processed |
| **AVAILABLE** | The data is available for download |
| **EXPIRED** | The data is no longer available. This occurs after a few days or when corresponding dataset content was updated. Please restart from Step 1. |
| **UNKNOWN_REQUEST** | In case the key provided cannot be matched to a request |
| ERROR | The request was processed but an unexpected error occurred.<br>Please retry or contact support with id of your request |

The current status of a given request can be obtained via a REST request:

- Request URL: https://\<api_base_uri>/1.0/async/status/\<id>
- Example of URL request: <https://ec.europa.eu/eurostat/api/dissemination/1.0/async/status/98de05ea-540a-43d3-903b-7c9e14faf808>

This request may provide different results, depending on the current status of the request:

- PROCESSING: As long as the request is not processed/finished, the following result will be returned:

```xml
<env:Envelope xmlns:env="http://schemas.xmlsoap.org/soap/envelope/">
    <env:Header />
    <env:Body>
        <ns0:asyncResponse xmlns:ns0="http://estat.ec.europa.eu/disschain/soap/asynchronous"
            xmlns:ns1="http://estat.ec.europa.eu/disschain/asynchronous">
            <ns1:status>
                <ns1:key>98de05ea-540a-43d3-903b-7c9e14faf808</ns1:key>
                <ns1:status>PROCESSING</ns1:status>
            </ns1:status>
        </ns0:asyncResponse>
    </env:Body>
</env:Envelope>
```

- AVAILABLE: The request is processed/finished. When the query is fully executed, the returned status will be AVAILABLE and the following result will be returned:

```xml
<env:Envelope xmlns:env="http://schemas.xmlsoap.org/soap/envelope/">
    <env:Header />
    <env:Body>
        <ns0:asyncResponse xmlns:ns0="http://estat.ec.europa.eu/disschain/soap/asynchronous"
            xmlns:ns1="http://estat.ec.europa.eu/disschain/asynchronous">
            <ns1:status>
                <ns1:key>98de05ea-540a-43d3-903b-7c9e14faf808</ns1:key>
                <ns1:status>AVAILABLE</ns1:status>
            </ns1:status>
        </ns0:asyncResponse>
    </env:Body>
</env:Envelope>
```

#### Step 3: Get the data

When the results are AVAILABLE, it is possible to to download the data. Data can be obtained via a REST request:

- Request URL: https://\<api_base_uri>/1.0/async/data/\<id>
- Example of URL request: <https://ec.europa.eu/eurostat/api/dissemination/1.0/async/data/98de05ea-540a-43d3-903b-7c9e14faf808>

#### Errors returned

NO DATA

In case the query eventually did not contains any statistical value,

```xml
<S:Fault xmlns:S="http://schemas.xmlsoap.org/soap/envelope/">
    <faultcode>100</faultcode>
    <faultstring>NO_RESULTS: The query that has been sent did not return any results.</faultstring>
</S:Fault>
```

DATA NOT YET READY

As long as the data is not ready as informed by the status service call, the returned XML response will be:

```xml
<S:Fault>
    <faultcode>100</faultcode>
    <faultstring>DATA_NOT_YET_AVAILABLE: Requested data is not yet available for download. Check the status of your request.</faultstring>
</S:Fault>
```

INVALID KEY

If the key provided is not valid, the returned SOAP result will be:

```xml
<S:Fault>
    <faultcode>100</faultcode>
    <faultstring>UNKNOWN_REQUEST: Unknown request.</faultstring>
</S:Fault>
```
