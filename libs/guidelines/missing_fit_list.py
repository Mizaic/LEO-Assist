"""Filter a list of referrals that appear to lack a FIT.

A mass-bypass (not_required / exempt) match drops the referral.

Atlas trace: DI-55CCC312
"""

from __future__ import annotations

from typing import Any


def in_missing_fit_list(matches: list[dict[str, Any]] | None) -> bool:
    """True when a required rule is missing FIT and no exempt rule matched."""
    rows = [m for m in (matches or []) if isinstance(m, dict)]
    if any(
        m.get("investigation_policy") == "not_required"
        or m.get("investigation_status") == "exempt"
        for m in rows
    ):
        return False
    return any(
        m.get("investigation_policy") == "required"
        and m.get("investigation_status") == "missing"
        for m in rows
    )


def filter_missing_fit_referrals(
    referrals: list[dict[str, Any]],
    *,
    organization_id: str,
) -> list[dict[str, Any]]:
    """Keep tenant-scoped referrals that belong on the missing-FIT list."""
    org = (organization_id or "").strip()
    if not org:
        return []
    out: list[dict[str, Any]] = []
    for row in referrals:
        if str(row.get("organization_id") or "") != org:
            continue
        if in_missing_fit_list(row.get("matched_rules")):
            out.append(row)
    return out
