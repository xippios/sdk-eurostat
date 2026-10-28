"""Public API: ``__version__`` and the task functions re-exported here (conventions §2).

Upstream: Eurostat dissemination API. ``parse.parse_sdmx_csv`` reads the files the bulk
tasks ``download_dataset`` and ``download_trade`` write.
"""

from xippios.eurostat._version import __version__
from xippios.eurostat.tasks import (
    download_dataset,
    download_trade,
    get_cross_section,
    get_data,
    get_latest_period,
    get_series,
    get_sold_production,
    get_total_production,
    get_trade,
    get_trade_hs,
    list_cn8,
    list_codes,
    list_datasets,
    list_hs,
    list_products,
)

__all__ = [
    "__version__",
    "download_dataset",
    "download_trade",
    "get_cross_section",
    "get_data",
    "get_latest_period",
    "get_series",
    "get_sold_production",
    "get_total_production",
    "get_trade",
    "get_trade_hs",
    "list_cn8",
    "list_codes",
    "list_datasets",
    "list_hs",
    "list_products",
]
