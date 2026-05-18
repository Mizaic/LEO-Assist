#!/usr/bin/env python3
"""Build blood feature vectors and run GDS-based cancer signal analysis.

Computes per-test z-scores for each episode/patient in the study across a
window of 12 months before referral + 28 days after. For each patient and
each test, only the single most-recent result in the window is used (not an
average). Stores results on EpisodeOfCare nodes (cancer + benign episodes)
and BloodPanel nodes (no-episode FTR patients). Then runs GDS kNN and
computes Pearson correlations (feature importance). Also performs Python-side
k-means clustering and writes cluster assignments back.

Cohort:
  cancer -- EpisodeOfCare with diagnosis_confirmed milestone, bf_label=1
  benign -- EpisodeOfCare with status=closed_benign,           bf_label=0
  benign -- BloodPanel (no EpisodeOfCare, has FTR encounter),  bf_label=0

Window: referral_date - 12 months to referral_date + 28 days

Usage:
  # Dry run -- shows what would be written:
  python scripts/gds/build_blood_feature_vectors.py

  # Apply -- writes to Neo4j and runs GDS:
  python scripts/gds/build_blood_feature_vectors.py --apply

  # Apply with custom k-means clusters:
  python scripts/gds/build_blood_feature_vectors.py --apply --k 4
"""

from __future__ import annotations

import argparse
import os
import random
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402
from neo4j import GraphDatabase  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env.secrets", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

# ---------------------------------------------------------------------------
# Blood test features: property_key -> SNOMED concept name (Observable_entity)
# All clinically relevant coded blood tests with >=2 episode coverage.
# Vitals (BP, HR, O2 sat, weight) and single-episode specialist assays excluded.
# ---------------------------------------------------------------------------

BLOOD_FEATURES: dict[str, str] = {
    # Full blood count
    "bf_lymphocyte_z":     "Lymphocyte count",
    "bf_nucleated_rbc_z":  "Nucleated red blood cell count",
    "bf_neutrophil_pct_z": "Neutrophil percent count in blood",
    "bf_mcv_z":            "Mean corpuscular volume",
    "bf_mch_z":            "Mean corpuscular haemoglobin",
    "bf_haemoglobin_z":    "Mass concentration of haemoglobin in blood (observable entity)",
    "bf_monocyte_z":       "Monocyte count",
    "bf_rbc_z":            "Red blood cell count",
    "bf_platelet_z":       "Platelet count",
    # Biochemistry / metabolic
    "bf_alp_z":            "Serum alkaline phosphatase placental enzyme level",
    "bf_albumin_z":        "Serum albumin level",
    "bf_bilirubin_z":      "Serum bilirubin level",
    "bf_phosphate_z":      "Serum inorganic phosphate level",
    "bf_sodium_z":         "Serum sodium level (observable entity)",
    "bf_total_protein_z":  "Serum total protein",
    "bf_calcium_z":        "Serum calcium level (observable entity)",
    # Endocrine / metabolic markers
    "bf_hba1c_z":          "Haemoglobin A1c level (observable entity)",
    "bf_folate_z":         "Serum folate level (observable entity)",
    # Lipids
    "bf_ldl_z":            "Serum random low density lipoprotein cholesterol level",
    "bf_hdl_z":            "Serum random high density lipoprotein cholesterol level (obs",
    "bf_total_chol_z":     "Total cholesterol level (observable entity)",
}

FEATURE_KEYS: list[str] = list(BLOOD_FEATURES.keys())

FEATURE_LABELS: dict[str, str] = {
    "bf_lymphocyte_z":     "Lymphocyte",
    "bf_nucleated_rbc_z":  "Nucleated RBC",
    "bf_neutrophil_pct_z": "Neutrophil %",
    "bf_mcv_z":            "MCV",
    "bf_mch_z":            "MCH",
    "bf_haemoglobin_z":    "Haemoglobin",
    "bf_monocyte_z":       "Monocyte",
    "bf_rbc_z":            "RBC",
    "bf_platelet_z":       "Platelets",
    "bf_alp_z":            "ALP",
    "bf_albumin_z":        "Albumin",
    "bf_bilirubin_z":      "Bilirubin",
    "bf_phosphate_z":      "Phosphate",
    "bf_sodium_z":         "Sodium",
    "bf_total_protein_z":  "Total Protein",
    "bf_calcium_z":        "Calcium",
    "bf_hba1c_z":          "HbA1c",
    "bf_folate_z":         "Folate",
    "bf_ldl_z":            "LDL Chol",
    "bf_hdl_z":            "HDL Chol",
    "bf_total_chol_z":     "Total Chol",
}

