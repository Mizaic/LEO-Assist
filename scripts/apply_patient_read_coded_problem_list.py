#!/usr/bin/env python3
"""Link SNOMED concepts for a curated EMIS Read-coded problem list to encounters.

Resolves each surface form via Terminology, matches patient encounter text, and
writes Concept DOCUMENTS (same pattern as code_2ww_encounters). Default is
dry-run; use --apply to persist.
"""

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
from libs.testing.synthetic_patient_ids import (
    EXAMPLE_READ_CODED_PROBLEM_LIST,
)  # noqa: E402

REPORT_DIR = _REPO_ROOT / "artifacts" / "patient_read_coded_problem_list"
SOURCE = "manual_read_coded_problem_list"

# EMIS (BB91.) can resolve to oropharynx; breast IDC is intended for this list.
READ_OVERRIDES: dict[str, tuple[str, str, str]] = {
    "BB91.": (
        "408643008",
        "Infiltrating duct carcinoma of breast (disorder)",
        "disorder",
    ),
    # EMIS XaW9C: CT abdomen/pelvis; long surface form can miss in lexical index.
    "XaW9C": (
        "419394006",
        "Computed tomography of abdomen and pelvis (procedure)",
        "procedure",
    ),
}

ENCOUNTERS_Q = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(p.id) = $patient_id
OPTIONAL MATCH (e)-[:DOCUMENTS]->(c:Concept)
WITH e, collect(DISTINCT c.conceptId) AS existing_concept_ids
RETURN toString(e.id) AS encounter_id,
       toString(e.date) AS date,
       coalesce(e.text, '') AS text,
       existing_concept_ids
