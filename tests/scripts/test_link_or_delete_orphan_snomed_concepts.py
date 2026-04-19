"""VT-LEO-AI-510 (DI-LEO-AI-528) tests for the schema-unification migration.

The migration script
``scripts/migrations/2026_link_or_delete_orphan_snomed_concepts.py`` rewires
legacy `(:SnomedConcept {conceptId})` guidance nodes onto the canonical
`(:Concept {id})` graph, then deletes orphans. The script must be:

  TC-001  Static-source: every legacy node selector excludes the patient
          coding subgraph (`NOT (legacy)<-[:DOCUMENTS]-()`). The patient
          subgraph also writes `:SnomedConcept` and must NEVER be touched.
  TC-002  Static-source: writes are guarded by --apply (default-safe);
          --dry-run and --apply are mutually exclusive.
  TC-003  Static-source: rewire query is content-addressed (MERGE on the
          canonical edge, DELETE on the legacy edge) so a second pass is a
          no-op.
  TC-004  Behaviour: dry-run never invokes the mutating MERGE / DELETE
          queries (the operator can preview safely).
  TC-005  Behaviour: apply runs MERGE_TWINS, then one rewire per relationship
          type, then DELETE_ORPHANS, then AUDIT_REMAINING -- in that exact
          order so partial failure leaves a recoverable graph.
  TC-006  Behaviour: rewire is invoked once per guidance relationship type
          (HAS_CRITERIA, HAS_ACTION, APPLIES_TO, INCLUDES_CONCEPT) and never
          for relationship types outside the guidance subgraph.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

# The migration filename starts with a digit (year prefix) so it cannot be
# imported via the normal package syntax. Load it from disk via importlib
# so the test exercises the same source the operator runs.
import importlib.util  # noqa: E402

_MIGRATION_PATH = REPO / "scripts" / "migrations" / "2026_link_or_delete_orphan_snomed_concepts.py"
_MIGRATION_MODULE_NAME = "link_or_delete_orphan_snomed_concepts"
_spec = importlib.util.spec_from_file_location(
    _MIGRATION_MODULE_NAME, _MIGRATION_PATH
)
assert _spec is not None and _spec.loader is not None
migration = importlib.util.module_from_spec(_spec)
# Register in sys.modules BEFORE exec_module so @dataclass and other
# decorators that introspect cls.__module__ can resolve the module.
sys.modules[_MIGRATION_MODULE_NAME] = migration
_spec.loader.exec_module(migration)


# ---- Static-source guardrails (TC-001..TC-003) -------------------------------


def _module_source() -> str:
    path = Path(migration.__file__)
    return path.read_text(encoding="utf-8")


class TestStaticGuardrails:
    """Critical safety properties pinned by reading the script's own source."""

    def test_every_legacy_selector_excludes_patient_documents_subgraph(self):
        # The patient coding subgraph (libs/cypher/documents_queries.py)
        # writes `:SnomedConcept` connected via `:DOCUMENTS`. Any selector
        # that touches `:SnomedConcept` MUST exclude that path. We pin the
        # invariant by counting MATCH (legacy:SnomedConcept ...) blocks
        # and asserting each one carries the documents guard.
        source = _module_source()
        cypher_blocks = source.split("MATCH (legacy:SnomedConcept")
        # First chunk is the imports/module head; every subsequent chunk
        # opens a Cypher MATCH that we must guard.
        for idx, chunk in enumerate(cypher_blocks[1:], start=1):
            head = chunk.split('"""')[0]
            assert "NOT (legacy)<-[:DOCUMENTS]-()" in head, (
                f"MATCH (legacy:SnomedConcept) block #{idx} is missing the "
                "patient-coding guard. Without it, this query would mutate "
                "patient :SnomedConcept nodes connected via :DOCUMENTS."
            )

    def test_apply_and_dry_run_are_mutually_exclusive_and_required(self):
        source = _module_source()
        assert 'parser.error("Pass --dry-run or --apply explicitly.")' in source
        assert (
            'parser.error("--apply and --dry-run are mutually exclusive.")'
            in source
        )

    def test_rewire_template_is_idempotent(self):
        # MERGE on the canonical edge means a second pass finds an existing
        # edge instead of inserting a duplicate. DELETE on the legacy edge
        # means a second pass finds nothing to migrate. Together those make
        # the rewire safe to re-run.
        template = migration._REWIRE_REL_TEMPLATE
        assert "MERGE (parent)-[new_r:{rel}]->(canonical)" in template
        assert "DELETE r" in template
        # Properties must be preserved.
        assert "SET new_r += props" in template

    def test_orphan_delete_only_targets_unreferenced_legacy_nodes(self):
        # Belt-and-braces: the delete query must require zero relationships
        # of any kind AND a known guidance source tag.
        delete_q = migration._DELETE_ORPHANS
        assert "NOT (legacy)--()" in delete_q
        assert "guidance_rule_extraction" in delete_q
        assert "guidance_migration_2026" in delete_q


# ---- Behavioural tests with a stub session (TC-004..TC-006) ------------------


class _SingleResult:
    def __init__(self, value: dict[str, Any] | None) -> None:
        self._value = value

    def single(self):
        return self._value

    def __iter__(self):
        return iter([] if self._value is None else [self._value])


