"""Endpoint wrappers for Eurostat dissemination API.

Layer 1 of ADR-0001: one function per upstream operation, named after it, the WADL's
method id as upstream writes it (``getData``). One module per Eurostat service, since
the method ids repeat across services (the Statistics API's and the asynchronous API's
data operations are both ``getData``): ``statistics`` holds the Statistics API's. A
wrapper takes the parameters as upstream names them (snake_cased), calls
``xippios.eurostat._client.client`` and returns models from ``models.py`` that mirror
the payload. No composition and no defaults beyond upstream's own. The reference is the
snapshot in ``docs/upstream/``.
"""

from xippios.eurostat.api import statistics

__all__ = ["statistics"]
