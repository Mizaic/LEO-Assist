"""Live persist: teach the imaging phrases a referral letter actually prints.

NHS 4568668417 arrived with three completed imaging studies listed in the
investigation log::

    | 30 May 2026: Standard chest X-ray (535..) |
    | 24 Jun 2026: US PELVIS |
    | 24 Jun 2026: US PELVIS TRANSVAGINAL |

None of them was coded, and rule 1.5.2 then asked for a pelvic ultrasound
the letter already reported. Two surfaces own that miss. Recall belongs to
the few-shot library in PromptConfig. The phrase-to-concept mapping belongs
here, in SurfaceForm, per ``.cursor/rules/architecture-first.mdc``: it is not
a job for a hardcoded map in Python.

Ward shorthand is what gets typed on a form. "US PELVIS" is not a SNOMED
term and never will be, so it has to be taught.

Opt-in:

  LIVE_NEO4J_GUIDANCE=1 pytest tests/test_imaging_surface_forms_live_persist.py -v

Atlas: DI-47D2CD86 (surface-form approval), DI-B3B44F09 (already-done).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

from libs.neo4j_client.client import KnowledgeGraphClient
from libs.terminology.surface_form_policy import (
    APPROVED_SURFACE_FORM_STATUS,
    is_resolvable_surface_form_status,
)

pytestmark = pytest.mark.skipif(
    os.getenv("LIVE_NEO4J_GUIDANCE") != "1",
    reason="Set LIVE_NEO4J_GUIDANCE=1 to write imaging SurfaceForms.",
)

#: Phrase as printed, and the procedure it names.
#:
#: Each target is the scan itself, not what the scan found. A procedure code
#: is what proves the investigation was carried out, which is what the
#: already-done check reads.
IMAGING_SURFACE_FORMS: tuple[tuple[str, str, str], ...] = (
    ("US PELVIS", "24848001", "Pelvic echography"),
    ("US Pelvis", "24848001", "Pelvic echography"),
    ("pelvic ultrasound", "24848001", "Pelvic echography"),
    (
        "US PELVIS TRANSVAGINAL",
        "315011000000105",
        "Transvaginal ultrasound scan of pelvis",
    ),
    (
        "US Pelvis transvaginal",
        "315011000000105",
        "Transvaginal ultrasound scan of pelvis",
    ),
    (
        "transvaginal ultrasound scan of pelvis",
        "315011000000105",
        "Transvaginal ultrasound scan of pelvis",
    ),
    ("Standard chest X-ray", "399208008", "Plain X-ray of chest"),
    ("chest x-ray", "399208008", "Plain X-ray of chest"),
)

# Everything is ON CREATE. Three of these phrases were already taught by a
# human in the gold-label editor and are already correct, so this must add
# what is missing and touch nothing that exists -- not the form, not the
# status, not the source.
_UPSERT = """
MATCH (c:Concept {id: $concept_id})
MERGE (sf:SurfaceForm {normalized: $normalized})
ON CREATE SET sf.source = 'imaging_shorthand',
              sf.created_at = datetime(),
              sf.created_by = 'teach_imaging_surface_forms',
              sf.form = $form,
              sf.status = $status
MERGE (sf)-[m:MAPS_TO]->(c)
ON CREATE SET m.created_at = datetime(),
              m.created_by = 'teach_imaging_surface_forms',
              m.approved_at = datetime(),
              m.confidence = 1.0,
              m.provenance = 'imaging_shorthand'
RETURN sf.normalized AS normalized, sf.status AS status, c.id AS concept_id
"""

_READ = """
MATCH (sf:SurfaceForm {normalized: $normalized})-[:MAPS_TO]->(c:Concept)
RETURN sf.status AS status, collect(c.id) AS concept_ids
"""


def _normalise(phrase: str) -> str:
    return " ".join(phrase.strip().lower().split())


@pytest.fixture(scope="module")
def kg_client():
    root = Path(__file__).resolve().parent.parent
    load_dotenv(root / "secrets" / ".env.config", override=True)
    load_dotenv(root / "secrets" / ".env", override=False)
    load_dotenv(root / ".env", override=False)
    client = KnowledgeGraphClient()
    yield client
    client.close()


def test_the_target_concepts_exist_before_we_map_to_them(kg_client) -> None:
    """A mapping to a concept the graph does not hold resolves to nothing."""
    for _phrase, concept_id, expected in IMAGING_SURFACE_FORMS:
        rows = kg_client.run(
            "MATCH (c:Concept {id: $id}) RETURN c.fsn AS fsn", id=concept_id
        )
        assert rows, f"{concept_id} is not in the graph"
        assert expected.lower() in str(rows[0]["fsn"]).lower()


def test_persist_imaging_surface_forms(kg_client) -> None:
    for phrase, concept_id, _display in IMAGING_SURFACE_FORMS:
        rows = kg_client.run(
            _UPSERT,
            normalized=_normalise(phrase),
            form=phrase.strip(),
            concept_id=concept_id,
            status=APPROVED_SURFACE_FORM_STATUS,
        )
        assert rows, f"{phrase!r} did not map to {concept_id}"
        assert rows[0]["concept_id"] == concept_id


def test_each_phrase_now_resolves_to_its_scan(kg_client) -> None:
    for phrase, concept_id, _display in IMAGING_SURFACE_FORMS:
        rows = kg_client.run(_READ, normalized=_normalise(phrase))
        assert rows, f"{phrase!r} has no SurfaceForm"
        assert concept_id in rows[0]["concept_ids"]
        assert is_resolvable_surface_form_status(rows[0]["status"])


def test_the_pelvic_phrases_land_in_the_pelvic_ultrasound_family(kg_client) -> None:
    """A phrase that codes outside the family still would not read as done."""
    from libs.guidelines.investigation_family_catalog import (
        FETCH_INVESTIGATION_FAMILIES,
        family_ids_for_concept,
        index_family_rows,
    )

    index = index_family_rows(kg_client.run(FETCH_INVESTIGATION_FAMILIES))
    # 418394000 is what NG12 rule 1.5.2 asks for.
    family = family_ids_for_concept("418394000", index)
    assert "24848001" in family
    assert "315011000000105" in family
