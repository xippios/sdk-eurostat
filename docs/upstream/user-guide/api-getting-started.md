# API - Getting started

## Getting started

Focus is made in the APIs on the general delivery of statistical data and related metadata starting **from a product online data code** found either in Data Browser, in publications or Eurostat website.

Additionally, data discovery is supported via

- the listing of the data products **in SDMX APIs** as SDMX dataflows
- the Eurostat Table of Contents XML or as RDF document expressed in DCAT Application Profile **in CATALOGUE API**.

## APIs documentation

The following REST APIs are available:

- STATISTICS, which ensure business continuity with previous Eurostat JSON web service;
- SDMX 3.0, used for metadata and data queries following SDMX 3.0 specification;
- SDMX 2.1, used for metadata and data queries following SDMX 2.1 specification;
- CATALOGUE, which is used for dataset discovery;

### STATISTICS API

Statistics API is a REST web service for data query focused on supporting Eurostat Visualisations Tools and open for public use.

This web service:

- **provides data in JSON-stat 2.0 format**;
- supports only REpresentation State Transfer (REST) protocol;
- **supports Cross-Origin Resource Sharing (CORS)**
- delivers responses in English, French or German.

[API - Getting started with statistics API](https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-getting-started)

[API - Detailed guidelines - API Statistics](https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-detailed-guidelines)

### SDMX 3.0 API

The SDMX 3.0 API is a programmatic access to [metadata](https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-detailed-guidelines/sdmx3-0/structure-queries) and [data](https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-detailed-guidelines/sdmx3-0/data-query), in line with [SDMX technical specifications for version 3.0](https://sdmx.org/?page_id=5008), with the possibility to:

- Get a complete list of publicly available datasets
- Get the complete structure definition for a specific dataset
- Download a dataset in full, or a subset of a specific dataset. This supports customised requests for data.

Processing time and the data response depend on the query and the target dataset size:

- A request for a small subset of a dataset could result in a response with few kilobytes, and can be returned within seconds
- A request for full dataset could result in a response of up to several megabytes, and can be returned after several minutes. When submitting this kind of request, asynchronous requests (described hereafter), may be useful.

This API supports returning data in formats other than SDMX-ML 3.0:

- SDMX-CSV 2.0
- JSON-stat 2.0
- TSV
- SDMX-ML 2.1 (for usage of new API query with content backward compatibility)

[API - Getting started with SDMX3.0 API](https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-getting-started/api)

[API - Detailed guidelines - SDMX3.0 API](https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-detailed-guidelines/sdmx3-0)

### SDMX 2.1 API

The SDMX 2.1 API is a programmatic access to [metadata](https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-detailed-guidelines/sdmx2-1/structure-queries) and [data](https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-detailed-guidelines/sdmx2-1/data-query), in line with [SDMX technical specifications for version 2.1](https://sdmx.org/?page_id=5008), with the possibility to:

- Get a complete list of publicly available datasets
- Get the complete structure definition for a specific dataset
- Download a dataset in full, or a subset of a specific dataset. This supports customized requests for data.

Processing time and the data response depend on the query, i.e.

- A request for a small subset of a dataset could result in a response with few kilobytes, and can be returned within seconds
- A request for full dataset could result in a response of up to several megabytes, and can be returned after several minutes. When submitting this kind of request, asynchronous requests (described hereafter), may be useful.

**This API supports returning data in formats other than SDMX-ML 2.1:**

- SDMX-CSV 1.0
- JSON-stat 2.0
- TSV

[API - Getting started with SDMX2.1 API](https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-getting-started/sdmx2.1)

[API - Detailed guidelines - SDMX2.1 API](https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-detailed-guidelines/sdmx2-1)

### CATALOGUE API

The CATALOGUE API serves dataset discovery purposes via programmatic access to catalogue of datasets.

[API - Getting started with catalogue API](https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-getting-started/catalogue-api)

[API - Detailed guidelines - Catalogue API](https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-detailed-guidelines/catalogue-api)

## Additional information

### Parameter \<api_base_uri> in all operations descriptions

This documentation mentions a parameter \<api_base_uri> in the operation description for each REST request. This parameter is specific to each organization exposing the API.

The allowed values for parameter \<api_base_uri> are:

| Agency | \<api_base_uri> value to be used |
| --- | --- |
| Eurostat | ec.europa.eu/eurostat/api/dissemination |
| DG EMPL | webgate.ec.europa.eu/empl/redisstat/api/dissemination |
| DG GROW | webgate.ec.europa.eu/grow/redisstat/api/dissemination |
| DG TAXUD | webgate.ec.europa.eu/taxation_customs/redisstat/api/dissemination |
