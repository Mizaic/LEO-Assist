"""Copy a real patient as a de-identified :TestPatient.

Implements DI-59824215 (Atlas) -- the "copy a real patient and
de-identify" action that powers the Knowledge > Test Patients page.

What this module does, in plain English:

1. Reads a real :Patient row from the patient graph.
2. Creates a new :TestPatient root node next to it. The new node
   carries:
       - a brand new id (always prefixed "test_")
       - an `aspect` tag (one of nlp / episodes / guidelines /
         summarisation) so the library can filter by what the patient
         is for
       - `is_test = true` so any future label-agnostic query can also
         filter it out
       - a `source_patient_id` pointer back to the source row, kept
         only so the QA lead can re-clone after the source changes
       - a display name that ALWAYS starts with "test_"
3. Mirrors the source subgraph at the level needed for replay across
   every aspect:
       - every (:Patient)-[:HAS_ENCOUNTER]->(:Encounter) is cloned
         under the new root with a fresh id and `is_test = true`
       - every (:Patient)-[:HAS_DOCUMENT]->(:Document) is cloned the
         same way
       - direct concept relationships from the patient root
         (HAS_FINDING / HAS_DISORDER / HAS_OBSERVABLE / HAS_PROCEDURE
         / HAS_SITUATION / HAS_CONCEPT) are re-pointed at the same
         SNOMED concept nodes (concepts are reference data, not PII)
4. Strips every identifiable property the source carried (NHS number,
   name, date of birth, address, phone numbers and a longer list of
   common PII keys) before persisting the new root. The test patient
   age and sex ARE kept because they drive coding/guideline rules.

Risk R-8C0CC94B (Atlas) -- "test patient mistaken for a real patient
on a clinician surface" -- is mitigated by three independent layers
implemented here and in the queries:
    a. Separate :TestPatient label so production `MATCH (p:Patient)`
       queries cannot return cloned patients.
    b. `is_test = true` propagated to every cloned node and
       relationship, so any future property-level filter also catches
       them.
    c. `test_` display-name prefix so a clinician glimpsing the row
       on any surface can see it is fake.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from app.db.neo4j_client import CodingGraphClient
from libs.cypher.test_patient_queries import (
    ASSERT_TEST_PATIENT_DEIDENTIFIED,
    CLONE_PATIENT_CONCEPT_RELATIONSHIPS_NO_APOC,
    CLONE_PATIENT_DOCUMENTS,
    CLONE_PATIENT_ENCOUNTERS,
    CREATE_TEST_PATIENT_FOR_ASPECT,
    GET_SOURCE_PATIENT_FOR_CLONE,
    LIST_REAL_PATIENTS_FOR_CLONE_PICKER,
    TEST_PATIENT_ASPECTS,
)

logger = logging.getLogger(__name__)


# Properties that MUST NOT survive a clone. The clone never copies
# the source patient's properties bag wholesale; it only copies the
# small allow-list of fields below. Every other source property is
# dropped, including any future PII fields a tenant adds.
_ALLOWED_ROOT_PROPERTIES: frozenset[str] = frozenset(
    {"age", "sex"}
)


# Properties the verification step will assert are NULL on the cloned
# root. Mirrors DI-59824215 acceptance criterion 2 (no NHS number /
# name / date of birth / address / phone numbers).
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
    source, etc.). Translates to HTTP 4xx in the router."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def list_source_patients(
    client: CodingGraphClient, *, limit: int = 50
) -> list[dict]:
    """Return real patients that can be cloned, most active first.

    Backs the source-picker dropdown in the Clone-from-real dialog.
    """
    rows = client.run(LIST_REAL_PATIENTS_FOR_CLONE_PICKER, limit=int(limit))
    return [dict(r) for r in rows]


def clone_patient_as_test_patient(
    client: CodingGraphClient,
    *,
    source_patient_id: str,
    aspect: str,
    created_by: str,
    description: str = "",
) -> dict:
    """Copy `source_patient_id` to a new :TestPatient and return it.

    Returns ``{id, source_patient_id, aspect, encounters_cloned,
    documents_cloned, concept_rels_cloned}`` on success. Raises
    :class:`CloneError` if the aspect is invalid or the source does
    not exist.
    """
    aspect = (aspect or "").lower().strip()
    if aspect not in TEST_PATIENT_ASPECTS:
        raise CloneError(
            "aspect must be one of " + ", ".join(TEST_PATIENT_ASPECTS)
        )

    source = _load_source(client, source_patient_id=source_patient_id)
    if source is None:
        raise CloneError(
            f"Source patient {source_patient_id!r} not found or already a test patient"
        )

    new_id = f"test_{uuid.uuid4().hex[:12]}"
    id_prefix = f"{new_id}_"

    display_name = _build_display_name(source, new_id)
    root_props = _strip_pii(source)

    client.run(
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

    encounters = _run_cloned_count(
        client,
        CLONE_PATIENT_ENCOUNTERS,
        source_patient_id=source_patient_id,
        test_patient_id=new_id,
        id_prefix=id_prefix,
        result_key="encounters_cloned",
    )
    documents = _run_cloned_count(
        client,
        CLONE_PATIENT_DOCUMENTS,
        source_patient_id=source_patient_id,
        test_patient_id=new_id,
        id_prefix=id_prefix,
        result_key="documents_cloned",
    )
    concept_rels = _run_cloned_count(
        client,
        CLONE_PATIENT_CONCEPT_RELATIONSHIPS_NO_APOC,
        source_patient_id=source_patient_id,
        test_patient_id=new_id,
        result_key="rel_count",
    )

    return {
        "id": new_id,
        "source_patient_id": source_patient_id,
        "aspect": aspect,
        "name": display_name,
        "encounters_cloned": encounters,
        "documents_cloned": documents,
        "concept_rels_cloned": concept_rels,
    }


def assert_deidentified(
    client: CodingGraphClient, *, test_patient_id: str
) -> dict:
    """Run the verification query for VT-5BDFE5F7 TC-002.

    Returns the row directly so callers (router, tests) can assert
    individual fields.
    """
    rows = client.run(
        ASSERT_TEST_PATIENT_DEIDENTIFIED, test_patient_id=test_patient_id
    )
    return dict(rows[0]) if rows else {}


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _load_source(
    client: CodingGraphClient, *, source_patient_id: str
) -> dict | None:
    rows = client.run(
        GET_SOURCE_PATIENT_FOR_CLONE, source_patient_id=source_patient_id
    )
    return dict(rows[0]) if rows else None


def _strip_pii(source_row: dict[str, Any]) -> dict[str, Any]:
    """Keep only the allow-list of root properties.

    Anything not in :data:`_ALLOWED_ROOT_PROPERTIES` is dropped, which
    protects against future PII keys appearing on :Patient.
    """
    return {k: source_row.get(k) for k in _ALLOWED_ROOT_PROPERTIES}


def _build_display_name(source_row: dict[str, Any], new_id: str) -> str:
    """Return a display name guaranteed to start with ``test_``.

    The original display name is not reused -- copying any of the
    source's name fields would defeat the de-id step. Instead we
    build a stable, human-readable name from the new id plus age/sex
    so the QA lead can still scan the table.
    """
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


def _run_cloned_count(
    client: CodingGraphClient,
    cypher: str,
    *,
    result_key: str,
    **params: Any,
) -> int:
    rows = client.run(cypher, **params)
    if not rows:
        return 0
    try:
        return int(rows[0][result_key] or 0)
    except (KeyError, TypeError, ValueError):
        return 0
