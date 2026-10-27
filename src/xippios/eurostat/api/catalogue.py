"""``GET catalogue/toc/xml``: the Catalogue API's table of contents as XML, ``getTocXml``.

Reference: ``docs/upstream/api/catalogue.wadl``, resource ``toc/xml`` under
``dissemination/catalogue/``, method ``GET`` with the id ``getTocXml``, answering
``application/xml;charset=UTF-8``; its content is
``docs/upstream/user-guide/api-detailed-guidelines/catalogue-api/toc.md``: every folder,
dataset and table of Eurostat's navigation tree with its code, titles, last update and
period coverage, multilingual. The file is large (23 MB on 2026-10-27), so it is
streamed to disk with core's ``download`` (ADR-0019), never held in memory, and read by
``scripts/refresh_reference.py`` alone, the only code that parses XML (D44): no task
calls this operation, the package answers ``list_datasets`` from its packaged copy.
"""

import os

from xippios.core import Downloaded

from xippios.eurostat._client import client

__all__ = ["PATH", "getTocXml"]

PATH = "catalogue/toc/xml"
"""The operation's path under the base URL, the packaged TOC's ``endpoint``."""


async def getTocXml(dest: str | os.PathLike[str]) -> Downloaded:
    """Call ``getTocXml``: stream the table of contents' XML to ``dest``.

    Args:
        dest: The file to write, in a directory that exists, e.g.
            ``tmp_path / "toc.xml"``.

    Returns:
        The file written, with its size and when it was complete.

    Raises:
        XippiosError: The taxonomy error for a refusal; ``dest`` is left untouched.
    """
    return await client.download(f"/{PATH}", dest)
