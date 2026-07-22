"""
VT-7DE8E8ED -- Problem list chips show SNOMED code, term, and dated evidence.

Atlas trace:
    DO: DO-5D3EA371
    DI: DI-7DE8E8ED

These are static-source assertions on the router and query module source
files. No live Neo4j connection is required, matching the sibling
test_patients_epr_router.py convention.

Covers:
    AC1 - Mentions endpoint returns encounter id, date, and assertion.
    AC2 - Mentions query reads :DOCUMENTS off Encounter, not the bare
          patient-level HAS_* shortcut edges (which carry no properties).
    AC3 - Mentions are ordered most-recent-first.
    AC4 - Mention-detail endpoint returns the evidence sentence, name
          (preferred term), and read code for one dated mention.
    AC5 - Mention-detail 404s when no matching :DOCUMENTS link exists.
    AC6 - Both admin and scoped Cypher variants exist and carry the org
          guard on the scoped path.
    AC7 - Cypher strings live in a separate queries module (LOC limit).
"""

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
ROUTER = (
    ROOT / "services" / "analytics_api" / "app" / "routers" / "patients_epr_evidence.py"
)
QUERIES = (
    ROOT
    / "services"
    / "analytics_api"
    / "app"
    / "routers"
    / "patients_epr_evidence_queries.py"
)


def _read(p: pathlib.Path) -> str:
    return p.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# AC7 - query extraction
# ---------------------------------------------------------------------------


def test_ac7_cypher_extracted_to_queries_module():
    """Cypher strings must live in patients_epr_evidence_queries.py."""
    router_src = _read(ROUTER)
    queries_src = _read(QUERIES)
    assert QUERIES.exists(), "patients_epr_evidence_queries.py must exist"
    assert "patients_epr_evidence_queries" in router_src
    assert "MATCH (p)-[:HAS_ENCOUNTER]->" not in router_src
    assert "MATCH (p)-[:HAS_ENCOUNTER]->" in queries_src


# ---------------------------------------------------------------------------
# AC2 - reads :DOCUMENTS, not the bare patient-level shortcut edges
# ---------------------------------------------------------------------------


def test_ac2_mentions_query_reads_documents_relationship_not_shortcut():
    """Evidence must come from :DOCUMENTS, since HAS_* edges carry no props."""
    queries_src = _read(QUERIES)
    assert "-[r:DOCUMENTS]->(s)" in queries_src
    assert "r.evidence_sentence" in queries_src
    assert "r.context" in queries_src


def test_ac2_mentions_query_matches_by_concept_id():
    queries_src = _read(QUERIES)
    assert "toString(s.conceptId) = toString($concept_id)" in queries_src


# ---------------------------------------------------------------------------
# AC3 - most-recent-first ordering
# ---------------------------------------------------------------------------


def test_ac3_mentions_ordered_most_recent_first():
    queries_src = _read(QUERIES)
    assert "ORDER BY coalesce(e.date, r.coded_at) DESC" in queries_src


# ---------------------------------------------------------------------------
# AC1 / AC4 - response shapes
# ---------------------------------------------------------------------------


def test_ac1_mentions_endpoint_returns_encounter_date_and_assertion():
    router_src = _read(ROUTER)
    assert "class ConceptMention(BaseModel):" in router_src
    assert "encounter_id: str" in router_src
    assert "encounter_date: Optional[str]" in router_src
    assert "assertion: Optional[str]" in router_src


def test_ac4_mention_detail_endpoint_returns_evidence_and_preferred_term():
    router_src = _read(ROUTER)
    assert "class ConceptMentionDetail(BaseModel):" in router_src
    assert "evidence_sentence: Optional[str]" in router_src
    assert "name: Optional[str]" in router_src
    assert "read_code: Optional[str]" in router_src


def test_ac1_mentions_route_declared():
    router_src = _read(ROUTER)
    assert '"/patients/{patient_id}/coded-entities/{concept_id}/mentions"' in router_src


def test_ac4_mention_detail_route_declared():
    router_src = _read(ROUTER)
    assert (
        '"/patients/{patient_id}/coded-entities/{concept_id}/mentions/{encounter_id}"'
        in router_src
    )


# ---------------------------------------------------------------------------
# AC5 - 404 on missing mention
# ---------------------------------------------------------------------------


def test_ac5_mention_detail_raises_404_when_not_found():
    router_src = _read(ROUTER)
    assert "raise HTTPException(status_code=404" in router_src


# ---------------------------------------------------------------------------
# AC6 - admin + scoped Cypher variants
# ---------------------------------------------------------------------------


def test_ac6_admin_and_scoped_mentions_queries_exist():
    queries_src = _read(QUERIES)
    assert "GET_CONCEPT_MENTIONS_ADMIN" in queries_src
    assert "GET_CONCEPT_MENTIONS_SCOPED" in queries_src
    assert "_ORG_GUARD" in queries_src


def test_ac6_admin_and_scoped_mention_detail_queries_exist():
    queries_src = _read(QUERIES)
    assert "GET_CONCEPT_MENTION_DETAIL_ADMIN" in queries_src
    assert "GET_CONCEPT_MENTION_DETAIL_SCOPED" in queries_src


def test_ac6_router_picks_admin_or_scoped_by_caller_scope():
    router_src = _read(ROUTER)
    assert (
        "def _pick_query(scope: CallerScope, admin_q: str, scoped_q: str)" in router_src
    )
    assert "scope.is_admin" in router_src
