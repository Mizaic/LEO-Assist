"""Seed SurfaceForm mappings for common UK GP filing phrases -> letter concepts.

Links to SNOMED 308470004 (Letter record artifact) unless graph lacks concept.

Run:
    python scripts/investigations/_seed_specialist_letter_surface_forms.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()

from libs.neo4j_client.client import KnowledgeGraphClient
from services.terminology_api.app.queries.terminology import UPSERT_SURFACE_FORM_MAPPING

_LETTER_CONCEPT = "308470004"

_ROWS = [
    dict(
        normalized="dermatology to",
        form="Dermatology to",
        concept_id=_LETTER_CONCEPT,
        confidence=0.85,
        source="manual",
        provenance="specialist_letter_pipeline",
    ),
    dict(
        normalized="clinic letter received",
        form="clinic letter received",
        concept_id=_LETTER_CONCEPT,
        confidence=0.9,
        source="manual",
        provenance="specialist_letter_pipeline",
    ),
    dict(
        normalized="discharge summary",
        form="discharge summary",
        concept_id=_LETTER_CONCEPT,
        confidence=0.85,
        source="manual",
        provenance="specialist_letter_pipeline",
    ),
    dict(
        normalized="letter from specialist",
        form="letter from specialist",
        concept_id=_LETTER_CONCEPT,
        confidence=0.85,
        source="manual",
        provenance="specialist_letter_pipeline",
    ),
]


def main() -> None:
    kg = KnowledgeGraphClient()
    try:
        for sf in _ROWS:
            rows = kg.run(UPSERT_SURFACE_FORM_MAPPING, **sf)
            if rows:
                r = rows[0]
                print(f"OK   {r.get('normalized')!r} => {r.get('concept_fsn')}")
            else:
                print(f"MISS concept {_LETTER_CONCEPT} for {sf['normalized']!r}")
    finally:
        kg.close()


if __name__ == "__main__":
    main()
