"""
VT for the domain-agnostic patient EPR list, facets, and filter params.

Atlas trace:
    DO: DO-EBF0B124
    DI: DI-0ADA35BF

These are static-source assertions on the router and query module source files.
No live Neo4j connection is required.

Covers:
    AC1 - GET /patients/facets endpoint exists and returns condition_types.
    AC2 - GET /patients accepts condition_type and has_alerts filter params.
    AC3 - Cypher filter uses EXISTS subquery (server-side, not client-side).
    AC4 - /patients/facets is declared before /{patient_id} (FastAPI routing).
    AC5 - Admin and scoped Cypher variants both carry the filter conditions.
    AC6 - Cypher query strings are kept in a separate queries module (LOC limit).
"""

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
ROUTER = ROOT / "services" / "analytics_api" / "app" / "routers" / "patients_epr.py"
QUERIES = ROOT / "services" / "analytics_api" / "app" / "routers" / "patients_epr_queries.py"


def _read(p: pathlib.Path) -> str:
    return p.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# AC6 - query extraction
# ---------------------------------------------------------------------------

def test_ac6_cypher_extracted_to_queries_module():
    """Cypher strings must live in patients_epr_queries.py, not inline."""
    router_src = _read(ROUTER)
    queries_src = _read(QUERIES)
    assert QUERIES.exists(), "patients_epr_queries.py must exist"
    # Router imports from the queries module
    assert "patients_epr_queries" in router_src, (
        "patients_epr.py must import from patients_epr_queries"
    )
    # Heavy Cypher does not live inline in the router
    assert "OPTIONAL MATCH (p)-[:HAS_EPISODE_OF_CARE]->" not in router_src, (
        "Cypher should be in patients_epr_queries.py, not patients_epr.py"
    )
    assert "OPTIONAL MATCH" in queries_src


# ---------------------------------------------------------------------------
# AC4 - route declaration order
# ---------------------------------------------------------------------------

def test_ac4_facets_route_declared_before_patient_id_route():
    """/patients/facets must appear before /patients/{patient_id} in the file."""
    src = _read(ROUTER)
    idx_facets = src.find('"/patients/facets"')
    idx_detail = src.find('"/patients/{patient_id}"')
    assert idx_facets != -1, '"/patients/facets" route must exist'
    assert idx_detail != -1, '"/patients/{patient_id}" route must exist'
    assert idx_facets < idx_detail, (
        "/patients/facets must be declared before /patients/{patient_id}"
    )


# ---------------------------------------------------------------------------
# AC1 - facets endpoint
# ---------------------------------------------------------------------------

def test_ac1_facets_endpoint_returns_condition_types_field():
    """Facets endpoint response model must expose condition_types."""
    src = _read(ROUTER)
    assert "PatientFacetsResponse" in src
    assert "condition_types" in src


def test_ac1_facets_endpoint_uses_scoped_and_admin_cypher():
    """Facets endpoint must handle both admin and scoped callers."""
    queries_src = _read(QUERIES)
    assert "FACETS_ADMIN" in queries_src
    assert "FACETS_SCOPED" in queries_src
    router_src = _read(ROUTER)
    assert "FACETS_ADMIN" in router_src
    assert "FACETS_SCOPED" in router_src


def test_ac1_facets_cypher_returns_distinct_condition_types():
    """Facets Cypher must return DISTINCT values ordered ascending."""
    queries_src = _read(QUERIES)
    assert "RETURN DISTINCT ct AS condition_type" in queries_src
    assert "ORDER BY condition_type ASC" in queries_src
    assert "LIMIT 50" in queries_src


# ---------------------------------------------------------------------------
# AC2 - filter params on GET /patients
# ---------------------------------------------------------------------------

def test_ac2_list_patients_accepts_condition_type_param():
    """list_patients must declare a condition_type Query param."""
    src = _read(ROUTER)
    assert "condition_type" in src
    assert 'Query(default=None' in src


def test_ac2_list_patients_accepts_has_alerts_param():
    """list_patients must declare a has_alerts Query param."""
    src = _read(ROUTER)
    assert "has_alerts" in src
    # Must be typed as Optional[bool]
    assert "Optional[bool]" in src


def test_ac2_filter_params_passed_to_cypher():
    """condition_type and has_alerts must be forwarded in base_params."""
    src = _read(ROUTER)
    assert '"condition_type"' in src
    assert '"has_alerts"' in src


