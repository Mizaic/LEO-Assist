"""Seed the SBAR golden-set fixtures as :TestPatient rows.

Reads every YAML file in design-controls/training-data/sbar-golden-set/
that the manifest registers as a fixture and upserts a corresponding
:TestPatient {aspect: 'summarisation', is_test: true} subgraph into the
**knowledge graph**. Idempotent: re-running the script refreshes the
node properties and rebuilds the cloned encounters / expected SBAR
nodes from the YAML in place.

Why the knowledge graph?
------------------------
Test patients are configuration / regression data, not real PHI. They
live in the knowledge graph alongside SNOMED concepts, surface forms
and rule definitions so the patient graph stays clean. See the module
docstring of `libs.cypher.test_patient_queries` for the rationale.

Loud failures
-------------
Before any write happens the script verifies that every SNOMED
concept_id referenced by every fixture is already present in the
knowledge graph. If any concept is missing, the script exits non-zero
without touching the database -- this is intentional, because the
clone-from-real flow uses the same MERGE-by-snomed-id rule and we want
seed data and clone data to share the same guarantee.

Usage
-----
    python -m scripts.seed_sbar_test_patients

Linked design controls (Atlas):
    DI-59824215 (TestPatient data model)
    DI-7625C251 (centralised library)
    R-8C0CC94B (mistaking test patient for real patient)
    VT-5BDFE5F7 (centralised test patient library)
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
SBAR_DIR = REPO_ROOT / "design-controls" / "training-data" / "sbar-golden-set"
MANIFEST_PATH = SBAR_DIR / "manifest.yaml"

# Load secrets BEFORE importing the Neo4j client. The client wrapper
# auto-loads .env.config but not .env.secrets, so scripts that need
# credentials must load .env.secrets themselves first.
load_dotenv(REPO_ROOT / "secrets" / ".env.secrets")
load_dotenv(REPO_ROOT / "secrets" / ".env.config", override=True)

from libs.cypher.test_patient_queries import (  # noqa: E402
    ASSERT_CONCEPTS_PRESENT,
    RESET_SBAR_FIXTURE_CHILDREN,
    SEED_EXPECTED_SBAR,
    SEED_SBAR_ENCOUNTER,
    SEED_SBAR_TEST_PATIENT,
)
from libs.neo4j_client.client import KnowledgeGraphClient  # noqa: E402

logger = logging.getLogger(__name__)

# Mid-band ages so tests that filter on numeric age have something
# usable, while age_band remains the source of truth for cohort logic.
AGE_BAND_MIDPOINTS: dict[str, int] = {
    "0-9": 5,
    "10-19": 15,
    "20-29": 25,
    "30-39": 35,
    "40-49": 45,
    "50-59": 55,
    "60-69": 65,
    "70-79": 75,
    "80-89": 85,
    "90-99": 95,
}


def _slug(text: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "_" for ch in text)
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned.strip("_")


def _flatten_phrase_list(value: Any) -> list[str]:
    """Required-phrases fields can be str / list[str] / list[list[str]].

    Flatten to a list[str] so the seed query has a stable shape; nested
    lists (alternative phrasings) are joined with ' | ' so the reviewer
    surface can still see the alternatives.
    """
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    out: list[str] = []
    for item in value:
        if isinstance(item, list):
            out.append(" | ".join(str(x) for x in item))
        elif item is not None:
            out.append(str(item))
    return out


def _load_manifest() -> list[dict[str, Any]]:
    with MANIFEST_PATH.open("r", encoding="utf-8") as fh:
        manifest = yaml.safe_load(fh)
    fixtures = manifest.get("fixtures") or []
    if not fixtures:
        raise RuntimeError(f"manifest at {MANIFEST_PATH} declares no fixtures")
    return fixtures


def _load_fixture(file_name: str) -> dict[str, Any]:
    path = SBAR_DIR / file_name
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _collect_concept_ids(fixtures: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    for fix in fixtures:
        for enc in fix.get("resolved_background") or []:
            for code in enc.get("codes") or []:
                cid = code.get("concept_id")
                if cid:
                    seen.add(str(cid))
    return sorted(seen)


def _missing_concepts(
    client: KnowledgeGraphClient, concept_ids: list[str]
) -> list[str]:
    if not concept_ids:
        return []
    rows = client.run(ASSERT_CONCEPTS_PRESENT, concept_ids=concept_ids)
    return (rows[0].get("missing") if rows else []) or []


def _assert_concepts_present(
    client: KnowledgeGraphClient,
    concept_ids: list[str],
    allow_missing: bool = False,
) -> set[str]:
    """Pre-flight check.

    Returns the set of missing ids. When `allow_missing` is False the
    function raises SystemExit instead of returning. When True the
    caller is expected to filter encounter codes by the returned set
    and log a per-code warning for each skipped concept.
    """
    missing = _missing_concepts(client, concept_ids)
    if not missing:
        return set()
    if not allow_missing:
        raise SystemExit(
            "Refusing to seed SBAR test patients: the knowledge graph is "
            f"missing {len(missing)} SNOMED concept(s) referenced by the "
            f"golden set: {', '.join(sorted(missing))}. Load the SNOMED "
            "subset before re-running, or pass --allow-missing-concepts "
            "to skip just the affected codes."
        )
    logger.warning(
        "skipping %d concept(s) not present in the knowledge graph: %s",
        len(missing),
        ", ".join(sorted(missing)),
    )
    return set(missing)


def _test_patient_id(fixture_id: str) -> str:
    return f"test_{fixture_id.lower().replace('-', '_')}"


def _build_root_props(
    fixture: dict[str, Any],
    fixture_id: str,
    file_name: str,
) -> dict[str, Any]:
    summary = (fixture.get("resolved_situation") or {}).get(
        "patient_summary"
    ) or {}
    age_band = summary.get("age_band")
    title = fixture.get("title") or fixture_id
    scenario = (fixture.get("clinical_scenario") or "").strip()
    guideline_ids = (fixture.get("input") or {}).get("guideline_ids") or []
    return {
        "id": _test_patient_id(fixture_id),
        "name": f"test_{fixture_id.lower()}_{_slug(title)[:40]}",
        "description": scenario or title,
        "title": title,
        "fixture_id": fixture_id,
        "fixture_path": f"design-controls/training-data/sbar-golden-set/{file_name}",
        "age": AGE_BAND_MIDPOINTS.get(age_band) if age_band else None,
        "age_band": age_band,
        "sex": summary.get("sex"),
        "smoking_status": summary.get("smoking_status"),
        "guideline_ids": list(guideline_ids),
        "created_by": "sbar-importer",
    }


def _build_encounter_payload(
    enc: dict[str, Any],
    fixture_id: str,
    tp_id: str,
    index: int,
) -> dict[str, Any]:
    encounter_id = (
        f"{tp_id}_enc_{index:02d}_"
        f"{_slug(str(enc.get('source_id') or 'unknown'))[:30]}"
    )
    codes = []
    for code in enc.get("codes") or []:
        cid = code.get("concept_id")
        if not cid:
            continue
        codes.append(
            {
                "concept_id": str(cid),
                "term": code.get("term"),
                "assertion": code.get("assertion") or "present",
            }
        )
    return {
        "tp_id": tp_id,
        "encounter_id": encounter_id,
        "source_label": enc.get("source_label"),
        "source_id": enc.get("source_id"),
        "text": (enc.get("text") or "").strip(),
        "fixture_id": fixture_id,
        "codes": codes,
    }


def _build_expected_sbar_payload(
    fixture: dict[str, Any],
    fixture_id: str,
    tp_id: str,
) -> dict[str, Any]:
    transcript = fixture.get("llm_transcript") or {}
    expectations = fixture.get("reviewer_expectations") or {}
    evaluator = fixture.get("evaluator_response") or {}
    matched = evaluator.get("matched_rules") or []
    matched_ids = [str(m.get("rule_id")) for m in matched if m.get("rule_id")]
    return {
        "tp_id": tp_id,
        "sbar_id": f"{tp_id}_expected_sbar",
        "fixture_id": fixture_id,
        "situation_md": (transcript.get("situation") or {}).get("markdown")
        or "",
        "background_md": (transcript.get("background") or {}).get("markdown")
        or "",
        "recommendation_md": (transcript.get("recommendation") or {}).get(
            "markdown"
        )
        or "",
        "matched_rule_ids": matched_ids,
        "required_phrases": _flatten_phrase_list(
            expectations.get("required_phrases_in_assessment")
        )
        + _flatten_phrase_list(
            expectations.get("required_phrases_in_recommendation")
        ),
        "banned_phrases": _flatten_phrase_list(
            expectations.get("banned_phrases")
        ),
        "expected_action_priority": expectations.get(
            "expected_action_priority"
        ),
        "reviewer_focus": (expectations.get("reviewer_focus") or "").strip(),
        "evaluator_outage": bool(evaluator.get("outage", False)),
    }


def _seed_fixture(
    client: KnowledgeGraphClient,
    fixture: dict[str, Any],
    file_name: str,
    skip_concepts: set[str] | None = None,
) -> tuple[str, int]:
    fixture_id = str(fixture.get("id") or "").strip()
    if not fixture_id:
        raise ValueError(f"fixture in {file_name} is missing an id")
    tp_id = _test_patient_id(fixture_id)
    skip = skip_concepts or set()

    root = _build_root_props(fixture, fixture_id, file_name)
    client.run(SEED_SBAR_TEST_PATIENT, **root)
    client.run(
        RESET_SBAR_FIXTURE_CHILDREN, id=tp_id, id_prefix=f"{tp_id}_"
    )

    encounters = fixture.get("resolved_background") or []
    for index, enc in enumerate(encounters, start=1):
        payload = _build_encounter_payload(enc, fixture_id, tp_id, index)
        if skip:
            payload["codes"] = [
                c for c in payload["codes"] if c["concept_id"] not in skip
            ]
        if not payload["codes"] and not payload["text"]:
            continue
        client.run(SEED_SBAR_ENCOUNTER, **payload)

    sbar_payload = _build_expected_sbar_payload(fixture, fixture_id, tp_id)
    client.run(SEED_EXPECTED_SBAR, **sbar_payload)
    return tp_id, len(encounters)


def seed(
    client: KnowledgeGraphClient | None = None,
    allow_missing_concepts: bool = False,
) -> list[str]:
    own = client is None
    graph = client or KnowledgeGraphClient()
    try:
        manifest = _load_manifest()
        fixtures = [
            (entry, _load_fixture(entry["file"])) for entry in manifest
        ]
        concept_ids = _collect_concept_ids([fix for _, fix in fixtures])
        skip = _assert_concepts_present(
            graph, concept_ids, allow_missing=allow_missing_concepts
        )
        seeded: list[str] = []
        for entry, fixture in fixtures:
            tp_id, n_enc = _seed_fixture(
                graph, fixture, entry["file"], skip_concepts=skip
            )
            logger.info(
                "seeded %s (%s) with %d encounter(s)",
                tp_id,
                entry.get("file"),
                n_enc,
            )
            seeded.append(tp_id)
        return seeded
    finally:
        if own:
            graph.close()


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="enable INFO logging",
    )
    parser.add_argument(
        "--allow-missing-concepts",
        action="store_true",
        help=(
            "Skip individual codes whose SNOMED id is not in the "
            "knowledge graph instead of failing loudly. Use only when "
            "you accept partial seed data; the affected encounters will "
            "still be created."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(message)s",
    )
    seeded = seed(allow_missing_concepts=args.allow_missing_concepts)
    print(
        f"seeded {len(seeded)} SBAR test patient(s) "
        "into the knowledge graph"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
