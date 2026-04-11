"""Extract encounters on and up to 90 days before each referral date.

Saves raw encounter text to JSON, then scans for candidate surface forms
for symptoms and place-of-presentation subdomains.

Usage:
    python scripts/investigations/_extract_pre_referral_encounters.py

Output:
    scripts/investigations/output/pre_referral_encounters.json
    scripts/investigations/output/pre_referral_surface_forms.json
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()
from libs.neo4j_client.client import PatientGraphClient

OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

ENCOUNTERS_FILE = OUTPUT_DIR / "pre_referral_encounters.json"
SURFACE_FORMS_FILE = OUTPUT_DIR / "pre_referral_surface_forms.json"

# 90-day lookback window (in days)
LOOKBACK_DAYS = 90

# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

# Fetch all episodes that have a referral_date
Q_EPISODES = """
MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare)
WHERE ep.referral_date IS NOT NULL
RETURN
    toString(p.id)          AS patient_id,
    ep.episode_id           AS episode_id,
    ep.cancer_type          AS cancer_type,
    toString(ep.referral_date) AS referral_date
ORDER BY ep.referral_date
"""

# For each patient + date window, fetch encounters with text
Q_ENCOUNTERS = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(p.id) = $patient_id
  AND toString(e.date) >= $window_start
  AND toString(e.date) <= $referral_date
  AND e.text IS NOT NULL
  AND trim(e.text) <> ''
RETURN
    toString(e.id)   AS encounter_id,
    toString(e.date) AS encounter_date,
    e.text           AS text,
    coalesce(e.classification_content_type, '') AS content_type,
    coalesce(e.classification_encounter_purpose, '') AS purpose
ORDER BY e.date
"""

# ---------------------------------------------------------------------------
# Surface form extraction patterns
# ---------------------------------------------------------------------------

