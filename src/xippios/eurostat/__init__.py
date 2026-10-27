"""Typed client, MCP tools and HTTP routes for Eurostat dissemination API.

Distribution ``xippios-eurostat``. Public API: ``__version__`` and the task
functions re-exported here. Endpoint wrappers under ``api/`` and the configured client
in ``_client`` are internal.
"""

from xippios.eurostat._version import __version__

__all__ = ["__version__"]
