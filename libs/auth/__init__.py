"""Shared authentication and authorization library.

Provides JWT validation, tenant context extraction, org-scoped access control,
and FastAPI dependency injection for all services that require authentication.
"""

__all__ = [
    "CallerScope",
    "TenantContext",
    "get_caller_scope",
    "get_tenant_context",
]


def __getattr__(name: str):
    if name in {"CallerScope", "get_caller_scope"}:
        from libs.auth.org_scope import CallerScope, get_caller_scope

        return {"CallerScope": CallerScope, "get_caller_scope": get_caller_scope}[name]
    if name in {"TenantContext", "get_tenant_context"}:
        from libs.auth.tenant_context import TenantContext, get_tenant_context

        return {"TenantContext": TenantContext, "get_tenant_context": get_tenant_context}[name]
    raise AttributeError(name)
