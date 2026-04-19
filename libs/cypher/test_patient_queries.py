"""Cypher queries for the centralised test-patient library.

Test patients are reusable, reviewer-curated synthetic patient profiles
that exercise every part of the AI: NLP (reading clinical notes),
Episodes (building the patient story), Guidelines (rule firing) and
Summarisation (SBAR handover).

STORAGE -- IMPORTANT
--------------------
Test patients are CONFIG / TEST data, not patient data. They live in
the **knowledge graph** (KNOWLEDGE_GRAPH_NEO4J_URI) alongside SNOMED
concepts, surface forms, guidelines and rules. They MUST NEVER be
written to the patient graph (NEO4J_URI), which holds real PHI/PII.

The clone-from-real action therefore does cross-graph work:
    1. READ source patient subgraph from the patient graph.
    2. STRIP PII in Python (root props + free-text redactor).
    3. WRITE de-identified :TestPatient subgraph to the knowledge
       graph, MERGE'd against pre-loaded :Concept reference data.

Cypher in this module is split into READ_SOURCE_* (run on the patient
graph driver) and WRITE_TEST_* / list+update queries (run on the
knowledge graph driver). The Python service layer
(`services.test_patient_clone`) is the only place that holds both
drivers; no Cypher in this file is allowed to span both graphs.

Per DI-59824215 / DI-7625C251 (Atlas) -- the source of truth for the
data model lives in those design inputs.

Key invariants enforced here:

1. Every :TestPatient node carries `is_test = true` and an `aspect`
   property in {"nlp","episodes","guidelines","summarisation"}. Risk
   R-8C0CC94B is mitigated by structural separation: the patient
   graph never carries a :TestPatient node, so production queries
   against :Patient cannot return one.

2. Test patients can either be authored from scratch (existing flow,
   guidelines aspect only today), seeded from YAML fixtures (the SBAR
   golden set importer), or cloned from a real patient via
   `services.test_patient_clone`. Cloned subgraphs (encounters,
   documents, concept relationships) all carry `is_test = true` so
   any future label-agnostic query can also filter them out.

3. The display name of every test patient starts with "test_" so a
   clinician seeing one in any surface can tell at a glance.

Legacy guideline-specific edges (:FIXTURE_FOR, :EXPECTED_RESULT) are
preserved unchanged so the existing replay flow keeps working while
phases B-D bring up the per-aspect replay backends.
"""

# Aspect vocabulary -- every TestPatient must carry exactly one of
# these values in its `aspect` property. Mirrors the four parts of
# the AI we run regression against.
TEST_PATIENT_ASPECTS: tuple[str, ...] = (
    "nlp",
    "episodes",
    "guidelines",
    "summarisation",
)


# Schema constraints / indexes.  Wire into CODING_SCHEMA_CONSTRAINTS.
TEST_PATIENT_CONSTRAINTS = [
    "CREATE CONSTRAINT test_patient_id IF NOT EXISTS FOR (tp:TestPatient) REQUIRE tp.id IS UNIQUE",
    "CREATE INDEX test_patient_guideline IF NOT EXISTS FOR (tp:TestPatient) ON (tp.guideline_id)",
    "CREATE INDEX test_patient_content_hash IF NOT EXISTS FOR (tp:TestPatient) ON (tp.content_hash)",
    "CREATE INDEX test_patient_aspect IF NOT EXISTS FOR (tp:TestPatient) ON (tp.aspect)",
    "CREATE INDEX test_patient_is_test IF NOT EXISTS FOR (tp:TestPatient) ON (tp.is_test)",
    "CREATE INDEX test_patient_source IF NOT EXISTS FOR (tp:TestPatient) ON (tp.source_patient_id)",
    "CREATE CONSTRAINT ruleset_replay_id IF NOT EXISTS FOR (rv:RulesetReplay) REQUIRE rv.id IS UNIQUE",
    "CREATE INDEX ruleset_replay_version IF NOT EXISTS FOR (rv:RulesetReplay) ON (rv.ruleset_version)",
]


# One-shot backfill -- stamp `is_test = true` and a default aspect on
# any pre-existing :TestPatient node that was created before the
# centralised library landed. Safe to run repeatedly; it only updates
# rows missing the new fields.
BACKFILL_LEGACY_TEST_PATIENTS = """
MATCH (tp:TestPatient)
WHERE tp.is_test IS NULL OR tp.aspect IS NULL
SET tp.is_test = true,
    tp.aspect  = coalesce(tp.aspect, 'guidelines')
RETURN count(tp) AS updated
"""


# Look up an existing test patient by content hash inside one guideline,
# so the generator and the manual save flow can skip duplicates.
FIND_BY_CONTENT_HASH = """
MATCH (tp:TestPatient { content_hash: $content_hash })
      -[:FIXTURE_FOR]->(g:Guideline { id: $guideline_id })
RETURN tp.id AS id
LIMIT 1
"""


# Create a test patient and link it to its guideline.
# Snapshot expectations are written separately via WRITE_EXPECTED_RESULT.
#
# Always stamps `is_test = true` and `aspect = 'guidelines'` -- this
# is the legacy guideline-firing flow. Other aspects (NLP, Episodes,
# Summarisation) use CREATE_TEST_PATIENT_FOR_ASPECT or the clone tool.
CREATE_TEST_PATIENT = """
MATCH (g:Guideline { id: $guideline_id })
CREATE (tp:TestPatient {
    id:                $id,
    name:              $name,
    description:       $description,
    codes:             $codes,
    age:               $age,
    sex:               $sex,
    pathway_id:        $pathway_id,
    scope_type:        $scope_type,
    scope_id:          $scope_id,
    generation_source: $generation_source,
    content_hash:      $content_hash,
    guideline_id:      $guideline_id,
    aspect:            'guidelines',
    is_test:           true,
    created_by:        $created_by,
    created_at:        datetime(),
    updated_at:        datetime()
})
MERGE (tp)-[:FIXTURE_FOR]->(g)
RETURN tp.id AS id
"""


