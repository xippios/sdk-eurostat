"""Public API: ``__version__`` and the task functions re-exported here (conventions §2).

Upstream: Eurostat dissemination API. ``parse.parse_sdmx_csv`` reads the file the bulk
task ``download_dataset`` writes.
"""

from xippios.eurostat._version import __version__
from xippios.eurostat.tasks import (
    download_dataset,
    get_cross_section,
    get_data,
    get_latest_period,
    get_series,
    get_sold_production,
    get_total_production,
    list_codes,
    list_datasets,
    list_products,
)

__all__ = [
    "__version__",
    "download_dataset",
    "get_cross_section",
    "get_data",
    "get_latest_period",
    "get_series",
    "get_sold_production",
    "get_total_production",
    "list_codes",
    "list_datasets",
    "list_products",
]
