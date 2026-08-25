"""DI-LEO-AI-528 schema-invariant tests for the guidance subsystem.

Pins the canonical-vs-legacy contract across every production write site
so the dual-graph bug (DI-LEO-AI-508 / R-LEO-AI-508) cannot regress.

  TC-001  Guidance writes (criteria / action / applies_to / promotion)
          MUST MERGE on the canonical `(:Concept {id})` -- never on the
          legacy parallel `(:SnomedConcept {conceptId})`.
  TC-002  Guidance reads in the API router and the bitmap compiler MUST
          tolerate either label (coalesce on id properties / project
          via coalesce on display properties), so the migration in
          scripts/migrations/2026_link_or_delete_orphan_snomed_concepts.py
          can run on any environment without breaking the running app.
  TC-003  The `(:SnomedConcept ...)` label may STILL appear in:
            - the patient coding subgraph (libs/cypher/documents_queries.py
              + libs/cypher/remediation_queries.py + GDS projection +
              encounter_coding_agent), which is a separate subsystem; and
            - the verifier's dual-graph fallback in
              services/api/app/services/guidance_rule_edit.py, which
              tolerates legacy data until migration completes; and
            - the migration script itself (scripts/migrations/2026_*),
              which exists to remove the legacy nodes; and
            - the test suite, which exercises both paths.
          NO OTHER PRODUCTION GUIDANCE FILE may contain that label.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


# ---- TC-001: canonical writes ------------------------------------------------


def _read(path: str) -> str:
    return (REPO / path).read_text(encoding="utf-8")


GENERATOR = "services/api/app/services/guidance_rule_generator.py"
ROUTER = "services/api/app/routers/guidance_rules.py"
COMPILER = "services/terminology_api/app/services/guideline_compiler.py"


class TestCanonicalWrites:
    """No production guidance write may MERGE on the legacy label."""

    def test_generator_writes_only_canonical_concept(self):
        src = _read(GENERATOR)
        assert "MERGE (concept:Concept {id: $concept_id})" in src
        assert "MERGE (proc:Concept {id: $concept_id})" in src
        # The legacy label MUST NOT be MERGEd anywhere in the generator.
        # (Comments referencing it for documentation are fine -- but no
        # MERGE statement may target it.)
        for line in src.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith('"""'):
                continue
            assert "MERGE (" not in stripped or ":SnomedConcept" not in stripped, (
                f"Generator must not MERGE :SnomedConcept; offending line: {line!r}"
            )

    def test_router_promotion_writes_only_canonical_concept(self):
        src = _read(ROUTER)
        assert "MERGE (concept:Concept {id: c.concept_id})" in src
        for line in src.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith('"""'):
                continue
            assert "MERGE (" not in stripped or ":SnomedConcept" not in stripped, (
                f"Router must not MERGE :SnomedConcept; offending line: {line!r}"
            )


# ---- TC-002: dual-tolerant reads ---------------------------------------------