# Create a test patient for any aspect. Runs on the KNOWLEDGE graph.
#
# When `source_patient_id` is non-null we record it as a STRING property
# (not an edge) -- the source :Patient lives in the patient graph, so
# a Neo4j relationship across graphs is impossible. The clone audit
# trail is preserved by the property + the cloned subgraph below.
#
# The display name is forced to carry a "test_" prefix; the service
# layer is responsible for stripping any patient PII before passing
# props in.
CREATE_TEST_PATIENT_FOR_ASPECT = """
CREATE (tp:TestPatient {
    id:                 $id,
    name:               $name,
    description:        $description,
    aspect:             $aspect,
    is_test:            true,
    source_patient_id:  $source_patient_id,
    generation_source:  $generation_source,
    age:                $age,
    sex:                $sex,
    created_by:         $created_by,
    created_at:         datetime(),
    updated_at:         datetime()
})
RETURN tp.id AS id
"""


# Snapshot one expectation against a specific rule.
WRITE_EXPECTED_RESULT = """
MATCH (tp:TestPatient { id: $test_patient_id })
MATCH (rule:AppropriatenessRule { id: $rule_id })
MERGE (tp)-[r:EXPECTED_RESULT { rule_id: $rule_id }]->(rule)
SET   r.fires                    = $fires,
      r.matched_branch_node_ids  = $matched_branch_node_ids,
      r.snapshot_at              = datetime(),
      r.ruleset_version          = $ruleset_version,
      r.snapshot_by              = $snapshot_by
RETURN r.rule_id AS rule_id
"""


# List patients with optional filters. Common to all aspects.
#   - $aspect filters on tp.aspect (None or "all" => no filter)
#   - $guideline_id / $rule_id / $node_id are guideline-aspect specific
#   - The result row carries the aspect so the UI can colour rows
#     correctly when "All" is selected.
LIST_TEST_PATIENTS = """
MATCH (tp:TestPatient)
WHERE coalesce(tp.is_test, false) = true
  AND ($aspect IS NULL OR $aspect = 'all' OR coalesce(tp.aspect, 'guidelines') = $aspect)
OPTIONAL MATCH (tp)-[:FIXTURE_FOR]->(g:Guideline)
WHERE ($guideline_id IS NULL OR g.id = $guideline_id)
OPTIONAL MATCH (tp)-[er:EXPECTED_RESULT]->(rule:AppropriatenessRule)
WITH tp, g,
     collect(DISTINCT {
         rule_id:                  er.rule_id,
         fires:                    er.fires,
         matched_branch_node_ids:  er.matched_branch_node_ids,
         snapshot_at:              toString(er.snapshot_at),
         ruleset_version:          er.ruleset_version
     }) AS expectations
// Pull the expected SBAR priority + evaluator outage flag so the
// reviewer can filter the library by triage outcome (2ww / urgent /
// routine / safety-net / no rule fired / evaluator outage). Only the
// summarisation aspect has an ExpectedSBAR -- the rest project NULL
// and the UI shows them under "(no triage outcome)".
//
// We also union the SBAR matched_rule_ids into the rule_id filter
// below so that SBAR / referral-triage test patients (which link to
// rules via ExpectedSBAR.matched_rule_ids rather than an
// EXPECTED_RESULT relationship) surface in the rule editor's "Try
// it on real patients" panel. Without the union the panel would say
// "0 saved" for any rule that only has SBAR coverage.
OPTIONAL MATCH (tp)-[:HAS_EXPECTED_SBAR]->(s:ExpectedSBAR)
WHERE coalesce(s.is_test, false) = true
WITH tp, g, expectations, s
WHERE ($rule_id IS NULL
       OR any(e IN expectations WHERE e.rule_id = $rule_id)
       OR (s IS NOT NULL AND $rule_id IN coalesce(s.matched_rule_ids, [])))
  AND ($node_id  IS NULL OR
       any(e IN expectations WHERE $node_id IN coalesce(e.matched_branch_node_ids, [])))
WITH tp, g, expectations, s,
     CASE
       WHEN s IS NULL                              THEN NULL
       WHEN coalesce(s.evaluator_outage, false)    THEN 'evaluator_outage'
       WHEN s.expected_action_priority IS NOT NULL THEN s.expected_action_priority
       WHEN size(coalesce(s.matched_rule_ids, [])) = 0 THEN 'no_rule_fired'
       ELSE 'routine'
     END AS triage_outcome
WHERE ($triage_outcome IS NULL OR $triage_outcome = 'all'
       OR triage_outcome = $triage_outcome
       OR ($triage_outcome = 'unset' AND triage_outcome IS NULL))
RETURN tp.id              AS id,
       tp.name            AS name,
       tp.description     AS description,
       coalesce(tp.aspect, 'guidelines') AS aspect,
       coalesce(tp.is_test, true)        AS is_test,
       tp.source_patient_id              AS source_patient_id,
       tp.codes           AS codes,
       tp.age             AS age,
       tp.sex             AS sex,
       tp.pathway_id      AS pathway_id,
       tp.scope_type      AS scope_type,
       tp.scope_id        AS scope_id,
       tp.generation_source AS generation_source,
       tp.content_hash    AS content_hash,
       g.id               AS guideline_id,
       g.title            AS guideline_title,
       toString(tp.created_at) AS created_at,
       tp.created_by      AS created_by,
       triage_outcome     AS triage_outcome,
       [e IN expectations WHERE e.rule_id IS NOT NULL] AS expectations
ORDER BY tp.created_at DESC
LIMIT $limit
"""


# Count test patients grouped by aspect. Backs the four count tiles
# at the top of the Knowledge > Test Patients page.
COUNT_TEST_PATIENTS_BY_ASPECT = """
MATCH (tp:TestPatient)
WHERE coalesce(tp.is_test, false) = true
RETURN coalesce(tp.aspect, 'guidelines') AS aspect,
       count(tp)                         AS total
"""


