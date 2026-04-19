"""Copy a real patient as a de-identified :TestPatient (cross-graph).

Implements DI-59824215 (Atlas) -- the "copy a real patient and
de-identify" action that powers the Knowledge > Test Patients page.

Cross-graph design (R-PHI-XGRAPH mitigation)
--------------------------------------------
Real patients live in the patient graph (PHI/PII boundary). Test
patients are configuration / regression data and live in the knowledge
graph alongside SNOMED concepts and rules. This service is the ONLY
place in the codebase that holds both Neo4j drivers, and it always
flows in one direction:

    PatientGraphClient.READ_SOURCE_*  ->  Python de-identification
        -> KnowledgeGraphClient.WRITE_TEST_*

No Cypher in this module ever spans graphs. Free text from documents
and encounters is run through `services.test_patient_redactor` before
it leaves Python on its way to the knowledge graph -- this is the
mitigation for residual PHI in narrative text.

What this module does, in plain English
---------------------------------------
1. Reads a real :Patient row from the patient graph.
2. Reads every encounter, document and direct concept edge under that
   patient from the patient graph.
3. Redacts free text in Python (NLP redactor + regex fallbacks for
   NHS number / postcode / phone / email / DOB).
4. Creates a new :TestPatient root in the knowledge graph with a
   "test_" display name, the chosen aspect, `is_test = true` and a
   `source_patient_id` pointer (string property -- there is no edge
   between graphs).
5. Re-creates every encounter / document / concept edge under the new
   root in the knowledge graph, MERGE'd against pre-loaded :Concept
   nodes by SNOMED id. Loud failure if a referenced concept is missing
   so partial / silently-incorrect clones cannot land.

Risk R-8C0CC94B (Atlas) -- "test patient mistaken for a real patient
on a clinician surface" -- is mitigated by three independent layers
implemented here and in the queries:
    a. Separate :TestPatient label LIVES IN A DIFFERENT DATABASE so
       production `MATCH (p:Patient)` queries in the patient graph
       cannot return cloned patients.
    b. `is_test = true` propagated to every cloned node and
       relationship, so any future property-level filter also catches
       them.
    c. `test_` display-name prefix so a clinician glimpsing the row
       on any surface can see it is fake.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Iterable

from app.db.neo4j_client import CodingGraphClient, PatientGraphClient
from libs.cypher.test_patient_queries import (
    ALLOWED_CONCEPT_EDGE_TYPES,
    ASSERT_CONCEPTS_PRESENT,
    ASSERT_TEST_PATIENT_DEIDENTIFIED,
    CREATE_TEST_PATIENT_FOR_ASPECT,
    LIST_REAL_PATIENTS_FOR_CLONE_PICKER,
    READ_SOURCE_CONCEPT_EDGES,
    READ_SOURCE_DOCUMENTS,
    READ_SOURCE_ENCOUNTERS,
    READ_SOURCE_PATIENT_FOR_CLONE,
    TEST_PATIENT_ASPECTS,
    WRITE_TEST_CONCEPT_EDGE,
    WRITE_TEST_DOCUMENT,
    WRITE_TEST_ENCOUNTER,
)

logger = logging.getLogger(__name__)


# Properties the clone is allowed to copy onto the new TestPatient
# root. Everything else from the source row is dropped, including any
# future PII fields a tenant adds. age and sex drive coding/guideline
# rules so they are kept; everything else is PII or display chrome.
_ALLOWED_ROOT_PROPERTIES: frozenset[str] = frozenset({"age", "sex"})


# Properties the verification step asserts are NULL on the cloned root.
PII_KEYS_TO_STRIP: tuple[str, ...] = (
    "nhs_number",
    "nhsNumber",
    "name",
    "displayName",
    "given_name",
    "givenName",
    "family_name",
    "familyName",
    "date_of_birth",
    "dateOfBirth",
    "dob",
    "address",
    "address_line",
    "postcode",
    "postCode",
    "phone",
    "phone_number",
    "phoneNumber",
    "email",
)


class CloneError(ValueError):
    """Raised when clone-from-real cannot proceed (bad aspect, missing
    source concept, etc.). Translates to HTTP 4xx in the router."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def list_source_patients(
    patient_graph: PatientGraphClient, *, limit: int = 50
) -> list[dict]:
    """Return real patients that can be cloned, most active first.

    Backs the source-picker dropdown. Runs on the PATIENT graph.
    """
    rows = patient_graph.run(
        LIST_REAL_PATIENTS_FOR_CLONE_PICKER, limit=int(limit)
    )
    return [dict(r) for r in rows]


