# API - Detailed guidelines - DS- prefixed datasets from Comext database

## Important note for "DS- prefixed" / "Comext and PRODCOM" datasets :

For technical reason Comext and Prodcom datasets (DS- prefixed dataset code, i.e DS-057555) are separated.

For these datasets, the \<api_base_uri> is: [https://ec.europa.eu/eurostat/api/**comext**/dissemination](https://ec.europa.eu/eurostat/api/comext/dissemination)

In the URL above, "comext/" is added to differenciate this base URL from the main one: <https://ec.europa.eu/eurostat/api/dissemination>

Further note concerning Comext datasets: full datasets cannot be downloaded because of their size. They have to be filtered.