# Count test patients grouped by triage outcome. Backs the secondary
# filter chip group that sits inside the SBAR / referral triage aspect.
# Outcome derivation matches LIST_TEST_PATIENTS exactly.
COUNT_TEST_PATIENTS_BY_TRIAGE_OUTCOME = """
MATCH (tp:TestPatient)
WHERE coalesce(tp.is_test, false) = true
  AND coalesce(tp.aspect, 'guidelines') = 'summarisation'
OPTIONAL MATCH (tp)-[:HAS_EXPECTED_SBAR]->(s:ExpectedSBAR)
WHERE coalesce(s.is_test, false) = true
WITH tp, s,
     CASE
       WHEN s IS NULL                              THEN 'unset'
       WHEN coalesce(s.evaluator_outage, false)    THEN 'evaluator_outage'
       WHEN s.expected_action_priority IS NOT NULL THEN s.expected_action_priority
       WHEN size(coalesce(s.matched_rule_ids, [])) = 0 THEN 'no_rule_fired'
       ELSE 'routine'
     END AS triage_outcome
RETURN triage_outcome AS triage_outcome,
       count(tp)      AS total
"""


# Picker for the "Clone from real patient" dialog. Runs on the
# PATIENT graph (PatientGraphClient) -- :Patient nodes do not live in
# the knowledge graph so this query MUST NOT be run there.
LIST_REAL_PATIENTS_FOR_CLONE_PICKER = """
MATCH (p:Patient)
WHERE coalesce(p.is_test, false) = false
OPTIONAL MATCH (p)-[:HAS_ENCOUNTER]->(e:Encounter)
WITH p, count(DISTINCT e) AS encounter_count
ORDER BY encounter_count DESC, p.id ASC
LIMIT $limit
RETURN p.id            AS id,
       coalesce(p.displayName, p.id) AS display_name,
       encounter_count
"""


GET_TEST_PATIENT = """
MATCH (tp:TestPatient { id: $id })
WHERE coalesce(tp.is_test, false) = true
OPTIONAL MATCH (tp)-[:FIXTURE_FOR]->(g:Guideline)
OPTIONAL MATCH (tp)-[er:EXPECTED_RESULT]->(rule:AppropriatenessRule)
WITH tp, g,
     collect(DISTINCT {
         rule_id:                  er.rule_id,
         fires:                    er.fires,
         matched_branch_node_ids:  er.matched_branch_node_ids,
         snapshot_at:              toString(er.snapshot_at),
         ruleset_version:          er.ruleset_version
     }) AS expectations
// SBAR / referral-triage test patients do not write EXPECTED_RESULT
// edges -- their rule expectations live on (:ExpectedSBAR).matched_rule_ids
// instead. Project them here so replay_one can union them into the
// expectations list without making a second Cypher call. Each id is
// surfaced individually so the replay layer can map them to the same
// {rule_id, fires} shape EXPECTED_RESULT uses.
OPTIONAL MATCH (tp)-[:HAS_EXPECTED_SBAR]->(s:ExpectedSBAR)
WHERE coalesce(s.is_test, false) = true
WITH tp, g, expectations,
     coalesce(s.matched_rule_ids, []) AS expected_sbar_rule_ids
// The AI scaffolder + clone path attach SNOMED codes to the patient
// via :Encounter -[:DOCUMENTS]-> :Concept (with a present / absent /
// negated assertion). The bitmap evaluator only reads ``tp.codes``,
// so a SBAR patient whose codes property is null would silently fire
// zero rules. We project the union of ``present`` document codes here
// and let the replay layer fall back to it when ``tp.codes`` is empty.
OPTIONAL MATCH (tp)-[:HAS_ENCOUNTER]->(:Encounter)
            -[d:DOCUMENTS]->(c:Concept)
WHERE coalesce(d.context, d.assertion, 'present') = 'present'
WITH tp, g, expectations, expected_sbar_rule_ids,
     [cid IN collect(DISTINCT toString(c.id)) WHERE cid IS NOT NULL AND cid <> '']
       AS document_codes
RETURN tp.id              AS id,
       tp.name            AS name,
       tp.description     AS description,
       coalesce(tp.aspect, 'guidelines') AS aspect,
       coalesce(tp.is_test, true)        AS is_test,
       tp.source_patient_id              AS source_patient_id,
       tp.codes           AS codes,
       tp.age             AS age,
       tp.sex             AS sex,
       tp.pathway_id      AS pathway_id,
       tp.scope_type      AS scope_type,
       tp.scope_id        AS scope_id,
       tp.generation_source AS generation_source,
       tp.content_hash    AS content_hash,
       g.id               AS guideline_id,
       g.title            AS guideline_title,
       toString(tp.created_at) AS created_at,
       tp.created_by      AS created_by,
       [e IN expectations WHERE e.rule_id IS NOT NULL] AS expectations,
       expected_sbar_rule_ids,
       document_codes
"""


# -- Clone-from-real-patient helpers (CROSS-GRAPH) --------------------
#
# The Python service in services/api/app/services/test_patient_clone.py
# orchestrates these in sequence. The READ_SOURCE_* queries run against
# the PATIENT graph (PatientGraphClient). The WRITE_TEST_* queries run
# against the KNOWLEDGE graph (CodingGraphClient / KnowledgeGraphClient)
# so that no test patient row is ever written to the patient graph and
# no real PHI is ever written to the knowledge graph.
#
# Concepts (:Concept) live ONLY in the knowledge graph -- the read side
# returns concept_ids and the write side MERGE'es against pre-loaded
# :Concept nodes by id (loud failure if the concept is missing).
#
# Allowed concept-edge types -- mirror real :Patient -> :Concept and
# :Encounter -> :Concept relationship types that production code emits.
ALLOWED_CONCEPT_EDGE_TYPES: tuple[str, ...] = (
    "HAS_FINDING",
    "HAS_DISORDER",
    "HAS_OBSERVABLE",
    "HAS_PROCEDURE",
    "HAS_SITUATION",
    "HAS_CONCEPT",
    "DOCUMENTS",
)


