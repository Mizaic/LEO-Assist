"""NCDA audit interval section: PCI and DI calculations.

Atlas trace:
  DO: DO-A6D3FE39
  DI: DI-BA2C8F3E
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-A6D3FE39")

Separated from the main section queries because the interval logic uses
its own Cypher fragments (INFERRED_CANCER_DIAG_CASE, FP_DATE_EXPR) that
are also referenced by the summary endpoint.
"""

from __future__ import annotations

from libs.neo4j_client.client import PatientGraphClient
from libs.oncology.cancer_types import normalise_cancer_type

# ---------------------------------------------------------------------------
# Cypher fragments used by intervals + summary
# ---------------------------------------------------------------------------

INFERRED_CANCER_DIAG_CASE = (
    "CASE "
    "  WHEN trim(coalesce(diag_date, '')) <> '' THEN diag_date "
    "  WHEN ep.inferred_outcome = 'cancer' "
    "    AND trim(coalesce(toString(ep.inferred_outcome_date), '')) <> '' "
    "    THEN toString(ep.inferred_outcome_date) "
    "  WHEN ep.status = 'completed' "
    "    AND trim(coalesce(toString(ep.end_date), '')) <> '' "
    "    THEN toString(ep.end_date) "
    "  ELSE null "
    "END"
)

# Use first_presentation_date for PCI when it is present. Episodes without a
# first-presentation anchor should not be counted as 0-day PCI.
FP_DATE_EXPR = (
    "CASE "
    "  WHEN trim(coalesce(toString(ep.first_presentation_date), '')) <> '' "
    "    THEN toString(ep.first_presentation_date) "
    "  ELSE null "
    "END"
)

DI_START_DATE_EXPR = (
    "CASE "
    "  WHEN trim(coalesce(toString(ep.first_presentation_date), '')) <> '' "
    "    THEN toString(ep.first_presentation_date) "
    "  WHEN trim(coalesce(toString(ep.referral_date), '')) <> '' "
    "    THEN toString(ep.referral_date) "
    "  ELSE null "
    "END"
)


# ---------------------------------------------------------------------------
# Intervals
# ---------------------------------------------------------------------------


def _q_intervals(base: str, params: dict, client: PatientGraphClient) -> dict:
    """Primary care interval (PCI) and diagnostic interval (DI).

    Returns server-side aggregate stats (n, mean, median, IQR) plus
    individual patient data points capped at 500 for rendering.
    """
    agg = client.run(
        f"{base}"
        "AND ep.referral_date IS NOT NULL "
        "OPTIONAL MATCH (diag_enc:Encounter)-[dr:IS_PART_OF]->(ep) "
        "  WHERE dr.milestone_type IN ['diagnosis', 'diagnosis_confirmed'] "
        "With ep, min(toString(diag_enc.date)) AS diag_date "
        f"WITH ep, diag_date, {INFERRED_CANCER_DIAG_CASE} AS effective_diag_date, "
        f"{FP_DATE_EXPR} AS fp_date, {DI_START_DATE_EXPR} AS di_start_date "
        "WITH "
        "  CASE WHEN trim(coalesce(fp_date, '')) <> '' "
        "        AND trim(coalesce(toString(ep.referral_date), '')) <> '' "
        "       THEN duration.inDays(date(fp_date), "
        "date(toString(ep.referral_date))).days "
        "       ELSE null END AS raw_pci_days, "
        "  CASE WHEN trim(coalesce(effective_diag_date, '')) <> '' "
        "        AND trim(coalesce(di_start_date, '')) <> '' "
        "       THEN duration.inDays(date(di_start_date), "
        "date(effective_diag_date)).days "
        "       ELSE null END AS raw_di_days "
        "WITH "
        "  CASE WHEN raw_pci_days >= 0 THEN raw_pci_days ELSE null END AS pci_days, "
        "  CASE WHEN raw_di_days >= 0 THEN raw_di_days ELSE null END AS di_days "
        "RETURN "
        "  sum(CASE WHEN pci_days IS NOT NULL THEN 1 ELSE 0 END) AS pci_n, "
        "  avg(pci_days) AS mean_pci, "
        "  percentileCont(pci_days, 0.5) AS median_pci, "
        "  percentileCont(pci_days, 0.25) AS pci_q1, "
        "  percentileCont(pci_days, 0.75) AS pci_q3, "
        "  sum(CASE WHEN di_days IS NOT NULL THEN 1 ELSE 0 END) AS di_n, "
        "  avg(di_days) AS mean_di, "
        "  percentileCont(di_days, 0.5) AS median_di, "
        "  percentileCont(di_days, 0.25) AS di_q1, "
        "  percentileCont(di_days, 0.75) AS di_q3",
        **params,
    )
    pts = client.run(
        f"{base}"
        "AND ep.referral_date IS NOT NULL "
        "OPTIONAL MATCH (diag_enc:Encounter)-[dr:IS_PART_OF]->(ep) "
        "  WHERE dr.milestone_type IN ['diagnosis', 'diagnosis_confirmed'] "
        "With ep, min(toString(diag_enc.date)) AS diag_date "
        f"WITH ep, diag_date, {INFERRED_CANCER_DIAG_CASE} AS effective_diag_date, "
        f"{FP_DATE_EXPR} AS fp_date, {DI_START_DATE_EXPR} AS di_start_date, "
        "  (diag_date IS NULL AND ep.inferred_outcome = 'cancer' "
        "   AND ep.inferred_outcome_date IS NOT NULL) AS diag_is_inferred "
        "WITH ep, diag_is_inferred, fp_date, di_start_date, effective_diag_date, "
        "  CASE WHEN trim(coalesce(fp_date, '')) <> '' "
        "        AND trim(coalesce(toString(ep.referral_date), '')) <> '' "
        "       THEN duration.inDays(date(fp_date), "
        "date(toString(ep.referral_date))).days "
        "       ELSE null END AS raw_pci_days, "
        "  CASE WHEN trim(coalesce(effective_diag_date, '')) <> '' "
        "        AND trim(coalesce(di_start_date, '')) <> '' "
        "       THEN duration.inDays(date(di_start_date), "
        "date(effective_diag_date)).days "
        "       ELSE null END AS raw_di_days "
        "RETURN "
        "  ep.episode_id AS episode_id, ep.cancer_type AS cancer_type, "
        "  diag_is_inferred, "
        "  CASE WHEN raw_pci_days >= 0 THEN raw_pci_days ELSE null END AS pci_days, "
        "  CASE WHEN raw_di_days >= 0 THEN raw_di_days ELSE null END AS di_days "
        "ORDER BY ep.referral_date LIMIT 500",
        **params,
    )

    s = agg[0] if agg else {}

    return {
        "pci": {
            "n": s.get("pci_n"),
            "mean": s.get("mean_pci"),
            "median": s.get("median_pci"),
            "q1": s.get("pci_q1"),
            "q3": s.get("pci_q3"),
        },
        "di": {
            "n": s.get("di_n"),
            "mean": s.get("mean_di"),
            "median": s.get("median_di"),
            "q1": s.get("di_q1"),
            "q3": s.get("di_q3"),
        },
        "patients": [
            {
                "episode_id": r["episode_id"],
                "cancer_type": normalise_cancer_type(r.get("cancer_type")),
                "pci_days": r.get("pci_days"),
                "di_days": r.get("di_days"),
                "diag_is_inferred": r.get("diag_is_inferred"),
            }
            for r in pts
        ],
    }
