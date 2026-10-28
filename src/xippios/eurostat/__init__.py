"""Typed client, MCP tools and HTTP routes for Eurostat dissemination API.

Distribution ``xippios-eurostat``. Public API: ``__version__`` and the task
functions re-exported here. Endpoint wrappers under ``api/`` and the configured client
in ``_client`` are internal.
"""

from xippios.eurostat._version import __version__
from xippios.eurostat.tasks import (
    get_cross_section,
    get_data,
    get_latest_period,
    get_series,
    list_codes,
    list_datasets,
)

__all__ = [
    "__version__",
    "get_cross_section",
    "get_data",
    "get_latest_period",
    "get_series",
    "list_codes",
    "list_datasets",
]