def clone_patient_as_test_patient(
    patient_graph: PatientGraphClient,
    knowledge_graph: CodingGraphClient,
    *,
    source_patient_id: str,
    aspect: str,
    created_by: str,
    description: str = "",
    redactor: Any | None = None,
) -> dict:
    """Copy a real patient as a de-identified test patient.

    Returns a summary of what was cloned. Raises :class:`CloneError`
    when the aspect is invalid, the source is missing, or a referenced
    SNOMED concept is missing from the knowledge graph (loud failure).
    """
    aspect = (aspect or "").lower().strip()
    if aspect not in TEST_PATIENT_ASPECTS:
        raise CloneError(
            "aspect must be one of " + ", ".join(TEST_PATIENT_ASPECTS)
        )

    source = _read_source(patient_graph, source_patient_id=source_patient_id)
    if source is None:
        raise CloneError(
            f"Source patient {source_patient_id!r} not found or already a test patient"
        )

    encounters = _read_source_encounters(
        patient_graph, source_patient_id=source_patient_id
    )
    documents = _read_source_documents(
        patient_graph, source_patient_id=source_patient_id
    )
    concept_edges = _read_source_concept_edges(
        patient_graph, source_patient_id=source_patient_id
    )

    concept_ids = _collect_concept_ids(encounters, concept_edges)
    _assert_concepts_present(knowledge_graph, concept_ids)

    redacted_encounters = [
        _redact_encounter(enc, redactor) for enc in encounters
    ]
    redacted_documents = [
        _redact_document(doc, redactor) for doc in documents
    ]

    new_id = f"test_{uuid.uuid4().hex[:12]}"
    display_name = _build_display_name(source, new_id)
    root_props = _strip_pii(source)

    knowledge_graph.run(
        CREATE_TEST_PATIENT_FOR_ASPECT,
        id=new_id,
        name=display_name,
        description=description or "",
        aspect=aspect,
        source_patient_id=source_patient_id,
        generation_source="cloned",
        age=root_props.get("age"),
        sex=root_props.get("sex"),
        created_by=created_by,
    )

    encounters_written = _write_test_encounters(
        knowledge_graph,
        test_patient_id=new_id,
        source_patient_id=source_patient_id,
        encounters=redacted_encounters,
    )
    documents_written = _write_test_documents(
        knowledge_graph,
        test_patient_id=new_id,
        source_patient_id=source_patient_id,
        documents=redacted_documents,
    )
    concept_rels_written = _write_test_concept_edges(
        knowledge_graph,
        test_patient_id=new_id,
        edges=concept_edges,
    )

    return {
        "id": new_id,
        "source_patient_id": source_patient_id,
        "aspect": aspect,
        "name": display_name,
        "encounters_cloned": encounters_written,
        "documents_cloned": documents_written,
        "concept_rels_cloned": concept_rels_written,
    }


def assert_deidentified(
    knowledge_graph: CodingGraphClient, *, test_patient_id: str
) -> dict:
    """Run the verification query for VT-5BDFE5F7 TC-002.

    Returns the row directly so callers can assert individual fields.
    """
    rows = knowledge_graph.run(
        ASSERT_TEST_PATIENT_DEIDENTIFIED, test_patient_id=test_patient_id
    )
    return dict(rows[0]) if rows else {}


# ---------------------------------------------------------------------------
# Read helpers (patient graph)
# ---------------------------------------------------------------------------


