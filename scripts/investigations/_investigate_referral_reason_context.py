from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from libs.keyvault.loader import load_keyvault_secrets
from libs.neo4j_client.client import PatientGraphClient

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
load_keyvault_secrets()

OUT = (
    ROOT
    / "scripts"
    / "investigations"
    / "output"
    / "missing_fp_referral_reason_context.json"
)

Q_EXCLUDED = """
MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare)
WHERE ep.referral_date IS NOT NULL
  AND ep.first_presentation_date IS NULL
  AND NOT ep.status IN ['merged', 'closed_phantom', 'closed_related']
  AND EXISTS {
    MATCH (:Encounter)-[rr:IS_PART_OF]->(ep)
    WHERE rr.milestone_type = 'referral'
  }
RETURN
  toString(p.id) AS patient_id,
  ep.episode_id AS episode_id,
  ep.cancer_type AS cancer_type,
  toString(ep.referral_date) AS referral_date
ORDER BY referral_date
"""

Q_WINDOW = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(p.id) = $pid
  AND toString(e.date) >= $start_date
  AND toString(e.date) <= $end_date
OPTIONAL MATCH (e)-[r:DOCUMENTS]->(c)
RETURN
  toString(e.id) AS encounter_id,
  toString(e.date) AS encounter_date,
  coalesce(e.text, '') AS text,
  collect(
    DISTINCT {
      concept_id: toString(c.conceptId),
      concept_name: c.name,
      semantic_tag: coalesce(c.semanticTag, ''),
      assertion: coalesce(r.assertion, 'present')
    }
  ) AS docs
