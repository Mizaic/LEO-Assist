"""Helpers for deciding whether an OAuth login may receive a LEO session.

Atlas trace:
  DO: DO-FDC2F8CC
  DI: DI-C04323B0
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-FDC2F8CC")
"""

from __future__ import annotations


def may_issue_session(is_platform_admin: bool, resolved_roles: list[str]) -> bool:
    """Return True when the caller may receive a leo_session cookie.

    Platform admins may sign in with no HAS_ROLE edges. Everyone else needs
    at least one resolved LEO role.
    """
    if is_platform_admin:
        return True
    return bool(resolved_roles)