def _read_source(
    patient_graph: PatientGraphClient, *, source_patient_id: str
) -> dict | None:
    rows = patient_graph.run(
        READ_SOURCE_PATIENT_FOR_CLONE, source_patient_id=source_patient_id
    )
    return dict(rows[0]) if rows else None


def _read_source_encounters(
    patient_graph: PatientGraphClient, *, source_patient_id: str
) -> list[dict]:
    rows = patient_graph.run(
        READ_SOURCE_ENCOUNTERS, source_patient_id=source_patient_id
    )
    return [dict(r) for r in rows]


def _read_source_documents(
    patient_graph: PatientGraphClient, *, source_patient_id: str
) -> list[dict]:
    rows = patient_graph.run(
        READ_SOURCE_DOCUMENTS, source_patient_id=source_patient_id
    )
    return [dict(r) for r in rows]


def _read_source_concept_edges(
    patient_graph: PatientGraphClient, *, source_patient_id: str
) -> list[dict]:
    rows = patient_graph.run(
        READ_SOURCE_CONCEPT_EDGES,
        source_patient_id=source_patient_id,
        allowed_types=list(ALLOWED_CONCEPT_EDGE_TYPES),
    )
    return [dict(r) for r in rows]


def _collect_concept_ids(
    encounters: Iterable[dict], concept_edges: Iterable[dict]
) -> list[str]:
    ids: set[str] = set()
    for enc in encounters:
        for doc in enc.get("documents") or []:
            cid = doc.get("concept_id")
            if cid:
                ids.add(str(cid))
    for edge in concept_edges:
        cid = edge.get("concept_id")
        if cid:
            ids.add(str(cid))
    return sorted(ids)


def _assert_concepts_present(
    knowledge_graph: CodingGraphClient, concept_ids: list[str]
) -> None:
    if not concept_ids:
        return
    rows = knowledge_graph.run(ASSERT_CONCEPTS_PRESENT, concept_ids=concept_ids)
    missing = (rows[0].get("missing") if rows else []) or []
    if missing:
        raise CloneError(
            "Cannot clone patient: the knowledge graph is missing "
            f"{len(missing)} SNOMED concept(s) referenced by the source: "
            + ", ".join(sorted(missing))
        )


# ---------------------------------------------------------------------------
# De-identification helpers (Python)
# ---------------------------------------------------------------------------


def _strip_pii(source_row: dict[str, Any]) -> dict[str, Any]:
    """Keep only the allow-list of root properties."""
    return {k: source_row.get(k) for k in _ALLOWED_ROOT_PROPERTIES}


def _build_display_name(source_row: dict[str, Any], new_id: str) -> str:
    """Return a display name guaranteed to start with ``test_``."""
    bits: list[str] = []
    age = source_row.get("age")
    sex = source_row.get("sex")
    if age is not None:
        try:
            bits.append(f"{int(float(age))}y")
        except (TypeError, ValueError):
            pass
    if sex:
        bits.append(str(sex).title())
    suffix = ", ".join(bits) if bits else new_id[5:13]
    return f"test_{suffix}"


def _redact_text(text: str | None, redactor: Any | None) -> str:
    if text is None or text == "":
        return ""
    if redactor is None:
        # Fail loud rather than silently passing PHI through. The
        # router always injects a ClinicalTextRedactor; the only way
        # to hit this branch is unit-test misuse.
        raise CloneError(
            "Refusing to clone free text without a redactor injected. "
            "Pass redactor=ClinicalTextRedactor() (or NoopRedactor in "
            "tests that explicitly accept un-redacted text)."
        )
    try:
        redacted = str(redactor.redact(text))
    except Exception as exc:
        raise CloneError(
            f"Redactor failed; refusing to write source text to the "
            f"knowledge graph: {exc!s}"
        ) from exc
    assert_clean = getattr(redactor, "assert_clean", None)
    if callable(assert_clean):
        try:
            assert_clean(redacted)
        except Exception as exc:
            raise CloneError(
                f"Redactor left residual PHI after de-identification; "
                f"refusing to clone: {exc!s}"
            ) from exc
    return redacted


