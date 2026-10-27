# API - Detailed guidelines - SDMX2.1 API - structure queries

## Overview

Structure queries allow **retrieving structural metadata**.

Below is a list of popular types of structural metadata, that you will typically find in SDMX web services.

- `Concept schemes`: In order to make sense of some statistical data, we need to know the *concepts* associated with them. For example, on its own, the figure 1.2953 is pretty meaningless, but if we know that this is an exchange rate for the US dollar against the euro on 23 November 2006, it starts making more sense. The various concepts are typically grouped into collections known as *concept schemes*.
- `Codelists`: Some of the concepts can be *free text* (such as a comment about a particular observation value) but others take their values from a *controlled vocabulary list* (such as, for example, a list of countries). These are known as *codelists* in SDMX.
- `Data structure definitions`: All the concepts that describe a particular domain (such as exchange rates or inflation) are grouped into a *data structure definition (DSD)*. In a DSD, concepts are divided into *dimensions* and *attributes*. Dimensions, when combined, allow to uniquely *identify* statistical data. Attributes on the other hand do not help identifying statistical data, but add useful information (like the unit of measure or the number of decimals). In order to perform granular data queries, one must know the concepts that are used as dimensions, as well as their allowed values (as defined in the codelists).
- `Dataflows`: Dataflows represent the data that cover a particular domain (such as, for example, balance of payments). A *dataflow* provides a reference to the data structure definition that applies for a particular domain, thereby indicating how the data for that domain will look like.

Structure queries in SDMX allow you to retrieve structural metadata at various levels of granularity, from all structural metadata available in the source to a single code from a particular version of a particular codelist maintained by a particular agency.

### About versioned artefacts

Following structural artefacts are versioned and final following SDMX specification: code lists, concept schemes and data structure definitions: each version of each item is available and can be downloaded via the API.

For statistical dataset, corresponding SDMX artefacts are non-final and always with version=1.0.

There is no history available on data.

In the case of multiple versions of the resourceID, which belongs to an agencyID, the highest version means the latest version. If the version parameter is not supplied, then the response to the request includes all existing versions for the specified agencyID and resourceID.

Generic syntax is the following

`protocol://ws-entry-point/{artefactType}/{agencyID}/{resourceID}/{version}?{detail}&{references}&{format}&{compressed}`

