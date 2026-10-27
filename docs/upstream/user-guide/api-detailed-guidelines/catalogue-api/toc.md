# API - Detailed guidelines - Catalogue API - TOC

The "table of contents" (TOC) provides a textual representation of Eurostat navigation tree and information on datasets and tables available on the Eurostat website and via the API. The TOC is available in two formats: TXT or XML.

## TOC by format and type of information

| Type of information | Additional description | TXT | XML |
| --- | --- | --- | --- |
| code | Each item (dataset, table and folder) of the TOC has a unique code which allows it to be identified both in the navigation tree and in the API.<br>However, some of them can be classified at different places in the data navigation tree | x | x |
| title - English | | x | x |
| title - French | | x | x |
| title - German | | x | x |
| sub-title - English | | | x |
| sub-title - French | | | x |
| sub-title - German | | | x |
| short description - English | | | x |
| short description - French | | | x |
| short description - German | | | x |
| type (dataset, table, folder) | Dataset: i.e. an "open dataset"<br>Table: i.e. a "pre-defined table"<br>Folder: i.e. a "section" or "chapter" | x | x |
| last update of data | Indicates the last time the dataset/table was updated | x | x |
| last table structure change | Indicates the last time the dataset/table structure was modified | x | x |
| data start | Date of the oldest value included in the dataset (if available) | x | x |
| data end | Date of the most recent value included in the dataset (if available) | x | x |
| number of values | Number of actual values included in the dataset | x | x |
| reference metadata (ESMS) access via url | | | x |
| reference metadata (ESMS) download file (zip) | | | x |
| data download in TSV format | | | x |
| data download in SDMX format | | | x |
| hierarchy of the data navigation tree | hierarchy level in the TXT format is represented by a 4-spaces indentation prefix in the title | x | x |

## Download links

<table>
<thead>
<tr>
<th>Format</th>
<th>Description</th>
</tr>
</thead>
<tbody>
<tr>
<td rowspan="2">XML</td>
<td>XML table of contents is multilingual<br><a href="https://ec.europa.eu/eurostat/api/dissemination/catalogue/toc/xml">https://ec.europa.eu/eurostat/api/dissemination/catalogue/toc/xml</a></td>
</tr>
<tr>
<td>XSD - XML Schema definition of the XML table of contents<br><a href="https://ec.europa.eu/eurostat/api/dissemination/catalogue/toc/TableOfContent.xsd">https://ec.europa.eu/eurostat/api/dissemination/catalogue/toc/TableOfContent.xsd</a></td>
</tr>
<tr>
<td>TXT</td>
<td>Textual table of contents is language specific to be specified via the "lang" URL parameter:<br><ul><li>en : <a href="https://ec.europa.eu/eurostat/api/dissemination/catalogue/toc/txt?lang=en">https://ec.europa.eu/eurostat/api/dissemination/catalogue/toc/txt?lang=en</a></li><li>fr : <a href="https://ec.europa.eu/eurostat/api/dissemination/catalogue/toc/txt?lang=fr">https://ec.europa.eu/eurostat/api/dissemination/catalogue/toc/txt?lang=fr</a></li><li>de : <a href="https://ec.europa.eu/eurostat/api/dissemination/catalogue/toc/txt?lang=de">https://ec.europa.eu/eurostat/api/dissemination/catalogue/toc/txt?lang=de</a></li></ul></td>
</tr>
</tbody>
</table>
