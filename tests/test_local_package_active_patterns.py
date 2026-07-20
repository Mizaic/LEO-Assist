"""VT-F266ECFB -- active-patterns loader (global + tenant, draft excluded)."""

from __future__ import annotations

from unittest.mock import MagicMock

from libs.ner.local_concept_recovery import (
    dedupe_tenant_over_global,
    load_active_package_patterns,
)


def _row(
    *,
    normalized: str,
    concept_id: str,
    scope: str,
    org_id: str | None = None,
    form: str | None = None,
) -> dict:
    return {
        "normalized": normalized,
        "form": form or normalized,
        "concept_id": concept_id,
        "fsn": f"{normalized} (LEO local)",
        "semantic_tag": "finding",
        "package_scope": scope,
        "package_org_id": org_id,
        "package_id": f"pkg-{scope}-{org_id or 'g'}",
    }


class TestDedupeTenantWins:
    def test_tenant_wins_same_normalized(self):
        rows = [
            _row(
                normalized="flare",
                concept_id="LEO-LOCAL-GLOBAL-FLARE",
                scope="global",
            ),
            _row(
                normalized="flare",
                concept_id="LEO-LOCAL-TENANT-FLARE",
                scope="tenant",
                org_id="org-A",
            ),
        ]
        patterns = dedupe_tenant_over_global(rows)
        assert len(patterns) == 1
        assert patterns[0].concept_id == "LEO-LOCAL-TENANT-FLARE"


class TestLoadActivePatterns:
    def test_org_a_includes_global_and_tenant_a(self):
        client = MagicMock()
        client.run.return_value = [
            _row(
                normalized="global-only",
                concept_id="LEO-LOCAL-G",
                scope="global",
            ),
            _row(
                normalized="tenant-a",
                concept_id="LEO-LOCAL-A",
                scope="tenant",
                org_id="org-A",
            ),
        ]
        patterns = load_active_package_patterns(client, "org-A")
        ids = {p.concept_id for p in patterns}
        assert ids == {"LEO-LOCAL-G", "LEO-LOCAL-A"}
        client.run.assert_called_once()
        assert client.run.call_args.kwargs.get("org_id") == "org-A"

    def test_no_org_global_only_query(self):
        client = MagicMock()
        client.run.return_value = [
            _row(
                normalized="global-only",
                concept_id="LEO-LOCAL-G",
                scope="global",
            ),
        ]
        patterns = load_active_package_patterns(client, None)
        assert [p.concept_id for p in patterns] == ["LEO-LOCAL-G"]
        assert client.run.call_args.kwargs.get("org_id") is None

    def test_draft_rows_never_returned_by_query_contract(self):
        """Loader trusts Cypher status='active'; empty result for draft-only."""
        client = MagicMock()
        client.run.return_value = []
        patterns = load_active_package_patterns(client, "org-A")
        assert patterns == []