class _StubSession:
    """A minimal Neo4j session double for unit tests.

    Records every `.run(query, **params)` call in `.calls` so tests can
    assert ordering and parameterisation. Returns canned responses keyed
    by query identity (the script's module-level Cypher constants).
    """

    def __init__(self, responses: dict[str, dict[str, Any] | list[dict[str, Any]]]):
        self._responses = responses
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def run(self, query: str, **params: Any) -> _SingleResult:
        self.calls.append((query, params))
        canned = self._responses.get(query)
        if canned is None:
            return _SingleResult(None)
        if isinstance(canned, list):
            # AUDIT_REMAINING returns rows -- emulate by yielding the first
            # element on .single() and the full list on iteration.
            return _SingleResult(canned[0] if canned else None)
        return _SingleResult(canned)


class TestRunMigration:
    """End-to-end behaviour driven by a stub Neo4j session."""

    def _responses(self) -> dict[str, Any]:
        return {
            migration._COUNT_GUIDANCE_LEGACY: {"n": 7},
            migration._MERGE_CANONICAL_TWINS: {"twins": 7},
            migration._DELETE_ORPHANS: {"deleted": 5},
            migration._AUDIT_REMAINING: [],
            **{
                migration._REWIRE_REL_TEMPLATE.format(rel=r): {"rewired": 3}
                for r in migration.GUIDANCE_REL_TYPES
            },
            **{
                migration._COUNT_REL_TEMPLATE.format(rel=r): {"rewired": 3}
                for r in migration.GUIDANCE_REL_TYPES
            },
        }

    def test_dry_run_never_invokes_mutating_queries(self):
        session = _StubSession(self._responses())
        stats = migration.run_migration(session, apply=False)

        executed = [q for q, _ in session.calls]
        assert migration._MERGE_CANONICAL_TWINS not in executed, (
            "Dry-run must never run the canonical MERGE -- it would mutate "
            "the graph even though no relationships are rewired."
        )
        assert migration._DELETE_ORPHANS not in executed
        assert migration._AUDIT_REMAINING not in executed
        for rel in migration.GUIDANCE_REL_TYPES:
            assert (
                migration._REWIRE_REL_TEMPLATE.format(rel=rel) not in executed
            ), (
                f"Dry-run executed the {rel} rewire query, which MERGEs and "
                "DELETEs. Use _COUNT_REL_TEMPLATE for previews instead."
            )
        # The dry-run still surfaces a useful preview.
        assert stats.pre_legacy_count == 7
        assert stats.twins_merged == 7
        for rel in migration.GUIDANCE_REL_TYPES:
            assert stats.rels_rewired[rel] == 3

    def test_apply_runs_merge_then_rewires_then_delete_then_audit(self):
        session = _StubSession(self._responses())
        stats = migration.run_migration(session, apply=True)

        executed = [q for q, _ in session.calls]
        # Ordering: count -> merge twins -> rewires -> delete -> audit.
        assert executed[0] == migration._COUNT_GUIDANCE_LEGACY
        assert executed[1] == migration._MERGE_CANONICAL_TWINS
        rewire_indices = []
        for rel in migration.GUIDANCE_REL_TYPES:
            q = migration._REWIRE_REL_TEMPLATE.format(rel=rel)
            assert q in executed, f"Rewire query for {rel} was not executed"
            rewire_indices.append(executed.index(q))
        # Every rewire happens AFTER the merge of canonical twins.
        assert all(i > 1 for i in rewire_indices)
        # The orphan delete + audit are the LAST writes / reads.
        last_delete = executed.index(migration._DELETE_ORPHANS)
        last_audit = executed.index(migration._AUDIT_REMAINING)
        assert all(i < last_delete for i in rewire_indices)
        assert last_audit > last_delete
        # Stats round-trip.
        assert stats.twins_merged == 7
        assert stats.orphans_deleted == 5

    def test_rewire_runs_exactly_once_per_guidance_relationship_type(self):
        session = _StubSession(self._responses())
        migration.run_migration(session, apply=True)

        executed = [q for q, _ in session.calls]
        for rel in migration.GUIDANCE_REL_TYPES:
            q = migration._REWIRE_REL_TEMPLATE.format(rel=rel)
            assert executed.count(q) == 1
        # Specifically confirm DOCUMENTS is NOT a guidance rel-type.
        assert "DOCUMENTS" not in migration.GUIDANCE_REL_TYPES


# ---- Schema invariant pin (TC-006 belt) --------------------------------------


def test_guidance_relationship_types_are_a_closed_known_set():
    """Adding a new guidance rel-type without updating the migration would
    silently leave legacy nodes behind. Pin the set so any change triggers
    a code review of the migration script."""
    assert migration.GUIDANCE_REL_TYPES == (
        "HAS_CRITERIA",
        "HAS_ACTION",
        "APPLIES_TO",
        "INCLUDES_CONCEPT",
    )


def test_canonical_property_names_match_snomed_loader():
    """The canonical SNOMED loader (services/terminology/scripts/loaders/
    snomed_concept.py) writes `id` / `preferred_term` / `semantic_tag`.
    The migration's MERGE must use the same property names so terminology
    search and guidance reads project the same fields."""
    # Whitespace-tolerant: the column-aligned SET clause has variable
    # internal spacing; what matters is the property name appears.
    import re

    merge = migration._MERGE_CANONICAL_TWINS
    assert "(canonical:Concept {id: legacy.conceptId})" in merge
    assert re.search(r"canonical\.preferred_term\s*=", merge)
    assert re.search(r"canonical\.semantic_tag\s*=", merge)
