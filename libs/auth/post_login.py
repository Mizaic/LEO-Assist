"""Resolve the path to open after a successful login.

Atlas trace:
  DO: DO-308DD1A6
  DI: DI-D49BCE55
"""

from __future__ import annotations

_GENERIC_HOMES = frozenset(
    {
        "/",
        "/sign-in",
        "/auth/callback",
        "/dashboard",
        "/care/dashboard",
    }
)
_PLATFORM_ADMIN_LANDING = "/admin/knowledge"
_DEFAULT_LANDING = "/dashboard"


def post_login_path(next_url: str, *, is_platform_admin: bool) -> str:
    """Keep deep links. Send platform admins to Knowledge from a generic home."""
    path = next_url if next_url.startswith("/") else f"/{next_url.lstrip('/')}"
    if path in {"/", "/sign-in", "/auth/callback"}:
        path = _DEFAULT_LANDING
    if is_platform_admin and path in _GENERIC_HOMES:
        return _PLATFORM_ADMIN_LANDING
    return path
