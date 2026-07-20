"""VT-F266ECFB -- resolve scoped to active packages; SNOMED unchanged."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from services.terminology_api.app.queries.terminology import (
    BATCH_EXACT_QUERY,
    EXACT_SURFACE_FORM_QUERY,
)
from services.terminology_api.app.services.cache import TerminologyCache


class TestCacheKeyIncludesOrg:
    def test_different_org_different_key(self):
        cache = TerminologyCache.__new__(TerminologyCache)
        k1 = TerminologyCache.generate_key(
            cache, "flare", None, True, org_id="org-A", package_fingerprint="aaa"
        )
        k2 = TerminologyCache.generate_key(
            cache, "flare", None, True, org_id="org-B", package_fingerprint="aaa"
        )
        assert k1 != k2
        assert "org-A" in k1
        assert "v2:" in k1


class TestSurfaceFormQueryGatesLocal:
    def test_batch_exact_includes_package_exists(self):
        assert "LocalTerminologyPackage" in BATCH_EXACT_QUERY
        assert "$org_id" in BATCH_EXACT_QUERY
        assert "is_local" in BATCH_EXACT_QUERY

    def test_exact_surface_form_includes_package_exists(self):
        assert "LocalTerminologyPackage" in EXACT_SURFACE_FORM_QUERY
        assert "$org_id" in EXACT_SURFACE_FORM_QUERY

    def test_snomed_path_not_gated_by_package_only(self):
        # Non-local concepts still match when is_local is false.
        assert "coalesce(cs.is_local, false) = false" in BATCH_EXACT_QUERY


class TestResolverPassesOrgId:
    @patch(
        "services.terminology_api.app.services.coding_resolver.TerminologyCache"
    )
    def test_batch_exact_receives_org_id(self, MockCache):
        from services.terminology_api.app.services.coding_resolver import (
            CodingResolver,
        )

        mock_cache = MagicMock()
        MockCache.return_value = mock_cache
        mock_cache.generate_key.return_value = "k1"
        mock_cache.mget.return_value = {}
        mock_cache.msetex.return_value = None

        session = MagicMock()
        session.run.side_effect = [
            # fingerprint
            [{"id": "pkg-1", "version": 1}],
            # batch exact (surface form probe skipped when already True)
            [],
        ]
        resolver = CodingResolver()
        resolver._surface_form_exact_ok = True
        resolver.resolve_candidates(
            ["acne"],
            neo4j_session=session,
            org_id="org-A",
            enrich_lab_domain=False,
        )
        batch_calls = [
            c
            for c in session.run.call_args_list
            if c.args and "UNWIND $normalized_terms" in str(c.args[0])
        ]
        assert batch_calls
        assert batch_calls[0].kwargs.get("org_id") == "org-A"


class TestResolveRequestSchema:
    def test_resolve_request_declares_org_id(self):
        import ast
        from pathlib import Path

        src = Path(
            "services/terminology_api/app/routers/resolve.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(src)
        found = False
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name == "ResolveRequest":
                names = {
                    n.target.id
                    for n in node.body
                    if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)
                }
                found = "org_id" in names
        assert found
