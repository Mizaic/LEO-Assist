#!/usr/bin/env python3
"""Audit and code explicit cancer diagnosis disorder entries."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_REPO_ROOT / "secrets" / ".env.config", override=True)
load_dotenv(_REPO_ROOT / "secrets" / ".env", override=False)
load_dotenv(_REPO_ROOT / "secrets" / ".env.secrets", override=False)

from libs.cypher.documents_queries import upsert_encounter_documents_link  # noqa: E402
from libs.neo4j_client.client import PatientGraphClient  # noqa: E402
from libs.terminology.client import ResolvedTerm, TerminologyClient  # noqa: E402

REPORT_DIR = _REPO_ROOT / "artifacts" / "cancer_diagnosis_coding"
SOURCE = "deterministic_cancer_diagnosis_coder"

CANCER_WORD_RE = re.compile(
    r"\b(?:malignant|cancer|carcinoma|adenocarcinoma|melanoma|lymphoma|"
    r"leukaemia|leukemia|metastasis|metastatic|neoplasm|tumou?r)\b",
    re.IGNORECASE,
)
EXPLICIT_CODED_RE = re.compile(
    r"(?P<prefix>\b(?:Major|Minor|Problem(?:\s*-\s*whole event)?|Diagnosis):\s*)?"
    r"(?P<term>[A-Z][^()\n\r:]{2,130}?"
    r"(?:malignant|cancer|carcinoma|adenocarcinoma|melanoma|lymphoma|"
    r"leukaemia|leukemia|metastasis|metastatic|neoplasm|tumou?r)"
    r"[^()\n\r:]{0,90}?)\s*\((?P<read>[A-Za-z0-9.]+)\)",
    re.IGNORECASE,
)
FREE_TEXT_RE = re.compile(
    r"\b(?:new diagnosis of|diagnosed with|known|reason:)\s+"
    r"(?P<term>[A-Za-z][^.\n\r;]{0,80}?"
    r"(?:cancer|carcinoma|adenocarcinoma|melanoma|lymphoma|"
    r"leukaemia|leukemia|metastatic)[^.\n\r;]{0,40})",
    re.IGNORECASE,
)
BOILERPLATE_REJECT_RE = re.compile(
    r"\b(?:fast track referral|2ww|urgent suspected cancer|cancer care review|"
    r"skin cancer follow up|screening programme|family history|fhx|pathway)\b",
    re.IGNORECASE,
)
UNCERTAIN_REVIEW_RE = re.compile(
    r"(?:\?|suspected|suspicion|suggestive|concerning|possible|probable|"
    r"rule out|\br/o\b|exclude|if abnormal|awaiting)",
    re.IGNORECASE,
)
NEGATED_REJECT_RE = re.compile(
    r"\b(?:no evidence of|no sign of|without evidence of|nad|benign|not cancer|"
    r"no mets|no metastasis|marked in error|merging problem)\b",
    re.IGNORECASE,
)

MATCH_QUERY = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WITH p, e, coalesce(e.text, '') AS text, toLower(coalesce(e.text, '')) AS t
WHERE t CONTAINS 'malignant'
   OR t CONTAINS 'cancer'
   OR t CONTAINS 'neoplasm'
   OR t CONTAINS 'tumour'
   OR t CONTAINS 'tumor'
   OR t CONTAINS 'metastasis'
   OR t CONTAINS 'metastatic'
   OR t CONTAINS 'carcinoma'
   OR t CONTAINS 'adenocarcinoma'
   OR t CONTAINS 'lymphoma'
   OR t CONTAINS 'melanoma'
   OR t CONTAINS 'leukaemia'
   OR t CONTAINS 'leukemia'
OPTIONAL MATCH (e)-[:DOCUMENTS]->(c:Concept)
WHERE toLower(coalesce(c.semanticTag, '')) = 'disorder'
RETURN toString(p.id) AS patient_id,
       toString(e.id) AS encounter_id,
       e.date AS date,
       text AS text,
       collect(DISTINCT c.conceptId) AS existing_disorder_concepts
ORDER BY patient_id, date, encounter_id
"""

@dataclass(frozen=True)
class Candidate:
    patient_id: str
    encounter_id: str
    date: str
    term: str
    lookup_text: str
    read_code: str | None
    evidence: str
    classification: str
    reason: str


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write safe links.")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--report-dir", type=Path, default=REPORT_DIR)
    return parser.parse_args()


def _load_rows(limit: int) -> list[dict[str, Any]]:
    client = PatientGraphClient()
    try:
        rows = client.run(MATCH_QUERY)
    finally:
        client.close()
    return rows[:limit] if limit > 0 else rows