# READ (patient graph) -- pull source patient row. Identifier fields
# (PII) are surfaced so the service can both populate the test
# patient's age/sex AND prove via assertion tests that PII never made
# it to the knowledge graph.
READ_SOURCE_PATIENT_FOR_CLONE = """
MATCH (p:Patient { id: $source_patient_id })
WHERE coalesce(p.is_test, false) = false
OPTIONAL MATCH (p)-[:HAS_ENCOUNTER]->(e:Encounter)
OPTIONAL MATCH (p)-[:HAS_DOCUMENT]->(d:Document)
WITH p, count(DISTINCT e) AS encounter_count, count(DISTINCT d) AS document_count
RETURN p.id          AS id,
       p.displayName AS display_name,
       p.age         AS age,
       p.sex         AS sex,
       p.nhs_number  AS nhs_number,
       p.dateOfBirth AS date_of_birth,
       p.address     AS address,
       p.phone       AS phone,
       p.email       AS email,
       encounter_count,
       document_count
"""


# READ (patient graph) -- every encounter under the source patient,
# with the concept ids it documents and any free text. The service
# layer takes the returned rows, runs free text through the NLP
# redactor, then issues WRITE_TEST_ENCOUNTER calls against the
# knowledge graph.
READ_SOURCE_ENCOUNTERS = """
MATCH (p:Patient { id: $source_patient_id })-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE coalesce(p.is_test, false) = false
OPTIONAL MATCH (e)-[r:DOCUMENTS]->(c)
WHERE c.id IS NOT NULL
WITH e, collect(DISTINCT {
    rel_type:    type(r),
    properties:  properties(r),
    concept_id:  c.id
}) AS documents
RETURN e.id                AS id,
       toString(e.date)    AS date,
       e.text              AS text,
       e.flags             AS flags,
       properties(e)       AS all_properties,
       [d IN documents WHERE d.concept_id IS NOT NULL] AS documents
ORDER BY e.date ASC
"""


# READ (patient graph) -- documents attached directly to the patient
# (referral letters, scanned PDFs that have been OCR'd, etc.).
READ_SOURCE_DOCUMENTS = """
MATCH (p:Patient { id: $source_patient_id })-[:HAS_DOCUMENT]->(d:Document)
WHERE coalesce(p.is_test, false) = false
RETURN d.id           AS id,
       d.title        AS title,
       d.text         AS text,
       properties(d)  AS all_properties
ORDER BY d.id ASC
"""


# READ (patient graph) -- direct (Patient)-[r]->(Concept) edges.
# Returns concept_ids only; the write side will MATCH them in the
# knowledge graph and MERGE the test edge.
READ_SOURCE_CONCEPT_EDGES = """
MATCH (p:Patient { id: $source_patient_id })-[r]->(c)
WHERE coalesce(p.is_test, false) = false
  AND c.id IS NOT NULL
  AND type(r) IN $allowed_types
RETURN type(r)        AS rel_type,
       properties(r)  AS properties,
       c.id           AS concept_id
"""


# WRITE (knowledge graph) -- create one cloned encounter under the
# already-created TestPatient. Documents link to existing :Concept
# nodes by id; the service layer is responsible for asserting all
# concept_ids exist before calling this query (loud failure on miss).
WRITE_TEST_ENCOUNTER = """
MATCH (tp:TestPatient { id: $test_patient_id })
CREATE (te:Encounter {
    id:               $encounter_id,
    is_test:          true,
    source_patient_id: $source_patient_id,
    text:             $text,
    date:             $date,
    flags:            $flags,
    extra_properties: $extra_properties_json
})
MERGE (tp)-[r:HAS_ENCOUNTER]->(te)
SET r.is_test = true
WITH te
UNWIND $documents AS doc
MATCH (c:Concept { id: doc.concept_id })
WITH te, doc, c
CALL {
    WITH te, doc, c
    WITH te, doc, c, doc.rel_type AS rt
    FOREACH (_ IN CASE WHEN rt = 'DOCUMENTS' THEN [1] ELSE [] END |
        MERGE (te)-[r:DOCUMENTS]->(c)
        SET r = doc.properties, r.is_test = true)
    RETURN 1 AS done
}
RETURN count(DISTINCT te) AS encounters_written
"""


# WRITE (knowledge graph) -- create one cloned document under the
# TestPatient. Free text is the redacted form -- the redactor runs
# in Python before this call.
WRITE_TEST_DOCUMENT = """
MATCH (tp:TestPatient { id: $test_patient_id })
CREATE (td:Document {
    id:               $document_id,
    is_test:          true,
    source_patient_id: $source_patient_id,
    title:            $title,
    text:             $text,
    extra_properties: $extra_properties_json
})
MERGE (tp)-[r:HAS_DOCUMENT]->(td)
SET r.is_test = true
RETURN td.id AS id
"""


# WRITE (knowledge graph) -- mirror one direct (Patient)->(Concept)
# edge onto the TestPatient. We dispatch by rel_type via FOREACH so
# Cypher type-checks each MERGE statically (it can't take a parameter
# for the relationship type without APOC).
WRITE_TEST_CONCEPT_EDGE = """
MATCH (tp:TestPatient { id: $test_patient_id })
MATCH (c:Concept { id: $concept_id })
WITH tp, c, $rel_type AS rt, $properties AS rp
FOREACH (_ IN CASE WHEN rt = 'HAS_FINDING'    THEN [1] ELSE [] END |
    MERGE (tp)-[r:HAS_FINDING]->(c)    SET r = rp, r.is_test = true)
FOREACH (_ IN CASE WHEN rt = 'HAS_DISORDER'   THEN [1] ELSE [] END |
    MERGE (tp)-[r:HAS_DISORDER]->(c)   SET r = rp, r.is_test = true)
FOREACH (_ IN CASE WHEN rt = 'HAS_OBSERVABLE' THEN [1] ELSE [] END |
    MERGE (tp)-[r:HAS_OBSERVABLE]->(c) SET r = rp, r.is_test = true)
FOREACH (_ IN CASE WHEN rt = 'HAS_PROCEDURE'  THEN [1] ELSE [] END |
    MERGE (tp)-[r:HAS_PROCEDURE]->(c)  SET r = rp, r.is_test = true)
FOREACH (_ IN CASE WHEN rt = 'HAS_SITUATION'  THEN [1] ELSE [] END |
    MERGE (tp)-[r:HAS_SITUATION]->(c)  SET r = rp, r.is_test = true)
FOREACH (_ IN CASE WHEN rt = 'HAS_CONCEPT'    THEN [1] ELSE [] END |
    MERGE (tp)-[r:HAS_CONCEPT]->(c)    SET r = rp, r.is_test = true)
RETURN 1 AS done
"""


