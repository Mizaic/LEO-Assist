"""
Full duplicate surface form audit and semi-automated clean-up.

Strategy for choosing which mapping to keep:
  1. If one mapping is from our verified audit batches and the other is generic
     (guideline_config_loader) and the audit mapping is more specific -> keep audit.
  2. If both are from trusted sources, prefer higher specificity (finding > disorder
     when describing a symptom; disorder preferred when it IS a diagnosis).
  3. If in doubt, print for manual review.

Outputs:
  duplicate_audit.json         - full audit with recommended action
  duplicates_to_remove.json    - mappings flagged for deletion (review before running)
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path as _P

import requests

BASE = "http://localhost:8001"

# ---------------------------------------------------------------------------
# Concept IDs for common over-broad / wrong pre-existing mappings
# ---------------------------------------------------------------------------
TOO_BROAD = {
    "74732009",   # Mental disorder (disorder) -- only correct if text literally says "mental disorder"
    "21522001",   # Abdominal pain -- fine for specific phrases, but watch for overuse
}

# Provenance trust order (lower = higher trust / more deliberately curated)
PROV_RANK = {
    "synonym_audit_april_2026": 0,
    "abbreviation_audit_april_2026": 0,
    "abbreviation_audit_april_2026_review": 0,
    "manual_correction": 1,
    "hitl_gold_sync": 2,
    "coding_review_resolution": 3,
    "guideline_config_loader": 4,
}


def prov_rank(p: str | None) -> int:
    return PROV_RANK.get(p or "", 5)


def fetch_duplicates() -> list[dict]:
    r = requests.get(f"{BASE}/terminology/surface-forms/duplicates", timeout=30)
    r.raise_for_status()
    return r.json()


def recommend(normalized: str, mappings: list[dict]) -> tuple[str, str, list[str]]:
    """Return (action, reason, concept_ids_to_remove)."""
    if len(mappings) < 2:
        return "keep_all", "only one mapping", []

    # Sort: best trust first, then higher confidence
    ranked = sorted(
        mappings,
        key=lambda m: (prov_rank(m.get("provenance")), -m.get("confidence", 0)),
    )
    best = ranked[0]
    others = ranked[1:]

    to_remove = []
    reasons = []

    for other in others:
        b_cid = best.get("concept_id", "")
        o_cid = other.get("concept_id", "")
        b_prov = best.get("provenance", "")
        o_prov = other.get("provenance", "")

        # Same concept -- keep one, remove duplicate
        if b_cid == o_cid:
            to_remove.append(o_cid)
            reasons.append(f"duplicate concept {o_cid}")
            continue

        # Our audit write vs guideline/auto -- keep audit
        if prov_rank(b_prov) < prov_rank(o_prov):
            to_remove.append(o_cid)
            reasons.append(
                f"superseded by {b_prov}: {o_cid} ({o_prov}) < {b_cid} ({b_prov})"
            )
            continue

        # Both same trust -- flag for manual review
        reasons.append(f"MANUAL REVIEW: {b_cid} ({b_prov}) vs {o_cid} ({o_prov})")

    if to_remove:
        return "remove", "; ".join(reasons), to_remove
    return "review", "; ".join(reasons), []


def main() -> None:
    print("Fetching duplicate surface forms...")
    duplicates = fetch_duplicates()
    print(f"Duplicates found: {len(duplicates)}")
    print()

    audit = []
    to_remove_list = []
    by_action = {"remove": 0, "review": 0, "keep_all": 0}

    for entry in duplicates:
        norm = entry.get("normalized", "")
        form = entry.get("form", "")
        mappings = entry.get("mappings", [])
        action, reason, remove_ids = recommend(norm, mappings)
        by_action[action] = by_action.get(action, 0) + 1

        audit.append({
            "normalized": norm,
            "form": form,
            "rel_count": entry.get("rel_count"),
            "mappings": mappings,
            "action": action,
            "reason": reason,
            "remove_concept_ids": remove_ids,
        })

        if remove_ids:
            for cid in remove_ids:
                to_remove_list.append({"normalized": norm, "concept_id": cid,
                                        "reason": reason})

    # Print summary
    print(f"{'Action':<10} {'Count'}")
    for action, count in by_action.items():
        print(f"  {action:<10} {count}")
    print()

    # Print review items
    review_items = [a for a in audit if a["action"] == "review"]
    if review_items:
        print("== MANUAL REVIEW REQUIRED ==")
        for a in review_items:
            print(f"  {a['normalized']!r:30} {a['reason']}")
        print()

    # Print what will be removed
    remove_items = [a for a in audit if a["action"] == "remove"]
    if remove_items:
        print("== WILL REMOVE (lower-trust mappings) ==")
        for a in remove_items:
            print(f"  {a['normalized']!r:30} remove: {a['remove_concept_ids']}")
            print(f"    reason: {a['reason'][:100]}")
        print()

    # Save outputs
    out_audit = _P("scripts/investigations/duplicate_audit.json")
    out_audit.write_text(json.dumps(audit, indent=2), encoding="utf-8")

    out_remove = _P("scripts/investigations/duplicates_to_remove.json")
    out_remove.write_text(json.dumps(to_remove_list, indent=2), encoding="utf-8")

    print(f"Audit written: {out_audit}")
    print(f"Removal list: {out_remove} ({len(to_remove_list)} items)")
    print()
    print("Run with --apply to execute the removals.")


def apply_removals() -> None:
    _ROOT = _P(__file__).resolve().parents[2]
    sys.path.insert(0, str(_ROOT))
    sys.path.insert(0, str(_ROOT / "services" / "api"))
    from dotenv import load_dotenv
    load_dotenv(_ROOT / "secrets" / ".env.config", override=True)
    try:
        from libs.keyvault.loader import load_keyvault_secrets
        load_keyvault_secrets()
    except Exception as e:
        print(f"KV: {e}")
    from libs.auth.service_auth import get_service_auth_header
    h = get_service_auth_header()

    removal_file = _P("scripts/investigations/duplicates_to_remove.json")
    if not removal_file.exists():
        print("Run without --apply first to generate the removal list.")
        sys.exit(1)

    items = json.loads(removal_file.read_text(encoding="utf-8"))
    print(f"Applying {len(items)} removals...")
    ok = fail = 0
    for item in items:
        norm = item["normalized"]
        cid = item["concept_id"]
        r = requests.delete(
            f"{BASE}/terminology/surface-forms/{norm}",
            params={"concept_id": cid},
            headers=h,
            timeout=15,
        )
        if r.status_code == 200:
            removed = r.json().get("removed", 0)
            print(f"  OK   {norm!r:35} removed mapping -> {cid}  (rels removed: {removed})")
            ok += 1
        else:
            print(f"  FAIL {norm!r:35} {r.status_code}: {r.text[:100]}")
            fail += 1
        time.sleep(0.05)

    print(f"\nDone. OK: {ok}  Failed: {fail}")


if __name__ == "__main__":
    if "--apply" in sys.argv:
        apply_removals()
    else:
        main()