def _extract_candidates(row: dict[str, Any]) -> list[Candidate]:
    text = str(row.get("text") or "")
    candidates = [
        _candidate_from_match(row, text, m) for m in EXPLICIT_CODED_RE.finditer(text)
    ]
    candidates.extend(_free_text_candidates(row, text))
    return _dedupe([candidate for candidate in candidates if candidate is not None])


def _candidate_from_match(
    row: dict[str, Any], text: str, match: re.Match[str]
) -> Candidate | None:
    term = _clean_term(match.group("term"))
    if not CANCER_WORD_RE.search(term):
        return None
    evidence = _window(text, match.start(), match.end())
    classification, reason = _classify(term, evidence, bool(match.group("prefix")))
    read_code = match.group("read")
    return Candidate(
        patient_id=str(row["patient_id"]),
        encounter_id=str(row["encounter_id"]),
        date=str(row.get("date") or ""),
        term=term,
        lookup_text=f"{term} ({read_code})",
        read_code=read_code,
        evidence=evidence,
        classification=classification,
        reason=reason,
    )


def _free_text_candidates(row: dict[str, Any], text: str) -> list[Candidate]:
    out = []
    for match in FREE_TEXT_RE.finditer(text):
        term = _clean_term(match.group("term"))
        evidence = _window(text, match.start(), match.end())
        classification, reason = _classify(term, evidence, has_prefix=True)
        out.append(
            Candidate(
                patient_id=str(row["patient_id"]),
                encounter_id=str(row["encounter_id"]),
                date=str(row.get("date") or ""),
                term=term,
                lookup_text=term,
                read_code=None,
                evidence=evidence,
                classification=classification,
                reason=reason,
            )
        )
    return out


def _classify(term: str, evidence: str, has_prefix: bool) -> tuple[str, str]:
    lowered = f"{term} {evidence}".lower()
    if NEGATED_REJECT_RE.search(lowered):
        return "reject", "negated_or_marked_in_error"
    if BOILERPLATE_REJECT_RE.search(lowered) and not _has_diagnosis_prefix(evidence):
        return "reject", "boilerplate_or_referral_context"
    if UNCERTAIN_REVIEW_RE.search(lowered):
        return "review", "uncertain_or_suspected_context"
    if not has_prefix and not re.search(
        r"\b(?:diagnosed|diagnosis|known|reason:)\b", lowered
    ):
        return "review", "free_text_without_diagnosis_anchor"
    return "safe", "explicit_diagnosis_context"


def _has_diagnosis_prefix(evidence: str) -> bool:
    return bool(re.search(r"\b(?:Major|Minor|Problem|Diagnosis):", evidence, re.I))


def _resolve(candidates: list[Candidate]) -> dict[str, list[ResolvedTerm]]:
    terms = list(
        dict.fromkeys(c.lookup_text for c in candidates if c.classification == "safe")
    )
    return TerminologyClient(timeout=30, max_retries=1).resolve(
        terms, {term: "disorder" for term in terms}
    )


def _finalise(
    candidate: Candidate,
    resolved: dict[str, list[ResolvedTerm]],
    existing: set[str],
) -> dict[str, Any]:
    top = (resolved.get(candidate.lookup_text) or [None])[0]
    status = _status(candidate, top)
    concept_id = top.concept_id if top else None
    return {
        "status": status,
        "patient_id": candidate.patient_id,
        "encounter_id": candidate.encounter_id,
        "date": candidate.date,
        "term": candidate.term,
        "lookup_text": candidate.lookup_text,
        "read_code": candidate.read_code,
        "classification": candidate.classification,
        "reason": candidate.reason,
        "evidence": candidate.evidence,
        "concept_id": concept_id,
        "snomed_term": top.term if top else None,
        "semantic_tag": top.semantic_tag if top else None,
        "score": top.score if top else None,
        "had_exact_match": top.had_exact_match if top else False,
        "already_linked": bool(concept_id and concept_id in existing),
        "write_eligible": status == "safe",
    }


def _status(candidate: Candidate, top: ResolvedTerm | None) -> str:
    if candidate.classification != "safe":
        return candidate.classification
    if top is None:
        return "unresolved"
    if _tag(top.semantic_tag) != "disorder":
        return "wrong_semantic_tag"
    if not top.had_exact_match and candidate.read_code is None:
        return "review"
    if not _concept_is_semantically_safe(candidate, top):
        return "review"
    return "safe"