# Backwards-compat re-exports so older code paths keep importing the
# old names; these now point at the cross-graph READ side. New code
# MUST import the READ_SOURCE_* / WRITE_TEST_* names directly.
GET_SOURCE_PATIENT_FOR_CLONE = READ_SOURCE_PATIENT_FOR_CLONE


# Verification helper used by VT-5BDFE5F7 TC-002: prove a TestPatient
# carries no PII, has the test_ prefix and at least one cloned edge.
ASSERT_TEST_PATIENT_DEIDENTIFIED = """
MATCH (tp:TestPatient { id: $test_patient_id })
OPTIONAL MATCH (tp)-[:HAS_ENCOUNTER]->(e:Encounter)
OPTIONAL MATCH (tp)-[:HAS_DOCUMENT]->(d:Document)
RETURN tp.id                                  AS id,
       tp.name                                AS name,
       tp.aspect                              AS aspect,
       coalesce(tp.is_test, false)            AS is_test,
       tp.source_patient_id                   AS source_patient_id,
       tp.nhs_number                          AS nhs_number,
       tp.dateOfBirth                         AS date_of_birth,
       tp.address                             AS address,
       tp.phone                               AS phone,
       count(DISTINCT e)                      AS encounter_count,
       count(DISTINCT d)                      AS document_count
"""


DELETE_TEST_PATIENT = """
MATCH (tp:TestPatient { id: $id })
DETACH DELETE tp
RETURN count(*) AS deleted
"""


# ---------------------------------------------------------------------
# Per-aspect editor (read + write the full editable subgraph)
# ---------------------------------------------------------------------
#
# Backs the Edit drawer in the Knowledge > Test Patients tab. The
# editor needs the whole editable surface in one shot so the form
# can render encounter timelines, expected SNOMED codes per chunk,
# and the expected SBAR transcript without N round-trips.
#
# Important: this is the read used by the EDITOR. It is intentionally
# distinct from GET_TEST_PATIENT (which only returns the root + the
# guideline-aspect EXPECTED_RESULT snapshot). The editor needs:
#
#   :TestPatient  -- root profile (demographics, name, source)
#       -[:HAS_ENCOUNTER]-> :Encounter (text + date + source label)
#                   -[:DOCUMENTS]-> :Concept (term + assertion)
#       -[:HAS_EXPECTED_SBAR]-> :ExpectedSBAR (S/B/A/R + phrases)
#
# The knowledge graph stores :Concept nodes by SNOMED id; the editor
# never invents new concepts, it only attaches existing ones (loud
# failure is enforced by ASSERT_CONCEPTS_PRESENT before any write).

READ_TEST_PATIENT_FULL = """
MATCH (tp:TestPatient { id: $id })
WHERE coalesce(tp.is_test, false) = true
OPTIONAL MATCH (tp)-[:FIXTURE_FOR]->(g:Guideline)
OPTIONAL MATCH (tp)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE coalesce(e.is_test, false) = true
OPTIONAL MATCH (e)-[d:DOCUMENTS]->(c:Concept)
WITH tp, g, e,
     collect(DISTINCT
       CASE WHEN c IS NULL THEN NULL ELSE {
         concept_id: c.id,
         term:       coalesce(d.term, c.preferredTerm, c.fsn),
         assertion:  coalesce(d.assertion, 'present')
       } END
     ) AS code_rows
WITH tp, g,
     collect(DISTINCT
       CASE WHEN e IS NULL THEN NULL ELSE {
         id:           e.id,
         text:         coalesce(e.text, ''),
         date:         toString(e.date),
         source_label: e.source_label,
         source_id:    e.source_id,
         codes:        [code IN code_rows WHERE code IS NOT NULL]
       } END
     ) AS encounter_rows
OPTIONAL MATCH (tp)-[:HAS_EXPECTED_SBAR]->(s:ExpectedSBAR)
WHERE coalesce(s.is_test, false) = true
WITH tp, g, encounter_rows,
     CASE WHEN s IS NULL THEN NULL ELSE {
       id:                       s.id,
       situation_md:             coalesce(s.situation_md, ''),
       background_md:            coalesce(s.background_md, ''),
       recommendation_md:        coalesce(s.recommendation_md, ''),
       matched_rule_ids:         coalesce(s.matched_rule_ids, []),
       required_phrases:         coalesce(s.required_phrases, []),
       banned_phrases:           coalesce(s.banned_phrases, []),
       expected_action_priority: s.expected_action_priority,
       reviewer_focus:           coalesce(s.reviewer_focus, '')
     } END AS expected_sbar
RETURN tp.id              AS id,
       tp.name            AS name,
       tp.description     AS description,
       coalesce(tp.aspect, 'guidelines')  AS aspect,
       coalesce(tp.is_test, true)         AS is_test,
       tp.source_patient_id               AS source_patient_id,
       tp.codes           AS codes,
       tp.age             AS age,
       tp.sex             AS sex,
       tp.pathway_id      AS pathway_id,
       tp.generation_source AS generation_source,
       g.id               AS guideline_id,
       g.title            AS guideline_title,
       toString(tp.created_at) AS created_at,
       toString(tp.updated_at) AS updated_at,
       tp.created_by      AS created_by,
       tp.updated_by      AS updated_by,
       [enc IN encounter_rows WHERE enc IS NOT NULL] AS encounters,
       expected_sbar      AS expected_sbar
"""