def _drop_pii_from_dict(props: dict[str, Any] | None) -> dict[str, Any]:
    if not props:
        return {}
    return {k: v for k, v in props.items() if k not in PII_KEYS_TO_STRIP}


def _redact_encounter(enc: dict[str, Any], redactor: Any | None) -> dict:
    redacted_text = _redact_text(enc.get("text"), redactor)
    extra_props = _drop_pii_from_dict(enc.get("all_properties"))
    extra_props.pop("text", None)
    extra_props.pop("id", None)
    extra_props.pop("date", None)
    extra_props.pop("flags", None)
    documents = []
    for doc in enc.get("documents") or []:
        if not doc.get("concept_id"):
            continue
        documents.append(
            {
                "concept_id": str(doc["concept_id"]),
                "rel_type": doc.get("rel_type") or "DOCUMENTS",
                "properties": _drop_pii_from_dict(doc.get("properties")),
            }
        )
    return {
        "source_id": enc.get("id"),
        "date": enc.get("date"),
        "flags": enc.get("flags"),
        "text": redacted_text,
        "extra_properties_json": json.dumps(extra_props, default=str),
        "documents": documents,
    }


def _redact_document(doc: dict[str, Any], redactor: Any | None) -> dict:
    extra_props = _drop_pii_from_dict(doc.get("all_properties"))
    extra_props.pop("text", None)
    extra_props.pop("id", None)
    extra_props.pop("title", None)
    return {
        "source_id": doc.get("id"),
        "title": doc.get("title"),
        "text": _redact_text(doc.get("text"), redactor),
        "extra_properties_json": json.dumps(extra_props, default=str),
    }


# ---------------------------------------------------------------------------
# Write helpers (knowledge graph)
# ---------------------------------------------------------------------------


def _write_test_encounters(
    knowledge_graph: CodingGraphClient,
    *,
    test_patient_id: str,
    source_patient_id: str,
    encounters: list[dict],
) -> int:
    written = 0
    for index, enc in enumerate(encounters, start=1):
        encounter_id = f"{test_patient_id}_enc_{index:03d}"
        knowledge_graph.run(
            WRITE_TEST_ENCOUNTER,
            test_patient_id=test_patient_id,
            source_patient_id=source_patient_id,
            encounter_id=encounter_id,
            text=enc.get("text") or "",
            date=enc.get("date"),
            flags=enc.get("flags"),
            extra_properties_json=enc.get("extra_properties_json") or "{}",
            documents=enc.get("documents") or [],
        )
        written += 1
    return written


def _write_test_documents(
    knowledge_graph: CodingGraphClient,
    *,
    test_patient_id: str,
    source_patient_id: str,
    documents: list[dict],
) -> int:
    written = 0
    for index, doc in enumerate(documents, start=1):
        document_id = f"{test_patient_id}_doc_{index:03d}"
        knowledge_graph.run(
            WRITE_TEST_DOCUMENT,
            test_patient_id=test_patient_id,
            source_patient_id=source_patient_id,
            document_id=document_id,
            title=doc.get("title"),
            text=doc.get("text") or "",
            extra_properties_json=doc.get("extra_properties_json") or "{}",
        )
        written += 1
    return written


def _write_test_concept_edges(
    knowledge_graph: CodingGraphClient,
    *,
    test_patient_id: str,
    edges: list[dict],
) -> int:
    written = 0
    for edge in edges:
        rel_type = (edge.get("rel_type") or "").upper()
        if rel_type not in ALLOWED_CONCEPT_EDGE_TYPES:
            continue
        concept_id = edge.get("concept_id")
        if not concept_id:
            continue
        properties = _drop_pii_from_dict(edge.get("properties"))
        properties.setdefault("is_test", True)
        knowledge_graph.run(
            WRITE_TEST_CONCEPT_EDGE,
            test_patient_id=test_patient_id,
            concept_id=str(concept_id),
            rel_type=rel_type,
            properties=properties,
        )
        written += 1
    return written
