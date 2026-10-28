"""Endpoint wrappers, layer 1: one async function per upstream operation (conventions §2).

Each is named after its operation's WADL method id in snake case (conventions 1.22 §2;
ADR-0003, amendment 2026-10-28): ``get_data`` for ``getData``, ``get_toc_xml`` for
``getTocXml``, ``code_list_query`` for ``codeListQuery`` and ``data_query`` for
``dataQuery``. The verbatim id stays in the first line of the wrapper's docstring and in
the endpoint constants ``ENDPOINT``, ``CODELIST_ENDPOINT`` and ``DATA_ENDPOINT``, which
``parse``'s ``endpoint=`` and the tasks' ``meta.endpoint`` take, so ``meta.endpoint``
keeps upstream's name; ``getTocXml`` has none, since no task calls it and the packaged
TOC's endpoint is ``catalogue.PATH``. One module per Eurostat service, since the method
ids repeat across services (the Statistics API's and the asynchronous API's data
operations are both ``getData``): ``statistics`` holds the Statistics API's, ``catalogue``
the Catalogue API's and ``sdmx`` the SDMX 2.1 API's. A wrapper's fixtures live under
``tests/fixtures/<wrapper>/`` (conventions §10): ``get_data/`` and ``data_query/``. A
wrapper returns models from ``models.py``, or for a file the ``Downloaded`` file.
``/add-endpoint`` adds them.
"""

from xippios.eurostat.api import catalogue, sdmx, statistics

__all__ = ["catalogue", "sdmx", "statistics"]