# Detach + delete every editor-managed child node under one
# :TestPatient, in one shot. Used as the reset step before the
# editor re-writes the new encounter list and expected SBAR. Only
# touches nodes that carry ``is_test = true`` so a hand-seeded
# fixture cannot poison a manual edit and vice versa.
RESET_TEST_PATIENT_CHILDREN = """
MATCH (tp:TestPatient { id: $id })
OPTIONAL MATCH (tp)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE coalesce(e.is_test, false) = true
DETACH DELETE e
WITH tp
OPTIONAL MATCH (tp)-[:HAS_EXPECTED_SBAR]->(s:ExpectedSBAR)
WHERE coalesce(s.is_test, false) = true
DETACH DELETE s
WITH tp
OPTIONAL MATCH (tp)-[:HAS_DOCUMENT]->(d:Document)
WHERE coalesce(d.is_test, false) = true
DETACH DELETE d
RETURN 1 AS reset
"""


# Update the editable demographic + name fields on a :TestPatient
# without touching guideline-only properties (codes / pathway_id /
# content_hash) and without dropping the EXPECTED_RESULT snapshot
# the guidelines aspect maintains via UPDATE_TEST_PATIENT.
UPDATE_TEST_PATIENT_PROFILE = """
MATCH (tp:TestPatient { id: $id })
WHERE coalesce(tp.is_test, false) = true
SET tp.name        = $name,
    tp.description = $description,
    tp.age         = $age,
    tp.sex         = $sex,
    tp.updated_at  = datetime(),
    tp.updated_by  = $updated_by
RETURN tp.id AS id
"""


# Create one editor-authored encounter under a :TestPatient and link
# its expected SNOMED codes. Concept ids are MERGE'd against
# pre-loaded :Concept nodes -- the service layer pre-flights every
# id with ASSERT_CONCEPTS_PRESENT and fails loudly if any id is
# missing, so a missing match here is a programmer error.
WRITE_EDITOR_ENCOUNTER = """
MATCH (tp:TestPatient { id: $tp_id })
WHERE coalesce(tp.is_test, false) = true
CREATE (e:Encounter {
    id:           $encounter_id,
    is_test:      true,
    source_label: $source_label,
    source_id:    $source_id,
    text:         coalesce($text, ''),
    date:         $date
})
MERGE (tp)-[r:HAS_ENCOUNTER]->(e)
SET r.is_test = true
WITH e
UNWIND $codes AS code
MATCH (c:Concept { id: code.concept_id })
MERGE (e)-[d:DOCUMENTS]->(c)
SET d.is_test    = true,
    d.assertion  = coalesce(code.assertion, 'present'),
    d.term       = code.term
RETURN count(DISTINCT c) AS codes_linked
"""


# ---------------------------------------------------------------------
# SBAR golden-set seeding (knowledge graph)
# ---------------------------------------------------------------------
#
# These queries are used by `scripts/seed_sbar_test_patients.py` to
# load the YAML fixtures in design-controls/training-data/sbar-golden-
# set/ as :TestPatient {aspect: 'summarisation'} rows. Idempotent --
# re-running the script updates the existing rows in place.
#
# Each fixture becomes:
#     (:TestPatient {aspect:'summarisation', is_test:true})
#         -[:HAS_ENCOUNTER {is_test:true}]->(:Encounter {is_test:true, text:...})
#         -[:DOCUMENTS {assertion, term, is_test:true}]->(:Concept) (MERGE'd
#             against pre-loaded SNOMED Concept nodes)
#         -[:HAS_EXPECTED_SBAR {is_test:true}]->(:ExpectedSBAR
#             {situation_md, background_md, recommendation_md,
#              required_phrases, banned_phrases, matched_rule_ids,
#              reviewer_focus})

SBAR_FIXTURE_CONSTRAINTS: tuple[str, ...] = (
    "CREATE CONSTRAINT expected_sbar_id IF NOT EXISTS FOR (e:ExpectedSBAR) REQUIRE e.id IS UNIQUE",
    "CREATE INDEX test_patient_fixture_id IF NOT EXISTS FOR (tp:TestPatient) ON (tp.fixture_id)",
)


# Upsert the test patient root for an SBAR fixture. Always stamps
# is_test=true and aspect='summarisation'. Re-running the seed for an
# existing fixture_id refreshes the metadata (title / scenario / age
# band / sex) without churning the node identity.
SEED_SBAR_TEST_PATIENT = """
MERGE (tp:TestPatient { id: $id })
ON CREATE SET tp.created_at = datetime(),
              tp.created_by = $created_by
SET tp.is_test            = true,
    tp.aspect             = 'summarisation',
    tp.name               = $name,
    tp.description        = $description,
    tp.fixture_id         = $fixture_id,
    tp.fixture_path       = $fixture_path,
    tp.title              = $title,
    tp.age                = $age,
    tp.sex                = $sex,
    tp.age_band           = $age_band,
    tp.smoking_status     = $smoking_status,
    tp.guideline_ids      = $guideline_ids,
    tp.generation_source  = 'fixture',
    tp.updated_at         = datetime(),
    tp.updated_by         = $created_by
RETURN tp.id AS id
"""


# Detach previously-seeded children for this fixture so re-runs cannot
# leave orphan encounters / documents / expected SBARs hanging around.
# Only deletes children whose ids carry the fixture's id_prefix and
# whose is_test flag is true.
RESET_SBAR_FIXTURE_CHILDREN = """
MATCH (tp:TestPatient { id: $id })
OPTIONAL MATCH (tp)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE coalesce(e.is_test, false) = true
  AND e.id STARTS WITH $id_prefix
DETACH DELETE e
WITH tp
OPTIONAL MATCH (tp)-[:HAS_EXPECTED_SBAR]->(s:ExpectedSBAR)
WHERE coalesce(s.is_test, false) = true
DETACH DELETE s
RETURN count(*) AS reset
"""