| Parameter | Type | Description | Default |
| --- | --- | --- | --- |
| artefactType | One of the following types:<br>- codelist<br>- conceptscheme<br>- datastructure<br>- dataflow<br>- contentconstraint<br>- categoryscheme<br>- categorisation | The type of structural metadata to be returned. | all |
| agencyID | A string compliant with the SDMX *common:NCNameIDType* | The agency maintaining the artefact to be returned. It is possible to set more than one agency, using `,` as separator (e.g. BIS,ECB). | all |
| resourceID | A string compliant with the SDMX *common:IDType* | The id of the artefact to be returned. It is possible to set more than one id, using `,` as separator (e.g. CL_FREQ,CL_CONF_STATUS). | all |
| version | A string compliant with the SDMX *semantic versioning* rules | The version of the artefact to be returned. It is possible to set more than one version, using `,` as separator (e.g. 1.0.0,2.1.7). | latest |
| detail | *String* | This attribute specifies the desired amount of information to be returned. For example, it is possible to instruct the web service to return only basic information about the maintainable artefact (i.e.: id, agency id, version and name). Most notably, items of item schemes will not be returned (for example, it will not return the codes in a code list query). Possible values are:<br>(1) `full`: all available information for all returned artefacts should be returned. Returned extended codelists are to be resolved, i.e. include all inherited codes, and must not include the CodelistExtension property. As the inherited codelists must be resolved, they should not be returned a second time as separated codelists.<br>(2) `allstubs`: all returned artefacts should be returned as stubs, i.e. only containing identification information and the artefacts' name.<br>(3) `referencestubs`: same as full with the exception that referenced artefacts should be returned only as stubs, i.e. only containing identification information and the artefacts' name.<br>(4) `allcompletestubs`: all returned artefacts should be returned as complete stubs, i.e. only containing identification information, the artefacts' name, description and annotations.<br>(5) `referencecompletestubs`: same as full with the exception that referenced artefacts should be returned as complete stubs, i.e. only containing identification information, the artefacts' name, description and annotations.<br>(6) `referencepartial`: same as full with the exception that referenced item schemes should only include items used by the artefact to be returned. For example, a concept scheme would only contain the concepts used in a DSD, and its isPartial flag would be set to true. Likewise, if a dataflow has been constrained, then the codelists referenced by the DSD referenced by the dataflow should only contain the codes referenced by the content constraint. (7) `raw`: same as full with the exception that the returned extended codelists are not resolved and must include the CodelistExtension property, and if referenced codelists or descendants are to be returned then they include also all inherited codelists. | **full** |
| references | *String* | This attribute instructs the web service to return (or not) the artefacts referenced by the artefact to be returned (for example, the code lists and concepts used by the data structure definition matching the query), as well as the artefacts that use the matching artefact (for example, the dataflows that use the data structure definition matching the query). Possible values are: `none` (no references will be returned), `parents` (the artefacts that use the artefact matching the query), `parentsandsiblings` (the artefacts that use the artefact matching the query, as well as the artefacts referenced by these artefacts), `ancestors` (the artefacts that use the artefact matching the query, up to any level), `children` (artefacts referenced by the artefact to be returned), `descendants` (references of references, up to any level, will also be returned), `all` (the combination of parentsandsiblings and descendants).<br>Some option may not be supported depending on the type of resource. please see details below<br>Usage of `concrete type of resource` is not supported (for example, references=codelist). | **none** |
| format | *String* | Alternative to media type HTTP header<br>To get responses in other format than SDMX-ML.<br>This parameter is only supported for resource 'codelist' and 'dataflow'.<br>Supported values are:<br>- JSON for JSON-stat<br>- TSV for Tab Separated Value | |
| lang | *String* | Alternative to Accept HTTP header<br>**Used for JSON or TSV response format**<br>To get responses in languages other than English (if supported by the content provider).<br>This parameter maybe set only for resource 'codelist'. Accepted values are for instance for Eurostat:<br>- en for English<br>- fr for French<br>- de for German | **en** |
| compression | *boolean* | &compressed=true<br>To get responses in .gz compressed format | **false** |

### Response types

The following media types can be used with *structure* queries:

- **application/vnd.sdmx.structure+xml;version=2.1**

The default format is highlighted in **bold**.

### Multiple values and special keywords

Usage of multiple values is not supported, please make one request per resource

The keyword 'all' can be used as a wildcard with the **agencyID or resourceID** parameter to retrieve a "catalog" of content.

Main query is about getting the dataset catalog by requesting the list of all dataflows with the following query `https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/dataflow/all/all/latest`

For the version field, the keyword 'latest' can be used

For non versioned artefacts (dataflow, dataconstraints) the version value "1.0" "\*" or "latest" are equivalents

- the number of decimals). In order to perform granular data queries, one must know the concepts that are used as dimensions, as well as their allowed values (as defined in the codelists).
- `Dataflows`: Dataflows represent the data that cover a particular domain (such as, for example, balance of payments). A *dataflow* provides a reference to the data structure definition that applies for a particular domain, thereby indicating how the data for that domain will look like.

Structure queries in SDMX allow you to retrieve structural metadata at various levels of granularity, from all structural metadata available in the source to a single code from a particular version of a particular codelist maintained by a particular agency.

Generic syntax is the following

`protocol://ws-entry-point/structure/{artefactType}/{agencyID}/{resourceID}/{version}?{detail}&{references}`