GDS_GRAPH_KNN = "blood-signal-knn"

# ---------------------------------------------------------------------------
# Cypher
# ---------------------------------------------------------------------------

_GLOBAL_STATS_Q = """
MATCH (enc:Encounter)-[d:DOCUMENTS]->(obs:Observable_entity)
WHERE obs.name = $test_name
  AND d.value IS NOT NULL
  AND trim(toString(d.value)) <> ''
WITH toFloat(toString(d.value)) AS v
WHERE v IS NOT NULL
RETURN avg(v) AS mean_val, stDev(v) AS std_val, count(v) AS n
"""

_EPISODE_TEST_VALUES_Q = """
MATCH (p:Patient {id: $patient_id})-[:HAS_ENCOUNTER]->(enc:Encounter)-[d:DOCUMENTS]->(obs:Observable_entity)
WHERE obs.name = $test_name
  AND d.value IS NOT NULL AND trim(toString(d.value)) <> ''
  AND toFloat(toString(d.value)) IS NOT NULL
  AND date(enc.date) >= date($anchor_date) - duration({years: 1})
  AND date(enc.date) <= date($anchor_date) + duration({days: 28})
WITH toFloat(toString(d.value)) AS v, enc.date AS enc_date
WHERE v IS NOT NULL
ORDER BY enc_date DESC
RETURN head(collect(v)) AS latest_val, count(v) AS n
"""

_CANCER_EPISODES_Q = """
MATCH (diag_enc:Encounter)-[ipo:IS_PART_OF]->(ep:EpisodeOfCare)
WHERE ipo.milestone_type = 'diagnosis_confirmed'
  AND ep.referral_date IS NOT NULL
  AND trim(toString(ep.referral_date)) <> ''
MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep)
RETURN ep.episode_id AS episode_id,
       ep.cancer_type AS cancer_type,
       toString(ep.referral_date) AS referral_date,
       p.id AS patient_id
"""

_BENIGN_EPISODES_Q = """
MATCH (ep:EpisodeOfCare)
WHERE ep.status = 'closed_benign'
  AND ep.referral_date IS NOT NULL
  AND trim(toString(ep.referral_date)) <> ''
MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep)
RETURN ep.episode_id AS episode_id,
       ep.cancer_type AS cancer_type,
       toString(ep.referral_date) AS referral_date,
       p.id AS patient_id
"""

# No-episode patients: has FTR concept but no EpisodeOfCare
_NO_EPISODE_PATIENTS_Q = """
MATCH (p:Patient)
WHERE NOT EXISTS { MATCH (p)-[:HAS_EPISODE_OF_CARE]->(:EpisodeOfCare) }
MATCH (p)-[:HAS_ENCOUNTER]->(enc:Encounter)-[:DOCUMENTS]->(c)
WHERE c.name CONTAINS 'fast track' OR c.name CONTAINS 'Fast track'
   OR toLower(c.name) CONTAINS 'suspected'
WITH p, min(enc.date) AS anchor_date
WHERE anchor_date IS NOT NULL
RETURN p.id AS patient_id, toString(anchor_date) AS anchor_date
"""

_WRITE_EPISODE_FEATURES_Q = """
UNWIND $rows AS row
MATCH (ep:EpisodeOfCare {episode_id: row.episode_id})
SET ep.bf_cohort_label     = row.cohort_label,
    ep.bf_label            = row.bf_label,
    ep.bf_anchor_date      = row.anchor_date,
    ep.bf_cancer_type      = row.cancer_type,
    ep.bf_lymphocyte_z     = row.bf_lymphocyte_z,
    ep.bf_nucleated_rbc_z  = row.bf_nucleated_rbc_z,
    ep.bf_neutrophil_pct_z = row.bf_neutrophil_pct_z,
    ep.bf_mcv_z            = row.bf_mcv_z,
    ep.bf_mch_z            = row.bf_mch_z,
    ep.bf_haemoglobin_z    = row.bf_haemoglobin_z,
    ep.bf_monocyte_z       = row.bf_monocyte_z,
    ep.bf_rbc_z            = row.bf_rbc_z,
    ep.bf_platelet_z       = row.bf_platelet_z,
    ep.bf_alp_z            = row.bf_alp_z,
    ep.bf_albumin_z        = row.bf_albumin_z,
    ep.bf_bilirubin_z      = row.bf_bilirubin_z,
    ep.bf_phosphate_z      = row.bf_phosphate_z,
    ep.bf_sodium_z         = row.bf_sodium_z,
    ep.bf_total_protein_z  = row.bf_total_protein_z,
    ep.bf_calcium_z        = row.bf_calcium_z,
    ep.bf_hba1c_z          = row.bf_hba1c_z,
    ep.bf_folate_z         = row.bf_folate_z,
    ep.bf_ldl_z            = row.bf_ldl_z,
    ep.bf_hdl_z            = row.bf_hdl_z,
    ep.bf_total_chol_z     = row.bf_total_chol_z,
    ep.bf_features_vec     = row.bf_features_vec,
    ep.bf_updated_at       = datetime()
"""

