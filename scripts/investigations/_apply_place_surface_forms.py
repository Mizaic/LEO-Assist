"""Apply place-of-presentation surface form changes to the KG.

Actions:
  1. Remove the one genuinely incorrect mapping:
       'accident & emergency' -> 393357004 (qualifier value) -- wrong concept
  2. Add all clean missing surface forms to their correct place concepts.

Dry-run mode (default): prints what would happen without writing.
Pass --apply to execute.

Usage:
    python scripts/investigations/_apply_place_surface_forms.py           # dry run
    python scripts/investigations/_apply_place_surface_forms.py --apply   # write
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets
load_keyvault_secrets()
from libs.neo4j_client.client import KnowledgeGraphClient

DRY_RUN = "--apply" not in sys.argv

_DELETE_Q = """
MATCH (sf:SurfaceForm {normalized: $normalized})-[r:MAPS_TO]->(c:Concept {id: $concept_id})
DELETE r
RETURN count(r) AS removed
"""

_UPSERT_Q = """
MATCH (c:Concept {id: $concept_id})
MERGE (sf:SurfaceForm {normalized: $normalized})
ON CREATE SET sf.form = $form,
              sf.source = $source,
              sf.status = 'active',
              sf.created_at = datetime()
MERGE (sf)-[m:MAPS_TO]->(c)
ON CREATE SET m.created_at = datetime(),
              m.approved_at = datetime()
SET m.confidence = $confidence,
    m.provenance = $provenance
RETURN sf.normalized AS normalized,
       sf.form       AS form,
       c.id          AS concept_id,
       c.fsn         AS concept_fsn