| Parameter | Type | Description | Default |
| --- | --- | --- | --- |
| artefactType | One of the following types:<br>- codelist<br>- conceptscheme<br>- datastructure<br>- dataflow<br>- dataconstraint<br>- categoryscheme<br>- categorisation | The type of structural metadata to be returned. | \* |
| agencyID | A string compliant with the SDMX *common:NCNameIDType* | The agency maintaining the artefact to be returned. It is possible to set more than one agency, using `,` as separator (e.g. BIS,ECB). | \* |
| resourceID | A string compliant with the SDMX *common:IDType* | The id of the artefact to be returned. It is possible to set more than one id, using `,` as separator (e.g. CL_FREQ,CL_CONF_STATUS). | \* |
| version | A string compliant with the SDMX *semantic versioning* rules | The version of the artefact to be returned. It is possible to set more than one version, using `,` as separator (e.g. 1.0.0,2.1.7). | ~ |
| detail | *String* | This attribute specifies the desired amount of information to be returned. For example, it is possible to instruct the web service to return only basic information about the maintainable artefact (i.e.: id, agency id, version and name). Most notably, items of item schemes will not be returned (for example, it will not return the codes in a code list query). Possible values are:<br>(1) `full`: all available information for all returned artefacts should be returned. Returned extended codelists are to be resolved, i.e. include all inherited codes, and must not include the CodelistExtension property. As the inherited codelists must be resolved, they should not be returned a second time as separated codelists.<br>(2) `allstubs`: all returned artefacts should be returned as stubs, i.e. only containing identification information and the artefacts' name.<br>(3) `referencestubs`: same as full with the exception that referenced artefacts should be returned only as stubs, i.e. only containing identification information and the artefacts' name.<br>(4) `allcompletestubs`: all returned artefacts should be returned as complete stubs, i.e. only containing identification information, the artefacts' name, description and annotations.<br>(5) `referencecompletestubs`: same as full with the exception that referenced artefacts should be returned as complete stubs, i.e. only containing identification information, the artefacts' name, description and annotations.<br>(6) `referencepartial`: same as full with the exception that referenced item schemes should only include items used by the artefact to be returned. For example, a concept scheme would only contain the concepts used in a DSD, and its isPartial flag would be set to true. Likewise, if a dataflow has been constrained, then the codelists referenced by the DSD referenced by the dataflow should only contain the codes referenced by the content constraint. (7) `raw`: same as full with the exception that the returned extended codelists are not resolved and must include the CodelistExtension property, and if referenced codelists or descendants are to be returned then they include also all inherited codelists. | **full** |
| references | *String* | This attribute instructs the web service to return (or not) the artefacts referenced by the artefact to be returned (for example, the code lists and concepts used by the data structure definition matching the query), as well as the artefacts that use the matching artefact (for example, the dataflows that use the data structure definition matching the query). Possible values are: `none` (no references will be returned), `parents` (the artefacts that use the artefact matching the query), `parentsandsiblings` (the artefacts that use the artefact matching the query, as well as the artefacts referenced by these artefacts), `ancestors` (the artefacts that use the artefact matching the query, up to any level), `children` (artefacts referenced by the artefact to be returned), `descendants` (references of references, up to any level, will also be returned), `all` (the combination of parentsandsiblings and descendants).<br>Some option may not be supported depending on the type of resource. please see details below<br>Usage of `concrete type of resource` is not supported (for example, references=codelist). | **none** |

### Response types

The following media types can be used with *structure* queries:

- **application/vnd.sdmx.structure+xml;version=3.0.0**
- application/vnd.sdmx.structure+xml;version=2.1

The default format is highlighted in **bold**.

### Multiple values and wildcard value support

Usage of multiple values is not supported, please make one request per resource

Main usage of wildcard '\*' is with the **resourceID** parameter to retrieve a "catalog" of content. Main query is about getting the dataset catalog by requesting the list of all dataflows with the following query `https://ec.europa.eu/eurostat/api/dissemination/sdmx/3.0/structure/dataflow/*/*/~`

Usage of wildcard '\*' is not allowed for the **artefactType** parameter and the **version** parameter

Usage of wildcard '\*' is not allowed for the version **artefactType** parameter

For non versioned artefacts (dataflow, dataconstraints) the version value "1.0" "\*" or "~" are equivalents

### Basic examples