_WRITE_BLOOD_PANEL_Q = """
UNWIND $rows AS row
MERGE (bp:BloodPanel {patient_id: row.patient_id})
SET bp.bf_cohort_label     = row.cohort_label,
    bp.bf_label            = row.bf_label,
    bp.bf_anchor_date      = row.anchor_date,
    bp.bf_cancer_type      = row.cancer_type,
    bp.bf_lymphocyte_z     = row.bf_lymphocyte_z,
    bp.bf_nucleated_rbc_z  = row.bf_nucleated_rbc_z,
    bp.bf_neutrophil_pct_z = row.bf_neutrophil_pct_z,
    bp.bf_mcv_z            = row.bf_mcv_z,
    bp.bf_mch_z            = row.bf_mch_z,
    bp.bf_haemoglobin_z    = row.bf_haemoglobin_z,
    bp.bf_monocyte_z       = row.bf_monocyte_z,
    bp.bf_rbc_z            = row.bf_rbc_z,
    bp.bf_platelet_z       = row.bf_platelet_z,
    bp.bf_alp_z            = row.bf_alp_z,
    bp.bf_albumin_z        = row.bf_albumin_z,
    bp.bf_bilirubin_z      = row.bf_bilirubin_z,
    bp.bf_phosphate_z      = row.bf_phosphate_z,
    bp.bf_sodium_z         = row.bf_sodium_z,
    bp.bf_total_protein_z  = row.bf_total_protein_z,
    bp.bf_calcium_z        = row.bf_calcium_z,
    bp.bf_hba1c_z          = row.bf_hba1c_z,
    bp.bf_folate_z         = row.bf_folate_z,
    bp.bf_ldl_z            = row.bf_ldl_z,
    bp.bf_hdl_z            = row.bf_hdl_z,
    bp.bf_total_chol_z     = row.bf_total_chol_z,
    bp.bf_features_vec     = row.bf_features_vec,
    bp.bf_updated_at       = datetime()
"""

_WRITE_CLUSTER_LABELS_EP_Q = """
UNWIND $rows AS row
MATCH (ep:EpisodeOfCare {episode_id: row.node_id})
SET ep.bf_cluster = row.cluster
"""

_WRITE_CLUSTER_LABELS_BP_Q = """
UNWIND $rows AS row
MATCH (bp:BloodPanel {patient_id: row.node_id})
SET bp.bf_cluster = row.cluster
"""