"""

# ---------------------------------------------------------------------------
# 1. Incorrect mappings to REMOVE
# ---------------------------------------------------------------------------
# Only 'accident & emergency' is genuinely wrong (maps to a qualifier value).
# Everything else either is correct or too ambiguous to touch.
REMOVALS: list[dict] = [
    {
        "normalized": "accident & emergency",
        "concept_id": "393357004",
        "reason": "Mapped to qualifier value, not an environment",
    },
]

# ---------------------------------------------------------------------------
# 2. New surface forms to ADD
# ---------------------------------------------------------------------------
# Format: (normalised_form, raw_form, concept_id, label)
# Excluded ambiguous forms: 'ed', 'er', '111', 'ae'
ADDITIONS: list[tuple[str, str, str, str]] = [
    # -- 4525004  Emergency department patient visit -------------------------
    ("a&e",                    "A&E",                      "4525004", "accident and emergency"),
    ("accident and emergency", "accident and emergency",   "4525004", "accident and emergency"),
    ("accident & emergency",   "accident & emergency",     "4525004", "accident and emergency"),
    ("emergency department",   "emergency department",     "4525004", "accident and emergency"),
    ("emergency room",         "emergency room",           "4525004", "accident and emergency"),
    ("a and e",                "A and E",                  "4525004", "accident and emergency"),
    ("a+e",                    "A+E",                      "4525004", "accident and emergency"),
    ("a & e",                  "A & E",                    "4525004", "accident and emergency"),
    ("casualty",               "casualty",                 "4525004", "accident and emergency"),
    ("emergency dept",         "emergency dept",           "4525004", "accident and emergency"),
    ("attended a&e",           "attended A&E",             "4525004", "accident and emergency"),
    ("seen in a&e",            "seen in A&E",              "4525004", "accident and emergency"),
    ("went to a&e",            "went to A&E",              "4525004", "accident and emergency"),

    # -- 185202000  Seen in general practitioner surgery --------------------
    ("gp appointment",         "GP appointment",           "185202000", "GP surgery"),
    ("gp visit",               "GP visit",                 "185202000", "GP surgery"),
    ("gp clinic",              "GP clinic",                "185202000", "GP surgery"),
    ("seen at gp",             "seen at GP",               "185202000", "GP surgery"),
    ("attended gp",            "attended GP",              "185202000", "GP surgery"),
    ("primary care",           "primary care",             "185202000", "GP surgery"),
    ("gp consultation",        "GP consultation",          "185202000", "GP surgery"),
    ("gp review",              "GP review",                "185202000", "GP surgery"),
    ("surgery appointment",    "surgery appointment",      "185202000", "GP surgery"),
    ("seen in surgery",        "seen in surgery",          "185202000", "GP surgery"),

    # -- 386472008  Telephone consultation ----------------------------------
    ("telephone appointment",  "telephone appointment",    "386472008", "telephone"),
    ("phone consultation",     "phone consultation",       "386472008", "telephone"),
    ("phone call",             "phone call",               "386472008", "telephone"),
    ("telephone call",         "telephone call",           "386472008", "telephone"),
    ("tel consult",            "tel consult",              "386472008", "telephone"),
    ("phone appointment",      "phone appointment",        "386472008", "telephone"),
    ("telephone review",       "telephone review",         "386472008", "telephone"),
    ("phone review",           "phone review",             "386472008", "telephone"),
    ("spoke by phone",         "spoke by phone",           "386472008", "telephone"),
    ("called by phone",        "called by phone",          "386472008", "telephone"),
    ("telephone advice",       "telephone advice",         "386472008", "telephone"),

    # -- 439708006  Home visit -----------------------------------------------
    ("home call",              "home call",                "439708006", "home visit"),
    ("visited at home",        "visited at home",          "439708006", "home visit"),
    ("seen at home",           "seen at home",             "439708006", "home visit"),
    ("housecall",              "housecall",                "439708006", "home visit"),
    ("home consultation",      "home consultation",        "439708006", "home visit"),
    ("visited patient at home","visited patient at home",  "439708006", "home visit"),

    # -- 185463005  Visit out of hours ---------------------------------------
    ("out of hours",           "out of hours",             "185463005", "out of hours"),
    ("out-of-hours",           "out-of-hours",             "185463005", "out of hours"),
    ("out of hours visit",     "out of hours visit",       "185463005", "out of hours"),
    ("ooh visit",              "OOH visit",                "185463005", "out of hours"),
    ("out of hours gp",        "out of hours GP",          "185463005", "out of hours"),
    ("ooh gp",                 "OOH GP",                   "185463005", "out of hours"),
    ("ooh service",            "OOH service",              "185463005", "out of hours"),
    ("nhs 111",                "NHS 111",                  "185463005", "out of hours"),
    ("evening appointment",    "evening appointment",      "185463005", "out of hours"),
    ("weekend appointment",    "weekend appointment",      "185463005", "out of hours"),
    ("urgent out of hours",    "urgent out of hours",      "185463005", "out of hours"),
    ("out of hours consultation", "out of hours consultation", "185463005", "out of hours"),

    # -- 557761000005104  E-mail consultation --------------------------------
    ("email consult",          "email consult",            "557761000005104", "email"),
    ("e-consult",              "e-consult",                "557761000005104", "email"),
    ("econsult",               "econsult",                 "557761000005104", "email"),
    ("online form",            "online form",              "557761000005104", "email"),
    ("askmygp",                "askmygp",                  "557761000005104", "email"),
    ("emailed gp",             "emailed GP",               "557761000005104", "email"),
    ("electronic consultation","electronic consultation",  "557761000005104", "email"),
    ("online consultation request", "online consultation request", "557761000005104", "email"),
    ("sent message to gp",     "sent message to GP",       "557761000005104", "email"),
    ("accubook",               "accubook",                 "557761000005104", "email"),
    ("patchs",                 "patchs",                   "557761000005104", "email"),

    # -- 719410009  Video consultation ---------------------------------------
    ("video call",             "video call",               "719410009", "video"),
    ("video appointment",      "video appointment",        "719410009", "video"),
    ("video conference",       "video conference",         "719410009", "video"),
    ("video consult",          "video consult",            "719410009", "video"),
    ("online video",           "online video",             "719410009", "video"),
    ("microsoft teams consultation", "Microsoft Teams consultation", "719410009", "video"),
    ("teams call",             "Teams call",               "719410009", "video"),
    ("zoom consultation",      "Zoom consultation",        "719410009", "video"),
    ("attend anywhere",        "Attend Anywhere",          "719410009", "video"),
    ("video review",           "video review",             "719410009", "video"),
    ("remote video consultation", "remote video consultation", "719410009", "video"),
    ("online consultation",    "online consultation",      "719410009", "video"),
    ("virtual consultation",   "virtual consultation",     "719410009", "video"),
    ("virtual appointment",    "virtual appointment",      "719410009", "video"),

    # -- 286901000000107  Bowel cancer screening ----------------------------
    ("colorectal screening",   "colorectal screening",     "286901000000107", "bowel screening"),
    ("bowel scope",            "bowel scope",              "286901000000107", "bowel screening"),
    ("colonoscopy screening",  "colonoscopy screening",    "286901000000107", "bowel screening"),
    ("bowel cancer check",     "bowel cancer check",       "286901000000107", "bowel screening"),

    # -- 268547008  Breast screening ----------------------------------------
    ("breast screening",       "breast screening",         "268547008", "breast screening"),
    ("nhs breast screening",   "NHS breast screening",     "268547008", "breast screening"),
    ("breast check",           "breast check",             "268547008", "breast screening"),
    ("mammogram appointment",  "mammogram appointment",    "268547008", "breast screening"),
    ("breast x-ray",           "breast x-ray",             "268547008", "breast screening"),
    ("breast screening appointment", "breast screening appointment", "268547008", "breast screening"),

    # -- 171149006  Cervical screening --------------------------------------
    ("cervical screening",     "cervical screening",       "171149006", "cervical screening"),
    ("smear test",             "smear test",               "171149006", "cervical screening"),
    ("cervical cancer screening", "cervical cancer screening", "171149006", "cervical screening"),
    ("nhs cervical screening", "NHS cervical screening",   "171149006", "cervical screening"),
    ("hpv test",               "HPV test",                 "171149006", "cervical screening"),
    ("cervical check",         "cervical check",           "171149006", "cervical screening"),
    ("routine smear",          "routine smear",            "171149006", "cervical screening"),

    # -- 275981009  Lung screening ------------------------------------------
    ("lung screening",         "lung screening",           "275981009", "lung screening"),
    ("ldct",                   "LDCT",                     "275981009", "lung screening"),
    ("low dose ct scan",       "low dose CT scan",         "275981009", "lung screening"),
    ("lung check",             "lung check",               "275981009", "lung screening"),
    ("chest ct screening",     "chest CT screening",       "275981009", "lung screening"),
    ("targeted lung health check", "targeted lung health check", "275981009", "lung screening"),
    ("tlhc",                   "TLHC",                     "275981009", "lung screening"),

    # -- 307778003  Seen in primary care establishment ----------------------
    ("primary care visit",     "primary care visit",       "307778003", "primary care"),
    ("seen in primary care",   "seen in primary care",     "307778003", "primary care"),
    ("seen at primary care",   "seen at primary care",     "307778003", "primary care"),
    ("primary care appointment", "primary care appointment", "307778003", "primary care"),
    ("gp led",                 "GP led",                   "307778003", "primary care"),
    ("community health centre","community health centre",  "307778003", "primary care"),
    ("utc",                    "UTC",                      "307778003", "primary care"),
    ("ucc",                    "UCC",                      "307778003", "primary care"),

    # -- 185211000  Seen in hospital outpatient department ------------------
    ("opd",                    "OPD",                      "185211000", "outpatient"),
    ("outpatients",            "outpatients",              "185211000", "outpatient"),
    ("outpatient department",  "outpatient department",    "185211000", "outpatient"),
    ("outpatient appointment", "outpatient appointment",   "185211000", "outpatient"),
    ("outpatient clinic",      "outpatient clinic",        "185211000", "outpatient"),
    ("outpatient visit",       "outpatient visit",         "185211000", "outpatient"),
    ("hospital outpatient",    "hospital outpatient",      "185211000", "outpatient"),
    ("seen in outpatients",    "seen in outpatients",      "185211000", "outpatient"),
    ("clinic appointment",     "clinic appointment",       "185211000", "outpatient"),
    ("attended outpatients",   "attended outpatients",     "185211000", "outpatient"),
    ("seen at hospital",       "seen at hospital",         "185211000", "outpatient"),
    ("hospital appointment",   "hospital appointment",     "185211000", "outpatient"),
    ("specialist outpatient",  "specialist outpatient",    "185211000", "outpatient"),

    # -- 185289007  Dental --------------------------------------------------
    ("dental appointment",     "dental appointment",       "185289007", "dental"),
    ("dental visit",           "dental visit",             "185289007", "dental"),
    ("dental consultation",    "dental consultation",      "185289007", "dental"),
    ("seen at dentist",        "seen at dentist",          "185289007", "dental"),

    # -- 305856003  Optometry -----------------------------------------------
    ("optometry",              "optometry",                "305856003", "optometry"),
    ("eye test",               "eye test",                 "305856003", "optometry"),
    ("eye appointment",        "eye appointment",          "305856003", "optometry"),
    ("optics appointment",     "optics appointment",       "305856003", "optometry"),
    ("vision test",            "vision test",              "305856003", "optometry"),
    ("seen at optician",       "seen at optician",         "305856003", "optometry"),

    # -- 305751001  Community nurse -----------------------------------------
    ("nurse visit",            "nurse visit",              "305751001", "community nurse"),
    ("nurse appointment",      "nurse appointment",        "305751001", "community nurse"),
    ("community health nurse", "community health nurse",   "305751001", "community nurse"),
    ("nurse consultation",     "nurse consultation",       "305751001", "community nurse"),
    ("nursing visit",          "nursing visit",            "305751001", "community nurse"),
    ("nurse review",           "nurse review",             "305751001", "community nurse"),
    ("seen at nurse clinic",   "seen at nurse clinic",     "305751001", "community nurse"),
]


def main() -> None:
    mode = "DRY RUN" if DRY_RUN else "APPLYING"
    print(f"\n{'=' * 60}")
    print(f"  Place surface form update -- {mode}")
    print(f"  Removals : {len(REMOVALS)}")
    print(f"  Additions: {len(ADDITIONS)}")
    print(f"{'=' * 60}\n")

    if DRY_RUN:
        print("REMOVALS:")
        for r in REMOVALS:
            print(f"  DELETE  {r['normalized']!r} -> {r['concept_id']}  ({r['reason']})")
        print(f"\nADDITIONS ({len(ADDITIONS)}):")
        prev_label = ""
        for norm, raw, cid, label in ADDITIONS:
            if label != prev_label:
                print(f"\n  -- {cid}  {label} --")
                prev_label = label
            print(f"    ADD  {norm!r}")
        print("\nRe-run with --apply to commit changes.")
        return

    kg = KnowledgeGraphClient()
    removed = 0
    added = 0
    errors: list[str] = []

    try:
        # -- Removals --------------------------------------------------------
        print("Removing incorrect mappings ...")
        for r in REMOVALS:
            rows = kg.run(_DELETE_Q, normalized=r["normalized"], concept_id=r["concept_id"]) or []
            n = rows[0].get("removed", 0) if rows else 0
            removed += n
            print(f"  {'REMOVED' if n else 'NOT FOUND'}  {r['normalized']!r} -> {r['concept_id']}")

        # -- Additions -------------------------------------------------------
        print(f"\nAdding {len(ADDITIONS)} surface forms ...")
        prev_label = ""
        for norm, raw, cid, label in ADDITIONS:
            if label != prev_label:
                print(f"\n  -- {cid}  {label} --")
                prev_label = label
            try:
                rows = kg.run(
                    _UPSERT_Q,
                    normalized=norm,
                    form=raw,
                    concept_id=cid,
                    confidence=0.95,
                    source="manual_curation",
                    provenance="place_of_presentation_audit_2026",
                ) or []
                if rows:
                    added += 1
                    print(f"    OK   {norm!r}")
                else:
                    errors.append(f"No result for {norm!r} -> {cid}")
                    print(f"    WARN no result for {norm!r} -- concept may not exist")
            except Exception as exc:
                errors.append(f"{norm!r}: {exc}")
                print(f"    ERR  {norm!r}: {exc}")

    finally:
        kg.close()

    print(f"\n{'=' * 60}")
    print(f"Removed : {removed}")
    print(f"Added   : {added}")
    print(f"Errors  : {len(errors)}")
    if errors:
        for e in errors:
            print(f"  {e}")
    print("Done.")


if __name__ == "__main__":
    main()