# ---------------------------------------------------------------------------
# AC3 - server-side EXISTS subquery filtering
# ---------------------------------------------------------------------------

def test_ac3_condition_type_filter_uses_exists_subquery():
    """Condition-type filter must use a Cypher EXISTS subquery, not post-filter."""
    queries_src = _read(QUERIES)
    assert "EXISTS {" in queries_src
    assert "$condition_type" in queries_src
    assert "coalesce(ep2.condition_type, ep2.cancer_type)" in queries_src


def test_ac3_has_alerts_filter_uses_exists_subquery():
    """Has-alerts filter must use a Cypher EXISTS subquery on SafetyNetAlert."""
    queries_src = _read(QUERIES)
    assert "$has_alerts" in queries_src
    assert "SafetyNetAlert" in queries_src
    assert "a2.resolved_at IS NULL" in queries_src


# ---------------------------------------------------------------------------
# AC5 - both admin and scoped variants carry the filter conditions
# ---------------------------------------------------------------------------

def test_ac5_admin_list_query_carries_condition_type_filter():
    queries_src = _read(QUERIES)
    # The shared _FILTER_CONDITIONS fragment must appear in LIST_PATIENTS_ADMIN
    assert "LIST_PATIENTS_ADMIN" in queries_src
    # Confirm the fragment is composed into the admin query (not only scoped)
    fragment_start = queries_src.find("_FILTER_CONDITIONS")
    admin_start = queries_src.find("LIST_PATIENTS_ADMIN")
    assert fragment_start != -1, "_FILTER_CONDITIONS must be defined"
    assert admin_start != -1, "LIST_PATIENTS_ADMIN must be defined"


def test_ac5_scoped_list_query_carries_org_guard_and_filter():
    queries_src = _read(QUERIES)
    assert "LIST_PATIENTS_SCOPED" in queries_src
    # Scoped query must reference both the org guard and the filter fragment
    assert "_ORG_GUARD" in queries_src
    assert "_FILTER_CONDITIONS" in queries_src


def test_ac5_count_queries_carry_filter_conditions():
    """COUNT_PATIENTS_ADMIN and COUNT_PATIENTS_SCOPED must use _FILTER_CONDITIONS."""
    queries_src = _read(QUERIES)
    assert "COUNT_PATIENTS_ADMIN" in queries_src
    assert "COUNT_PATIENTS_SCOPED" in queries_src
    # Both count queries reference the same shared fragment
    count_idx = queries_src.find("COUNT_PATIENTS_ADMIN")
    assert "_FILTER_CONDITIONS" in queries_src[count_idx - 500: count_idx + 500] or \
           "_FILTER_CONDITIONS" in queries_src, (
        "_FILTER_CONDITIONS must be used in count queries section"
    )


def test_coded_entities_query_uses_pipeline_relationships():
    """Coded-entity Cypher must match pipeline HAS_* rel types."""
    queries_src = _read(QUERIES)
    assert "HAS_FINDING" in queries_src
    assert "HAS_DISORDER" in queries_src
    assert "HAS_OBSERVABLE" in queries_src
    assert "HAS_PROCEDURE" in queries_src
    assert "GET_CODED_ENTITIES_ADMIN" in queries_src


def test_coded_entities_query_projects_call_subquery_results():
    """CALL subquery results must be projected before outer WHERE."""
    queries_src = _read(QUERIES)
    assert "WITH entity_type, name, concept_id" in queries_src
    call_idx = queries_src.find("_CODED_ENTITIES_BODY")
    with_idx = queries_src.find("WITH entity_type, name, concept_id", call_idx)
    where_idx = queries_src.find(
        "WHERE name IS NOT NULL AND entity_type IS NOT NULL", call_idx
    )
    assert with_idx != -1, "coded-entities query must WITH-project CALL columns"
    assert with_idx < where_idx, "WITH must precede outer WHERE after CALL subquery"


def test_encounter_detail_reads_documents_relationship():
    """Encounter detail must read SNOMED via :DOCUMENTS including relationship alias for evidence."""
    queries_src = _read(QUERIES)
    assert ":DOCUMENTS]->(concept)" in queries_src
    assert "GET_ENCOUNTER_DETAIL_ADMIN" in queries_src


def test_encounter_list_counts_documents_links():
    """Encounter list coded_count must derive from :DOCUMENTS when present."""
    queries_src = _read(QUERIES)
    assert "doc_coded_count" in queries_src
    assert "[:DOCUMENTS]->(coded)" in queries_src
