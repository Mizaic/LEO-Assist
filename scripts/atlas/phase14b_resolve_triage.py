"""Phase 14b -- resolve the 3 phase13c-triage-queue files.

Two distinct shapes:

  Group A (DO already exists, DI parent missing):
    - DO-0DFA6961  "Gold-mined cancer-site dictionary..."
    - Files:
        services/analysis_worker/app/analyzers/cancer_site_terms.py
        services/analysis_worker/app/analyzers/episode_builder/_site_resolution.py
    - Action: create UN + DI for the capability, link to DO-0DFA6961, then
      stamp the files as part of Phase 14e re-stamp.

  Group B (audit mis-labelled DO as DI):
    - File: services/ui/src/app/care/encounters/page.tsx
    - Audit row put DO-F78C84A6 in the "owning_atlas_dis" column.
      Atlas confirms DO-F78C84A6 IS a Design Output with parent
      DI-D0FC22FE.
    - Action: re-classify in audit (no Atlas mutation needed) and stamp.

This script is idempotent. It writes a ledger CSV at
compliance/atlas-migration-evidence/phase14b-ledger.csv recording every
Atlas call and its outcome.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))
from _mcp_transport import McpError, call_tool, initialize  # noqa: E402
from product import PRODUCT_ID as PRODUCT  # noqa: E402

EVIDENCE = ROOT / "compliance" / "atlas-migration-evidence"
LEDGER = EVIDENCE / "phase14b-ledger.csv"

# Cancer-site DI/UN to create (Group A).
CANCER_UN = {
    "title": "Cancer site recognition in unstructured oncology text",
    "description": (
        "As an oncology data engineer, I need the analysis pipeline to "
        "identify which cancer site (breast, prostate, lung, ...) an "
        "unstructured clinical document refers to, so that downstream "
        "episode builders can route the document to the correct cancer "
        "pathway."
    ),
    "stakeholder_types": ["Developer", "Clinician"],
    "rationale": (
        "Free-text oncology documents do not always carry a structured "
        "site code. We mine and curate a deterministic surface-form "
        "dictionary so site classification is reproducible, auditable, "
        "and independent of any model."
    ),
    "acceptance_criteria": [
        "Each NCDA cancer-site key resolves to a deduplicated list of "
        "lower-case literal surface forms.",
        "match_cancer_site(text) returns the (site_key, hit_count) tuple "
        "for the dominant site, or None when no surface form matches.",
        "The episode builder _site_resolution layer prefers structured "
        "codes over text matches and falls back to text matches "
        "deterministically.",
    ],
    "priority": "MUST",
    "safety_class": "B",
}
CANCER_DI = {
    "title": (
        "Deterministic cancer-site dictionary and text-path episode "
        "builder integration"
    ),
    "description": (
        "The analysis pipeline shall classify the cancer site of an "
        "unstructured oncology document using a curated surface-form "
        "dictionary and shall use the result to route the document to "
        "the correct site-specific episode builder when no structured "
        "site code is available."
    ),
    "rationale": (
        "Removes model dependency from the site classification step on "
        "the text path; ensures the same input always yields the same "
        "site decision; allows the dictionary to be regenerated from "
        "the gold corpus on demand."
    ),
    "input_type": "functional",
    "verification_method": "test",
    "acceptance_criteria": [
        "cancer_site_terms.match_cancer_site is deterministic for a "
        "given input string.",
        "_site_resolution layer prefers structured site codes over text "
        "matches when both are present.",
        "Regenerating the dictionary from the gold corpus does not break "
        "any existing episode-builder tests.",
    ],
    "safety_class": "B",
}
CANCER_DO = "DO-0DFA6961"


def _append_ledger(row: dict) -> None:
    cols = ["operation", "subject", "result", "note"]
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    new = not LEDGER.exists()
    with LEDGER.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        if new:
            w.writeheader()
        w.writerow({c: row.get(c, "") for c in cols})


def _safe_call(name: str, args: dict, subject: str) -> dict | None:
    try:
        out = call_tool(name, args)
    except McpError as e:
        _append_ledger(
            {
                "operation": name,
                "subject": subject,
                "result": "error",
                "note": str(e)[:300],
            }
        )
        print(f"  ! {name}({subject}): {str(e)[:160]}")
        return None
    err = (out or {}).get("error")
    if err:
        _append_ledger(
            {
                "operation": name,
                "subject": subject,
                "result": "error",
                "note": str(err)[:300],
            }
        )
        print(f"  ! {name}({subject}): {str(err)[:160]}")
        return None
    return out


def _resume_id(operation: str, subject: str) -> str | None:
    if not LEDGER.exists():
        return None
    for r in csv.DictReader(LEDGER.open()):
        if (
            r["operation"] == operation
            and r["subject"] == subject
            and r["result"] == "created"
        ):
            return r["note"]
    return None


def create_cancer_un_di() -> tuple[str | None, str | None]:
    un_id = _resume_id("create_user_need", CANCER_UN["title"])
    if not un_id:
        print("Creating cancer-site UN...")
        out = _safe_call(
            "create_user_need", {"product_id": PRODUCT, **CANCER_UN}, CANCER_UN["title"]
        )
        if out is None:
            return None, None
        un_id = (
            out.get("dcId")
            or (out.get("userNeed") or {}).get("dcId")
            or out.get("dc_id")
        )
        _append_ledger(
            {
                "operation": "create_user_need",
                "subject": CANCER_UN["title"],
                "result": "created",
                "note": un_id or "",
            }
        )
        print(f"  -> {un_id}")

    di_id = _resume_id("create_design_input", CANCER_DI["title"])
    if not di_id:
        print("Creating cancer-site DI...")
        out = _safe_call(
            "create_design_input",
            {"product_id": PRODUCT, **CANCER_DI},
            CANCER_DI["title"],
        )
        if out is None:
            return un_id, None
        di_id = (
            out.get("dcId")
            or (out.get("designInput") or {}).get("dcId")
            or out.get("dc_id")
        )
        _append_ledger(
            {
                "operation": "create_design_input",
                "subject": CANCER_DI["title"],
                "result": "created",
                "note": di_id or "",
            }
        )
        print(f"  -> {di_id}")

    return un_id, di_id


def link_chain(un_id: str, di_id: str) -> None:
    if not _resume_id("link_un_di", f"{un_id}->{di_id}"):
        out = _safe_call(
            "link_design_controls",
            {
                "source_ids": [un_id],
                "target_ids": [di_id],
                "relationship": "HAS_DESIGN_INPUT",
            },
            f"{un_id}->{di_id}",
        )
        if out is not None:
            _append_ledger(
                {
                    "operation": "link_un_di",
                    "subject": f"{un_id}->{di_id}",
                    "result": "created",
                    "note": "HAS_DESIGN_INPUT",
                }
            )
            print(f"  linked UN->DI: {un_id} -> {di_id}")
    if not _resume_id("link_do_di", f"{CANCER_DO}->{di_id}"):
        out = _safe_call(
            "link_design_controls",
            {
                "source_ids": [CANCER_DO],
                "target_ids": [di_id],
                "relationship": "IMPLEMENTS",
            },
            f"{CANCER_DO}->{di_id}",
        )
        if out is not None:
            _append_ledger(
                {
                    "operation": "link_do_di",
                    "subject": f"{CANCER_DO}->{di_id}",
                    "result": "created",
                    "note": "IMPLEMENTS",
                }
            )
            print(f"  linked DO->DI: {CANCER_DO} -> {di_id}")


def update_audit_row_for_encounters() -> None:
    """The audit put DO-F78C84A6 in the DI column. Move it to DO column for
    services/ui/src/app/care/encounters/page.tsx."""
    audit = EVIDENCE / "phase13a-file-trace-audit.csv"
    rows = list(csv.DictReader(audit.open()))
    fixed = 0
    for r in rows:
        if r["path"] == "services/ui/src/app/care/encounters/page.tsx":
            if r.get("owning_atlas_dos") in ("", None) and "DO-F78C84A6" in (
                r.get("owning_atlas_dis") or ""
            ):
                r["owning_atlas_dos"] = "DO-F78C84A6"
                r["owning_atlas_dis"] = ""
                fixed += 1
    if fixed:
        with audit.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=rows[0].keys())
            w.writeheader()
            w.writerows(rows)
        _append_ledger(
            {
                "operation": "audit_reclassify",
                "subject": "services/ui/src/app/care/encounters/page.tsx",
                "result": "fixed",
                "note": "DO-F78C84A6 moved from DI -> DO column",
            }
        )
        print("  audit: re-classified care/encounters/page.tsx -> DO-F78C84A6")
    else:
        print("  audit: no reclassification needed (already done)")


def main() -> int:
    initialize()
    print("Phase 14b -- triage queue")
    print("Group A: cancer-site dictionary (DO-0DFA6961)")
    un_id, di_id = create_cancer_un_di()
    if un_id and di_id:
        link_chain(un_id, di_id)

    print("Group B: care/encounters/page.tsx")
    update_audit_row_for_encounters()

    print("\nLedger written to", LEDGER)
    return 0


if __name__ == "__main__":
    sys.exit(main())
