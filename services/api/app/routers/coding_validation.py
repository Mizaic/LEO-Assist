"""Auto-stamped Atlas trace.

Atlas trace:
  DO: DO-EC41233C
  DI: DI-9D0DF618
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-EC41233C")
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.deps import require_admin
from libs.auth.org_scope import CallerScope
from libs.terminology.client import ResolvedTerm, TerminologyClient
from libs.validation.clinical_extraction_scenario_loader import fixture_dir
from scripts.run_val_41005ba4_terminology_resolve import (
    RESOLVE_BATCH,
    _build_fact_row,
    iter_cases,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/coding-validation", tags=["coding-validation"])


class UpdateGroundTruthRequest(BaseModel):
    case_id: str
    surface_form: str
    action: str  # "accept", "remove", "add"
    new_surface_form: str | None = None
    expected_concept_id: str | None = None


def _json_loads_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, ValueError):
            return value
    return value


def _coding_client():
    from app.db.neo4j_client import CodingGraphClient

    return CodingGraphClient()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fixture_path() -> Path:
    return fixture_dir() / "expected_strings.json"


def _load_cases_from_neo4j() -> list[dict[str, Any]]:
    from libs.cypher.extraction_scenario_queries import (
        LIST_EXTRACTION_SCENARIOS,
    )

    client = _coding_client()
    try:
        rows = client.run(
            LIST_EXTRACTION_SCENARIOS, status=None, site=None, search=None
        )
    finally:
        client.close()
    if not rows:
        return []
    return [
        {
            "case_id": row["case_id"],
            "expected_strings": (
                _json_loads_safe(row.get("expected_strings")) or []
            ),
        }
        for row in rows
    ]


def _load_cases_from_fixture() -> list[dict[str, Any]]:
    return list(iter_cases())


def _load_cases() -> list[dict[str, Any]]:
    cases = _load_cases_from_neo4j()
    if cases:
        return cases
    if _fixture_path().exists():
        return _load_cases_from_fixture()
    raise HTTPException(
        status_code=404,
        detail=(
            "Extraction scenario corpus not found. "
            "Seed ExtractionScenario nodes or provide fixture files."
        ),
    )


def _apply_ground_truth_action(
    strings: list[Any], req: UpdateGroundTruthRequest
) -> tuple[list[Any], bool]:
    updated = False
    for index, item in enumerate(strings):
        if isinstance(item, dict) and item.get("text") == req.surface_form:
            if req.action == "remove":
                strings.pop(index)
                updated = True
            elif req.action == "accept":
                pass
            break
    else:
        if req.action == "add":
            strings.append(
                {"text": req.surface_form, "semantic_tag": "finding"}
            )
            updated = True
    return strings, updated


def _update_fixture_ground_truth(req: UpdateGroundTruthRequest) -> bool:
    fixture_path = _fixture_path()
    with open(fixture_path, encoding="utf-8") as handle:
        data = json.load(handle)
    updated = False
    for case in data.get("cases", []):
        if case["case_id"] != req.case_id:
            continue
        strings = case.get("expected_strings", [])
        strings, updated = _apply_ground_truth_action(strings, req)
        case["expected_strings"] = strings
        break
    if updated:
        with open(fixture_path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=4)
    return updated


def _update_neo4j_ground_truth(req: UpdateGroundTruthRequest) -> bool:
    from libs.cypher.extraction_scenario_queries import (
        GET_EXTRACTION_SCENARIO,
        PATCH_EXTRACTION_SCENARIO_EXPECTED_STRINGS,
    )

    client = _coding_client()
    try:
        rows = client.run(GET_EXTRACTION_SCENARIO, case_id=req.case_id)
        if not rows:
            raise HTTPException(status_code=404, detail="Scenario not found")
        case = rows[0]
        strings = _json_loads_safe(case.get("expected_strings")) or []
        strings, updated = _apply_ground_truth_action(strings, req)
        if not updated:
            return False
        client.run(
            PATCH_EXTRACTION_SCENARIO_EXPECTED_STRINGS,
            case_id=req.case_id,
            expected_strings=json.dumps(strings),
            updated_at=_now_iso(),
        )
    finally:
        client.close()
    return True


@router.get("")
def list_coding_validation(_: Annotated[CallerScope, Depends(require_admin)]):
    """Run terminology validation and return terms and their resolution."""
    cases = _load_cases()

    unique_terms_dict: dict[str, dict[str, str]] = {}
    for case in cases:
        for item in case.get("expected_strings", []):
            if isinstance(item, dict):
                text = str(item.get("text", "")).strip()
                tag = str(item.get("semantic_tag", "finding")).strip()
                if text:
                    unique_terms_dict[f"{text}::{tag}"] = {
                        "text": text,
                        "semantic_tag": tag,
                    }

    client = TerminologyClient(timeout=30.0)
    unique_terms = list(unique_terms_dict.values())
    unique_terms.sort(key=lambda item: item["text"].lower())
    results: dict[str, list[ResolvedTerm]] = {}

    for index in range(0, len(unique_terms), RESOLVE_BATCH):
        chunk = unique_terms[index : index + RESOLVE_BATCH]
        chunk_texts = [item["text"] for item in chunk]
        expected_tags = {
            item["text"]: item["semantic_tag"]
            for item in chunk
            if item.get("semantic_tag")
        }
        results.update(
            client.resolve(chunk_texts, expected_tags=expected_tags)
        )

    case_reports = []
    for case in cases:
        case_id = case["case_id"]
        facts = []
        for item in case.get("expected_strings", []):
            if not isinstance(item, dict):
                continue
            surface_form = str(item.get("text", "")).strip()
            tag = str(item.get("semantic_tag", "finding")).strip()
            if not surface_form:
                continue
            candidates = results.get(surface_form, [])
            fact_row = _build_fact_row(surface_form, tag, candidates)
            fact_row["semantic_tag"] = tag
            facts.append(fact_row)

        case_reports.append({"case_id": case_id, "facts": facts})

    return {"cases": case_reports, "total_terms": len(unique_terms)}


@router.post("/update")
def update_ground_truth(
    req: UpdateGroundTruthRequest,
    _: Annotated[CallerScope, Depends(require_admin)],
):
    """Update expected_strings in Neo4j or the local fixture file."""
    if _load_cases_from_neo4j():
        updated = _update_neo4j_ground_truth(req)
        return {"status": "ok", "updated": updated}

    fixture_path = _fixture_path()
    if not fixture_path.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                "Extraction scenario corpus not found. "
                "Seed ExtractionScenario nodes or provide fixture files."
            ),
        )
    updated = _update_fixture_ground_truth(req)
    return {"status": "ok", "updated": updated}