# Create one cloned encounter under the SBAR test patient. The :Concept
# nodes are MERGE'd by SNOMED id, NOT created. The seed-time check in
# the importer asserts every concept_id is already present in the
# knowledge graph (loud failure on missing reference data) before this
# query runs, so a missing match here is a programming error.
SEED_SBAR_ENCOUNTER = """
MATCH (tp:TestPatient { id: $tp_id })
CREATE (e:Encounter {
    id:           $encounter_id,
    is_test:      true,
    source_label: $source_label,
    source_id:    $source_id,
    text:         $text,
    fixture_id:   $fixture_id
})
MERGE (tp)-[r:HAS_ENCOUNTER]->(e)
SET r.is_test = true
WITH e
UNWIND $codes AS code
MATCH (c:Concept { id: code.concept_id })
MERGE (e)-[d:DOCUMENTS]->(c)
SET d.is_test     = true,
    d.assertion   = code.assertion,
    d.term        = code.term,
    d.fixture_id  = $fixture_id
RETURN count(DISTINCT c) AS codes_linked
"""


# Persist the expected SBAR transcript + reviewer expectations so the
# Phase D replay can score generated SBARs against this baseline.
SEED_EXPECTED_SBAR = """
MATCH (tp:TestPatient { id: $tp_id })
MERGE (s:ExpectedSBAR { id: $sbar_id })
SET s.is_test                 = true,
    s.fixture_id              = $fixture_id,
    s.situation_md            = $situation_md,
    s.background_md           = $background_md,
    s.recommendation_md       = $recommendation_md,
    s.matched_rule_ids        = $matched_rule_ids,
    s.required_phrases        = $required_phrases,
    s.banned_phrases          = $banned_phrases,
    s.expected_action_priority = $expected_action_priority,
    s.reviewer_focus          = $reviewer_focus,
    s.evaluator_outage        = $evaluator_outage
MERGE (tp)-[r:HAS_EXPECTED_SBAR]->(s)
SET r.is_test = true
RETURN s.id AS id
"""


# Pre-flight check used by the SBAR importer: returns the subset of
# concept ids that are NOT present in the knowledge graph. Used to fail
# loudly before any partial seed is written.
ASSERT_CONCEPTS_PRESENT = """
UNWIND $concept_ids AS cid
OPTIONAL MATCH (c:Concept { id: cid })
WITH cid, c
WHERE c IS NULL
RETURN collect(cid) AS missing
"""


# Update a test patient's profile in place AND clear its existing
# EXPECTED_RESULT relationships so the caller can rewrite them.
# Returns one row when the patient exists, zero rows otherwise (the
# service layer translates that into a 404).  The expectation rewrite
# is a separate WRITE_EXPECTED_RESULT loop driven by the service
# (matching the create flow), so empty-expectation updates are
# still well-defined.
UPDATE_TEST_PATIENT = """
MATCH (tp:TestPatient { id: $id })
SET tp.name              = $name,
    tp.description       = $description,
    tp.codes             = $codes,
    tp.age               = $age,
    tp.sex               = $sex,
    tp.pathway_id        = $pathway_id,
    tp.content_hash      = $content_hash,
    tp.updated_at        = datetime(),
    tp.updated_by        = $updated_by
WITH tp
OPTIONAL MATCH (tp)-[er:EXPECTED_RESULT]->()
DELETE er
RETURN tp.id AS id
"""


# Collect rules in a scope.  Used by both the generator (to know what
# to synthesise fixtures for) and replay (to know what to evaluate).
#
# Status filter:
#   - When the caller targets a single rule by id we accept any non-
#     superseded / non-rejected status -- the reviewer is in the Edit
#     dialog and explicitly asked us to generate test patients for THIS
#     rule, even if it is still pending_review.
#   - For "all rules in a guideline" / "all guidelines" we restrict to
#     rules that the runtime evaluator would actually consider, i.e.
#     active or pending_review (drafts that have been generated and are
#     ready for sign-off).
LIST_RULES_IN_SCOPE = """
MATCH (rule:AppropriatenessRule)
WHERE
  CASE
    WHEN $rule_id IS NOT NULL
      THEN rule.id = $rule_id
           AND coalesce(rule.status, 'active') IN
               ['active', 'pending_review', 'approved', 'draft']
    ELSE coalesce(rule.status, 'active') IN ['active', 'pending_review']
  END
  AND ($guideline_id IS NULL OR
       EXISTS {
         MATCH (g:Guideline { id: $guideline_id })
               -[:HAS_RECOMMENDATION]->()-[:HAS_RULE]->(rule)
       })
OPTIONAL MATCH (rule)<-[:HAS_RULE]-(rec:Recommendation)
              <-[:HAS_RECOMMENDATION]-(g:Guideline)
RETURN rule.id          AS rule_id,
       rule.name        AS name,
       rule.logicJson   AS logic_json,
       coalesce(rule.status, 'active') AS status,
       g.id             AS guideline_id,
       g.title          AS guideline_title
ORDER BY rule.name
"""


