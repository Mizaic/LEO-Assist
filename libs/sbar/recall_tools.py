"""Scoped recall tools for bounded referral retrieval (E3.1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

AuditFn = Callable[[str, dict[str, Any], dict[str, Any]], None]


@dataclass(frozen=True)
class RecallScope:
    tenant_id: str
    patient_id: str
    referral_id: str
    run_id: str
    allowed_chunk_ids: frozenset[str]


@dataclass
class RecallToolRegistry:
    """Fixed generic tools constrained to the pinned input manifest."""

    scope: RecallScope
    list_coded_facts: Callable[[], list[dict[str, Any]]]
    fetch_chunk: Callable[[str], dict[str, Any] | None]
    find_referral_reason: Callable[[], dict[str, Any] | None]
    audit: AuditFn | None = None
    fetch_count: int = 0
    audit_log: list[dict[str, Any]] = field(default_factory=list)

    def list_coded_facts_scoped(self) -> list[dict[str, Any]]:
        result = self.list_coded_facts()
        self._audit("list_coded_facts", {}, {"count": len(result)})
        return result

    def fetch_chunk_scoped(self, chunk_id: str) -> dict[str, Any] | None:
        cid = str(chunk_id or "").strip()
        if cid not in self.scope.allowed_chunk_ids:
            self._audit(
                "fetch_chunk",
                {"chunk_id": cid},
                {"error": "chunk_out_of_manifest"},
            )
            return None
        self.fetch_count += 1
        result = self.fetch_chunk(cid)
        self._audit("fetch_chunk", {"chunk_id": cid}, {"found": result is not None})
        return result

    def find_referral_reason_scoped(self) -> dict[str, Any] | None:
        result = self.find_referral_reason()
        self._audit("find_referral_reason", {}, {"found": result is not None})
        return result

    def _audit(
        self, tool_name: str, tool_input: dict[str, Any], tool_result: Any
    ) -> None:
        entry = {
            "tool_name": tool_name,
            "tool_input": tool_input,
            "tool_result": tool_result,
            "run_id": self.scope.run_id,
        }
        self.audit_log.append(entry)
        if self.audit is not None:
            self.audit(tool_name, tool_input, tool_result)
