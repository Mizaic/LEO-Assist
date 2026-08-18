"""Map Operations ignore-this-phrase rules onto Pipeline Guards rows.

Atlas: DI-DA60AC55 / DO-7E9AD55B / VT-AEA5D045
"""

from __future__ import annotations

from typing import Any


def as_ignore_phrase_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    mapped: list[dict[str, Any]] = []
    for row in rows:
        pattern = str(row.get("match_text") or row.get("context_regex") or "")
        mapped.append(
            {
                "rule_id": row.get("rule_id"),
                "family": "ignore_phrase",
                "rule_type": str(row.get("action") or "suppress"),
                "pattern": pattern,
                "summary": str(row.get("notes") or row.get("match_label") or ""),
                "active": bool(row.get("active", True)),
                "org_id": row.get("org_id"),
                "source": "custom",
                "readonly": False,
            }
        )
    return mapped
