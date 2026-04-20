"""Microsoft Graph client for the /admin/entra/* admin-portal router.

All Graph calls are delegated (on-behalf-of); no client-credentials
permissions are ever held by the LEO Entra app registration. See
DI-3610585D (amended) and DI-6CF7FCE0.

Public surface
--------------
- ``GraphClient`` -- async wrapper over the Graph endpoints we use.
- ``GraphScopes`` -- canonical Graph delegated scopes the app reg holds.
- ``probe_capability`` -- best-effort capability matrix for a tenant.
- ``GraphClientError`` plus typed subclasses ``MissingUserToken``,
  ``InsufficientConsent``, ``RateLimited``, ``NotFound``, ``Forbidden``.
"""

from libs.graph_client.client import (  # noqa: F401
    GraphClient,
    GraphScopes,
    probe_capability,
)
from libs.graph_client.errors import (  # noqa: F401
    Forbidden,
    GraphClientError,
    InsufficientConsent,
    MissingUserToken,
    NotFound,
    RateLimited,
)
from libs.graph_client.obo import (  # noqa: F401
    exchange_for_graph_token,
    obo_cache_key,
)