def _concept_is_semantically_safe(candidate: Candidate, top: ResolvedTerm) -> bool:
    source = f"{candidate.term} {candidate.evidence}".lower()
    snomed = str(top.term or "").lower()
    if "pilomatrix" in snomed and "pilomatrix" not in source:
        return False
    if "oropharynx" in snomed and not re.search(
        r"\b(oropharynx|mouth|oral|buccal)\b", source
    ):
        return False
    if "testis" in snomed and not re.search(r"\b(testis|testicular)\b", source):
        return False
    if "ovary" in snomed and not re.search(r"\b(ovary|ovarian)\b", source):
        return False
    ambiguous = (
        "infiltrating duct carcinoma",
        "endometrioid carcinoma",
        "metastatic carcinoma",
        "granulosa cell tumour",
        "granulosa cell tumor",
    )
    if any(term in source for term in ambiguous):
        return False
    return True


def _apply(items: list[dict[str, Any]]) -> int:
    client = PatientGraphClient()
    applied = 0
    try:
        with client.session() as session:
            for item in items:
                if not item["write_eligible"] or item["already_linked"]:
                    continue
                upsert_encounter_documents_link(
                    session,
                    str(item["patient_id"]),
                    str(item["encounter_id"]),
                    str(item["concept_id"]),
                    "disorder",
                    str(item.get("snomed_term") or ""),
                    str(item.get("evidence") or ""),
                    read_code=item.get("read_code"),
                    assertion="present",
                    modifiers={"source": SOURCE, "lookup_text": item["lookup_text"]},
                    source=SOURCE,
                    model_name=SOURCE,
                    model_version="2026-04-25",
                    confidence=float(item.get("score") or 0.0) or 0.95,
                )
                applied += 1
    finally:
        client.close()
    return applied


def _summary(
    items: list[dict[str, Any]], rows_scanned: int, applied: int
) -> dict[str, int]:
    return {
        "encounters_scanned": rows_scanned,
        "candidates": len(items),
        "safe": sum(1 for item in items if item["status"] == "safe"),
        "review": sum(1 for item in items if item["status"] == "review"),
        "reject": sum(1 for item in items if item["status"] == "reject"),
        "unresolved": sum(1 for item in items if item["status"] == "unresolved"),
        "wrong_semantic_tag": sum(
            1 for item in items if item["status"] == "wrong_semantic_tag"
        ),
        "already_linked": sum(1 for item in items if item["already_linked"]),
        "to_add": sum(
            1 for item in items if item["write_eligible"] and not item["already_linked"]
        ),
        "patients_with_safe": len(
            {i["patient_id"] for i in items if i["status"] == "safe"}
        ),
        "patients_to_add": len(
            {
                i["patient_id"]
                for i in items
                if i["write_eligible"] and not i["already_linked"]
            }
        ),
        "applied": applied,
    }


def _write_report(report_dir: Path, report: dict[str, Any]) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    mode = "apply" if report["apply"] else "dry_run"
    json_path = report_dir / f"cancer_diagnosis_coding_{mode}_{stamp}.json"
    csv_path = report_dir / f"cancer_diagnosis_coding_{mode}_{stamp}.csv"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        rows = report["items"]
        writer = csv.DictWriter(
            handle, fieldnames=list(rows[0]) if rows else ["status"]
        )
        writer.writeheader()
        writer.writerows(rows)
    return json_path


def _dedupe(candidates: list[Candidate]) -> list[Candidate]:
    seen = set()
    out = []
    for candidate in candidates:
        key = (candidate.encounter_id, candidate.lookup_text.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(candidate)
    return out


def _clean_term(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip(" -:;,.")
    value = re.sub(r"\s+-\s+.*$", "", value).strip()
    value = re.sub(r"^(?:Major|Minor|Problem|Diagnosis):\s*", "", value, flags=re.I)
    return value


def _window(text: str, start: int, end: int) -> str:
    left = max(0, start - 120)
    right = min(len(text), end + 180)
    return re.sub(r"\s+", " ", text[left:right]).strip()


def _tag(raw: str | None) -> str:
    return str(raw or "").strip().lower().replace(" ", "_").replace("-", "_")


def main() -> int:
    args = _parse_args()
    rows = _load_rows(args.limit)
    existing = {
        str(row["encounter_id"]): {
            str(concept_id)
            for concept_id in (row.get("existing_disorder_concepts") or [])
            if concept_id
        }
        for row in rows
    }
    candidates = [candidate for row in rows for candidate in _extract_candidates(row)]
    resolved = _resolve(candidates)
    items = [
        _finalise(candidate, resolved, existing.get(candidate.encounter_id, set()))
        for candidate in candidates
    ]
    applied = _apply(items) if args.apply else 0
    report = {
        "apply": bool(args.apply),
        "summary": _summary(items, len(rows), applied),
        "items": items,
    }
    path = _write_report(args.report_dir, report)
    print(json.dumps({"report": str(path), **report["summary"]}, indent=2))
    return 0 if report["summary"]["wrong_semantic_tag"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
