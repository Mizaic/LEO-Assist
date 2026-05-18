#!/usr/bin/env python3
"""Audit 2WW/fast-track encounter phrases against the Terminology API."""

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

from libs.terminology.client import ResolvedTerm, TerminologyClient  # noqa: E402

DEFAULT_INPUT = _REPO_ROOT / "artifacts" / "encounters_2ww_related_terms.json"
DEFAULT_REPORT_DIR = _REPO_ROOT / "artifacts" / "terminology_2ww_audits"

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


@dataclass(frozen=True)
class Probe:
    term: str
    label: str
    expected_concept_id: str | None
    expected_term_contains: str
    source: str
    site: str
    patient_id: str
    encounter_id: str
    raw_evidence: str


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--limit", type=int, default=0)
    return parser.parse_args()


def _load_items(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data.get("items", data)
    if not isinstance(items, list):
        raise ValueError(f"Expected list of items in {path}")
    return [dict(item) for item in items if isinstance(item, dict)]


def _extract_probes(item: dict[str, Any]) -> list[Probe]:
    text = str(item.get("text_preview") or "")
    probes = []
    probes.extend(
        _explicit_probes(item, text, FAST_REFERRAL_RE, LABEL_PROCEDURE, "fast_referral")
    )
    probes.extend(
        _explicit_probes(
            item, text, SEEN_FAST_TRACK_RE, LABEL_FINDING, "seen_fast_track"
        )
    )
    probes.extend(_tww_situation_probes(item, text))
    return probes


def _explicit_probes(
    item: dict[str, Any],
    text: str,
    pattern: re.Pattern[str],
    label: str,
    source: str,
) -> list[Probe]:
    probes = []
    for match in pattern.finditer(text):
        term = _normalise_explicit_term(match.group(0))
        if not term:
            continue
        site = _infer_site(term)
        expected_text = (
            "Seen in fast track" if label == LABEL_FINDING else "Fast track referral"
        )
        probes.append(_probe(item, term, label, None, expected_text, source, site))
    return probes


def _normalise_explicit_term(term: str) -> str:
    clean = _clean_term(term)
    clean = re.sub(r"\s+\([A-Za-z0-9.]+\)$", "", clean)
    clean = re.sub(r"\s+updated:\s+Waiting\s+For\s+Information$", "", clean, flags=re.I)
    clean = re.sub(r":\s+Yes$", "", clean, flags=re.I)
    return clean.strip(" -:;.")


def _tww_situation_probes(item: dict[str, Any], text: str) -> list[Probe]:
    probes = []
    for match in TWW_LINE_RE.finditer(text):
        raw = _normalise_tww_line(match.group(0))
        if not raw or _skip_tww_line(raw):
            continue
        site = _infer_site(raw)
        term = _canonical_tww_term(site, raw)
        concept_id, expected_text = EXPECTED_SITUATIONS[site]
        probes.append(
            _probe(
                item,
                term,
                LABEL_SITUATION,
                concept_id,
                expected_text,
                "tww_situation",
                site,
                raw,
            )
        )
    return probes


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
    term = re.sub(r"\s+", " ", term).strip()
    return term.strip(" -:;.")


def _infer_site(text: str) -> str:
    lowered = text.lower()
    if re.search(r"\b(?:nss|non[-\s]?site[-\s]?specific)\b", lowered):
        return "generic"
    for site, pattern in SITE_PATTERNS:
        if pattern.search(text):
            return site
    return "generic"


def _probe(
    item: dict[str, Any],
    term: str,
    label: str,
    expected_concept_id: str | None,
    expected_text: str,
    source: str,
    site: str,
    raw_evidence: str | None = None,
) -> Probe:
    return Probe(
        term=term,
        label=label,
        expected_concept_id=expected_concept_id,
        expected_term_contains=expected_text,
        source=source,
        site=site,
        patient_id=str(item.get("patient_id") or ""),
        encounter_id=str(item.get("encounter_id") or ""),
        raw_evidence=raw_evidence or term,
    )


def _dedupe_probes(probes: list[Probe]) -> list[Probe]:
    seen = set()
    unique = []
    for probe in probes:
        key = (probe.term.lower(), probe.label, probe.expected_concept_id, probe.source)
        if key in seen:
            continue
        seen.add(key)
        unique.append(probe)
    return unique


def _resolve(probes: list[Probe]) -> dict[str, list[ResolvedTerm]]:
    terms = [probe.term for probe in probes]
    tags = {probe.term: probe.label for probe in probes}
    return TerminologyClient(timeout=30, max_retries=1).resolve(
        terms, expected_tags=tags
    )


def _audit_probe(probe: Probe, candidates: list[ResolvedTerm]) -> dict[str, Any]:
    top = candidates[0] if candidates else None
    status = _status(probe, top)
    return {
        "status": status,
        "term": probe.term,
        "raw_evidence": probe.raw_evidence,
        "label": probe.label,
        "source": probe.source,
        "site": probe.site,
        "expected_concept_id": probe.expected_concept_id,
        "expected_term_contains": probe.expected_term_contains,
        "top_concept_id": top.concept_id if top else None,
        "top_term": top.term if top else None,
        "top_semantic_tag": top.semantic_tag if top else None,
        "top_score": top.score if top else None,
        "had_exact_match": top.had_exact_match if top else False,
        "patient_id": probe.patient_id,
        "encounter_id": probe.encounter_id,
        "candidate_count": len(candidates),
    }


def _status(probe: Probe, top: ResolvedTerm | None) -> str:
    if top is None:
        return "unresolved"
    if _tag(top.semantic_tag) != probe.label:
        return "wrong_semantic_tag"
    if probe.expected_concept_id and top.concept_id != probe.expected_concept_id:
        return "wrong_concept"
    if probe.expected_term_contains.lower() not in str(top.term or "").lower():
        return "term_mismatch"
    return "pass"


def _tag(raw: str | None) -> str:
    return str(raw or "").strip().lower().replace(" ", "_").replace("-", "_")


def _write_reports(
    report_dir: Path, rows: list[dict[str, Any]], summary: dict[str, Any]
) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    json_path = report_dir / f"terminology_2ww_audit_{stamp}.json"
    csv_path = report_dir / f"terminology_2ww_audit_{stamp}.csv"
    json_path.write_text(
        json.dumps({"summary": summary, "items": rows}, indent=2), encoding="utf-8"
    )
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(rows[0]) if rows else ["status"]
        )
        writer.writeheader()
        writer.writerows(rows)
    return json_path


def main() -> int:
    args = _parse_args()
    items = _load_items(args.input)
    if args.limit > 0:
        items = items[: args.limit]
    probes = _dedupe_probes(
        [probe for item in items for probe in _extract_probes(item)]
    )
    resolved = _resolve(probes)
    rows = [_audit_probe(probe, resolved.get(probe.term, [])) for probe in probes]
    counts = _count(rows, "status")
    summary = {
        "input": str(args.input),
        "encounters_scanned": len(items),
        "unique_terms_tested": len(probes),
        "status_counts": counts,
        "source_counts": _count(rows, "source"),
        "site_counts": _count(rows, "site"),
    }
    report_path = _write_reports(args.report_dir, rows, summary)
    print(json.dumps({"report": str(report_path), **summary}, indent=2))
    return 0 if counts.get("pass", 0) == len(probes) else 1


def _count(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or "")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


if __name__ == "__main__":
    raise SystemExit(main())