ORDER BY e.date, encounter_id
"""

_EPISODE_RE = re.compile(r"\s*\((?:New|Ongoing)\s+Episode\)\s*$", re.IGNORECASE)
_PREFIX_RE = re.compile(r"^(?:Major|Minor)\s*:\s*", re.IGNORECASE)
_READ_RE = re.compile(r"\(\s*([A-Za-z0-9.]+)\s*\)\s*$")
# EMIS: read code is often the first (CODE) in the line, not the last.
_READ_PARENS = re.compile(r"\(\s*([A-Za-z0-9.]+)\s*\)")


@dataclass(frozen=True)
class ListItem:
    line: str
    expected_tag: str


PATIENT_EXAMPLE_READ_CODED_PROBLEM_LIST_ITEMS: tuple[ListItem, ...] = (
    ListItem(
        "Ultrasound scan (X70lf) - axilla - malignant looking LNs (New Episode)",
        "procedure",
    ),
    ListItem("Biopsy of breast (7135.) - core biopsy (New Episode)", "procedure"),
    ListItem("Major: Infiltrating duct carcinoma (BB91.) (New Episode)", "disorder"),
    ListItem(
        "CT (computed tomography) of abdomen and pelvis (XaW9C) (New Episode)",
        "procedure",
    ),
    ListItem("Mammogram (537..) (New Episode)", "procedure"),
    ListItem("Infiltrating duct carcinoma (BB91.)", "disorder"),
    ListItem("Ultrasound scan (X70lf) - axillary (New Episode)", "procedure"),
    ListItem("Major: Metastasis to lymph node (Xa980) (New Episode)", "disorder"),
    ListItem("Metastasis to lymph node (Xa980)", "disorder"),
    ListItem("Biopsy of breast (7135.) - left (New Episode)", "procedure"),
    ListItem("Mammogram (537..) (New Episode)", "procedure"),
    ListItem(
        "US scan of breast (585C.) - and axilla - left (New Episode)", "procedure"
    ),
    ListItem("Biopsy of axillary lymph node (X20AR) - left (New Episode)", "procedure"),
    ListItem(
        "Major: Metastasis to bone of unknown primary (Xa3AJ) (New Episode)", "disorder"
    ),
    ListItem(
        "Magnetic resonance cholangiopancreatography (XaFC7) (New Episode)", "procedure"
    ),
    ListItem(
        "Minor: Dilation of biliary tract (XaAzZ) - intra and extra hepatic (New Episode)",
        "disorder",
    ),
    ListItem("Major: Atrial fibrillation (G5730) (New Episode)", "disorder"),
    ListItem("Minor: Hypercalcaemia (X40Qa) (New Episode)", "disorder"),
    ListItem("Minor: Gallstone (X79cS) (New Episode)", "disorder"),
    ListItem("Dilation of biliary tract (XaAzZ) - intra and extra hepatic", "disorder"),
    ListItem("Atrial fibrillation (G5730)", "disorder"),
    ListItem("Gallstone (X79cS)", "disorder"),
    ListItem("Metastasis to bone of unknown primary (Xa3AJ)", "disorder"),
    ListItem("Hypercalcaemia (X40Qa)", "disorder"),
    ListItem("MRI of spine (X70pC) (New Episode)", "procedure"),
    ListItem(
        "Major: Metastatic spinal cord compression (Y2bfc) (New Episode)", "disorder"
    ),
    ListItem(
        "Major: Palliative course of radiotherapy (5149.) (New Episode)", "procedure"
    ),
    ListItem("Metastatic spinal cord compression (Y2bfc)", "disorder"),
    ListItem("Palliative course of radiotherapy (5149.)", "procedure"),
    ListItem("Biopsy of breast (7135.) (Ongoing Episode)", "procedure"),
)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--patient-id", default=EXAMPLE_READ_CODED_PROBLEM_LIST)
    p.add_argument("--apply", action="store_true")
    p.add_argument("--report-dir", type=Path, default=REPORT_DIR)
    p.add_argument(
        "--items",
        choices=(EXAMPLE_READ_CODED_PROBLEM_LIST,),
        default=EXAMPLE_READ_CODED_PROBLEM_LIST,
    )
    return p.parse_args()


def _item_key(line: str) -> str:
    s = _PREFIX_RE.sub("", line.strip())
    s = _EPISODE_RE.sub("", s).strip()
    return s


def _read_code_from_key(key: str) -> str | None:
    m = _READ_RE.search(key.strip())
    if m:
        return m.group(1)
    p = _READ_PARENS.search(key)
    return p.group(1) if p else None


def _primary_lookup_phrase(key: str) -> str:
    """EMIS often appends ' - left' or ' - and axilla'; take head before ' - ' if it has a read code."""
    if " - " not in key:
        return key
    head = key.split(" - ")[0].strip()
    if _READ_PARENS.search(head):
        return head
    return key


def _lookup_for_resolve(key: str, read: str | None) -> str:
    if read == "BB91.":
        return "Infiltrating duct carcinoma of breast (BB91.)"
    return _primary_lookup_phrase(key)


def _norm(s: str) -> str:
    return " ".join(s.lower().split())


def _evidence_in_encounter(enc_text: str, raw_line: str) -> bool:
    key = _item_key(raw_line)
    t = _norm(enc_text)
    k = _norm(key)
    if not k:
        return False
    if k in t:
        return True
    k2 = re.sub(r"[.]{2,}", ".", k)
    t2 = re.sub(r"[.]{2,}", ".", t)
    return k2 in t2 if k2 != k else False


def _slice_evidence(enc_text: str, key: str) -> str:
    lo = enc_text.lower().find(key.lower()[: min(30, len(key))])
    if lo < 0:
        return key
    hi = min(len(enc_text), lo + 200)
    return enc_text[lo:hi]


def _tag(s: str | None) -> str:
    return str(s or "").strip().lower().replace(" ", "_").replace("-", "_")


def _resolve_state(
    expected_tag: str, top: ResolvedTerm | None, read: str | None
) -> tuple[str, str | None, str | None, str | None, bool, float]:
    if read and read in READ_OVERRIDES:
        cid, term, wtag = READ_OVERRIDES[read]
        if _tag(wtag) != _tag(expected_tag):
            return "override_tag_mismatch", None, None, None, False, 0.0
        return "override", cid, term, wtag, True, 1.0
    if top is None:
        return "unresolved", None, None, None, False, 0.0
    if _tag(top.semantic_tag) != _tag(expected_tag):
        return (
            "wrong_semantic_tag",
            top.concept_id,
            top.term,
            top.semantic_tag,
            top.had_exact_match,
            top.score,
        )
    if (
        read == "BB91."
        and top.concept_id
        and "oropharynx" in str(top.term or "").lower()
    ):
        return (
            "review_wrong_sense",
            top.concept_id,
            top.term,
            top.semantic_tag,
            top.had_exact_match,
            top.score,
        )
    return (
        "safe",
        top.concept_id,
        top.term,
        top.semantic_tag,
        top.had_exact_match,
        top.score,
    )


def _load_items(key: str) -> tuple[ListItem, ...]:
    if key == EXAMPLE_READ_CODED_PROBLEM_LIST:
        return PATIENT_EXAMPLE_READ_CODED_PROBLEM_LIST_ITEMS
    raise ValueError(key)


def _apply(rows: list[dict[str, Any]]) -> int:
    client = PatientGraphClient()
    n = 0
    try:
        with client.session() as session:
            for r in rows:
                if r.get("status") not in ("safe", "override"):
                    continue
                if not r.get("write_eligible"):
                    continue
                if r.get("already_linked"):
                    continue
                if not r.get("concept_id") or not r.get("encounter_id"):
                    continue
                st = _tag_to_graph(r.get("resolved_tag") or r["expected_tag"])
                upsert_encounter_documents_link(
                    session,
                    str(r["patient_id"]),
                    str(r["encounter_id"]),
                    str(r["concept_id"]),
                    st,
                    str(r.get("snomed_term") or ""),
                    str(r.get("evidence") or ""),
                    read_code=r.get("read_code"),
                    assertion="present",
                    modifiers={
                        "source": SOURCE,
                        "read_code": r.get("read_code"),
                        "lookup": r.get("lookup"),
                    },
                    source=SOURCE,
                    model_name=SOURCE,
                    model_version="2026-04-25",
                    confidence=float(r.get("score") or 0.0) or 0.95,
                )
                n += 1
    finally:
        client.close()
    return n


def _tag_to_graph(tag: str) -> str:
    t = str(tag or "").lower()
    if t == "disorder":
        return "disorder"
    return t


def _write_report(report_dir: Path, report: dict[str, Any]) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    mode = "apply" if report.get("apply") else "dry_run"
    json_path = report_dir / f"read_coded_list_{mode}_{stamp}.json"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    rows = report.get("rows") or []
    if rows:
        csv_path = report_dir / f"read_coded_list_{mode}_{stamp}.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    return json_path


def main() -> int:
    args = _parse_args()
    patient_id = str(args.patient_id)
    list_items = _load_items(args.items)

    client = PatientGraphClient()
    try:
        enc_rows = client.run(ENCOUNTERS_Q, patient_id=patient_id)
    finally:
        client.close()

    if not enc_rows:
        print(f"No encounters for patient {patient_id}", file=sys.stderr)
        return 1

    # Unique lookups for terminology
    look_tags: list[tuple[str, str]] = []
    seen_lu: set[str] = set()
    for li in list_items:
        key = _item_key(li.line)
        read = _read_code_from_key(key)
        lookup = _lookup_for_resolve(key, read)
        if read in READ_OVERRIDES:
            continue
        if lookup not in seen_lu:
            seen_lu.add(lookup)
            look_tags.append((lookup, li.expected_tag))

    tc = TerminologyClient(timeout=90, max_retries=2)
    expected_tags = {a: b for a, b in look_tags}
    resolved: dict[str, list[ResolvedTerm]] = {}
    if expected_tags:
        resolved = tc.resolve(list(expected_tags.keys()), expected_tags=expected_tags)

    out_rows: list[dict[str, Any]] = []
    for li in list_items:
        key = _item_key(li.line)
        read = _read_code_from_key(key)
        lookup = _lookup_for_resolve(key, read)
        top = (
            (resolved.get(lookup) or [None])[0] if read not in READ_OVERRIDES else None
        )
        status, cid, sterm, stag, exm, score = _resolve_state(
            li.expected_tag, top, read
        )

        matched: list[dict[str, Any]] = []
        for er in enc_rows:
            text = str(er.get("text") or "")
            if not _evidence_in_encounter(text, li.line):
                continue
            eid = str(er.get("encounter_id") or "")
            ex = [str(x) for x in (er.get("existing_concept_ids") or []) if x]
            ev = _slice_evidence(text, key)
            matched.append(
                {
                    "encounter_id": eid,
                    "date": str(er.get("date") or ""),
                    "evidence": ev,
                    "existing_concept_ids": ex,
                }
            )

        if not matched:
            row_status = status
            if status in ("safe", "override"):
                row_status = "no_encounter_match"
            out_rows.append(
                {
                    "patient_id": patient_id,
                    "source_line": li.line,
                    "key": key,
                    "lookup": lookup,
                    "read_code": read,
                    "expected_tag": li.expected_tag,
                    "encounter_id": "",
                    "encounter_date": "",
                    "evidence": "",
                    "status": row_status,
                    "concept_id": cid,
                    "snomed_term": sterm,
                    "resolved_tag": stag,
                    "score": score,
                    "had_exact_match": exm,
                    "already_linked": False,
                    "write_eligible": False,
                }
            )
            continue

        for m in matched:
            eid = m["encounter_id"]
            exids = {str(x) for x in m["existing_concept_ids"]}
            al = bool(cid and str(cid) in exids)
            w_el = status in ("safe", "override") and bool(cid) and not al
            out_rows.append(
                {
                    "patient_id": patient_id,
                    "source_line": li.line,
                    "key": key,
                    "lookup": lookup,
                    "read_code": read,
                    "expected_tag": li.expected_tag,
                    "encounter_id": eid,
                    "encounter_date": m["date"],
                    "evidence": m["evidence"],
                    "status": status,
                    "concept_id": cid,
                    "snomed_term": sterm,
                    "resolved_tag": stag,
                    "score": score,
                    "had_exact_match": exm,
                    "already_linked": al,
                    "write_eligible": w_el,
                }
            )

    # Deduplicate writes: same encounter + concept from multiple list lines
    seen_eid_cid: set[tuple[str, str]] = set()
    for r in out_rows:
        p = (r.get("encounter_id") or "", str(r.get("concept_id") or ""))
        if not p[0] or not p[1]:
            continue
        if p in seen_eid_cid:
            if r.get("write_eligible"):
                r["write_eligible"] = False
                r["status"] = "deduped"
        else:
            seen_eid_cid.add(p)

    report = {
        "patient_id": patient_id,
        "apply": bool(args.apply),
        "rows": out_rows,
        "summary": {
            "encounters": len(enc_rows),
            "rows": len(out_rows),
            "write_eligible": sum(1 for r in out_rows if r.get("write_eligible")),
            "no_encounter_match": sum(
                1 for r in out_rows if r.get("status") == "no_encounter_match"
            ),
        },
    }

    applied = 0
    if args.apply:
        applied = _apply(out_rows)
    report["summary"]["applied"] = applied

    path = _write_report(args.report_dir, report)
    print(f"Wrote {path}  applied={applied}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