# Read everything the AI scaffolder needs about a rule to draft a test
# patient: the verbatim NICE recommendation, the chapter / guideline
# context, the action priority, and the rule's logic tree as a raw JSON
# blob.
#
# Why logic_json (not :HAS_CRITERIA edges)?
#   The v2 guidance rule writer (services/terminology_api guideline
#   compiler) persists every concept criterion + demographic constraint
#   inside rule.logicJson. There is NO :CriteriaGroup label and NO
#   :APPLIES_TO relationship in production -- those were leftovers from
#   an earlier draft schema. A hard-coded MATCH on them silently
#   collected zero triggers and zero demographic constraints, which
#   tripped the "no SNOMED criteria attached" guard for every real
#   NG12 / NG78 / TA rule. The scaffolder now derives both lists by
#   walking logic_json on the Python side (see
#   test_patient_scaffolder._extract_logic_payload), reusing the same
#   walker the picker uses so they stay consistent.
#
# The scaffolder still fails loudly when the walker returns no concept
# leaves so it never silently writes a half-baked patient.
READ_RULE_FOR_SCAFFOLD = """
MATCH (rule:AppropriatenessRule {id: $rule_id})
OPTIONAL MATCH (rule)<-[:HAS_RULE]-(rec:Recommendation)
              <-[:HAS_RECOMMENDATION]-(g:Guideline)
OPTIONAL MATCH (rec)<-[:HAS_RECOMMENDATION]-(ch:Chapter)
OPTIONAL MATCH (rule)-[:HAS_ACTION_GROUP]->(:ActionGroup)
              -[ha:HAS_ACTION]->(_action_target)
RETURN rule.id                               AS rule_id,
       rule.name                             AS rule_name,
       rule.logicJson                        AS logic_json,
       rec.verbatim                          AS recommendation_text,
       ch.title                              AS chapter_title,
       g.id                                  AS guideline_id,
       g.title                               AS guideline_title,
       ha.priority                           AS action_priority
"""


# Picker-friendly rule list used by the SBAR editor's "Matched rule IDs"
# typeahead and the rule editor's "Try it on real patients" panel.
# Returns plain-English fields a nurse-grade reader can parse:
#   - recommendation_text  -- the verbatim NICE text (the actual sentence)
#   - chapter_title        -- the section heading the rule lives in
#   - action_priority      -- 2ww | urgent | routine, pulled from the
#                             ActionGroup's HAS_ACTION edge
#   - logic_json           -- the rule's full logic tree as a raw JSON
#                             blob; the service walks it to derive the
#                             first 3 SNOMED preferred-terms shown as
#                             a concrete cue (see
#                             test_patient_service.list_rules_for_picker).
#                             The walker is shared with the AI scaffolder
#                             so the two stay consistent.
#
# rule_id stays in the payload so the saved value is still the canonical
# rule id; the UI just hides it behind the readable label.
#
# Why logic_json instead of a graph walk? See the long comment on
# READ_RULE_FOR_SCAFFOLD above -- the v2 schema persists criteria inside
# rule.logicJson and there are no :CriteriaGroup nodes in production.
LIST_RULES_FOR_PICKER = """
MATCH (rule:AppropriatenessRule)
WHERE coalesce(rule.status, 'active') IN ['active', 'pending_review']
  AND ($guideline_id IS NULL OR
       EXISTS {
         MATCH (g:Guideline { id: $guideline_id })
               -[:HAS_RECOMMENDATION]->()-[:HAS_RULE]->(rule)
       })
OPTIONAL MATCH (rule)<-[:HAS_RULE]-(rec:Recommendation)
              <-[:HAS_RECOMMENDATION]-(g:Guideline)
OPTIONAL MATCH (rec)<-[:HAS_RECOMMENDATION]-(ch:Chapter)
OPTIONAL MATCH (rule)-[:HAS_ACTION_GROUP]->(:ActionGroup)
              -[ha:HAS_ACTION]->(_action_target)
RETURN rule.id                                AS rule_id,
       coalesce(rule.status, 'active')        AS status,
       rule.name                              AS name,
       rule.logicJson                         AS logic_json,
       rec.verbatim                           AS recommendation_text,
       ch.title                               AS chapter_title,
       ha.priority                            AS action_priority,
       g.id                                   AS guideline_id,
       g.title                                AS guideline_title
ORDER BY g.title, ch.title, rule.name
"""


# List guidelines (used by library page scope picker)
LIST_GUIDELINES_FOR_PICKER = """
MATCH (g:Guideline)
OPTIONAL MATCH (g)-[:HAS_RECOMMENDATION]->()-[:HAS_RULE]->(r:AppropriatenessRule {status: 'active'})
WITH g, count(DISTINCT r) AS active_rule_count
WHERE active_rule_count > 0
RETURN g.id AS id, g.title AS title, active_rule_count
ORDER BY g.title
LIMIT 200
"""


# Persist a replay report so it can be surfaced in the UI and
# re-loaded without re-running expensive evaluations.
WRITE_REPLAY_REPORT = """
MERGE (rv:RulesetReplay { id: $id })
ON CREATE SET rv.created_at = datetime()
SET rv.ruleset_version    = $ruleset_version,
    rv.scope_type         = $scope_type,
    rv.scope_id           = $scope_id,
    rv.guideline_id       = $guideline_id,
    rv.report_json        = $report_json,
    rv.regressions_count  = $regressions_count,
    rv.passes_count       = $passes_count,
    rv.drift_count        = $drift_count,
    rv.total_count        = $total_count,
    rv.completed_at       = datetime()
RETURN rv.id AS id
"""


LIST_REPLAY_REPORTS = """
MATCH (rv:RulesetReplay)
WHERE ($guideline_id IS NULL OR rv.guideline_id = $guideline_id)
  AND ($scope_type   IS NULL OR rv.scope_type   = $scope_type)
  AND ($scope_id     IS NULL OR rv.scope_id     = $scope_id)
RETURN rv.id                AS id,
       rv.ruleset_version   AS ruleset_version,
       rv.scope_type        AS scope_type,
       rv.scope_id          AS scope_id,
       rv.guideline_id      AS guideline_id,
       rv.regressions_count AS regressions_count,
       rv.passes_count      AS passes_count,
       rv.drift_count       AS drift_count,
       rv.total_count       AS total_count,
       toString(rv.created_at)   AS created_at,
       toString(rv.completed_at) AS completed_at
ORDER BY rv.completed_at DESC
LIMIT $limit
"""


GET_REPLAY_REPORT = """
MATCH (rv:RulesetReplay { id: $id })
RETURN rv.id              AS id,
       rv.ruleset_version AS ruleset_version,
       rv.scope_type      AS scope_type,
       rv.scope_id        AS scope_id,
       rv.guideline_id    AS guideline_id,
       rv.report_json     AS report_json,
       toString(rv.completed_at) AS completed_at
"""
