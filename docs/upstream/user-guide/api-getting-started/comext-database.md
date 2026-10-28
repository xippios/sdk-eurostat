# API - Getting started for DS- prefixed datasets from Comext database

## Introduction

For technical reason datasets coming from **Comext reference database** are separated in a dedicated endpoint.

For these datasets, the \<api_base_uri> is [https://ec.europa.eu/eurostat/api/**comext**/dissemination](https://ec.europa.eu/eurostat/api/comext/dissemination)

In the URL above, "comext/" is added to differentiate this base URL from the main one: <https://ec.europa.eu/eurostat/api/dissemination>

### About Comext reference database

Information on [Comext](https://ec.europa.eu/eurostat/web/international-trade-in-goods/database#comext)

**Comext is Eurostat's reference database for detailed statistics on international trade in goods**. It provides access not only to both recent and historical data of the EU and its individual Member States but also to statistics of a significant number of non-EU countries.

Any aggregated and detailed statistics on international trade in goods disseminated through the Eurostat website are compiled from Comext. Note that the Comext system is also used to store and disseminate statistics on the production of manufactured goods ([PRODCOM](https://ec.europa.eu/eurostat/web/prodcom/overview) data).

## Information

### Listing of available datasets

The Comext and Prodcom datasets available can be listed with the following query

Link: <https://ec.europa.eu/eurostat/api/comext/dissemination/sdmx/2.1/dataflow/ESTAT/all>

### Download capabilities

This API dedicated endpoint has disabled download of a complete dataset due to the heavy size of datasets from Comext domain. They cannot be downloaded as a simple query without filtering parameter. **An exception is made for PRODCOM domain datasets.**

### Files available outside the API

International trade in goods statistics are available in csv format from the [Comext domain](http://ec.europa.eu/eurostat/estat-navtree-portlet-prod/BulkDownloadListing?sort=1&dir=comext). They are accompanied by metadata (classifications, data availability, etc.) and methodological notes.

These files are updated on a monthly basis.
