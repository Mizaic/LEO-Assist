"""Typed exceptions for the Microsoft Graph client.

Atlas trace:
  DO: DO-313A49AE
  DI: DI-31F4C232, DI-5A18A227, DI-6CF7FCE0
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-313A49AE")

The router (`services/api/app/routers/admin_entra.py`) maps each
exception type to a stable HTTP response shape so the UI can degrade
cleanly without parsing Graph error bodies.
"""

from __future__ import annotations


class GraphClientError(Exception):
    """Base for all Graph client failures."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        graph_error_code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.graph_error_code = graph_error_code or ""


class MissingUserToken(GraphClientError):
    """A Graph call was attempted without a delegated user-token.

    Raised before any HTTP call leaves the process so a buggy code path
    cannot accidentally fall back to client-credentials. Caller should
    return HTTP 401 to the UI.
    """


class InsufficientConsent(GraphClientError):
    """The signed-in admin's tenant has not granted one of the delegated
    Graph permissions LEO is asking for.

    Maps to Graph errors:
      - 403 Authorization_RequestDenied / Authorization_IdentityNotFound
      - 401 InvalidAuthenticationToken with reason `consent_required`
      - 401 invalid_grant with suberror `consent_required` (OBO)
    Caller should return HTTP 403 ``{code: "consent_required"}`` and
    surface ``admin_consent_url`` so the admin can request consent.
    """


class RateLimited(GraphClientError):
    """Graph returned 429 Too Many Requests.

    The client honours ``Retry-After`` once before re-raising.
    """

    def __init__(
        self,
        message: str,
        *,
        retry_after_seconds: int = 0,
        status_code: int | None = 429,
    ) -> None:
        super().__init__(message, status_code=status_code)
        self.retry_after_seconds = retry_after_seconds


class NotFound(GraphClientError):
    """Graph returned 404 (group / user / domain does not exist)."""


class Forbidden(GraphClientError):
    """Graph returned 403 for a reason other than missing consent.

    Typically: the signed-in admin is not a privileged role in the
    target tenant (e.g. tries to write groups when their Entra account
    is a Member, not a Global Administrator or Group Administrator).
    """
