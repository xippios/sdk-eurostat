"""File parsers for Eurostat dissemination API, one module per file kind (ADR-0020).

Layer 1's second part (ADR-0020 decision 1): a bulk task streams a file to disk with
core's ``download``, and a parser here reads it, without a request. ``sdmx_csv`` reads
SDMX-CSV 1.0, the SDMX 2.1 API's ``format=SDMX-CSV`` answer that ``download_dataset``
writes, plain or gzip-compressed, with ``parse_sdmx_csv(path)``.
"""

from xippios.eurostat.parse.sdmx_csv import parse_sdmx_csv

__all__ = ["parse_sdmx_csv"]
