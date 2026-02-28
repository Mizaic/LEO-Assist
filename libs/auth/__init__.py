"""Shared authentication and authorization library.

Provides JWT validation, tenant context extraction, org-scoped access control,
and FastAPI dependency injection for all services that require authentication.
"""

from libs.auth.org_scope import CallerScope, get_caller_scope
from libs.auth.tenant_context import TenantContext, get_tenant_context

__all__ = [
    "CallerScope",
    "TenantContext",
    "get_caller_scope",
    "get_tenant_context",
]
