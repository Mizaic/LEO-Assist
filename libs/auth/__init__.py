"""Shared Azure AD authentication library.

Provides JWT validation, tenant context extraction, and FastAPI dependency
injection for all services that require authentication.
"""

from libs.auth.tenant_context import TenantContext, get_tenant_context

__all__ = ["TenantContext", "get_tenant_context"]
