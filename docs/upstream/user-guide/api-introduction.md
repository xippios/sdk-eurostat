# API - Introduction

## General introduction

In addition to the [online database](https://ec.europa.eu/eurostat/web/main/data/database), it is possible to access Eurostat's datasets through **REST API web services** described in this online help section.

Eurostat datasets are **updated twice a day, at 11:00 and at 23:00 CET**, if newer data is available or for structural changes, for example for the dimensions in the dataset.

The Eurostat database always contains the **latest version of the datasets**, meaning that there is no versioning or documentation of past versions of the data.

These APIs are free of charge programmatic access to statistical metadata and data.

This is the interface to use for the automation of metadata and data queries or downloads.

### Supported semantic formats

The following formats are used in responses :

- **SDMX-ML**, i.e. Statistical Data and Metadata Exchange ([SDMX](https://sdmx.org/)) messages as XML document
- **SDMX-CSV**, i.e. Statistical Data and Metadata Exchange ([SDMX](https://sdmx.org/)) messages as SDMX-CSV document
- **JSON-stat**, i.e. a [simple lightweight JSON format for data dissemination](https://json-stat.org/)
- **TSV** (Tab-Separated Values) files that include a ‘tab delimited’ sequence of values in each line

### What can you find in this online help section

The API online help consists of the following parts:

- **This introductory page** summarizes basic information about the semantic formats of data and metadata responses.
- [Getting started](https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-getting-started) section provides a brief overview about the different APIs. It is strongly recommended to read this page, before proceeding.
- [Detailed guidelines](https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-detailed-guidelines) section provided complete details for each API.
- A [Frequently asked questions](https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-faq) section.

Important note for "DS- prefixed" / "Comext and PRODCOM" datasets :

For technical reason Comext and Prodcom datasets (DS- prefixed dataset code, i.e DS-057555) are provided on a different API endpoints starting with [https://ec.europa.eu/eurostat/api/**comext**/dissemination](https://ec.europa.eu/eurostat/api/comext/dissemination)

In the URL above, "comext/" is added to differenciate this base URL from the main one: <https://ec.europa.eu/eurostat/api/dissemination>

Please consult [API - Getting started for DS- prefixed datasets from Comext database](https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-getting-started/comext-database) for more details on these datasets.

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

This API supports returning data in formats other than SDMX-ML 2.1:

- SDMX-CSV 1.0
- JSON-stat 2.0
- TSV

[API - Getting started with SDMX2.1 API](https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-getting-started/sdmx2.1)

[API - Detailed guidelines - SDMX2.1 API](https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-detailed-guidelines/sdmx2-1)

### CATALOGUE API

The CATALOGUE API serves dataset discovery purposes via programmatic access to catalogue of datasets.

[API - Getting started with catalogue API](https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-getting-started/catalogue-api)

[API - Detailed guidelines - Catalogue API](https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-detailed-guidelines/catalogue-api)

## APIs endpoints

### Eurostat API endpoints

| API | WADL XML description of a deployed RESTful web application |
| --- | --- |
| **STATISTICS** | **Main endpoint :**<br><https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/statistics-rest.wadl><br>**For "DS- prefixed" / "Comext and PRODCOM" datasets** :<br><https://ec.europa.eu/eurostat/api/comext/dissemination/statistics/1.0/statistics-rest.wadl> |
| **SDMX 2.1**<br>**Agency ID = ESTAT** | **Main endpoint** :<br><https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/sdmx-rest.wadl><br>**For "DS- prefixed" / "Comext and PRODCOM" datasets** :<br>[https://ec.europa.eu/eurostat/api/**comext**/dissemination/sdmx/2.1/sdmx-rest.wadl](https://ec.europa.eu/eurostat/api/comext/dissemination/sdmx/2.1/sdmx-rest.wadl) (Comext and Prodcom datasets) |
| **SDMX 3.0** | **Main endpoint** :<br><https://ec.europa.eu/eurostat/api/dissemination/sdmx/3.0/sdmx-rest.wadl><br>**For "DS- prefixed" / "Comext and PRODCOM" datasets** :<br><https://ec.europa.eu/eurostat/api/comext/dissemination/sdmx/3.0/sdmx-rest.wadl> (Comext and Prodcom datasets) |
| **CATALOGUE** | **Main endpoint** :<br><https://ec.europa.eu/eurostat/api/dissemination/catalogue/catalogue.wadl><br>**For "DS- prefixed" / "Comext and PRODCOM" datasets** :<br><https://ec.europa.eu/eurostat/api/comext/dissemination/catalogue/catalogue.wadl> |
| **ASYNC** | **Main endpoint**:<br><https://ec.europa.eu/eurostat/api/dissemination/1.0/async/async.wadl><br>**For "DS- prefixed" / "Comext and PRODCOM" datasets :**<br>[https://ec.europa.eu/eurostat/api/**comext**/dissemination/1.0/async/async.wadl](https://ec.europa.eu/eurostat/api/comext/dissemination/1.0/async/async.wadl) |
| **Consolidated Open API Specification** | <https://ec.europa.eu/eurostat/api/dissemination/swagger-ui/sdmx-rest.yaml><br>**View online : <https://ec.europa.eu/eurostat/api/dissemination/swagger-ui>** |

### REDISSTAT APIs endpoints

Eurostat is providing other Commission Directorates-General, through the REDISSTAT project, with a reusable solution for statistics dissemination that also exposes API endpoints.

<table>
<thead>
<tr>
<th>Directorate-General</th>
<th>Endpoint</th>
<th>WADL XML description of a deployed RESTful web application</th>
</tr>
</thead>
<tbody>
<tr>
<th rowspan="3"><strong>Economic and Financial Affairs</strong></th>
<td>CATALOGUE</td>
<td><a href="https://webgate.ec.europa.eu/ecfin/redisstat/api/dissemination/catalogue/catalogue.wadl">https://webgate.ec.europa.eu/ecfin/redisstat/api/dissemination/catalogue/catalogue.wadl</a></td>
</tr>
<tr>
<td>SDMX 2.1 <strong>(agency ID = ECFIN)</strong></td>
<td><a href="https://webgate.ec.europa.eu/ecfin/redisstat/api/dissemination/sdmx/2.1/sdmx-rest.wadl">https://webgate.ec.europa.eu/ecfin/redisstat/api/dissemination/sdmx/2.1/sdmx-rest.wadl</a></td>
</tr>
<tr>
<td>ASYNC</td>
<td><a href="https://webgate.ec.europa.eu/ecfin/redisstat/api/dissemination/1.0/async/async.wadl">https://webgate.ec.europa.eu/ecfin/redisstat/api/dissemination/1.0/async/async.wadl</a></td>
</tr>
<tr>
<th rowspan="3"><strong>Employment, Social Affairs and Inclusion</strong></th>
<td>CATALOGUE</td>
<td><a href="https://webgate.ec.europa.eu/empl/redisstat/api/dissemination/catalogue/catalogue.wadl">https://webgate.ec.europa.eu/empl/redisstat/api/dissemination/catalogue/catalogue.wadl</a></td>
</tr>
<tr>
<td>SDMX 2.1 <strong>(agency ID = EMPL)</strong></td>
<td><a href="https://webgate.ec.europa.eu/empl/redisstat/api/dissemination/sdmx/2.1/sdmx-rest.wadl">https://webgate.ec.europa.eu/empl/redisstat/api/dissemination/sdmx/2.1/sdmx-rest.wadl</a></td>
</tr>
<tr>
<td>ASYNC</td>
<td><a href="https://webgate.ec.europa.eu/empl/redisstat/api/dissemination/1.0/async/async.wadl">https://webgate.ec.europa.eu/empl/redisstat/api/dissemination/1.0/async/async.wadl</a></td>
</tr>
<tr>
<th rowspan="3"><strong>Internal Market, Industry, Entrepreneurship and SMEs</strong></th>
<td>CATALOGUE</td>
<td><a href="https://webgate.ec.europa.eu/grow/redisstat/api/dissemination/catalogue/catalogue.wadl">https://webgate.ec.europa.eu/grow/redisstat/api/dissemination/catalogue/catalogue.wadl</a></td>
</tr>
<tr>
<td>SDMX 2.1 <strong>(agency ID = GROW)</strong></td>
<td><a href="https://webgate.ec.europa.eu/grow/redisstat/api/dissemination/sdmx/2.1/sdmx-rest.wadl">https://webgate.ec.europa.eu/grow/redisstat/api/dissemination/sdmx/2.1/sdmx-rest.wadl</a></td>
</tr>
<tr>
<td>ASYNC</td>
<td><a href="https://webgate.ec.europa.eu/grow/redisstat/api/dissemination/1.0/async/async.wadl">https://webgate.ec.europa.eu/grow/redisstat/api/dissemination/1.0/async/async.wadl</a></td>
</tr>
<tr>
<th rowspan="3">Taxation and Customs Union</th>
<td>CATALOGUE</td>
<td><a href="https://webgate.ec.europa.eu/taxation_customs/redisstat/api/dissemination/catalogue/catalogue.wadl">https://webgate.ec.europa.eu/taxation_customs/redisstat/api/dissemination/catalogue/catalogue.wadl</a></td>
</tr>
<tr>
<td>SDMX 2.1 <strong>(agency ID = TAXUD)</strong></td>
<td><a href="https://webgate.ec.europa.eu/taxation_customs/redisstat/api/dissemination/sdmx/2.1/sdmx-rest.wadl">https://webgate.ec.europa.eu/taxation_customs/redisstat/api/dissemination/sdmx/2.1/sdmx-rest.wadl</a></td>
</tr>
<tr>
<td>ASYNC</td>
<td><a href="https://webgate.ec.europa.eu/taxation_customs/redisstat/api/dissemination/1.0/async/async.wadl">https://webgate.ec.europa.eu/taxation_customs/redisstat/api/dissemination/1.0/async/async.wadl</a></td>
</tr>
</tbody>
</table>
