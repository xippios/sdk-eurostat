"""Endpoint wrappers, layer 1: one async function per upstream operation (conventions §2).

Each is named after its operation, the WADL's method id as upstream writes it
(``getData``). One module per Eurostat service, since the method ids repeat across
services (the Statistics API's and the asynchronous API's data operations are both
``getData``): ``statistics`` holds the Statistics API's, ``catalogue`` the Catalogue API's
(``getTocXml``) and ``sdmx`` the SDMX 2.1 API's (``codeListQuery``, ``dataQuery``). A
wrapper returns models from ``models.py``, or for a file the ``Downloaded`` file.
``/add-endpoint`` adds them.
"""

from xippios.eurostat.api import catalogue, sdmx, statistics

__all__ = ["catalogue", "sdmx", "statistics"]
