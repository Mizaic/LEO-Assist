#!/usr/bin/env python3
"""Dry-run-first deterministic coding for 2WW / fast-track encounters."""

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

DEFAULT_REPORT_DIR = _REPO_ROOT / "artifacts" / "encounter_2ww_coding"

LABEL_FINDING = "finding"
LABEL_PROCEDURE = "procedure"
LABEL_SITUATION = "situation"

EXPECTED_SITUATIONS = {
    "generic": ("162572001", "Malignant neoplastic disease suspected"),
    "breast": ("134405005", "Malignant neoplasm of breast suspected"),
    "lower_gi": (
        "315274008",
        "Malignant neoplasm of lower gastrointestinal tract suspected",
    ),
    "upper_gi": (
        "315273002",
        "Malignant neoplasm of upper gastrointestinal tract suspected",
    ),
    "urology": ("397657005", "Malignant neoplasm of urinary system suspected"),
    "prostate": ("315268008", "Malignant neoplasm of prostate suspected"),
    "gynae": ("397682005", "Malignant neoplasm of female genital organ suspected"),
    "skin": ("315276005", "Malignant neoplasm of skin suspected"),
    "head_neck": ("315277001", "Malignant neoplasm of head and/or neck suspected"),
    "lung": ("162573006", "Malignant neoplasm of lung suspected"),
    "haematology": ("315275009", "Hematological malignancy suspected"),
    "lymphoma": ("315264005", "Malignant lymphoma suspected"),
}

