from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from libs.keyvault.loader import load_keyvault_secrets
from libs.neo4j_client.client import PatientGraphClient

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
load_keyvault_secrets()

Q = """
MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare)
WHERE ep.referral_date IS NOT NULL
  AND NOT ep.status IN ['merged', 'closed_phantom', 'closed_related']
  AND EXISTS {
    MATCH (:Encounter)-[rr:IS_PART_OF]->(ep)
    WHERE rr.milestone_type = 'referral'
  }
OPTIONAL MATCH (diag_enc:Encounter)-[dr:IS_PART_OF]->(ep)
  WHERE dr.milestone_type IN ['diagnosis', 'diagnosis_confirmed']
OPTIONAL MATCH (treat_enc:Encounter)-[tr:IS_PART_OF]->(ep)
  WHERE tr.milestone_type IN ['treatment', 'treatment_started', 'first_treatment']
WITH ep, min(toString(diag_enc.date)) AS diag_date, min(toString(treat_enc.date)) AS treat_date
WITH ep, treat_date,
  CASE
    WHEN diag_date IS NOT NULL THEN diag_date
    WHEN ep.inferred_outcome = 'cancer' AND ep.inferred_outcome_date IS NOT NULL THEN ep.inferred_outcome_date
    WHEN ep.status = 'completed' AND ep.end_date IS NOT NULL THEN toString(ep.end_date)
    ELSE null
  END AS effective_diag_date
WITH ep, treat_date, effective_diag_date,
  CASE
    WHEN ep.first_presentation_date IS NOT NULL
     AND trim(coalesce(ep.presenting_complaint, '')) <> ''
    THEN duration.inDays(date(ep.first_presentation_date), date(toString(ep.referral_date))).days
    ELSE null
  END AS d_ref,
  CASE
    WHEN effective_diag_date IS NOT NULL
    THEN duration.inDays(date(toString(ep.referral_date)), date(effective_diag_date)).days
    ELSE null
  END AS d_diag,
  CASE
    WHEN effective_diag_date IS NOT NULL AND treat_date IS NOT NULL AND treat_date >= effective_diag_date
    THEN duration.inDays(date(effective_diag_date), date(treat_date)).days
    ELSE null
  END AS d_treat
RETURN
  count(ep) AS pathways_total,
  sum(CASE WHEN d_ref IS NOT NULL AND d_ref >= 0 THEN 1 ELSE 0 END) AS n_ref,
  avg(CASE WHEN d_ref IS NOT NULL AND d_ref >= 0 THEN d_ref ELSE null END) AS avg_ref,
  percentileCont(CASE WHEN d_ref IS NOT NULL AND d_ref >= 0 THEN d_ref ELSE null END, 0.5) AS med_ref,
  sum(CASE WHEN d_diag IS NOT NULL AND d_diag >= 0 THEN 1 ELSE 0 END) AS n_diag,
  avg(CASE WHEN d_diag IS NOT NULL AND d_diag >= 0 THEN d_diag ELSE null END) AS avg_diag,
  percentileCont(CASE WHEN d_diag IS NOT NULL AND d_diag >= 0 THEN d_diag ELSE null END, 0.5) AS med_diag,
  sum(CASE WHEN d_treat IS NOT NULL AND d_treat >= 0 THEN 1 ELSE 0 END) AS n_treat,
  avg(CASE WHEN d_treat IS NOT NULL AND d_treat >= 0 THEN d_treat ELSE null END) AS avg_treat,
  percentileCont(CASE WHEN d_treat IS NOT NULL AND d_treat >= 0 THEN d_treat ELSE null END, 0.5) AS med_treat
"""

Q_REASON_BREAKDOWN = """
MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare)
WHERE ep.referral_date IS NOT NULL
  AND NOT ep.status IN ['merged', 'closed_phantom', 'closed_related']
  AND EXISTS {
    MATCH (:Encounter)-[rr:IS_PART_OF]->(ep)
    WHERE rr.milestone_type = 'referral'
  }
WITH ep,
  CASE
    WHEN ep.first_presentation_date IS NULL THEN 'missing_first_presentation_date'
    WHEN trim(coalesce(ep.presenting_complaint, '')) = '' THEN 'missing_presenting_complaint'
    WHEN duration.inDays(date(ep.first_presentation_date), date(toString(ep.referral_date))).days < 0 THEN 'negative_interval'
    WHEN duration.inDays(date(ep.first_presentation_date), date(toString(ep.referral_date))).days > 14 THEN 'over_14_days'
    ELSE 'eligible'
  END AS bucket
RETURN bucket, count(*) AS n
ORDER BY n DESC
"""


def main() -> None:
    c = PatientGraphClient()
    try:
        row = (c.run(Q) or [{}])[0]
        reasons = c.run(Q_REASON_BREAKDOWN) or []
        dist = c.run(
            "MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
            "WHERE ep.referral_date IS NOT NULL "
            "  AND NOT ep.status IN ['merged', 'closed_phantom', 'closed_related'] "
            "  AND EXISTS { MATCH (:Encounter)-[rr:IS_PART_OF]->(ep) WHERE rr.milestone_type = 'referral' } "
            "  AND ep.first_presentation_date IS NOT NULL "
            "  AND trim(coalesce(ep.presenting_complaint, '')) <> '' "
            "WITH duration.inDays(date(ep.first_presentation_date), date(toString(ep.referral_date))).days AS d "
            "WHERE d >= 0 "
            "RETURN d AS days, count(*) AS n ORDER BY d"
        ) or []
        long_rows = c.run(
            "MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
            "WHERE ep.referral_date IS NOT NULL "
            "  AND NOT ep.status IN ['merged', 'closed_phantom', 'closed_related'] "
            "  AND EXISTS { MATCH (:Encounter)-[rr:IS_PART_OF]->(ep) WHERE rr.milestone_type = 'referral' } "
            "  AND ep.first_presentation_date IS NOT NULL "
            "  AND trim(coalesce(ep.presenting_complaint, '')) <> '' "
            "WITH ep, duration.inDays(date(ep.first_presentation_date), date(toString(ep.referral_date))).days AS d "
            "WHERE d > 14 "
            "RETURN ep.episode_id AS episode_id, ep.patient_id AS patient_id, ep.cancer_type AS cancer_type, "
            "       ep.first_presentation_date AS fp, ep.referral_date AS ref, d AS days, "
            "       ep.presenting_complaint AS complaint "
            "ORDER BY days DESC LIMIT 20"
        ) or []
    finally:
        c.close()
    print(row)
    print("reason_breakdown:")
    for r in reasons:
        print(r)
    print("distribution:")
    for r in dist:
        print(r)
    print("over_14_examples:")
    for r in long_rows:
        print(r)


if __name__ == "__main__":
    main()

