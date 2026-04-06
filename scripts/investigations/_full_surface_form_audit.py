"""Comprehensive surface form audit.

Fetches every MAPS_TO edge from the knowledge graph and applies eight
deletion rules to determine whether each edge should be KEPT, DELETED,
or flagged for REVIEW.

Deletion rules (applied in order, first match wins)
----------------------------------------------------
R1  INACTIVE_CONCEPT        - target concept is inactive in SNOMED
R2  SUPERSEDED              - a higher-provenance audit-fix edge exists for this
                              normalised form pointing to a DIFFERENT concept
R3  BROAD_WITH_BETTER       - maps to a known broad catch-all (generic mental
                              disorder, parent disability, etc.) AND a better
                              specific edge already exists for this form
R4  WRONG_SITUATION         - concept is a 'situation' (e.g. 'History of COPD')
                              but the form text doesn't contain any
                              history/absence prefix
R5  WRONG_PROCEDURE         - form text is a plain symptom/sign/condition but
                              concept is a procedure (e.g. 'COPD' -> 'Spirometry')
R6  INACTIVE_SEMANTIC       - concept tag is 'record artifact', 'occupation',
                              or 'environment' for a clinical-sounding form
R7  DUPLICATE_LOWER_CONF    - the same (normalised, concept_id) pair has
                              multiple MAPS_TO edges; keep only the highest-conf
R8  BROAD_NO_ALTERNATIVE    - maps to broad catch-all but no better edge exists
                              (REVIEW not DELETE -- don't leave forms unresolvable)

Usage
-----
  python scripts/investigations/_full_surface_form_audit.py [--apply]

Without --apply: prints decisions and writes report.
With    --apply: also executes the DELETE queries.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets
load_keyvault_secrets()

from neo4j import GraphDatabase

kg_uri  = os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI")
kg_user = os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "neo4j")
kg_pass = os.getenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "knowledge-dev")

OUTPUT = ROOT / "scripts" / "investigations" / "full_surface_form_audit.json"

# ---------------------------------------------------------------------------
# Known broad catch-all concept IDs that should never be the ONLY mapping
# for a specific clinical term -- but are acceptable alongside better ones
# ---------------------------------------------------------------------------
_BROAD_IDS = {
    "74732009",    # Mental disorder (disorder)
    "128462008",   # Metastatic malignant neoplasm (disorder)
    "415036007",   # Parent has physical disability (situation)
    "160303001",   # FH of mental disorder (situation)
    "267023007",   # Disorder of body system (disorder)  -- very broad
}

# ---------------------------------------------------------------------------
# Provenance ranking: higher = more authoritative. Audit-fix beats GCL.
# ---------------------------------------------------------------------------
_PROV_RANK = {
    "audit-fix-mh-orphan-2026-04":       100,
    "audit-fix-spot-check-2026-04":      100,
    "audit-fix-abbrev-2026-04":          100,
    "audit-fix-wrong-gcl-situations-2026-04": 100,
    "audit-fix-2026-04":                 100,
    "manual_correction":                  90,
    "pin-fast-track-referrals-2026-04-05": 90,
    "fix-guideline-coding-ng12-2026-04-05": 90,
    "manual-fix-2026-04-05":              90,
    "manual-fix-fit-2026-04-05":          90,
    "manual-fix-high-confidence-2026-04-05": 90,
    "coding_review_resolution":           85,
    "batch_coding_review_resolution":     85,
    "synonym_audit_april_2026":           80,
    "abbreviation_audit_april_2026":      80,
    "abbreviation_audit_april_2026_review": 80,
    "critical_audit_gap_april_2026":      75,
    "fit_bcsp_surface_forms_april_2026":  75,
    "batch7_audit_gap_april_2026":        70,
    "batch6_audit_gap_april_2026":        65,
    "batch2_audit_gap_april_2026":        60,
    "eval_gap_correction":                55,
    "guideline_config_loader":            10,
}

_HISTORY_PREFIXES = (
    "history of", "hx of", "h/o", "past history", "past ",
    "previous ", "previously ", "former ", "formerly ",
    "no history", "no known", "no ", "known history",
    "background of mental", "family history", "fh of",
    "absence of", "never had", "resolved ", "ex-",
    "ex ", "old ", "remote history",
)

_NEGATIVE_PREFIXES = (
    "no ", "not ", "without ", "absence of ", "denies ", "denied ",
    "negative for ", "ruled out ", "excluded ", "never ",
)

# Semantic tags that are NEVER appropriate for plain symptom/disorder forms
_WRONG_CLINICAL_TAGS = {"record artifact", "occupation", "environment", "social concept"}

# Procedure concept IDs often misused for clinical conditions
# (checked against the form text being clearly non-procedural)
_PROCEDURE_TAGS = {"procedure", "regime/therapy"}

# Tokens that indicate the form IS about a procedure (don't flag these)
_PROCEDURE_FORM_TOKENS = {
    "procedure", "therapy", "treatment", "operation", "surgery",
    "referral", "appointment", "screening", "scan", "test",
    "monitoring", "assessment", "review", "prescription",
    "administered", "initiated", "started", "done", "booked",
    "uptake", "attendance", "seen in", "admitted",
}


def _norm(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def _prov_rank(prov: str | None) -> int:
    if not prov:
        return 0
    return _PROV_RANK.get(prov, 50)  # unknown provenance = medium priority


def _is_history_form(form: str) -> bool:
    fl = (form or "").lower().strip()
    return any(fl.startswith(p) for p in _HISTORY_PREFIXES)


def _is_procedure_form(form: str) -> bool:
    fl = (form or "").lower()
    tokens = set(re.findall(r"[a-z]+", fl))
    return bool(tokens & _PROCEDURE_FORM_TOKENS)


# ---------------------------------------------------------------------------
# Cypher: fetch all MAPS_TO edges with full metadata
# ---------------------------------------------------------------------------
_FETCH_ALL = """
MATCH (sf:SurfaceForm)-[m:MAPS_TO]->(c:Concept)
RETURN
    sf.normalized    AS normalized,
    sf.form          AS form,
    sf.source        AS source,
    sf.status        AS sf_status,
    c.id             AS concept_id,
    c.fsn            AS concept_fsn,
    c.semantic_tag   AS semantic_tag,
    c.active         AS concept_active,
    m.confidence     AS confidence,
    m.provenance     AS provenance,
    m.created_at     AS created_at