# -- Symptoms (cancer-relevant presenting complaints) -----------------------
_SYMPTOM_PATTERNS: list[tuple[str, str]] = [
    # Respiratory
    (
        r"\bhaemoptysis\b|\bcoughing (?:up )?blood\b|\bblood(?:y)? sputum\b",
        "haemoptysis",
    ),
    (
        r"\bpersistent cough\b|\bchronic cough\b|\bcough(?:ing)? for (?:weeks|months)\b",
        "persistent cough",
    ),
    (
        r"\bbreathlessness\b|\bshortness of breath\b|\bdyspnoea\b|\bSOB\b",
        "breathlessness",
    ),
    (r"\bchest pain\b|\bchest tightness\b|\bchest discomfort\b", "chest pain"),
    (
        r"\bhoarseness\b|\bhoarse voice\b|\bchange in voice\b|\bdysphonia\b",
        "hoarseness",
    ),
    # GI
    (
        r"\brectal bleed(?:ing)?\b|\bblood(?:y)? stool\b|\bblood in (?:the )?stool\b|\bPR bleed(?:ing)?\b|\bblood per rectum\b",
        "rectal bleeding",
    ),
    (
        r"\bchange in bowel habit\b|\baltered bowel habit\b|\bbowel habit change\b",
        "change in bowel habit",
    ),
    (
        r"\bdysphagia\b|\bdifficulty swallow(?:ing)?\b|\bswallowing difficult\b",
        "dysphagia",
    ),
    (r"\bhaematemesis\b|\bvomiting blood\b|\bblood(?:y)? vomit\b", "haematemesis"),
    (
        r"\babdominal pain\b|\btummy pain\b|\bstomach pain\b|\bepigastric pain\b",
        "abdominal pain",
    ),
    (
        r"\bunexplained weight loss\b|\bweight loss\b|\blosing weight\b|\bweight has (?:been )?(?:dropping|falling)\b",
        "unexplained weight loss",
    ),
    (r"\bloose stools?\b|\bdiarrhoea\b|\bdiarrhea\b", "loose stools / diarrhoea"),
    # Urological
    (
        r"\bhaematuria\b|\bblood in (?:the )?urine\b|\bbloody urine\b|\bblood(?:y)? urine\b",
        "haematuria",
    ),
    (
        r"\bvoiding symptoms\b|\bLUTS\b|\bfrequency of urine\b|\burinary frequency\b|\bnocturia\b|\bdribbling\b|\bhesitancy\b|\bweak stream\b",
        "lower urinary tract symptoms",
    ),
    (
        r"\bPSA (?:raised|elevated|high)\b|\braised PSA\b|\bhigh PSA\b|\belevated PSA\b",
        "raised PSA",
    ),
    # Breast
    (
        r"\bbreast lump\b|\blump in (?:her|the) breast\b|\bbreast mass\b|\bpalpable (?:breast )?lump\b",
        "breast lump",
    ),
    (r"\bnipple discharge\b|\bdischarge from (?:the )?nipple\b", "nipple discharge"),
    (r"\bnipple inversion\b|\binverted nipple\b", "nipple inversion"),
    (r"\bbreast pain\b|\bmastalgia\b|\bbreast discomfort\b", "breast pain"),
    (
        r"\bbreast skin change\b|\bpeau d'orange\b|\bskin puckering\b|\bbreast skin puckering\b",
        "breast skin change",
    ),
    # Skin
    (
        r"\bchanging mole\b|\bchanging (?:skin )?lesion\b|\bnew mole\b|\bgrowing mole\b|\bsuspicious mole\b",
        "suspicious mole / changing lesion",
    ),
    (r"\bskin lesion\b|\bpigmented lesion\b|\bmelanoma\b", "skin lesion"),
    (
        r"\bnon-healing (?:wound|ulcer|sore)\b|\bchronic wound\b|\bfailing to heal\b",
        "non-healing lesion",
    ),
    # Gynaecological
    (
        r"\bpostmenopausal bleed(?:ing)?\b|\bPMB\b|\bbleeding after (?:the )?menopause\b",
        "postmenopausal bleeding",
    ),
    (
        r"\bintermenstrual bleed(?:ing)?\b|\bIMB\b|\bbleeding between periods\b",
        "intermenstrual bleeding",
    ),
    (
        r"\bvaginal bleed(?:ing)?\b|\bPV bleed(?:ing)?\b|\bblood(?:y)? vaginal discharge\b",
        "vaginal bleeding",
    ),
    (r"\bpelvic pain\b|\blower (?:abdominal|pelvic) pain\b", "pelvic pain"),
    # Head and neck
    (
        r"\bulcer in (?:the )?mouth\b|\boral ulcer\b|\bmouth ulcer (?:not healing|persisting)\b|\bpersistent (?:mouth|oral) ulcer\b",
        "persistent oral ulcer",
    ),
    (
        r"\bneck lump\b|\blump in (?:the )?neck\b|\bcervical lymphadenopathy\b|\bswollen (?:lymph )?node\b|\blymph node (?:swelling|enlargement)\b",
        "neck lump",
    ),
    (
        r"\bearache\b|\bear pain\b|\botalgia\b|\bpersistent earache\b",
        "persistent earache",
    ),
    # Haematological
    (r"\bnight sweats?\b", "night sweats"),
    (
        r"\bfatigue\b|\bexhaustion\b|\btiredness\b|\bconstant(?:ly)? tired\b",
        "unexplained fatigue",
    ),
    (r"\bbruising\b|\bunexplained bruise\b|\bbruise easily\b", "unexplained bruising"),
    # "pale" alone is too generic; require clinical qualifier
    (
        r"\banaemia\b|\banemia\b|\bhaemoglobin (?:low|drop(?:ped)?)\b|\blow Hb\b|\bpallor\b|\bpale and tired\b|\bpale appearance\b",
        "anaemia / pallor",
    ),
    # Lung / general
    (r"\bbone pain\b|\bpain in (?:my|the) bones?\b", "bone pain"),
    (r"\bheadache\b|\bsevere headache\b|\bworsening headache\b", "headache"),
    # "fit" alone excluded -- too ambiguous (FIT test, fit and well, fit for surgery, fit note).
    # Only match "fit" when it clearly means a seizure episode.
    (
        r"\bseizure\b|\bepilepsy\b|\bconvulsion\b"
        r"|\bepilep(?:tic)? fit\b"  # epileptic fit / epilepsy fit
        r"|\bhad a fit\b|\bsuffered a fit\b|\bfitting episode\b"
        r"|\btonic.clonic\b|\bfocal seizure\b|\babsence seizure\b",
        "seizure",
    ),
]