class TestDualTolerantReads:
    """Reads must coalesce id + display fields so canonical and legacy bind."""

    def test_router_list_query_projects_canonical_first(self):
        src = _read(ROUTER)
        # Every router list/detail query coalesces concept.id over conceptId.
        assert "coalesce(concept.id, concept.conceptId)" in src
        assert (
            "coalesce(concept.preferred_term, concept.fsn, concept.term, "
            "concept.id, concept.conceptId)"
        ) in src

    def test_router_surfaces_updated_at_and_reviewer(self):
        # DI-LEO-AI-528 AC-001 / AC-002: the Active list needs these
        # fields to sort stalest-first and label "Updated <relative>".
        src = _read(ROUTER)
        assert "coalesce(rule.updatedAt, rule.createdAt) AS updated_at" in src
        assert "rule.reviewedAt AS reviewed_at" in src
        assert "rule.reviewedBy AS reviewed_by" in src
        # And the JSON serialiser surfaces them on the API response.
        assert '"updated_at": str(r.get("updated_at")' in src
        assert '"reviewed_at": str(r.get("reviewed_at")' in src
        assert '"reviewed_by": str(r.get("reviewed_by")' in src

    def test_compiler_active_rules_unlabel_concept_and_proc(self):
        src = _read(COMPILER)
        # Concept and proc are both unlabeled in the production fetch
        # query so canonical AND legacy nodes bind.
        assert "OPTIONAL MATCH (grp)-[hc:HAS_CRITERIA]->(concept)\n" in src
        assert (
            "MATCH (rule:AppropriatenessRule)-[:HAS_ACTION_GROUP]->(:ActionGroup)-[ha:HAS_ACTION]->(proc)"
            in src
        )
        # ID and display projections are coalesced.
        assert "coalesce(concept.id, concept.conceptId)" in src
        assert "coalesce(proc.id, proc.conceptId)" in src

    def test_compiler_applies_to_query_unlabels_concept(self):
        src = _read(COMPILER)
        assert "MATCH (rule:AppropriatenessRule {status: 'active'})-[at:APPLIES_TO]->(concept)\n" in src

    def test_compiler_closure_walks_canonical_isa(self):
        # The legacy generator NEVER wrote IS_A edges between :SnomedConcept
        # nodes -- only the canonical SNOMED loader writes IS_A. The closure
        # MUST therefore traverse :Concept's IS_A graph to recover real
        # descendants (the previous query silently fell back to exact match).
        src = _read(COMPILER)
        assert '(d:Concept)-[:IS_A*1..' in src
        assert '(t)-[:IS_A*1..' in src
        # The seed is unlabeled so either label binds as the starting
        # concept, but IS_A traversal stays on canonical.
        assert "(t:Concept AND t.id = $concept_id)" in src
        assert "(t:SnomedConcept AND t.conceptId = $concept_id)" in src


# ---- TC-003: legacy label is now confined to known places --------------------


# Files that are EXPECTED to mention the legacy label (and why).
ALLOWED_LEGACY_REFERENCES = {
    # Patient coding subgraph -- a separate subsystem; this label is the
    # legitimate node type for patient-coded findings.
    "libs/cypher/documents_queries.py",
    "libs/cypher/remediation_queries.py",
    "services/api/app/services/patient_graph_writer.py",
    "services/api/app/routers/patients.py",
    "libs/pipeline_graph/subgraphs/encounter_coding_agent.py",
    # GDS projection (analytics) -- node-type label, not a Cypher MERGE.
    "services/analytics_api/app/services/gds_projection_manager.py",
    # The verifier dual-graph fallback (will be removed after migration
    # rolls out everywhere).
    "services/api/app/services/guidance_rule_edit.py",
    # The migration script itself.
    "scripts/migrations/2026_link_or_delete_orphan_snomed_concepts.py",
}


def test_no_unexpected_legacy_label_mentions_in_guidance_production_code():
    """Sweep production guidance files; flag any new :SnomedConcept mention."""
    guidance_paths = [
        "services/api/app/services/guidance_rule_generator.py",
        "services/api/app/routers/guidance_rules.py",
        "services/terminology_api/app/services/guideline_compiler.py",
    ]
    for rel in guidance_paths:
        src = _read(rel)
        # Comments and docstrings may mention the label for documentation.
        # Only flag actual Cypher patterns -- those are MERGE / MATCH /
        # OPTIONAL MATCH statements that bind a node by label.
        for line in src.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("//"):
                continue
            # The compiler's _closure_ids is the one production file that
            # legitimately mentions the legacy label inside a Cypher string
            # (its dual-tolerant seed match). All other Cypher writes / reads
            # in guidance must NOT hardcode the label.
            if rel.endswith("guideline_compiler.py") and "t:SnomedConcept" in line:
                continue
            assert ":SnomedConcept" not in line, (
                f"Unexpected :SnomedConcept reference in {rel}: {line!r}\n"
                "If this is intentional (e.g. a new dual-graph fallback), "
                "add the file path to ALLOWED_LEGACY_REFERENCES with a note."
            )