ORDER BY sf.normalized, m.confidence DESC
"""

# ---------------------------------------------------------------------------
# Cypher: delete a specific MAPS_TO edge
# ---------------------------------------------------------------------------
_DELETE = """
MATCH (sf:SurfaceForm {normalized: $normalized})-[m:MAPS_TO]->(c:Concept {id: $concept_id})
WHERE m.provenance = $provenance
DELETE m
RETURN count(m) AS deleted
"""

# Also delete where provenance is null
_DELETE_NULL_PROV = """
MATCH (sf:SurfaceForm {normalized: $normalized})-[m:MAPS_TO]->(c:Concept {id: $concept_id})
WHERE m.provenance IS NULL
DELETE m
RETURN count(m) AS deleted
"""


def load_all_edges(session) -> list[dict]:
    rows = session.run(_FETCH_ALL).data()
    return rows


def group_by_normalized(rows: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    for r in rows:
        key = r["normalized"]
        groups.setdefault(key, []).append(r)
    return groups


def audit_edges(groups: dict[str, list[dict]]) -> list[dict]:
    """Apply all rules and return a decision record per edge."""
    decisions: list[dict] = []

    for normalized, edges in groups.items():
        # Build sets for quick lookup
        concept_ids = {e["concept_id"] for e in edges}
        active_concepts = {e["concept_id"] for e in edges if e["concept_active"]}
        has_active_non_broad = any(
            e["concept_id"] not in _BROAD_IDS and e["concept_active"]
            for e in edges
        )
        has_audit_fix = any(_prov_rank(e["provenance"]) >= 90 for e in edges)
        audit_fix_concepts = {
            e["concept_id"] for e in edges if _prov_rank(e["provenance"]) >= 90
        }

        for edge in edges:
            cid = edge["concept_id"]
            form = edge["form"] or ""
            prov = edge["provenance"]
            conf = edge["confidence"] or 0.0
            tag = (edge["semantic_tag"] or "").lower()
            active = edge["concept_active"]
            fsn = edge["concept_fsn"] or ""

            decision = "KEEP"
            rule = None
            reason = ""

            # R1: Inactive concept
            if not active:
                decision = "DELETE"
                rule = "R1_INACTIVE_CONCEPT"
                reason = f"Concept {cid} is inactive in SNOMED"

            # R2: Superseded by audit-fix pointing to a DIFFERENT, BETTER concept.
            # Guard: do NOT supersede if...
            #   a) the audit-fix target is itself a broad catch-all (audit-fix was wrong)
            #   b) the current edge is a legitimate history/situation for a history-prefix form
            #   c) the audit-fix concept is LESS specific (e.g. replacing immunoassay with general)
            elif (
                has_audit_fix
                and cid not in audit_fix_concepts
                and _prov_rank(prov) < 90
                # Guard (a): audit-fix targets must not all be broad catch-alls
                and any(aid not in _BROAD_IDS for aid in audit_fix_concepts)
                # Guard (b): current edge is NOT a correct history situation for a history form
                and not (tag == "situation" and _is_history_form(form))
                # Guard (c): current edge must not be MORE specific than all audit-fix targets
                # (heuristic: skip if current concept not in broad set and audit targets include broad)
                and not (
                    cid not in _BROAD_IDS
                    and all(aid in _BROAD_IDS for aid in audit_fix_concepts)
                )
            ):
                decision = "DELETE"
                rule = "R2_SUPERSEDED"
                reason = (
                    f"Audit-fix edge(s) exist for this form pointing to "
                    f"{audit_fix_concepts - {cid}}; this edge ({cid}, prov={prov}) is superseded"
                )

            # R3: Broad catch-all AND a better specific edge exists
            elif cid in _BROAD_IDS and has_active_non_broad:
                decision = "DELETE"
                rule = "R3_BROAD_WITH_BETTER"
                reason = f"Broad catch-all {cid} has better specific alternatives: {active_concepts - _BROAD_IDS}"

            # R4: Wrong situation code for active condition
            elif tag == "situation" and not _is_history_form(form):
                # Check the FSN indicates it's a history/absence situation
                fsn_low = fsn.lower()
                is_legit_situation = (
                    "history of" in fsn_low
                    or "no known" in fsn_low
                    or "absence" in fsn_low
                    or "background of" in fsn_low
                    or "family history" in fsn_low
                    or "at risk" in fsn_low
                    or "risk of" in fsn_low
                    or "carer" in fsn_low
                    or "on waiting list" in fsn_low
                    or "under care" in fsn_low
                    or "lives" in fsn_low
                    or "employed" in fsn_low
                    or "admitted" in fsn_low
                )
                if not is_legit_situation:
                    # Only delete if we have an active non-situation alternative
                    non_situation_alternatives = {
                        e["concept_id"] for e in edges
                        if e["concept_active"]
                        and (e["semantic_tag"] or "").lower() not in {"situation"}
                        and e["concept_id"] != cid
                    }
                    if non_situation_alternatives or has_audit_fix:
                        decision = "DELETE"
                        rule = "R4_WRONG_SITUATION"
                        reason = f"Form '{form}' is an active condition but mapped to situation: {fsn}"
                    else:
                        decision = "REVIEW"
                        rule = "R4_WRONG_SITUATION_NO_ALT"
                        reason = f"Form '{form}' mapped to situation with no better alternative: {fsn}"

            # R5: Procedure concept for a plain symptom/finding form
            elif tag in _PROCEDURE_TAGS and not _is_procedure_form(form):
                # Only flag if there's a better alternative
                non_proc_alternatives = {
                    e["concept_id"] for e in edges
                    if e["concept_active"]
                    and (e["semantic_tag"] or "").lower() not in _PROCEDURE_TAGS
                    and e["concept_id"] != cid
                }
                if non_proc_alternatives:
                    decision = "DELETE"
                    rule = "R5_WRONG_PROCEDURE"
                    reason = f"Form '{form}' looks like a finding but mapped to procedure: {fsn}"
                else:
                    decision = "KEEP"  # No better alternative; keep

            # R6: Totally inappropriate semantic tag
            elif tag in _WRONG_CLINICAL_TAGS:
                if has_active_non_broad and cid not in active_concepts:
                    pass  # already caught above
                # Check if form text is clearly clinical (not admin)
                form_tokens = set(re.findall(r"[a-z]+", form.lower()))
                admin_tokens = {"record", "document", "form", "letter", "report", "note"}
                if not form_tokens & admin_tokens:
                    decision = "REVIEW"
                    rule = "R6_WRONG_SEMANTIC_TAG"
                    reason = f"Form '{form}' has tag '{tag}': {fsn}"

            # R7: Duplicate MAPS_TO edge (same normalized, same concept, same provenance twice)
            # -- handled at the group level but we check for exact dupes
            # This is rare but can happen; the DELETE will remove all matching prov edges
            # so we flag duplicates only if provenance matches another edge exactly
            same_concept_same_prov = [
                e for e in edges
                if e["concept_id"] == cid and e["provenance"] == prov
            ]
            if len(same_concept_same_prov) > 1 and decision == "KEEP":
                decision = "REVIEW"
                rule = "R7_DUPLICATE"
                reason = f"Multiple edges for same form->concept->provenance"

            # R8: Broad with no alternative (review only)
            if decision == "KEEP" and cid in _BROAD_IDS and not has_active_non_broad:
                decision = "REVIEW"
                rule = "R8_BROAD_NO_ALTERNATIVE"
                reason = f"Only mapping is to broad catch-all {cid} ({fsn}); consider adding specific concept"

            decisions.append({
                "normalized":    normalized,
                "form":          form,
                "concept_id":    cid,
                "concept_fsn":   fsn,
                "semantic_tag":  tag,
                "confidence":    round(conf, 4),
                "provenance":    prov,
                "concept_active": active,
                "decision":      decision,
                "rule":          rule,
                "reason":        reason,
            })

    return decisions


def apply_deletes(session, decisions: list[dict]) -> int:
    to_delete = [d for d in decisions if d["decision"] == "DELETE"]
    total_deleted = 0
    for d in to_delete:
        prov = d["provenance"]
        if prov:
            r = session.run(
                _DELETE,
                normalized=d["normalized"],
                concept_id=d["concept_id"],
                provenance=prov,
            ).data()
        else:
            r = session.run(
                _DELETE_NULL_PROV,
                normalized=d["normalized"],
                concept_id=d["concept_id"],
            ).data()
        n = r[0]["deleted"] if r else 0
        total_deleted += n
    return total_deleted


def main(apply: bool) -> None:
    mode = "APPLY" if apply else "DRY-RUN"
    print(f"Mode: {mode}")
    driver = GraphDatabase.driver(kg_uri, auth=(kg_user, kg_pass))

    with driver.session() as s:
        print("Loading all surface form edges ...")
        rows = load_all_edges(s)
        print(f"  Total edges: {len(rows)}")

        groups = group_by_normalized(rows)
        print(f"  Unique normalised forms: {len(groups)}")

        decisions = audit_edges(groups)

        # Summary counts
        keep    = [d for d in decisions if d["decision"] == "KEEP"]
        delete  = [d for d in decisions if d["decision"] == "DELETE"]
        review  = [d for d in decisions if d["decision"] == "REVIEW"]

        print(f"\n{'=' * 70}")
        print(f"KEEP  : {len(keep):>5}")
        print(f"DELETE: {len(delete):>5}")
        print(f"REVIEW: {len(review):>5}")
        print(f"TOTAL : {len(decisions):>5}")

        # Rule breakdown for DELETEs
        delete_by_rule: dict[str, int] = {}
        for d in delete:
            delete_by_rule[d["rule"]] = delete_by_rule.get(d["rule"], 0) + 1
        print(f"\nDELETE breakdown by rule:")
        for rule, n in sorted(delete_by_rule.items(), key=lambda x: -x[1]):
            print(f"  {rule:<40} {n:>5}")

        # Rule breakdown for REVIEWs
        review_by_rule: dict[str, int] = {}
        for d in review:
            review_by_rule[d["rule"]] = review_by_rule.get(d["rule"], 0) + 1
        print(f"\nREVIEW breakdown by rule:")
        for rule, n in sorted(review_by_rule.items(), key=lambda x: -x[1]):
            print(f"  {rule:<40} {n:>5}")

        # Show sample DELETEs
        print(f"\n--- Sample DELETE decisions (first 30) ---")
        for d in delete[:30]:
            print(f"  [{d['rule']}] {d['form']!r} -> {d['concept_id']} | {d['concept_fsn'][:50]}")
            print(f"    prov={d['provenance']}  conf={d['confidence']}  reason: {d['reason'][:80]}")

        # Show sample REVIEWs
        print(f"\n--- Sample REVIEW decisions (first 20) ---")
        for d in review[:20]:
            print(f"  [{d['rule']}] {d['form']!r} -> {d['concept_id']} | {d['concept_fsn'][:50]}")
            print(f"    reason: {d['reason'][:80]}")

        if apply:
            print(f"\nApplying {len(delete)} deletes ...")
            total_deleted = apply_deletes(s, decisions)
            print(f"Edges deleted: {total_deleted}")

    driver.close()

    # Save full report
    report = {
        "total": len(decisions),
        "keep":   len(keep),
        "delete": len(delete),
        "review": len(review),
        "delete_by_rule": delete_by_rule,
        "review_by_rule": review_by_rule,
        "decisions": decisions,
    }
    OUTPUT.write_text(json.dumps(report, indent=2, ensure_ascii=True), encoding="utf-8")
    print(f"\nFull report: {OUTPUT}  ({OUTPUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true",
                        help="Actually execute the DELETE queries (default: dry-run)")
    args = parser.parse_args()
    main(apply=args.apply)
