"""Patch DOCUMENTS edges: reclassify legacy 'hypothetical' context where appropriate.

The old pipeline stored assertion as a plain string: r.context = 'hypothetical'.
The new ConText engine has a PLANNED category (confirmed bookings/referrals/awaiting)
separate from HYPOTHETICAL (conditional/speculative future).

This script inspects each 'hypothetical' edge's evidence text and reclassifies:
  - Planning evidence  -> assertion='planned'  (booked, awaiting, referred for, etc.)
  - Uncertainty ('?')  -> assertion='possible'  (suspected diagnosis)
  - Ambiguous          -> assertion='hypothetical' (kept, upgraded to JSON format)

All updated edges are stamped with audit_flag='assertion_patched_planned_v1'.
Edges are also migrated from the old plain-string context to the new JSON format.

Usage:
    python scripts/investigations/_patch_hypothetical_to_planned.py            (dry run)
    python scripts/investigations/_patch_hypothetical_to_planned.py --apply   (write)
"""

from __future__ import annotations

import json
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

import os
from neo4j import GraphDatabase

# ---------------------------------------------------------------------------
# Classification rules
# ---------------------------------------------------------------------------
_PLANNING_RE = re.compile(
    r"\b("
    r"awaiting|"
    r"booked\s+for|booked\s+\d|appointment\s+booked|"
    r"confirmation\s+of\s+appointment|"
    r"scheduled\s+for|"
    r"referred\s+for|referral\s+for|"
    r"on\s+waiting\s+list|waiting\s+list|"
    r"arranged\s+for|"
    r"have\s+requested|"
    r"appointment\s+at\s+\w|"  # 'appointment at Woodbrook...'
    r"appointment\s+on\s+\d|"  # 'appointment on 27 Feb...'
    r"appointment\s+\d|"  # 'appointment 03 Sep...'
    r"physiotherapy\s+appointment|"
    r"outpatient\s+appointment"
    r")",
    re.IGNORECASE,
)

_UNCERTAINTY_RE = re.compile(r"^\?|\?\w+|query\s+\w", re.IGNORECASE)

# Evidence text that means the current encounter IS the event (not future)
_CURRENT_ENCOUNTER_RE = re.compile(
    r"\bthis\s+is\s+a\s+(face[\s-]to[\s-]face|telephone|video)\b",
    re.IGNORECASE,
)

_AUDIT_FLAG = "assertion_patched_planned_v1"


def _new_context_json(assertion: str) -> str:
    ctx = {
        "assertion": assertion,
        "negated": assertion == "absent",
        "refuted": assertion == "refuted",
        "uncertain": assertion == "possible",
        "historical": assertion == "historical",
        "planned": assertion == "planned",
        "hypothetical": assertion == "hypothetical",
        "family": assertion == "family",
        "declined": assertion == "declined",
        "cancelled": assertion == "cancelled",
    }
    return json.dumps(ctx, separators=(", ", ": "))


def _classify(evidence: str) -> str:
    ev = (evidence or "").strip()
    if _CURRENT_ENCOUNTER_RE.search(ev):
        return "present"
    if _PLANNING_RE.search(ev):
        return "planned"
    if _UNCERTAINTY_RE.search(ev):
        return "possible"
    return "hypothetical"


# ---------------------------------------------------------------------------
# Cypher
# ---------------------------------------------------------------------------
_FETCH_Q = """
MATCH (e:Encounter)-[r:DOCUMENTS]->(s)
WHERE r.context = 'hypothetical'
RETURN
    e.id          AS encounter_id,
    s.conceptId   AS concept_id,
    r.evidence    AS evidence,
    s.name        AS concept_name,
    s.semanticTag AS semantic_tag
"""

_UPDATE_Q = """
MATCH (e:Encounter {id: $encounter_id})-[r:DOCUMENTS]->(s {conceptId: $concept_id})
WHERE r.context = 'hypothetical'
SET r.context    = $new_context,
    r.audit_flag = $audit_flag
RETURN count(r) AS updated
"""


def main() -> None:
    apply = "--apply" in sys.argv

    pg_uri = os.getenv("NEO4J_URI", "") or os.getenv(
        "NEO4J_PATIENT_URI", "bolt://localhost:7687"
    )
    pg_user = os.getenv("NEO4J_USER", "") or os.getenv("NEO4J_PATIENT_USER", "neo4j")
    pg_pass = os.getenv("NEO4J_PASSWORD", "") or os.getenv(
        "NEO4J_PATIENT_PASSWORD", "patient-dev"
    )

    driver = GraphDatabase.driver(pg_uri, auth=(pg_user, pg_pass))
    try:
        with driver.session() as session:
            rows = list(session.run(_FETCH_Q))
            print(f"Total plain-string 'hypothetical' DOCUMENTS edges: {len(rows)}")

            buckets: dict[str, list] = {
                "planned": [],
                "possible": [],
                "present": [],
                "hypothetical": [],
            }
            for row in rows:
                ev = str(row["evidence"] or "")
                new_assertion = _classify(ev)
                buckets[new_assertion].append(
                    {
                        "encounter_id": row["encounter_id"],
                        "concept_id": row["concept_id"],
                        "evidence": ev,
                        "concept_name": str(row["concept_name"] or ""),
                        "new_assertion": new_assertion,
                        "new_context": _new_context_json(new_assertion),
                    }
                )

            print(f"\n--- Triage ---")
            for label, items in sorted(buckets.items(), key=lambda x: -len(x[1])):
                print(f"  -> {label:<12} {len(items):>4}")

            for label, items in sorted(buckets.items(), key=lambda x: -len(x[1])):
                if not items:
                    continue
                print(f"\n-- {label} sample --")
                for h in items[:5]:
                    print(
                        f"  enc={h['encounter_id'][:8]}  "
                        f"concept={h['concept_name'][:35]}  "
                        f"evidence={h['evidence'][:70]!r}"
                    )

            if not apply:
                print("\n[DRY RUN] -- pass --apply to write changes.")
                return

            # -- Apply --
            updated = 0
            errors = 0
            for label, items in buckets.items():
                for h in items:
                    try:
                        res = session.run(
                            _UPDATE_Q,
                            encounter_id=h["encounter_id"],
                            concept_id=h["concept_id"],
                            new_context=h["new_context"],
                            audit_flag=_AUDIT_FLAG,
                        ).single()
                        updated += res["updated"] if res else 0
                    except Exception as exc:
                        print(
                            f"ERROR enc={h['encounter_id'][:8]} cid={h['concept_id']}: {exc}"
                        )
                        errors += 1

            print(f"\nApplied. Updated={updated}  Errors={errors}")
            for label, items in sorted(buckets.items(), key=lambda x: -len(x[1])):
                print(f"  {label}: {len(items)}")

    finally:
        driver.close()


if __name__ == "__main__":
    main()
