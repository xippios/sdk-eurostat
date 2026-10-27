# API - Getting started with catalogue API

The Catalogue API provides information on the current listing of disseminated data products.

## TOC - Eurostat table of contents

When interested in working with from Eurostat navigation tree , a classification of Eurostat datasets into hierarchical categories, it is possible to retrieve a TXT or XML representation named "table of contents" (TOC)

Please consult [API - Detailed guidelines - Catalogue API - TOC](https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-detailed-guidelines/catalogue-api/toc) for the information provided by each format

### Download link

#### XML

<https://ec.europa.eu/eurostat/api/dissemination/catalogue/toc/xml>

XML table of contents is multilingual

#### TXT

One text file is available per language:

- english : <https://ec.europa.eu/eurostat/api/dissemination/catalogue/toc/txt?lang=en>
- french : <https://ec.europa.eu/eurostat/api/dissemination/catalogue/toc/txt?lang=fr>
- german : <https://ec.europa.eu/eurostat/api/dissemination/catalogue/toc/txt?lang=de>

## DCAT - Data Catalogue Vocabulary

The catalogue of datasets can be retrieved as a set of RDF files expressed following [Data Catalogue Vocabulary - Application Profile (DCAT-AP)](https://joinup.ec.europa.eu/collection/semantic-interoperability-community-semic/solution/dcat-application-profile-data-portals-europe).

This data catalogue is sent by Eurostat to <https://data.europa.eu/en> portal on a daily basis.

### Download link

#### FULL

Retrieve the full catalogue

<https://ec.europa.eu/eurostat/api/dissemination/catalogue/dcat/ESTAT/FULL>

#### UPDATES

Updates are the list of modified datasets since last update.

Eurostat datasets are **updated twice a day, at 11:00 and at 23:00 in Europe/Brussels time zone**

<http://ec.europa.eu/eurostat/api/dissemination/catalogue/dcat/ESTAT/UPDATES>

## RSS feed

RSS (Rich Site Summary) is a type of web feed that allows users to access updates to online content in a standardised, computer-readable format.

It allows to be informed about the last changes carried out to data products and code lists published by Eurostat.

Here are the URL’s of the RSS feeds:

- English version: <https://ec.europa.eu/eurostat/api/dissemination/catalogue/rss/en/statistics-update.rss>
- German version: <https://ec.europa.eu/eurostat/api/dissemination/catalogue/rss/de/statistics-update.rss>
- French version: <https://ec.europa.eu/eurostat/api/dissemination/catalogue/rss/fr/statistics-update.rss>

For further details, please refer to [API - Detailed guidelines - Catalogue API - RSS](https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-detailed-guidelines/catalogue-api/rss)

## Eurostat metabase.txt.gz

The metabase file includes the structure definition of all available Eurostat datasets via the API i.e. the dimensions codes used and their related positions codes in a delimiter-separated format separated by tabulations (**TAB**). One line of this file as the structure "Dataset Code **TAB** Dimension Code **TAB** Position Code" .

This list is alphabetically sorted on dataset code then dimension code and finally on **position code list order.**

Example for the "Agricultural Labour Input Statistics: absolute figures (1 000 annual work units)" dataset which is identified by the "aact_ali01" code.

`aact_ali01 geo EU`

`aact_ali01 geo EU27_2020_EFTA`

`aact_ali01 geo EU27_2020`

`aact_ali01 geo EU28`

`aact_ali01 geo EU27_2007`

`[...]`

`aact_ali01 geo UK`

`aact_ali01 itm_newa 40000`

`aact_ali01 itm_newa 41000`

`aact_ali01 itm_newa 42000`

`aact_ali01 time 2022`

`aact_ali01 time 2021`

`[...]`

`aact_ali01 time 1973`

This file can be loaded in Excel or processed with text manipulation tool of choice

### Download link

#### Metabase

<https://ec.europa.eu/eurostat/api/dissemination/catalogue/metabase.txt.gz>

Eurostat metabase is **refreshed** **twice a day, at 11:00 and at 23:00 in Europe/Brussels time zone**
