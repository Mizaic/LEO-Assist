"""
VT-7DE8E8ED -- Problem list chips show SNOMED code, term, and dated evidence.

Atlas trace:
    DO: DO-5D3EA371
    DI: DI-7DE8E8ED

These are static-source assertions on the router and query module source
files. No live Neo4j connection is required, matching the sibling
test_patients_epr_router.py convention.

Covers:
    AC1 - Mentions endpoint returns source id/type, date, and assertion.
    AC2 - Mentions query reads :DOCUMENTS off all three source node types
          (Encounter, Chunk via DocumentReference, Communication), not the
          bare patient-level HAS_* shortcut edges (which carry no
          properties) and not just the Encounter path.
    AC3 - Mentions are ordered most-recent-first.
    AC4 - Mention-detail endpoint returns the evidence sentence, name
          (preferred term), and read code for one dated mention.
    AC5 - Mention-detail 404s when no matching :DOCUMENTS link exists, and
          400s on an invalid source_type.
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
# AC2 - all three :DOCUMENTS source types, not just Encounter
# ---------------------------------------------------------------------------


def test_ac2_mentions_query_covers_encounter_source():
    queries_src = _read(QUERIES)
    assert "(p)-[:HAS_ENCOUNTER]->(src:Encounter)-[r:DOCUMENTS]->(s)" in queries_src


def test_ac2_mentions_query_covers_document_chunk_source():
    """Coded entities from the document/chunk pipeline must not be dropped.

    :DOCUMENTS can hang off a :Chunk reached via the patient's
    :DocumentReference, per libs/cypher/documents_queries.py
    _VALID_SOURCE_LABELS. Missing this branch is why a chip could show
    'No recorded mentions found' despite being on the problem list.
    """
    queries_src = _read(QUERIES)
    assert "HAS_DOCUMENT_REFERENCE|HAS_DOCUMENT" in queries_src
    assert "-[:HAS_CHUNK]->(src:Chunk)-[r:DOCUMENTS]->(s)" in queries_src


def test_ac2_mentions_query_covers_communication_source():
    queries_src = _read(QUERIES)
    assert "CommunicationRequest" in queries_src
    assert "-[:HAS_CONVERSATION]->(src:Communication)-[r:DOCUMENTS]->(s)" in queries_src


def test_ac2_mentions_query_matches_by_concept_id():
    queries_src = _read(QUERIES)
    assert queries_src.count("toString(s.conceptId) = toString($concept_id)") >= 3


# ---------------------------------------------------------------------------
# AC3 - most-recent-first ordering
# ---------------------------------------------------------------------------


def test_ac3_mentions_ordered_most_recent_first():
    queries_src = _read(QUERIES)
    assert "ORDER BY coalesce(source_date, coded_at) DESC" in queries_src


# ---------------------------------------------------------------------------
# AC1 / AC4 - response shapes
# ---------------------------------------------------------------------------


def test_ac1_mentions_endpoint_returns_source_date_and_assertion():
    router_src = _read(ROUTER)
    assert "class ConceptMention(BaseModel):" in router_src
    assert "source_id: str" in router_src
    assert "source_type: str" in router_src
    assert "source_date: Optional[str]" in router_src
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


def test_ac4_mention_detail_route_declared_with_source_type():
    router_src = _read(ROUTER)
    assert (
        '"/patients/{patient_id}/coded-entities/{concept_id}/mentions/'
        '{source_type}/{source_id}"' in router_src
    )


# ---------------------------------------------------------------------------
# AC5 - 404 on missing mention, 400 on invalid source_type
# ---------------------------------------------------------------------------


def test_ac5_mention_detail_raises_404_when_not_found():
    router_src = _read(ROUTER)
    assert "raise HTTPException(status_code=404" in router_src


def test_ac5_mention_detail_rejects_invalid_source_type():
    router_src = _read(ROUTER)
    assert "_VALID_SOURCE_TYPES" in router_src
    assert "raise HTTPException(\n            status_code=400" in router_src or (
        "status_code=400" in router_src
    )


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


def test_ac6_mention_detail_query_filters_by_source_type_param():
    """The detail query's UNION branches must gate on $source_type.

    Otherwise a source_id collision across node types (e.g. an Encounter
    and a Chunk sharing an id string) could return the wrong evidence.
    """
    queries_src = _read(QUERIES)
    assert queries_src.count("$source_type = ") >= 3