| Example | URL |
| --- | --- |
| Retrieving a Eurostat dataflow in SDMX-ML 2.1 format | <https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/dataflow/ESTAT/NAMA_10_GDP> |
| Retrieving a Eurostat data structure in SDMX-ML 2.1 format | <https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/datastructure/ESTAT/NAMA_10_GDP> |
| Retrieving a Eurostat codelist in SDMX-ML 2.1 format | <https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/codelist/ESTAT/GEO> |
| Retrieving a Eurostat codelist in JSON-stat in English format | <https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/codelist/ESTAT/GEO?format=JSON&lang=en> |
| Retrieving a Eurostat codelist in TSV format in English | <https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/codelist/ESTAT/GEO?format=TSV&lang=en> |
| Retrieving a Eurostat concept scheme in SDMX-ML 2.1 format | <https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/conceptscheme/ESTAT/NAMA_10_GDP> |
| Retrieving a Eurostat content constraint in SDMX-ML 2.1 format | <https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/contentconstraint/ESTAT/NAMA_10_GDP> |

### References parameter support

A request about dataflow or data structure resources can be customized by specifying the References parameter.

This parameter allows requesting other resources referenced by a dataflow or a data structure, e.g. codelists and concept schemes.

**Request**
https://\<api_base_uri>/sdmx/2.1/\<resource>/\<agencyID>/\<resourceID>?**references=\<value>**

#### References resolution for dataflows

| Parameter | Description |
| --- | --- |
| references | Supported values are:<br>children<br>Returns dataflow and data structure, without codelists and concept schemes<br>descendants<br>Returns dataflow and data structure, as for children, with codelists and concept schemes<br>none<br>Nothing is resolved (default) |

**Children resolution example**
<https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/dataflow/ESTAT/NAMA_10_GDP?references=children>
**Descendants resolution example**
<https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/dataflow/ESTAT/NAMA_10_GDP?references=descendants>
**Nothing resolved example**
<https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/dataflow/ESTAT/NAMA_10_GDP?references=none>

#### References resolution for data structures

The allowed values for references parameter in the request for a data structure resource are:

| Value | Description |
| --- | --- |
| children | Returns data structure with codelists and concept schemes |
| none | Nothing is resolved (default) |

**Children resolution example**
<https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/datastructure/ESTAT/NAMA_10_GDP?references=children>
**Nothing resolved example**
<https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/datastructure/ESTAT/NAMA_10_GDP?references=none>

### Detail parameter support

The following table lists the values for the SDMX 3.0 "detail" parameter, whether they will be supported or not.

The description is taken over from the [original SDMX-3.0 documentation.](https://github.com/sdmx-twg/sdmx-rest/blob/master/doc/structures.md)

| SDMX 3.0 "detail" parameter | Supported | Description |
| --- | --- | --- |
| full | Yes | All available information for all returned artefacts should be returned. Returned extended codelists are to be resolved, i.e. include all inherited codes, and must not include the CodelistExtension property. As the inherited codelists must be resolved, they should not be returned a second time as separated codelists. |
| allstubs | Yes | All returned artefacts should be returned as stubs, i.e. only containing identification information and the artefacts' name. |
| referencestubs | Yes<br>Not supported for data catalog (**resourceID=\***) | Same as full with the exception that referenced artefacts should be returned only as stubs, i.e. only containing identification information and the artefacts' name |
| allcompletestubs | Yes | All returned artefacts should be returned as complete stubs, i.e. only containing identification information, the artefacts' name, description and annotations. |
| referencecompletestubs | Yes<br>Not supported for data catalog (**resourceID=\***) | Same as full with the exception that referenced artefacts should be returned as complete stubs, i.e. only containing identification information, the artefacts' name, description and annotations. |
| referencepartial | Yes (only supported when the return artefact is of type dataflow and with references parameter in {children, descendants}.<br>Not supported for data catalog (**resourceID=\***) | Same as full with the exception that referenced item schemes should only include items used by the artefact to be returned. For example, a concept scheme would only contain the concepts used in a DSD, and its isPartial flag would be set to true. Likewise, if a dataflow has been constrained, then the codelists referenced by the DSD referenced by the dataflow should only contain the codes referenced by the content constraint |
| raw | No (as no hierarchical codelists in EUROSTAT API) | Not applicable. |
