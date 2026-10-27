"""MCP server for Eurostat dissemination API.

Every task in ``tasks.__all__`` is a read-only tool. No logic lives here (ADR-0001).
Entry point: ``xippios-eurostat-mcp``.
"""

from xippios.core.mcp import build_server, main

from xippios.eurostat import tasks
from xippios.eurostat._client import SOURCE
from xippios.eurostat._version import __version__

INSTRUCTIONS = (
    "Eurostat dissemination API via xippios. "
    "Tools are read-only. Where list tools (eurostat_list_*) exist, "
    "call them first to find valid codes, then query."
)

server = build_server(
    SOURCE,
    [getattr(tasks, name) for name in tasks.__all__],
    version=__version__,
    instructions=INSTRUCTIONS,
    caps=getattr(tasks, "MCP_CAPS", None),
)


def run() -> None:
    """Run the server: stdio by default, ``--http`` for streamable HTTP."""
    main(server)