# -- Place of presentation -------------------------------------------------
_PLACE_PATTERNS: list[tuple[str, str]] = [
    # "ED" and bare "ae" excluded -- too ambiguous. "A&E" requires the ampersand.
    (
        r"\bA&E\b|\baccident and emergency\b|\bemergency department\b|\bemergency room\b|\bA and E\b",
        "accident and emergency",
    ),
    (
        r"\bwalk.?in (?:centre|center)\b|\bwalk.?in clinic\b|\bUCC\b|\burgent (?:care|treatment) (?:centre|center)\b",
        "walk-in / urgent care centre",
    ),
    (
        r"\bGP (?:surgery|practice|clinic)\b|\bgeneral practice\b|\bprimary care\b|\bfamily (?:doctor|physician)\b|\bGP appointment\b|\bseen (?:by|at) (?:the )?GP\b",
        "GP surgery",
    ),
    (
        r"\bhospital outpatient\b|\boutpatient (?:clinic|department|appointment)\b|\bOPD\b|\bclinic appointment\b",
        "hospital outpatient clinic",
    ),
    (r"\bpharmacist\b|\bpharmacy\b|\bchemist\b", "pharmacy"),
    (
        r"\bonline (?:consultation|appointment|GP)\b|\bvideo (?:consultation|appointment)\b|\btelephone (?:consultation|appointment)\b|\bremote consultation\b|\be-consult\b",
        "remote / online consultation",
    ),
    (
        r"\bprivate (?:clinic|hospital|consultant)\b|\bprivate sector\b",
        "private clinic",
    ),
    (
        r"\bscreening (?:programme|clinic|appointment)\b|\bbowel screening\b|\bbreast screening\b|\bcervical screening\b|\bsmear\b",
        "screening programme",
    ),
    (
        r"\bself.?refer(?:ral)?\b|\bself referred\b|\bpatient self-refer\b",
        "self-referral",
    ),
    (
        r"\bdiagnostic (?:centre|imaging|radiology)\b|\bradiology\b|\bimaging (?:centre|department)\b",
        "diagnostic / radiology centre",
    ),
]


def _extract_surface_forms(
    text: str,
    patterns: list[tuple[str, str]],
) -> list[tuple[str, str]]:
    """Return list of (raw_match_text, canonical_label) tuples found in text."""
    found: list[tuple[str, str]] = []
    for pattern, label in patterns:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            found.append((m.group(0).strip().lower(), label))
    return found