SITE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("prostate", re.compile(r"\b(?:prostate|psa)\b", re.IGNORECASE)),
    (
        "lower_gi",
        re.compile(r"\b(?:lgi|lower\s+gi|bowel|colorectal|colon|fit)\b", re.IGNORECASE),
    ),
    (
        "upper_gi",
        re.compile(
            r"\b(?:ugi|upper\s+gi|oesophag|esophag|gastric|stomach|hpb)\b",
            re.IGNORECASE,
        ),
    ),
    ("breast", re.compile(r"\bbreast\b", re.IGNORECASE)),
    (
        "gynae",
        re.compile(
            r"\b(?:gynae|gynaecology|gynaecological|gyne|gynecological|vulva|vaginal|ovarian|uterine)\b",
            re.IGNORECASE,
        ),
    ),
    ("skin", re.compile(r"\b(?:skin|derm(?:atology)?|melanoma)\b", re.IGNORECASE)),
    (
        "head_neck",
        re.compile(
            r"\b(?:h&n|head\s+and\s+neck|ent|neck|throat|oral|mouth|tongue)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "lung",
        re.compile(
            r"\b(?:lung|chest|respiratory|haemoptysis|hemoptysis)\b", re.IGNORECASE
        ),
    ),
    ("lymphoma", re.compile(r"\blymphoma\b", re.IGNORECASE)),
    (
        "haematology",
        re.compile(
            r"\b(?:haematology|hematology|haematological|hematological|blood\s+cancer)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "urology",
        re.compile(
            r"\b(?:urology|urological|uro|urinary|bladder|renal|kidney|testicular|testis)\b",
            re.IGNORECASE,
        ),
    ),
)

TWW_TARGET_SITE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "head_neck",
        re.compile(
            r"\b(?:2\s*ww|tww|two[-\s]+week[-\s]+wait)\s+"
            r"(?:h&n|head\s+and\s+neck|neck|ent|throat|oral|mouth|tongue)\b|"
            r"\b(?:h&n|head\s+and\s+neck|neck|ent|throat|oral|mouth|tongue)"
            r"\s+(?:2\s*ww|tww|two[-\s]+week[-\s]+wait)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "skin",
        re.compile(
            r"\b(?:2\s*ww|tww|two[-\s]+week[-\s]+wait)\s+"
            r"(?:skin|derm(?:atology)?|melanoma)\b|"
            r"\b(?:skin|derm(?:atology)?|melanoma)\s+"
            r"(?:2\s*ww|tww|two[-\s]+week[-\s]+wait)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "breast",
        re.compile(
            r"\b(?:2\s*ww|tww|two[-\s]+week[-\s]+wait)\s+breast\b|"
            r"\bbreast\s+(?:2\s*ww|tww|two[-\s]+week[-\s]+wait)\b",
            re.IGNORECASE,
        ),
    ),
)

READ_CODE_RE = r"(?:\s+\([A-Za-z0-9.]+\))?"
FAST_REFERRAL_RE = re.compile(
    rf"\bFast\s+track\s+referral\s+for\s+suspected\s+[^.\n\r;()]+{READ_CODE_RE}",
    re.IGNORECASE,
)
SEEN_FAST_TRACK_RE = re.compile(
    rf"\bSeen\s+in\s+fast\s+track\s+suspected\s+[^.\n\r;()]+clinic{READ_CODE_RE}",
    re.IGNORECASE,
)
TWW_LINE_RE = re.compile(
    r"(?im)^[^\n\r]{0,90}\b(?:2\s*ww|tww|two[-\s]+week[-\s]+wait)\b[^\n\r]{0,90}$"
)

MATCH_QUERY = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WITH p, e, coalesce(e.text, '') AS text
WITH p, e, text,
  CASE WHEN toLower(text) CONTAINS '2ww' THEN 1 ELSE 0 END +
  CASE WHEN toLower(text) CONTAINS '2 ww' THEN 1 ELSE 0 END +
  CASE WHEN toLower(text) CONTAINS 'tww' THEN 1 ELSE 0 END +
  CASE WHEN toLower(text) CONTAINS 'two-week wait' THEN 1 ELSE 0 END +
  CASE WHEN toLower(text) CONTAINS 'two week wait' THEN 1 ELSE 0 END +
  CASE WHEN toLower(text) CONTAINS 'fast track' THEN 1 ELSE 0 END +
  CASE WHEN toLower(text) CONTAINS 'suspected cancer' THEN 1 ELSE 0 END +
  CASE WHEN toLower(text) CONTAINS 'cancer referral' THEN 1 ELSE 0 END AS hit_count
WHERE hit_count > 0
OPTIONAL MATCH (e)-[:DOCUMENTS]->(c)
RETURN toString(p.id) AS patient_id,
       toString(e.id) AS encounter_id,
       e.date AS date,
       e.source_label AS source_label,
       text AS text,
       collect(DISTINCT c.conceptId) AS existing_concept_ids
ORDER BY patient_id, encounter_id
"""

@dataclass(frozen=True)
class Proposal:
    patient_id: str
    encounter_id: str
    date: str
    term: str
    label: str
    site: str
    source: str
    evidence: str
    assertion: str
    expected_concept_id: str | None = None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write safe codes.")
    parser.add_argument(
        "--limit", type=int, default=0, help="Optional encounter limit."
    )
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    return parser.parse_args()


def _load_rows(limit: int) -> list[dict[str, Any]]:
    client = PatientGraphClient()
    try:
        rows = client.run(MATCH_QUERY)
    finally:
        client.close()
    return rows[:limit] if limit > 0 else rows


def _extract_proposals(row: dict[str, Any]) -> list[Proposal]:
    text = str(row.get("text") or "")
    proposals = []
    proposals.extend(
        _explicit_proposals(
            row, text, FAST_REFERRAL_RE, LABEL_PROCEDURE, "fast_referral"
        )
    )
    proposals.extend(
        _explicit_proposals(
            row, text, SEEN_FAST_TRACK_RE, LABEL_FINDING, "seen_fast_track"
        )
    )
    proposals.extend(_tww_situation_proposals(row, text))
    return _dedupe_proposals(proposals)


def _explicit_proposals(
    row: dict[str, Any],
    text: str,
    pattern: re.Pattern[str],
    label: str,
    source: str,
) -> list[Proposal]:
    proposals = []
    for match in pattern.finditer(text):
        evidence = _clean_term(match.group(0))
        term = _normalise_explicit_term(evidence)
        if not term:
            continue
        site = _infer_site(term)
        proposals.append(_proposal(row, term, label, site, source, evidence))
    return proposals


def _tww_situation_proposals(row: dict[str, Any], text: str) -> list[Proposal]:
    proposals = []
    for match in TWW_LINE_RE.finditer(text):
        evidence = _normalise_tww_line(match.group(0))
        if not evidence or _skip_tww_line(evidence):
            continue
        site = _infer_site(evidence)
        term = _canonical_tww_term(site, evidence)
        concept_id = EXPECTED_SITUATIONS[site][0]
        proposals.append(
            _proposal(
                row, term, LABEL_SITUATION, site, "tww_situation", evidence, concept_id
            )
        )
    return proposals


def _proposal(
    row: dict[str, Any],
    term: str,
    label: str,
    site: str,
    source: str,
    evidence: str,
    expected_concept_id: str | None = None,
) -> Proposal:
    return Proposal(
        patient_id=str(row.get("patient_id") or ""),
        encounter_id=str(row.get("encounter_id") or ""),
        date=str(row.get("date") or ""),
        term=term,
        label=label,
        site=site,
        source=source,
        evidence=evidence,
        assertion=_infer_assertion(evidence),
        expected_concept_id=expected_concept_id,
    )


def _dedupe_proposals(proposals: list[Proposal]) -> list[Proposal]:
    seen = set()
    out = []
    for proposal in proposals:
        key = (proposal.encounter_id, proposal.term.lower(), proposal.label)
        if key in seen:
            continue
        seen.add(key)
        out.append(proposal)
    return out


def _normalise_explicit_term(term: str) -> str:
    clean = _clean_term(term)
    clean = re.sub(r"\s+\([A-Za-z0-9.]+\)$", "", clean)
    clean = re.sub(r"\s+updated:\s+Waiting\s+For\s+Information$", "", clean, flags=re.I)
    clean = re.sub(r":\s+Yes$", "", clean, flags=re.I)
    return clean.strip(" -:;.")


def _normalise_tww_line(line: str) -> str:
    clean = _clean_term(line)
    clean = re.sub(r"^(?:\d{1,2}:\d{2}\s*-\s*)?Surgery:\s*", "", clean, flags=re.I)
    clean = re.sub(
        r"^(?:Patient awaiting OPD appt\.:\s*Yes|Diagnosis:)\s*", "", clean, flags=re.I
    )
    clean = re.sub(r"^-\s*PRISM\s+", "PRISM ", clean, flags=re.I)
    clean = re.sub(r"^WMC Medical Secretary Template\s+", "", clean, flags=re.I)
    return clean.strip(" -:;.")


def _skip_tww_line(line: str) -> bool:
    return bool(
        re.search(r"\bSeen\s+in\s+2WW\s+Clinic\b", line, re.IGNORECASE)
        or re.search(r"\bFast\s+track\s+referral\b", line, re.IGNORECASE)
        or re.search(r"\bDate\s+of\s+First\s+outpatient\s+appointment\b", line, re.I)
        or re.search(r"\bScheduled\s+Task\s+Creation\b", line, re.IGNORECASE)
        or re.search(r"\b2WW\s+Clinic\s+Letter\b", line, re.IGNORECASE)
        or re.search(r"\b(?:non|not)\s+2\s*ww\b", line, re.IGNORECASE)
        or re.search(r"\bdoesn'?t\s+need\s+2\s*ww\b", line, re.IGNORECASE)
    )


def _canonical_tww_term(site: str, raw: str) -> str:
    if re.search(r"\b(?:nss|non[-\s]?site[-\s]?specific)\b", raw, re.IGNORECASE):
        return "2WW NSS"
    return {
        "generic": "2ww referral",
        "breast": "2ww breast",
        "lower_gi": "2ww lower GI",
        "upper_gi": "Upper GI 2ww",
        "urology": "2ww urology",
        "prostate": "2ww prostate",
        "gynae": "2ww gynae",
        "skin": "2WW Dermatology",
        "head_neck": "2WW head and neck",
        "lung": "2ww lung",
        "haematology": "2ww Haematology",
        "lymphoma": "Lymphoma 2ww",
    }[site]


def _clean_term(term: str) -> str:
    return re.sub(r"\s+", " ", str(term or "")).strip(" -:;.,")


def _infer_site(text: str) -> str:
    if re.search(r"\b(?:nss|non[-\s]?site[-\s]?specific)\b", text, re.IGNORECASE):
        return "generic"
    for site, pattern in TWW_TARGET_SITE_PATTERNS:
        if pattern.search(text):
            return site
    for site, pattern in SITE_PATTERNS:
        if pattern.search(text):
            return site
    return "generic"


def _infer_assertion(evidence: str) -> str:
    lowered = evidence.lower()
    if re.search(r"\b(marked in error|rejected|dna|did not attend)\b", lowered):
        return "cancelled"
    if re.search(
        r"\b(was seen|seen on|earlier this year|previous|history of)\b", lowered
    ):
        return "historical"
    if re.search(
        r"\b(plan|awaiting|planned|started|requested|arrange|urgent|refer|referral|pathway accessed|agreed)\b",
        lowered,
    ):
        return "planned"
    lowered_without_follow_up = re.sub(r"\bif\s+not\s+heard\b[^.]*", "", lowered)
    if re.search(
        r"\b(if|may need|would|could|should|need if)\b", lowered_without_follow_up
    ):
        return "hypothetical"
    return "present"


def _resolve(proposals: list[Proposal]) -> dict[str, list[ResolvedTerm]]:
    terms = list(dict.fromkeys(proposal.term for proposal in proposals))
    expected_tags = {proposal.term: proposal.label for proposal in proposals}
    return TerminologyClient(timeout=30, max_retries=1).resolve(terms, expected_tags)


def _finalise(
    proposal: Proposal,
    candidates: list[ResolvedTerm],
    existing_concept_ids: set[str],
) -> dict[str, Any]:
    top = candidates[0] if candidates else None
    status = _status(proposal, top)
    write_eligible = status == "safe" and proposal.assertion in {
        "present",
        "planned",
        "historical",
    }
    return {
        "status": status,
        "write_eligible": write_eligible,
        "patient_id": proposal.patient_id,
        "encounter_id": proposal.encounter_id,
        "date": proposal.date,
        "source": proposal.source,
        "site": proposal.site,
        "term": proposal.term,
        "label": proposal.label,
        "evidence": proposal.evidence,
        "assertion": proposal.assertion,
        "expected_concept_id": proposal.expected_concept_id,
        "concept_id": top.concept_id if top else None,
        "snomed_term": top.term if top else None,
        "semantic_tag": top.semantic_tag if top else None,
        "score": top.score if top else None,
        "had_exact_match": top.had_exact_match if top else False,
        "already_linked": bool(top and top.concept_id in existing_concept_ids),
    }


def _status(proposal: Proposal, top: ResolvedTerm | None) -> str:
    if top is None:
        return "unresolved"
    if _tag(top.semantic_tag) != proposal.label:
        return "wrong_semantic_tag"
    if proposal.expected_concept_id and top.concept_id != proposal.expected_concept_id:
        return "wrong_concept"
    return "safe"


def _tag(raw: str | None) -> str:
    return str(raw or "").strip().lower().replace(" ", "_").replace("-", "_")


def _apply(items: list[dict[str, Any]]) -> int:
    client = PatientGraphClient()
    applied = 0
    try:
        with client.session() as session:
            for item in items:
                if not item["write_eligible"]:
                    continue
                upsert_encounter_documents_link(
                    session,
                    str(item["patient_id"]),
                    str(item["encounter_id"]),
                    str(item["concept_id"]),
                    str(item["label"]),
                    str(item.get("snomed_term") or item.get("term") or ""),
                    str(item.get("evidence") or ""),
                    read_code=None,
                    assertion=str(item.get("assertion") or "present"),
                    modifiers={
                        "site": item["site"],
                        "source": item["source"],
                        "deterministic_term": item["term"],
                    },
                    source="deterministic_2ww_coder",
                    model_name="deterministic_2ww_coder",
                    model_version="2026-04-25",
                    confidence=float(item.get("score") or 0.0) or 0.95,
                )
                applied += 1
    finally:
        client.close()
    return applied


def _write_report(report_dir: Path, report: dict[str, Any]) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    mode = "apply" if report["apply"] else "dry_run"
    json_path = report_dir / f"encounter_2ww_coding_{mode}_{stamp}.json"
    csv_path = report_dir / f"encounter_2ww_coding_{mode}_{stamp}.csv"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    rows = report["items"]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(rows[0]) if rows else ["status"]
        )
        writer.writeheader()
        writer.writerows(rows)
    return json_path


def _summary(
    items: list[dict[str, Any]], applied: int, rows_scanned: int
) -> dict[str, int]:
    return {
        "encounters_scanned": rows_scanned,
        "proposals": len(items),
        "safe": sum(1 for item in items if item["status"] == "safe"),
        "already_linked": sum(1 for item in items if item.get("already_linked")),
        "to_add_or_update": sum(
            1
            for item in items
            if item.get("write_eligible") and not item.get("already_linked")
        ),
        "not_write_eligible": sum(
            1
            for item in items
            if item["status"] == "safe" and not item.get("write_eligible")
        ),
        "unresolved": sum(1 for item in items if item["status"] == "unresolved"),
        "wrong_semantic_tag": sum(
            1 for item in items if item["status"] == "wrong_semantic_tag"
        ),
        "wrong_concept": sum(1 for item in items if item["status"] == "wrong_concept"),
        "applied": applied,
    }


def main() -> int:
    args = _parse_args()
    rows = _load_rows(args.limit)
    proposals_by_encounter = {
        row["encounter_id"]: _extract_proposals(row) for row in rows
    }
    proposals = [
        proposal for group in proposals_by_encounter.values() for proposal in group
    ]
    resolved = _resolve(proposals)
    existing_by_encounter = {
        str(row["encounter_id"]): {
            str(concept_id)
            for concept_id in (row.get("existing_concept_ids") or [])
            if concept_id
        }
        for row in rows
    }
    items = [
        _finalise(
            proposal,
            resolved.get(proposal.term, []),
            existing_by_encounter.get(proposal.encounter_id, set()),
        )
        for proposal in proposals
    ]
    applied = _apply(items) if args.apply else 0
    report = {
        "apply": bool(args.apply),
        "summary": _summary(items, applied, len(rows)),
        "items": items,
    }
    report_path = _write_report(args.report_dir, report)
    print(json.dumps({"report": str(report_path), **report["summary"]}, indent=2))
    return 0 if report["summary"]["safe"] == report["summary"]["proposals"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