ORDER BY encounter_date
"""

_SYMPTOM_TERM_RE = re.compile(
    r"\b("
    r"pain|bleed|bleeding|lump|mass|weight loss|fatigue|tired|"
    r"anaemi|anemi|haematuria|hematuria|dysphagia|night sweat|cough|"
    r"bowel|change in bowel|hoarseness|jaundice|vomit|nausea|"
    r"breast|skin lesion|mole|headache|seizure"
    r")\b",
    re.IGNORECASE,
)
_INVESTIGATION_TERM_RE = re.compile(
    r"\b("
    r"test|scan|ct|mri|ultrasound|xray|x-ray|biopsy|histology|"
    r"colonoscopy|gastroscopy|endoscopy|fit test|fbc|blood test|"
    r"psa|cea|ca125|imaging|investigation"
    r")\b",
    re.IGNORECASE,
)
_REFERRAL_TERM_RE = re.compile(
    r"\b("
    r"2ww|two week wait|fast track|urgent referral|suspected cancer referral|"
    r"cancer referral|referred to"
    r")\b",
    re.IGNORECASE,
)
_EXCLUDE_NAME_RE = re.compile(
    r"\b(seen in|consultation|appointment|clinic|service|general practitioner surgery)\b",
    re.IGNORECASE,
)


def _parse_day(raw: str) -> date | None:
    try:
        return date.fromisoformat(str(raw)[:10])
    except Exception:
        return None


def _is_present(doc: dict[str, Any]) -> bool:
    return str(doc.get("assertion") or "present").lower() in ("", "present")


def _symptom_from_doc(doc: dict[str, Any]) -> bool:
    if not _is_present(doc):
        return False
    name = str(doc.get("concept_name") or "")
    if not name or _EXCLUDE_NAME_RE.search(name):
        return False
    tag = str(doc.get("semantic_tag") or "").lower().replace("_", " ")
    if tag in {
        "procedure",
        "environment",
        "place",
        "physical_object",
        "record artifact",
    }:
        return False
    return bool(_SYMPTOM_TERM_RE.search(name))


def _investigation_from_doc(doc: dict[str, Any]) -> bool:
    if not _is_present(doc):
        return False
    name = str(doc.get("concept_name") or "")
    return bool(name and _INVESTIGATION_TERM_RE.search(name))


def _extract_text_clues(text: str) -> dict[str, list[str]]:
    s = text or ""
    sympt = sorted({m.group(0).lower() for m in _SYMPTOM_TERM_RE.finditer(s)})
    inv = sorted({m.group(0).lower() for m in _INVESTIGATION_TERM_RE.finditer(s)})
    ref = sorted({m.group(0).lower() for m in _REFERRAL_TERM_RE.finditer(s)})
    return {"symptom_terms": sympt, "investigation_terms": inv, "referral_terms": ref}


def main() -> None:
    pc = PatientGraphClient()
    try:
        eps = pc.run(Q_EXCLUDED) or []
        summary = Counter()
        top_symptom = Counter()
        top_investigation = Counter()
        top_referral_phrase = Counter()
        episodes = []

        for i, ep in enumerate(eps, 1):
            pid = str(ep["patient_id"])
            ref_day = _parse_day(ep["referral_date"])
            if not ref_day:
                continue
            start = (ref_day - timedelta(days=21)).isoformat()
            end = (ref_day + timedelta(days=3)).isoformat()
            rows = (
                pc.run(
                    Q_WINDOW,
                    pid=pid,
                    start_date=start,
                    end_date=end,
                )
                or []
            )

            symptom_hits: list[str] = []
            inv_hits: list[str] = []
            ref_hits: list[str] = []
            by_day: dict[str, dict[str, Any]] = {}
            for r in rows:
                day = str(r.get("encounter_date") or "")
                docs = [d for d in (r.get("docs") or []) if d.get("concept_id")]
                clues = _extract_text_clues(str(r.get("text") or ""))
                doc_symptoms = [
                    str(d.get("concept_name") or "")
                    for d in docs
                    if _symptom_from_doc(d)
                ]
                doc_investigations = [
                    str(d.get("concept_name") or "")
                    for d in docs
                    if _investigation_from_doc(d)
                ]
                symptom_hits.extend(doc_symptoms + clues["symptom_terms"])
                inv_hits.extend(doc_investigations + clues["investigation_terms"])
                ref_hits.extend(clues["referral_terms"])
                by_day.setdefault(
                    day,
                    {
                        "encounters": 0,
                        "doc_symptoms": set(),
                        "doc_investigations": set(),
                        "text_symptom_terms": set(),
                        "text_investigation_terms": set(),
                        "text_referral_terms": set(),
                    },
                )
                by_day[day]["encounters"] += 1
                by_day[day]["doc_symptoms"].update(doc_symptoms)
                by_day[day]["doc_investigations"].update(doc_investigations)
                by_day[day]["text_symptom_terms"].update(clues["symptom_terms"])
                by_day[day]["text_investigation_terms"].update(
                    clues["investigation_terms"]
                )
                by_day[day]["text_referral_terms"].update(clues["referral_terms"])

            has_symptom = bool(symptom_hits)
            has_investigation = bool(inv_hits)
            has_referral_phrase = bool(ref_hits)
            if has_symptom:
                cls = "symptom_evidence_near_referral"
            elif has_investigation:
                cls = "investigation_only_near_referral"
            elif has_referral_phrase:
                cls = "referral_phrase_only_near_referral"
            else:
                cls = "no_clear_reason_in_window"

            summary[cls] += 1
            for x in symptom_hits:
                top_symptom[x] += 1
            for x in inv_hits:
                top_investigation[x] += 1
            for x in ref_hits:
                top_referral_phrase[x] += 1

            episodes.append(
                {
                    "patient_id": pid,
                    "episode_id": ep["episode_id"],
                    "cancer_type": ep.get("cancer_type"),
                    "referral_date": ep["referral_date"],
                    "classification": cls,
                    "days_scanned": {"from": start, "to": end},
                    "window_day_summary": {
                        d: {
                            "encounters": v["encounters"],
                            "doc_symptoms": sorted(v["doc_symptoms"]),
                            "doc_investigations": sorted(v["doc_investigations"]),
                            "text_symptom_terms": sorted(v["text_symptom_terms"]),
                            "text_investigation_terms": sorted(
                                v["text_investigation_terms"]
                            ),
                            "text_referral_terms": sorted(v["text_referral_terms"]),
                        }
                        for d, v in sorted(by_day.items())
                    },
                }
            )
            if i % 20 == 0:
                print(f"processed {i}/{len(eps)}")

        out = {
            "excluded_count": len(eps),
            "classification_counts": dict(summary),
            "top_symptom_clues": top_symptom.most_common(40),
            "top_investigation_clues": top_investigation.most_common(40),
            "top_referral_phrases": top_referral_phrase.most_common(20),
            "episodes": episodes,
        }
        OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
        print(
            json.dumps(
                {"excluded_count": len(eps), "classification_counts": dict(summary)},
                indent=2,
            )
        )
        print(f"wrote: {OUT}")
    finally:
        pc.close()


if __name__ == "__main__":
    main()