# Pearson correlation (feature importance) via GDS similarity function
_PEARSON_CORR_Q = """
MATCH (n)
WHERE (n:EpisodeOfCare OR n:BloodPanel)
  AND n.bf_label IS NOT NULL
WITH collect(toFloat(n.bf_label)) AS labels,
     collect(coalesce(n.{prop}, 0.0)) AS vals
RETURN gds.similarity.pearson(labels, vals) AS r
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _connect():
    return GraphDatabase.driver(
        os.environ["NEO4J_URI"],
        auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
    )


def _get_global_stats(session, test_name: str) -> tuple[float, float]:
    row = session.run(_GLOBAL_STATS_Q, test_name=test_name).single()
    if not row or row["n"] == 0:
        return 0.0, 1.0
    mean = float(row["mean_val"] or 0.0)
    std = float(row["std_val"] or 1.0) or 1.0
    return mean, std


def _get_patient_test_latest(
    session, patient_id: str, anchor_date: str, test_name: str
) -> float | None:
    """Return the single most-recent result for this test in the 12-month window."""
    row = session.run(
        _EPISODE_TEST_VALUES_Q,
        patient_id=patient_id,
        test_name=test_name,
        anchor_date=anchor_date,
    ).single()
    if not row or row["n"] == 0:
        return None
    return float(row["latest_val"])


def _build_feature_row(
    session,
    patient_id: str,
    anchor_date: str,
    global_stats: dict[str, tuple[float, float]],
    cohort_label: str,
    bf_label: int,
    cancer_type: str | None,
    episode_id: str | None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "episode_id": episode_id,
        "patient_id": patient_id,
        "cohort_label": cohort_label,
        "bf_label": bf_label,
        "anchor_date": anchor_date,
        "cancer_type": cancer_type or "",
    }
    features_vec: list[float] = []
    for prop_key, test_name in BLOOD_FEATURES.items():
        mean, std = global_stats[prop_key]
        raw = _get_patient_test_latest(session, patient_id, anchor_date, test_name)
        z = round((raw - mean) / std, 4) if raw is not None else 0.0
        row[prop_key] = z
        features_vec.append(z)
    row["bf_features_vec"] = features_vec
    return row


def _simple_kmeans(
    vectors: list[list[float]], k: int, n_iter: int = 30, seed: int = 42
) -> list[int]:
    """K-means clustering without external libraries."""
    random.seed(seed)
    n = len(vectors)
    if n == 0:
        return []
    d = len(vectors[0])
    indices = list(range(n))
    random.shuffle(indices)
    centroids = [list(vectors[i]) for i in indices[:k]]
    labels = [0] * n

    for _ in range(n_iter):
        new_labels = []
        for v in vectors:
            dists = [
                sum((v[j] - c[j]) ** 2 for j in range(d)) for c in centroids
            ]
            new_labels.append(dists.index(min(dists)))
        if new_labels == labels:
            break
        labels = new_labels
        for ci in range(k):
            members = [vectors[i] for i, lbl in enumerate(labels) if lbl == ci]
            if members:
                centroids[ci] = [
                    sum(m[j] for m in members) / len(members) for j in range(d)
                ]

    return labels


def _run_gds_knn(session) -> dict[str, Any]:
    """Project a GDS graph for kNN and run kNN similarity."""
    print("\n--- GDS kNN Phase ---")

    # Drop existing projection
    session.run(f"CALL gds.graph.drop('{GDS_GRAPH_KNN}', false)")

    # Build property map string for projection.
    # Cypher property map keys use backtick-quoting (not double quotes).
    prop_entries = ", ".join(
        f"`{k}`: {{defaultValue: 0.0}}" for k in FEATURE_KEYS
    )
    prop_map = "{" + prop_entries + ", `bf_label`: {defaultValue: 0}}"

    project_q = f"""
    CALL gds.graph.project(
      '{GDS_GRAPH_KNN}',
      {{
        EpisodeOfCare: {{ properties: {prop_map} }},
        BloodPanel:    {{ properties: {prop_map} }}
      }},
      '*'
    )
    YIELD graphName, nodeCount, relationshipCount
    RETURN graphName, nodeCount, relationshipCount
    """
    proj_row = session.run(project_q).single()
    print(f"  Projected: {dict(proj_row) if proj_row else 'n/a'}")

    # Build kNN node properties map (Euclidean distance on all features).
    # Keys are backtick-quoted Cypher identifiers.
    knn_props = "{" + ", ".join(f'`{k}`: "EUCLIDEAN"' for k in FEATURE_KEYS) + "}"

    knn_q = f"""
    CALL gds.knn.write('{GDS_GRAPH_KNN}', {{
      nodeLabels: ['EpisodeOfCare', 'BloodPanel'],
      nodeProperties: {knn_props},
      topK: 5,
      writeRelationshipType: 'BLOOD_SIMILAR',
      writeProperty: 'score',
      randomSeed: 42,
      concurrency: 1
    }})
    YIELD nodesCompared, relationshipsWritten
    RETURN nodesCompared, relationshipsWritten
    """
    knn_row = session.run(knn_q).single()
    result = dict(knn_row) if knn_row else {}
    print(f"  kNN complete: {result}")
    return result


def _compute_pearson_correlations(session) -> dict[str, float]:
    """Compute Pearson r between each feature z-score and the cancer label."""
    print("\n--- Feature Importance (Pearson r) ---")
    correlations: dict[str, float] = {}
    for prop_key in FEATURE_KEYS:
        q = f"""
        MATCH (n)
        WHERE (n:EpisodeOfCare OR n:BloodPanel)
          AND n.bf_label IS NOT NULL
        WITH collect(toFloat(n.bf_label)) AS labels,
             collect(coalesce(n.{prop_key}, 0.0)) AS vals
        RETURN gds.similarity.pearson(labels, vals) AS r
        """
        row = session.run(q).single()
        r = float(row["r"]) if row and row["r"] is not None else 0.0
        correlations[prop_key] = round(r, 4)
        label = FEATURE_LABELS[prop_key]
        print(f"  {label:<20} r = {r:+.4f}")
    return correlations


def _write_correlations(session, correlations: dict[str, float]) -> None:
    """Store feature correlations as a singleton AnalysisResult node."""
    import json
    session.run(
        """
        MERGE (ar:BloodSignalAnalysis {name: 'blood_signal_v1'})
        SET ar.feature_correlations_json = $json,
            ar.feature_keys = $keys,
            ar.feature_labels_json = $labels_json,
            ar.updated_at = datetime()
        """,
        json=json.dumps(correlations),
        keys=list(correlations.keys()),
        labels_json=json.dumps(FEATURE_LABELS),
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", default=False,
        help="Write feature vectors and run GDS. Without this, dry-run only.",
    )
    parser.add_argument(
        "--k", type=int, default=3,
        help="Number of k-means clusters (default: 3).",
    )
    args = parser.parse_args(argv)

    driver = _connect()

    with driver.session() as session:

        # ------------------------------------------------------------------
        # Phase 1: Global population statistics per test
        # ------------------------------------------------------------------
        print("Phase 1: Global population statistics...")
        global_stats: dict[str, tuple[float, float]] = {}
        for prop_key, test_name in BLOOD_FEATURES.items():
            mean, std = _get_global_stats(session, test_name)
            global_stats[prop_key] = (mean, std)
            print(f"  {FEATURE_LABELS[prop_key]:<20} mean={mean:.3f} std={std:.3f}")

        # ------------------------------------------------------------------
        # Phase 2: Cancer episodes (diagnosis_confirmed milestone)
        # ------------------------------------------------------------------
        print("\nPhase 2: Cancer episodes...")
        cancer_ep_rows = list(session.run(_CANCER_EPISODES_Q))
        print(f"  {len(cancer_ep_rows)} cancer episodes found")

        cancer_feature_rows: list[dict[str, Any]] = []
        for r in cancer_ep_rows:
            feat = _build_feature_row(
                session,
                patient_id=str(r["patient_id"]),
                anchor_date=str(r["referral_date"]),
                global_stats=global_stats,
                cohort_label="cancer",
                bf_label=1,
                cancer_type=r.get("cancer_type"),
                episode_id=r["episode_id"],
            )
            cancer_feature_rows.append(feat)
            non_zero = sum(1 for k in FEATURE_KEYS if abs(feat[k]) > 0.0)
            print(
                f"  {str(r['episode_id'])[:24]:<24} {str(r.get('cancer_type','?')):<15}"
                f"  {non_zero}/{len(FEATURE_KEYS)} tests"
            )

        # ------------------------------------------------------------------
        # Phase 3: Benign episodes (closed_benign)
        # ------------------------------------------------------------------
        print("\nPhase 3: Benign episodes (closed_benign)...")
        benign_ep_rows = list(session.run(_BENIGN_EPISODES_Q))
        print(f"  {len(benign_ep_rows)} benign episodes found")

        benign_feature_rows: list[dict[str, Any]] = []
        for r in benign_ep_rows:
            feat = _build_feature_row(
                session,
                patient_id=str(r["patient_id"]),
                anchor_date=str(r["referral_date"]),
                global_stats=global_stats,
                cohort_label="benign",
                bf_label=0,
                cancer_type=None,
                episode_id=r["episode_id"],
            )
            benign_feature_rows.append(feat)

        # ------------------------------------------------------------------
        # Phase 4: No-episode FTR patients (BloodPanel nodes)
        # ------------------------------------------------------------------
        print("\nPhase 4: No-episode FTR patients...")
        no_ep_rows = list(session.run(_NO_EPISODE_PATIENTS_Q))
        print(f"  {len(no_ep_rows)} no-episode FTR patients found")

        panel_feature_rows: list[dict[str, Any]] = []
        for r in no_ep_rows:
            feat = _build_feature_row(
                session,
                patient_id=str(r["patient_id"]),
                anchor_date=str(r["anchor_date"]),
                global_stats=global_stats,
                cohort_label="benign",
                bf_label=0,
                cancer_type=None,
                episode_id=None,
            )
            panel_feature_rows.append(feat)

        # ------------------------------------------------------------------
        # Phase 5: Python-side k-means clustering
        # ------------------------------------------------------------------
        all_rows = cancer_feature_rows + benign_feature_rows + panel_feature_rows
        print(f"\nPhase 5: K-means clustering (k={args.k})...")
        print(f"  Total nodes: {len(all_rows)}")

        vectors = [r["bf_features_vec"] for r in all_rows]
        cluster_labels = _simple_kmeans(vectors, k=args.k) if vectors else []

        # Attach cluster to each row
        for i, row in enumerate(all_rows):
            row["bf_cluster"] = cluster_labels[i] if i < len(cluster_labels) else 0

        # Count per cluster
        from collections import Counter
        cluster_counts = Counter(cluster_labels)
        for ci, cnt in sorted(cluster_counts.items()):
            print(f"  Cluster {ci}: {cnt} nodes")

        print(f"\nSummary:")
        print(f"  Cancer episodes  : {len(cancer_feature_rows)}")
        print(f"  Benign episodes  : {len(benign_feature_rows)}")
        print(f"  BloodPanel nodes : {len(panel_feature_rows)}")
        print(f"  Total            : {len(all_rows)}")

        if not args.apply:
            print("\nDry run -- use --apply to write to Neo4j and run GDS.")
            driver.close()
            return 0

        # ------------------------------------------------------------------
        # Phase 6: Write feature vectors to Neo4j
        # ------------------------------------------------------------------
        print("\nPhase 6: Writing feature vectors to Neo4j...")

        if cancer_feature_rows:
            session.run(_WRITE_EPISODE_FEATURES_Q, rows=cancer_feature_rows)
            print(f"  Wrote {len(cancer_feature_rows)} cancer EpisodeOfCare nodes")

        if benign_feature_rows:
            session.run(_WRITE_EPISODE_FEATURES_Q, rows=benign_feature_rows)
            print(f"  Wrote {len(benign_feature_rows)} benign EpisodeOfCare nodes")

        if panel_feature_rows:
            session.run(_WRITE_BLOOD_PANEL_Q, rows=panel_feature_rows)
            print(f"  Wrote {len(panel_feature_rows)} BloodPanel nodes")

        # Write cluster assignments
        ep_cluster_rows = [
            {"node_id": r["episode_id"], "cluster": r["bf_cluster"]}
            for r in cancer_feature_rows + benign_feature_rows
            if r.get("episode_id")
        ]
        bp_cluster_rows = [
            {"node_id": r["patient_id"], "cluster": r["bf_cluster"]}
            for r in panel_feature_rows
        ]
        if ep_cluster_rows:
            session.run(_WRITE_CLUSTER_LABELS_EP_Q, rows=ep_cluster_rows)
        if bp_cluster_rows:
            session.run(_WRITE_CLUSTER_LABELS_BP_Q, rows=bp_cluster_rows)
        print(f"  Wrote cluster labels for {len(ep_cluster_rows + bp_cluster_rows)} nodes")

        # ------------------------------------------------------------------
        # Phase 7: GDS kNN
        # ------------------------------------------------------------------
        try:
            knn_result = _run_gds_knn(session)
        except Exception as exc:
            print(f"  WARNING: GDS kNN failed: {exc}")
            knn_result = {}

        # ------------------------------------------------------------------
        # Phase 8: Pearson correlations (feature importance)
        # ------------------------------------------------------------------
        correlations = _compute_pearson_correlations(session)
        _write_correlations(session, correlations)
        print(f"\nTop discriminating tests:")
        sorted_corr = sorted(correlations.items(), key=lambda x: abs(x[1]), reverse=True)
        for prop_key, r in sorted_corr[:5]:
            direction = "cancer higher" if r > 0 else "benign higher"
            print(f"  {FEATURE_LABELS[prop_key]:<20} r={r:+.4f} ({direction})")

    driver.close()
    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
