"""Reconcile place-of-presentation surface forms using TS exact lookup.

Uses the authoritative ADDITIONS set from _apply_place_surface_forms.py.
For each normalized surface form:
  - check current exact-surface return(s)
  - ensure desired concept mapping exists
  - remove competing mappings
  - re-check top returned concept

Dry-run by default. Use --apply to write.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from libs.keyvault.loader import load_keyvault_secrets
from libs.neo4j_client.client import KnowledgeGraphClient
from scripts.investigations._apply_place_surface_forms import ADDITIONS
from services.terminology_api.app.queries.terminology import (
    EXACT_SURFACE_FORM_QUERY,
    KEEP_SURFACE_FORM_MAPPING,
    UPSERT_SURFACE_FORM_MAPPING,
)

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
load_keyvault_secrets()

APPLY = "--apply" in sys.argv

_CURRENT_Q = """
MATCH (sf:SurfaceForm {normalized: $normalized})-[m:MAPS_TO]->(c:Concept)
RETURN c.id AS concept_id, c.fsn AS fsn, coalesce(m.confidence, 0.0) AS confidence
ORDER BY confidence DESC, c.id
"""


def main() -> None:
    desired: dict[str, tuple[str, str]] = {}
    for normalized, raw, concept_id, _label in ADDITIONS:
        if normalized not in desired:
            desired[normalized] = (concept_id, raw)

    print(
        f"Reconciling {len(desired)} place forms; mode={'APPLY' if APPLY else 'DRY RUN'}"
    )

    kg = KnowledgeGraphClient()
    try:
        changed = 0
        verify_fail = 0
        removed_total = 0
        upsert_total = 0

        for normalized, (concept_id, raw) in sorted(desired.items()):
            before = kg.run(_CURRENT_Q, normalized=normalized) or []
            before_ids = [str(r.get("concept_id") or "") for r in before]
            need_upsert = concept_id not in before_ids
            need_prune = any(cid and cid != concept_id for cid in before_ids)

            if need_upsert or need_prune:
                changed += 1
                if APPLY:
                    if need_upsert:
                        out = (
                            kg.run(
                                UPSERT_SURFACE_FORM_MAPPING,
                                normalized=normalized,
                                form=raw,
                                concept_id=concept_id,
                                confidence=0.99,
                                source="manual_curation",
                                provenance="place_lookup_reconcile_2026",
                            )
                            or []
                        )
                        if out:
                            upsert_total += 1
                    if need_prune:
                        rem = (
                            kg.run(
                                KEEP_SURFACE_FORM_MAPPING,
                                normalized=normalized,
                                keep_concept_id=concept_id,
                            )
                            or []
                        )
                        removed_total += int(rem[0].get("removed", 0)) if rem else 0
                else:
                    action = []
                    if need_upsert:
                        action.append("upsert")
                    if need_prune:
                        action.append("prune")
                    print(
                        f"PATCH {normalized!r:35s} desired={concept_id} "
                        f"before={before_ids or 'none'} action={'+'.join(action)}"
                    )

            verify = (
                kg.run(
                    EXACT_SURFACE_FORM_QUERY,
                    normalized=normalized,
                    k=3,
                )
                or []
            )
            if not verify:
                verify_fail += 1
                print(f"VERIFY FAIL no result: {normalized!r}")
                continue
            top_id = str(verify[0].get("concept_id") or "")
            if top_id != concept_id:
                verify_fail += 1
                print(
                    f"VERIFY FAIL {normalized!r}: top={top_id} expected={concept_id} "
                    f"all={[str(v.get('concept_id') or '') for v in verify]}"
                )

        print("\nSummary")
        print(f"  changed_forms: {changed}")
        if APPLY:
            print(f"  upserts_written: {upsert_total}")
            print(f"  competing_mappings_removed: {removed_total}")
        print(f"  verify_failures: {verify_fail}")
    finally:
        kg.close()


if __name__ == "__main__":
    main()
