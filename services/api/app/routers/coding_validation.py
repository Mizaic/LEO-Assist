import json
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.deps import require_admin
from libs.auth.org_scope import CallerScope
from libs.terminology.client import TerminologyClient, ResolvedTerm
from libs.validation.clinical_extraction_scenario_loader import fixture_dir
from scripts.run_val_41005ba4_terminology_resolve import (
    _build_fact_row,
    iter_cases,
    RESOLVE_BATCH,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/coding-validation", tags=["coding-validation"])

class UpdateGroundTruthRequest(BaseModel):
    case_id: str
    surface_form: str
    action: str  # "accept", "remove", "add"
    new_surface_form: str | None = None
    expected_concept_id: str | None = None

@router.get("")
def list_coding_validation(_: Annotated[CallerScope, Depends(require_admin)]):
    """Run terminology validation and return terms and their resolution."""
    try:
        cases = list(iter_cases())
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Fixture not found") from exc

    unique_terms_dict = {}
    for case in cases:
        for s in case.get("expected_strings", []):
            if isinstance(s, dict):
                text = str(s.get("text", "")).strip()
                tag = str(s.get("semantic_tag", "finding")).strip()
                if text:
                    unique_terms_dict[f"{text}::{tag}"] = {"text": text, "semantic_tag": tag}

    client = TerminologyClient(timeout=30.0)
    unique_terms = list(unique_terms_dict.values())
    unique_terms.sort(key=lambda x: x["text"].lower())
    results: dict[str, list[ResolvedTerm]] = {}
    
    # Resolve all terms in batches
    for i in range(0, len(unique_terms), RESOLVE_BATCH):
        chunk = unique_terms[i : i + RESOLVE_BATCH]
        chunk_texts = [t["text"] for t in chunk]
        expected_tags = {t["text"]: t["semantic_tag"] for t in chunk if t.get("semantic_tag")}
        results.update(client.resolve(chunk_texts, expected_tags=expected_tags))
        
    case_reports = []
    for case in cases:
        case_id = case["case_id"]
        strings = case.get("expected_strings", [])
        facts = []
        for s in strings:
            if not isinstance(s, dict):
                continue
            s_str = str(s.get("text", "")).strip()
            tag = str(s.get("semantic_tag", "finding")).strip()
            if not s_str:
                continue
            candidates = results.get(s_str, [])
            fact_row = _build_fact_row(s_str, tag, candidates)
            fact_row["semantic_tag"] = tag
            facts.append(fact_row)
            
        case_reports.append({
            "case_id": case_id,
            "facts": facts,
        })
        
    return {"cases": case_reports, "total_terms": len(unique_terms)}

@router.post("/update")
def update_ground_truth(
    req: UpdateGroundTruthRequest,
    _: Annotated[CallerScope, Depends(require_admin)]
):
    """Update expected_strings or alias mapping (conceptually)."""
    # For MVP, this could just write to the local JSON file
    fixture_path = fixture_dir() / "expected_strings.json"
    if not fixture_path.exists():
        raise HTTPException(status_code=404, detail="Fixture not found")
        
    with open(fixture_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    updated = False
    for case in data.get("cases", []):
        if case["case_id"] == req.case_id:
            strings = case.get("expected_strings", [])
            for i, s in enumerate(strings):
                if isinstance(s, dict) and s.get("text") == req.surface_form:
                    if req.action == "remove":
                        strings.pop(i)
                        updated = True
                    elif req.action == "accept":
                        pass
                    break
            else:
                if req.action == "add":
                    strings.append({"text": req.surface_form, "semantic_tag": "finding"})
                    updated = True
                    
            case["expected_strings"] = strings
            break
            
    if updated:
        with open(fixture_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
            
    return {"status": "ok", "updated": updated}
