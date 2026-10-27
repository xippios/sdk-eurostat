# API - Getting started with SDMX2.1 API

## Introduction

The SDMX initiative sets standards to facilitate the exchange of statistical data and metadata using modern information technology. SDMX has also been published as an ISO International Standard (ISO 17369).

The operations in this API supports SMDX-2.1 artefacts and implements the [SDMX Guidelines for the use of Web Services](https://sdmx.org/wp-content/uploads/SDMX_2-1-1-SECTION_07_WebServicesGuidelines_2013-04.pdf) formalized as the [REST API specification v1.5](https://github.com/sdmx-twg/sdmx-rest/tree/v1.5.0).

To make the most of this guide, a basic knowledge of XML and REST web services is required.

The main elements are referred to as **SDMX artefacts.** Here is a short definition of some terms used in SDMX:

- **Dataset**: a collection of related observations, organised according to a predefined structure
- **Data Structure Definition (DSD)**: metadata describing the structure and organisation of a dataset, the statistical concepts and attached to them code lists used within the dataset
- **Dimensions**: concepts that determine the dataset’s "physical" structure
- **Codelist**: a code list is a predefined list from which some statistical coded concepts take their values. Each code list has the following properties:
  - identifier (it provides a unique identification within the set of code lists specified by a structural definitions maintenance agency);
  - name (also unique);
  - description (a description of the purpose of the code list); and
  - code value length (either an exact or a maximum number of characters and a type, i.e. numeric or alphanumeric).
- **Attributes**: give additional information about the concepts used and do not affect the dataset structure itself
- **Dataflow**: a structure which describes, categorises and constrains the allowable content of a dataset that providers supply for different reference periods
- **Concept scheme**: the descriptive information for an arrangement or division of concepts into groups based on characteristics, which the objects have in common. A concept scheme is a maintained list of concepts that are used in key family and metadata structure definitions (Definitions from [EUROSTAT SDMX](https://webgate.ec.europa.eu/fpfis/mwikis/sdmx/index.php/SDMX) info space and [OECD Glossary of statistical terms](http://stats.oecd.org/glossary/index.htm))

For in depth details, check as well the [learning section of SDMX.org](https://sdmx.org/?page_id=2555) or the [formal definition of the SDMX information model](http://sdmx.org/wp-content/uploads/SDMX_2-1-1_SECTION_2_InformationModel_201108.pdf).

### About versioned artefacts

While all SDMX artefacts could be versioned, currently only the following structural artefacts are versioned: Code lists (CL), Concept Schemes (CS), Data structure definitions (DSD).

It means that such artefacts are final and identified by a version number and safe to be copied/cached for further reference.

Other artefacts : Dataflow, ContentConstraint will always have the default version '1.0' and need to be requested again for updates.

## Retrieving Structural metadata artefacts

Starting from the online data code of a dataset of choice, it is possible to query the API for detailed metadata on this data

### Looking up in the metadata of a dataset

#### in the SDMX Dataflow

Taking the dataset **ISOC_CI_ID_H** as example, its main information are available in its Dataflow SDMX artefact

Link:

<https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/dataflow/ESTAT/ISOC_CI_ID_H/1.0>

**This resource is not versioned, so 1.0 and latest can be used interchangeably**

The minimal response would always contains the dataset label and the reference to the versioned DSD currently used by the dataset

```xml
<s:Dataflow id="ISOC_CI_ID_H" urn="urn:sdmx:org.sdmx.infomodel.datastructure.Dataflow=ESTAT:ISOC_CI_ID_H(1.0)" agencyID="ESTAT" version="1.0" isFinal="false">
  <c:Name xml:lang="de">Haushalte - Verfügbarkeit von Internet-Geräten</c:Name>
  <c:Name xml:lang="en">Households - devices to access the internet</c:Name>
  <c:Name xml:lang="fr">Ménages - dispositifs pour accéder à l'internet</c:Name>
  <s:Structure>
    <Ref id="ISOC_CI_ID_H" version="28.0" agencyID="ESTAT" package="datastructure" class="DataStructure"/>
  </s:Structure>
</s:Dataflow>
```

Additionally a set of annotations would provide additional information (omitted in previous example, please expand full XML below to see them)

| Annotation type | Description | Value(s) (in AnnotationTitle or multi-lingual AnnotationText) |
| --- | --- | --- |
| OBS_COUNT | Number of statistical observations in the dataset | 95814 |
| OBS_PERIOD_OVERALL_OLDEST | Oldest TIME position reported in an observation | 2002 |
| OBS_PERIOD_OVERALL_LATEST | Latest TIME position reported in an observation | 2014 |
| UPDATE_STRUCTURE | Timestamp when the dataset structure last changed<br>- structural change to the list of dimensions<br>- change in list of dimension positions | 2021-02-08T23:00:00+0100 |
| UPDATE_DATA | Timestamp when the dataset data last changed | 2023-05-10T11:00:00+0200 |
| ESMS_HTML | Link to Reference Metadata page | <https://ec.europa.eu/eurostat/cache/metadata/en/isoc_i_esms.htm> |
| ESMS_SDMX | Link to Reference Metadata archive | `https://ec.europa.eu/eurostat/estat-navtree-portlet-prod/BulkDownloadListing?file=metadata/isoc_i_esms.sdmx.zip` |
| SOURCE_INSTITUTIONS | Source institution | Eurostat |

ISOC_CI_ID_H Dataflow XML

```xml
<m:Structure xmlns:m="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message" xmlns:s="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure" xmlns:c="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common">
    <m:Header>
        <m:ID>DF1684040131</m:ID>
        <m:Test>false</m:Test>
        <m:Prepared>2023-05-14T06:55:31.654+02:00</m:Prepared>
        <m:Sender id="ESTAT"/>
    </m:Header>
    <m:Structures>
        <s:Dataflows>
            <s:Dataflow id="ISOC_CI_ID_H" urn="urn:sdmx:org.sdmx.infomodel.datastructure.Dataflow=ESTAT:ISOC_CI_ID_H(1.0)" agencyID="ESTAT" version="1.0" isFinal="false">
                <c:Annotations>
                    <c:Annotation>
                        <c:AnnotationTitle>DATASET</c:AnnotationTitle>
                        <c:AnnotationType>DISSEMINATION_OBJECT_TYPE</c:AnnotationType>
                    </c:Annotation>
                    <c:Annotation>
                        <c:AnnotationTitle>95814</c:AnnotationTitle>
                        <c:AnnotationType>OBS_COUNT</c:AnnotationType>
                    </c:Annotation>
                    <c:Annotation>
                        <c:AnnotationTitle>2002</c:AnnotationTitle>
                        <c:AnnotationType>OBS_PERIOD_OVERALL_OLDEST</c:AnnotationType>
                    </c:Annotation>
                    <c:Annotation>
                        <c:AnnotationTitle>2014</c:AnnotationTitle>
                        <c:AnnotationType>OBS_PERIOD_OVERALL_LATEST</c:AnnotationType>
                    </c:Annotation>
                    <c:Annotation>
                        <c:AnnotationTitle>2021-02-08T23:00:00+0100</c:AnnotationTitle>
                        <c:AnnotationType>UPDATE_STRUCTURE</c:AnnotationType>
                    </c:Annotation>
                    <c:Annotation>
                        <c:AnnotationTitle>2023-05-10T11:00:00+0200</c:AnnotationTitle>
                        <c:AnnotationType>UPDATE_DATA</c:AnnotationType>
                    </c:Annotation>
                    <c:Annotation>
                        <c:AnnotationTitle>Explanatory texts (metadata)</c:AnnotationTitle>
                        <c:AnnotationType>ESMS_HTML</c:AnnotationType>
                        <c:AnnotationURL>https://ec.europa.eu/eurostat/cache/metadata/en/isoc_i_esms.htm</c:AnnotationURL>
                    </c:Annotation>
                    <c:Annotation>
                        <c:AnnotationTitle>Explanatory texts (metadata)</c:AnnotationTitle>
                        <c:AnnotationType>ESMS_SDMX</c:AnnotationType>
                        <c:AnnotationURL>https://ec.europa.eu/eurostat/estat-navtree-portlet-prod/BulkDownloadListing?file=metadata/isoc_i_esms.sdmx.zip</c:AnnotationURL>
                    </c:Annotation>
                    <c:Annotation>
                        <c:AnnotationType>SOURCE_INSTITUTIONS</c:AnnotationType>
                        <c:AnnotationText xml:lang="fr">Eurostat</c:AnnotationText>
                        <c:AnnotationText xml:lang="en">Eurostat</c:AnnotationText>
                        <c:AnnotationText xml:lang="de">Eurostat</c:AnnotationText>
                    </c:Annotation>
                    <c:Annotation>
                        <c:AnnotationTitle>
                            <adms:identifier xmlns:adms="http://www.w3.org/ns/adms#" xmlns:skos="http://www.w3.org/2004/02/skos/core.html" xmlns:dct="http://purl.org/dc/terms/" xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
                                <adms:Identifier rdf:about="https://doi.org/10.2908/ISOC_CI_ID_H">
                                    <skos:notation rdf:datatype="http://purl.org/spar/datacite/doi">10.2908/ISOC_CI_ID_H</skos:notation>
                                    <dct:creator rdf:resource="http://publications.europa.eu/resource/authority/corporate-body/ESTAT"/>
                                    <dct:issued rdf:datatype="http://www.w3.org/2001/XMLSchema#date">2023-01-19T12:50:39</dct:issued>
                                </adms:Identifier>
                            </adms:identifier>
                        </c:AnnotationTitle>
                        <c:AnnotationType>DISSEMINATION_DOI_XML</c:AnnotationType>
                    </c:Annotation>
                </c:Annotations>
                <c:Name xml:lang="de">Haushalte - Verfügbarkeit von Internet-Geräten</c:Name>
                <c:Name xml:lang="en">Households - devices to access the internet</c:Name>
                <c:Name xml:lang="fr">Ménages - dispositifs pour accéder à l'internet</c:Name>
                <s:Structure>
                    <Ref id="ISOC_CI_ID_H" version="28.0" agencyID="ESTAT" package="datastructure" class="DataStructure"/>
                </s:Structure>
            </s:Dataflow>
        </s:Dataflows>
    </m:Structures>
</m:Structure>
```

#### in the referenced data structure definition (DSD)

From the reference present in the dataflow, it is possible to query for the corresponding SDMX Data Structure Definition

DSD Link:

<https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/datastructure/ESTAT/ISOC_CI_ID_H/28.0>

**These resources are versioned, so version present in the reference must be used to ensure consistency.**

This definition is providing list of dimensions used in the definition of the time-series of the dataset.

The order of dimensions will help build key filtering in the Data query later

For each dimension a reference is provided

1. to the concept holding the dimension label, the concept is one item of a concept scheme.

   In current Eurostat Dissemination Chain, there is one DSD and one ConceptScheme generated for each dataset with identical identifier (but potentially different version).

   Concept Scheme Link

   <https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/conceptscheme/ESTAT/ISOC_CI_ID_H/28.0>

2. to the code lists holding the code and labels for the dimension positions

| Dimension | Version | Code list Link |
| --- | --- | --- |
| FREQ | 1.31 | <https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/codelist/ESTAT/FREQ/1.31> |
| INDIC_IS | 9.0 | <https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/codelist/ESTAT/INDIC_IS/9.0> |
| UNIT | 16.0 | <https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/codelist/ESTAT/UNIT/16.0> |
| HHTYP | 2.0 | <https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/codelist/ESTAT/HHTYP/2.0> |
| GEO | 14.0 | [https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/codelist/ESTAT/GEO/14.](https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/codelist/ESTAT/GEO/14.0) |

These code lists are reference metadata and may contains more code and labels than the one used by a specific dataset.

To known the list of positions present in the dataset, please refer to the Content Constraint artefact (next section).

Additionally the DSD defines

- the mandatory **TIME_PERIOD** time-dimension dimension where the value are expressed using ISO 8601 standard

- the primary measure **OBS_VALUE** holding the statistical value

- the optional value attribute OBS_FLAG holding the statistical status (also referred as flags)

  Flag codelist Link

  <https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/conceptscheme/ESTAT/OBS_FLAG/1.31>

**ISOC_CI_ID_H DSD XML**

```xml
<?xml version='1.0' encoding='UTF-8'?>
<m:Structure xmlns:m="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message" xmlns:s="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure" xmlns:c="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common">
    <m:Header>
        <m:ID>DS-ISOC_CI_ID_H1683705333393</m:ID>
        <m:Test>false</m:Test>
        <m:Prepared>2023-05-10T07:55:33.393Z</m:Prepared>
        <m:Sender id="ESTAT">
            <c:Name xml:lang="de">Statistische Amt der Europäischen Union (Eurostat)</c:Name>
            <c:Name xml:lang="en">Statistical Office of the European Union (Eurostat)</c:Name>
            <c:Name xml:lang="fr">Office de statistique de l'Union européenne (Eurostat)</c:Name>
        </m:Sender>
        <m:Receiver id="unknown"/>
    </m:Header>
    <m:Structures>
        <s:DataStructures>
            <s:DataStructure agencyID="ESTAT" id="ISOC_CI_ID_H" isFinal="true" urn="urn:sdmx:org.sdmx.infomodel.datastructure.DataStructure=ESTAT:ISOC_CI_ID_H(28.0)" version="28.0">
                <c:Annotations>
                    <c:Annotation>
                        <c:AnnotationTitle>OBS_FLAG</c:AnnotationTitle>
                        <c:AnnotationType>DISSEMINATION_FLAG_SETTINGS</c:AnnotationType>
                        <c:AnnotationURL/>
                    </c:Annotation>
                    <c:Annotation>
                        <c:AnnotationTitle>time</c:AnnotationTitle>
                        <c:AnnotationType>DISSEMINATION_TIME_DIMENSION_CODE</c:AnnotationType>
                        <c:AnnotationURL/>
                    </c:Annotation>
                </c:Annotations>
                <c:Name xml:lang="en">ISOC_CI_ID_H data structure</c:Name>
                <s:DataStructureComponents>
                    <s:DimensionList id="DimensionDescriptor" urn="urn:sdmx:org.sdmx.infomodel.datastructure.DimensionDescriptor=ESTAT:ISOC_CI_ID_H(28.0).DimensionDescriptor">
                        <s:Dimension id="freq" position="1" urn="urn:sdmx:org.sdmx.infomodel.datastructure.Dimension=ESTAT:ISOC_CI_ID_H(28.0).freq">
                            <s:ConceptIdentity>
                                <Ref agencyID="ESTAT" class="Concept" id="freq" maintainableParentID="ISOC_CI_ID_H" maintainableParentVersion="28.0" package="conceptscheme"/>
                            </s:ConceptIdentity>
                            <s:LocalRepresentation>
                                <s:Enumeration>
                                    <Ref agencyID="ESTAT" class="Codelist" id="FREQ" package="codelist" version="1.31"/>
                                </s:Enumeration>
                            </s:LocalRepresentation>
                        </s:Dimension>
                        <s:Dimension id="indic_is" position="2" urn="urn:sdmx:org.sdmx.infomodel.datastructure.Dimension=ESTAT:ISOC_CI_ID_H(28.0).indic_is">
                            <s:ConceptIdentity>
                                <Ref agencyID="ESTAT" class="Concept" id="indic_is" maintainableParentID="ISOC_CI_ID_H" maintainableParentVersion="28.0" package="conceptscheme"/>
                            </s:ConceptIdentity>
                            <s:LocalRepresentation>
                                <s:Enumeration>
                                    <Ref agencyID="ESTAT" class="Codelist" id="INDIC_IS" package="codelist" version="9.0"/>
                                </s:Enumeration>
                            </s:LocalRepresentation>
                        </s:Dimension>
                        <s:Dimension id="unit" position="3" urn="urn:sdmx:org.sdmx.infomodel.datastructure.Dimension=ESTAT:ISOC_CI_ID_H(28.0).unit">
                            <s:ConceptIdentity>
                                <Ref agencyID="ESTAT" class="Concept" id="unit" maintainableParentID="ISOC_CI_ID_H" maintainableParentVersion="28.0" package="conceptscheme"/>
                            </s:ConceptIdentity>
                            <s:LocalRepresentation>
                                <s:Enumeration>
                                    <Ref agencyID="ESTAT" class="Codelist" id="UNIT" package="codelist" version="16.0"/>
                                </s:Enumeration>
                            </s:LocalRepresentation>
                        </s:Dimension>
                        <s:Dimension id="hhtyp" position="4" urn="urn:sdmx:org.sdmx.infomodel.datastructure.Dimension=ESTAT:ISOC_CI_ID_H(28.0).hhtyp">
                            <s:ConceptIdentity>
                                <Ref agencyID="ESTAT" class="Concept" id="hhtyp" maintainableParentID="ISOC_CI_ID_H" maintainableParentVersion="28.0" package="conceptscheme"/>
                            </s:ConceptIdentity>
                            <s:LocalRepresentation>
                                <s:Enumeration>
                                    <Ref agencyID="ESTAT" class="Codelist" id="HHTYP" package="codelist" version="2.0"/>
                                </s:Enumeration>
                            </s:LocalRepresentation>
                        </s:Dimension>
                        <s:Dimension id="geo" position="5" urn="urn:sdmx:org.sdmx.infomodel.datastructure.Dimension=ESTAT:ISOC_CI_ID_H(28.0).geo">
                            <s:ConceptIdentity>
                                <Ref agencyID="ESTAT" class="Concept" id="geo" maintainableParentID="ISOC_CI_ID_H" maintainableParentVersion="28.0" package="conceptscheme"/>
                            </s:ConceptIdentity>
                            <s:LocalRepresentation>
                                <s:Enumeration>
                                    <Ref agencyID="ESTAT" class="Codelist" id="GEO" package="codelist" version="14.0"/>
                                </s:Enumeration>
                            </s:LocalRepresentation>
                        </s:Dimension>
                        <s:TimeDimension id="TIME_PERIOD" position="6" urn="urn:sdmx:org.sdmx.infomodel.datastructure.TimeDimension=ESTAT:ISOC_CI_ID_H(28.0).TIME_PERIOD">
                            <s:ConceptIdentity>
                                <Ref agencyID="ESTAT" class="Concept" id="TIME_PERIOD" maintainableParentID="ISOC_CI_ID_H" maintainableParentVersion="28.0" package="conceptscheme"/>
                            </s:ConceptIdentity>
                            <s:LocalRepresentation>
                                <s:TextFormat textType="ObservationalTimePeriod"/>
                            </s:LocalRepresentation>
                        </s:TimeDimension>
                    </s:DimensionList>
                    <s:AttributeList id="AttributeDescriptor" urn="urn:sdmx:org.sdmx.infomodel.datastructure.AttributeDescriptor=ESTAT:ISOC_CI_ID_H(28.0).AttributeDescriptor">
                        <s:Attribute assignmentStatus="Conditional" id="OBS_FLAG" urn="urn:sdmx:org.sdmx.infomodel.datastructure.DataAttribute=ESTAT:ISOC_CI_ID_H(28.0).OBS_FLAG">
                            <s:ConceptIdentity>
                                <Ref agencyID="ESTAT" class="Concept" id="OBS_FLAG" maintainableParentID="ISOC_CI_ID_H" maintainableParentVersion="28.0" package="conceptscheme"/>
                            </s:ConceptIdentity>
                            <s:LocalRepresentation>
                                <s:Enumeration>
                                    <Ref agencyID="ESTAT" class="Codelist" id="OBS_FLAG" package="codelist" version="1.31"/>
                                </s:Enumeration>
                            </s:LocalRepresentation>
                            <s:AttributeRelationship>
                                <s:PrimaryMeasure>
                                    <Ref id="OBS_VALUE"/>
                                </s:PrimaryMeasure>
                            </s:AttributeRelationship>
                        </s:Attribute>
                    </s:AttributeList>
                    <s:MeasureList id="MeasureDescriptor" urn="urn:sdmx:org.sdmx.infomodel.datastructure.MeasureDescriptor=ESTAT:ISOC_CI_ID_H(28.0).MeasureDescriptor">
                        <s:PrimaryMeasure id="OBS_VALUE" urn="urn:sdmx:org.sdmx.infomodel.datastructure.PrimaryMeasure=ESTAT:ISOC_CI_ID_H(28.0).OBS_VALUE">
                            <s:ConceptIdentity>
                                <Ref agencyID="ESTAT" class="Concept" id="OBS_VALUE" maintainableParentID="ISOC_CI_ID_H" maintainableParentVersion="28.0" package="conceptscheme"/>
                            </s:ConceptIdentity>
                            <s:LocalRepresentation>
                                <s:TextFormat textType="Double"/>
                            </s:LocalRepresentation>
                        </s:PrimaryMeasure>
                    </s:MeasureList>
                </s:DataStructureComponents>
            </s:DataStructure>
        </s:DataStructures>
    </m:Structures>
</m:Structure>
```

#### in the SDMX Content Constraint

Content Constraint Link:

<https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/contentconstraint/ESTAT/ISOC_CI_ID_H/1.0>

In the API, SDMX Content Constraints artefacts are used to define **available positions,** it lists for each dimension code the list of position code that are used at least once to refer to a statistical observation.

From example below we can see that ISOC_CI_ID_H dataset

- provides annual data ( freq = A)
- provides data for 14 indicators
- provides data in 2 units
- provides 17 breakdowns and a TOTAL on "Type of Household" [ hhtyp ]
- provides data for EU aggregates and member states + other countries
- provides data from 2002 to 2010 plus 2014

**Content Constraint SDMX XML**

```xml
<?xml version='1.0' encoding='UTF-8'?>
<m:Structure xmlns:m="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message" xmlns:s="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure" xmlns:c="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common">
    <m:Header>
        <m:ID>DS-ISOC_CI_ID_H1683705333706</m:ID>
        <m:Test>false</m:Test>
        <m:Prepared>2023-05-10T07:55:33.706Z</m:Prepared>
        <m:Sender id="ESTAT">
            <c:Name xml:lang="de">Statistische Amt der Europäischen Union (Eurostat)</c:Name>
            <c:Name xml:lang="en">Statistical Office of the European Union (Eurostat)</c:Name>
            <c:Name xml:lang="fr">Office de statistique de l'Union européenne (Eurostat)</c:Name>
        </m:Sender>
        <m:Receiver id="unknown"/>
    </m:Header>
    <m:Structures>
        <s:Constraints>
            <s:ContentConstraint agencyID="ESTAT" id="ISOC_CI_ID_H" isFinal="false" type="Actual" urn="urn:sdmx:org.sdmx.infomodel.registry.ContentConstraint=ESTAT:ISOC_CI_ID_H(1.0)" version="1.0">
                <c:Name xml:lang="en">Cube description for dataflow ISOC_CI_ID_H</c:Name>
                <s:ConstraintAttachment>
                    <s:Dataflow>
                        <Ref agencyID="ESTAT" class="Dataflow" id="ISOC_CI_ID_H" package="datastructure" version="1.0"/>
                    </s:Dataflow>
                </s:ConstraintAttachment>
                <s:CubeRegion include="true">
                    <c:KeyValue id="freq">
                        <c:Value>A</c:Value>
                    </c:KeyValue>
                    <c:KeyValue id="indic_is">
                        <c:Value>H_IPC</c:Value>
                        <c:Value>H_ITV</c:Value>
                        <c:Value>H_IPALM</c:Value>
                        <c:Value>H_IMPH</c:Value>
                        <c:Value>H_IGAME</c:Value>
                        <c:Value>H_IPCQ</c:Value>
                        <c:Value>H_ITVQ</c:Value>
                        <c:Value>H_IPALMQ</c:Value>
                        <c:Value>H_IMPHQ</c:Value>
                        <c:Value>H_IGAMEQ</c:Value>
                        <c:Value>H_IOTHDV</c:Value>
                        <c:Value>H_IDKPC</c:Value>
                        <c:Value>H_IPORT</c:Value>
                        <c:Value>H_ITV2</c:Value>
                    </c:KeyValue>
                    <c:KeyValue id="unit">
                        <c:Value>PC_HH</c:Value>
                        <c:Value>PC_HH_IACC</c:Value>
                    </c:KeyValue>
                    <c:KeyValue id="hhtyp">
                        <c:Value>TOTAL</c:Value>
                        <c:Value>A1</c:Value>
                        <c:Value>A1_DCH</c:Value>
                        <c:Value>A2</c:Value>
                        <c:Value>A2_DCH</c:Value>
                        <c:Value>A_GE3</c:Value>
                        <c:Value>A_GE3_DCH</c:Value>
                        <c:Value>ALL_NDCH</c:Value>
                        <c:Value>ALL_DCH</c:Value>
                        <c:Value>HH_O1</c:Value>
                        <c:Value>HH_NO1</c:Value>
                        <c:Value>HH_DEG1</c:Value>
                        <c:Value>HH_DEG2</c:Value>
                        <c:Value>HH_DEG3</c:Value>
                        <c:Value>HHI_Q1</c:Value>
                        <c:Value>HHI_Q2</c:Value>
                        <c:Value>HHI_Q3</c:Value>
                        <c:Value>HHI_Q4</c:Value>
                    </c:KeyValue>
                    <c:KeyValue id="geo">
                        <c:Value>EU27_2020</c:Value>
                        <c:Value>EU28</c:Value>
                        <c:Value>EU27_2007</c:Value>
                        <c:Value>EU25</c:Value>
                        <c:Value>EU15</c:Value>
                        <c:Value>EA</c:Value>
                        <c:Value>BE</c:Value>
                        <c:Value>BG</c:Value>
                        <c:Value>CZ</c:Value>
                        <c:Value>DK</c:Value>
                        <c:Value>DE</c:Value>
                        <c:Value>EE</c:Value>
                        <c:Value>IE</c:Value>
                        <c:Value>EL</c:Value>
                        <c:Value>ES</c:Value>
                        <c:Value>FR</c:Value>
                        <c:Value>HR</c:Value>
                        <c:Value>IT</c:Value>
                        <c:Value>CY</c:Value>
                        <c:Value>LV</c:Value>
                        <c:Value>LT</c:Value>
                        <c:Value>LU</c:Value>
                        <c:Value>HU</c:Value>
                        <c:Value>MT</c:Value>
                        <c:Value>NL</c:Value>
                        <c:Value>AT</c:Value>
                        <c:Value>PL</c:Value>
                        <c:Value>PT</c:Value>
                        <c:Value>RO</c:Value>
                        <c:Value>SI</c:Value>
                        <c:Value>SK</c:Value>
                        <c:Value>FI</c:Value>
                        <c:Value>SE</c:Value>
                        <c:Value>IS</c:Value>
                        <c:Value>NO</c:Value>
                        <c:Value>CH</c:Value>
                        <c:Value>UK</c:Value>
                        <c:Value>MK</c:Value>
                        <c:Value>RS</c:Value>
                        <c:Value>TR</c:Value>
                    </c:KeyValue>
                    <c:KeyValue id="TIME_PERIOD">
                        <c:Value>2002</c:Value>
                        <c:Value>2003</c:Value>
                        <c:Value>2004</c:Value>
                        <c:Value>2005</c:Value>
                        <c:Value>2006</c:Value>
                        <c:Value>2007</c:Value>
                        <c:Value>2008</c:Value>
                        <c:Value>2009</c:Value>
                        <c:Value>2010</c:Value>
                        <c:Value>2014</c:Value>
                    </c:KeyValue>
                </s:CubeRegion>
            </s:ContentConstraint>
        </s:Constraints>
    </m:Structures>
</m:Structure>
```

#### retrieve several artefacts in a single response

It is not necessary to do these calls one by one.

Starting back from the Dataflow it is possible to include the referenced artefacts, at two different level

| Scope | Link |
| --- | --- |
| Dataflow + DSD | <https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/dataflow/ESTAT/ISOC_CI_ID_H/1.0?references=children> |
| Dataflow + DSD + CS and CL | <https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/dataflow/ESTAT/ISOC_CI_ID_H/1.0?references=descendants> |
| Dataflow + DSD + CS and CL<br>**filtered on the constraints** | <https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/dataflow/ESTAT/ISOC_CI_ID_H/1.0?references=descendants&detail=referencepartial> |

Also form the DSD, it is possible to include the referenced artefacts:

`https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/datastructure/ESTAT/ISOC_CI_ID_H/28.0?references=children`

### Special case of Dataset listing

Instead of specifying a dataset code in the dataflow request the **ALL** keyword can be used to retrieve a list of all Eurostat datasets in one request

It is recommended to retrieve the compressed version

ALL DATAFLOWS link:

<https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/dataflow/ESTAT/all>

### Special case of Metadata harvesting

Similarly to the request on ALL dataflows it is possible to get the latest version for all artefacts for a specified type

| Scope | Link |
| --- | --- |
| All code lists | <https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/codelist/ESTAT/all> |
| All concept schemes | <https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/conceptscheme/ESTAT/all> |
| All data structure definitions | <https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/datastructure/ESTAT/all> |

## Data query

in SDMX 2.1, the data query directly use the dataflow identifier without agencyID

Data Link:

<https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/ISOC_CI_ID_H>

Above link retrieves the complete dataset in default format : SDMX-ML 2.1 Generic Data.

The data file is compose of time-series identified by a series-keys containing Observation as the one show below

**SDMX Generic Time Series XML Excerpt**

```xml
<g:Series>
    <g:SeriesKey>
        <g:Value id="geo" value="EA"/>
        <g:Value id="hhtyp" value="TOTAL"/>
        <g:Value id="unit" value="PC_HH_IACC"/>
        <g:Value id="indic_is" value="H_IPC"/>
        <g:Value id="freq" value="A"/>
    </g:SeriesKey>
    <g:Obs>
        <g:ObsDimension value="2003"/>
        <g:ObsValue value="96.27"/>
    </g:Obs>
    <g:Obs>
        <g:ObsDimension value="2004"/>
        <g:ObsValue value="96.02"/>
    </g:Obs>
    <g:Obs>
        <g:ObsDimension value="2005"/>
        <g:ObsValue value="96.27"/>
    </g:Obs>
    <g:Obs>
        <g:ObsDimension value="2006"/>
        <g:ObsValue value="96.23"/>
    </g:Obs>
    <g:Obs>
        <g:ObsDimension value="2007"/>
        <g:ObsValue value="96.59"/>
    </g:Obs>
    <g:Obs>
        <g:ObsDimension value="2008"/>
        <g:ObsValue value="84.89"/>
    </g:Obs>
    <g:Obs>
        <g:ObsDimension value="2009"/>
        <g:ObsValue value="96.81"/>
    </g:Obs>
    <g:Obs>
        <g:ObsDimension value="2010"/>
        <g:ObsValue value="97.16"/>
    </g:Obs>
    <g:Obs>
        <g:ObsDimension value="2014"/>
        <g:ObsValue value="95.63"/>
    </g:Obs>
</g:Series>
```

It is possible to further customize the query to retrieve only the needed data or to request a different output format :

### Filtering on series-keys

Filtering in SDMX REST web service is done by filtering the on the series-keys following the dimension order as specified in the DSD

In the example of ISOC_CI_ID_H, the series-keys template is as follow

`FREQ.INDIC_IS.UNIT.HHTYP.GEO`

with the following syntax:

- **a blank** means no filtering for this dimension
- Several values for a dimension must be separated by a '+' character

<table>
<thead>
<tr>
<th>Scope</th>
<th>Details on the series-keys filter</th>
<th>Link</th>
</tr>
</thead>
<tbody>
<tr>
<td>Single time-series<br>fully specified</td>
<td><table><thead><tr><th>Dimension</th><th>Value</th></tr></thead><tbody><tr><td>FREQ</td><td>A</td></tr><tr><td>INDIC_IS</td><td>H_IPC</td></tr><tr><td>UNIT</td><td>PC_HH_IACC</td></tr><tr><td>HHTYP</td><td>TOTAL</td></tr><tr><td>GEO</td><td>EA</td></tr></tbody></table></td>
<td><a href="https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/ISOC_CI_ID_H/A.H_IPC.PC_HH_IACC.TOTAL.EA">https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/ISOC_CI_ID_H/A.H_IPC.PC_HH_IACC.TOTAL.EA</a></td>
</tr>
<tr>
<td>EU27 and EA data</td>
<td>As the GEO dimension is the last, previous dimension must be left blank<br><code>....EU27_2020+EA</code></td>
<td><a href="https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/ISOC_CI_ID_H/....EU27_2020+EA">https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/ISOC_CI_ID_H/....EU27_2020+EA</a></td>
</tr>
</tbody>
</table>

### Filtering on time period

Filtering the observations to be returned based on their TIME_PERIOD value is controller via a FROM-TO filter with the query parameter **startPeriod** and **endPeriod ( case sensitive)**

Reusing above single time-series example, it can be restricted to 2008 to 2010 as follow

`https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/ISOC_CI_ID_H/A.H_IPC.PC_HH_IACC.TOTAL.EU27_2020?startPeriod=2008&endPeriod=2010`

### Supported format

An additional **format** parameter allows to request a response in a different semantic format

| Format | Description | Link |
| --- | --- | --- |
| SDMX-ML 2.1 Structured Data | More compact XML format | <https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/ISOC_CI_ID_H?format=SDMX_2.1_STRUCTURED> |
| SDMX-CSV 1.0 | SDMX standardized CSV format | <https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/ISOC_CI_ID_H?format=SDMX-CSV> |
| TSV | Eurostat specific format | <https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/ISOC_CI_ID_H?format=TSV> |
| JSONstat | JSON format usable with JSON-stat toolkit | <https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/ISOC_CI_ID_H?format=JSON> |

### Compression

An additional **compressed** parameter allows to optimize network transfer by retrieving the content compressed as GZIP

Compressed TSV data link:

<https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/ISOC_CI_ID_H?format=TSV&compressed=true>

## Retrieving Navigation artefacts

It is worth to mention secondary artefacts that represent as SDMX artefacts a classification of dataset in categories (also refrered as "Navigation Tree")

- **Category Scheme** : Hierarchy of categories
- **Categorisation** : one categorisation is referencing one dataset into a category of a Category Scheme

| Scope | Link |
| --- | --- |
| All category schemes | <https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/categoryscheme/ESTAT/all> |
| All categorisations | <https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/categorisation/ESTAT/all> |