def _window_start(referral_date: str) -> str:
    from datetime import date, timedelta

    rd = date.fromisoformat(referral_date[:10])
    return (rd - timedelta(days=LOOKBACK_DAYS)).isoformat()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    client = PatientGraphClient()
    try:
        print("Fetching episodes ...")
        episodes = client.run(Q_EPISODES) or []
        print(f"  Found {len(episodes)} episodes with a referral date")

        all_encounters: list[dict] = []
        seen_pairs: set[tuple[str, str]] = set()

        for ep in episodes:
            patient_id = str(ep["patient_id"])
            referral_date = str(ep["referral_date"])
            cancer_type = str(ep.get("cancer_type") or "unknown")
            key = (patient_id, referral_date)
            if key in seen_pairs:
                continue
            seen_pairs.add(key)

            ws = _window_start(referral_date)
            rows = (
                client.run(
                    Q_ENCOUNTERS,
                    patient_id=patient_id,
                    referral_date=referral_date,
                    window_start=ws,
                )
                or []
            )

            for r in rows:
                all_encounters.append(
                    {
                        "patient_id": patient_id,
                        "episode_id": str(ep["episode_id"]),
                        "cancer_type": cancer_type,
                        "referral_date": referral_date,
                        "window_start": ws,
                        "encounter_id": str(r["encounter_id"]),
                        "encounter_date": str(r["encounter_date"]),
                        "content_type": str(r.get("content_type") or ""),
                        "purpose": str(r.get("purpose") or ""),
                        "text": str(r["text"]),
                    }
                )
    finally:
        client.close()

    print(
        f"  Fetched {len(all_encounters)} pre-referral encounters across {len(seen_pairs)} patient-referral pairs"
    )
    ENCOUNTERS_FILE.write_text(
        json.dumps(all_encounters, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"  Saved -> {ENCOUNTERS_FILE}")

    # -----------------------------------------------------------------------
    # Scan encounter text for candidate surface forms
    # -----------------------------------------------------------------------
    print("\nScanning for candidate surface forms ...")

    # symptom_hits[label] -> Counter of raw surface form text
    symptom_hits: dict[str, Counter] = defaultdict(Counter)
    # place_hits[label] -> Counter of raw surface form text
    place_hits: dict[str, Counter] = defaultdict(Counter)

    # cancer_type breakdown: {label -> {cancer_type -> count}}
    symptom_by_cancer: dict[str, Counter] = defaultdict(Counter)
    place_by_cancer: dict[str, Counter] = defaultdict(Counter)

    for enc in all_encounters:
        text = enc["text"]
        cancer_type = enc["cancer_type"]

        for raw, label in _extract_surface_forms(text, _SYMPTOM_PATTERNS):
            symptom_hits[label][raw] += 1
            symptom_by_cancer[label][cancer_type] += 1

        for raw, label in _extract_surface_forms(text, _PLACE_PATTERNS):
            place_hits[label][raw] += 1
            place_by_cancer[label][cancer_type] += 1

    # Build output structure
    symptom_results = []
    for label, raw_counter in sorted(
        symptom_hits.items(), key=lambda x: -sum(x[1].values())
    ):
        total = sum(raw_counter.values())
        symptom_results.append(
            {
                "category": "symptom",
                "label": label,
                "total_occurrences": total,
                "surface_forms": dict(raw_counter.most_common()),
                "cancer_types": dict(symptom_by_cancer[label].most_common()),
            }
        )

    place_results = []
    for label, raw_counter in sorted(
        place_hits.items(), key=lambda x: -sum(x[1].values())
    ):
        total = sum(raw_counter.values())
        place_results.append(
            {
                "category": "place_of_presentation",
                "label": label,
                "total_occurrences": total,
                "surface_forms": dict(raw_counter.most_common()),
                "cancer_types": dict(place_by_cancer[label].most_common()),
            }
        )

    output = {
        "summary": {
            "episodes_scanned": len(episodes),
            "patient_referral_pairs": len(seen_pairs),
            "encounters_scanned": len(all_encounters),
            "symptom_labels_found": len(symptom_results),
            "place_labels_found": len(place_results),
        },
        "symptoms": symptom_results,
        "places_of_presentation": place_results,
    }

    SURFACE_FORMS_FILE.write_text(
        json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"  Saved -> {SURFACE_FORMS_FILE}")

    # Print summary to stdout
    print("\n=== SYMPTOMS FOUND ===")
    for s in symptom_results:
        print(f"  {s['total_occurrences']:4d}  {s['label']}")
        top_forms = list(s["surface_forms"].items())[:3]
        print(f"         forms: {top_forms}")

    print("\n=== PLACES OF PRESENTATION FOUND ===")
    for p in place_results:
        print(f"  {p['total_occurrences']:4d}  {p['label']}")
        top_forms = list(p["surface_forms"].items())[:3]
        print(f"         forms: {top_forms}")

    print(f"\nDone. Full results in {SURFACE_FORMS_FILE}")


if __name__ == "__main__":
    main()
