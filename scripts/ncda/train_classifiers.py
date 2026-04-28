#!/usr/bin/env python3
"""Train NCDA role + linkage classifiers from gold reviewed episodes + silver labels.

Steps
-----
1. Pull reviewed-episode milestones from Neo4j -> gold role rows.
2. Load silver labels from artifacts/ncda_silver/<latest or --silver-dir>.
3. Train role classifier (ncda_role_trainer).  Artifact -> artifacts/ncda_models/role.joblib.
4. Score all encounters with the trained role classifier to build RoleScores.
5. Construct linkage training pairs:
     - Positive (label=1): FTR+Dx in the same reviewed episode.
     - Negative (label=0): FTR from one episode paired with Dx from a different
       episode (cross-episode within same patient, or cross-patient).
6. Train linkage classifier (ncda_linkage_trainer).  Artifact -> artifacts/ncda_models/linkage.joblib.
7. Print metric summary.

Usage:
    python scripts/ncda/train_classifiers.py
    python scripts/ncda/train_classifiers.py --silver-dir artifacts/ncda_silver/20260428T183427Z
    python scripts/ncda/train_classifiers.py --out-dir artifacts/ncda_models/run_01
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env.secrets", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from neo4j import GraphDatabase  # noqa: E402

from services.analysis_worker.app.ncda_detector.linkage_features import (  # noqa: E402
    PairContext,
    extract_pair_features,
)
from services.analysis_worker.app.ncda_detector.pair_generator import (  # noqa: E402
    CandidatePair,
    RoleScore,
)
from services.training_worker.app.ncda_linkage_trainer import (  # noqa: E402
    train_linkage_classifier,
)
from services.training_worker.app.ncda_role_trainer import (  # noqa: E402
    train_role_classifier,
    _default_classifier_factory as _default_role_factory,
)

# ---------------------------------------------------------------------------
# Cypher: pull reviewed milestones + encounter text
# ---------------------------------------------------------------------------

_GOLD_QUERY = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(enc:Encounter)-[r:IS_PART_OF]->(e:EpisodeOfCare)
WHERE e.reviewed_at IS NOT NULL
  AND r.milestone_type IN [
      'referral','referral_sent','first_seen','diagnosis_confirmed',
      'treatment_started','benign_closure','outcome_letter'
  ]
RETURN
    coalesce(toString(p.id), toString(p.patient_id)) AS patient_id,
    e.id AS episode_id,
    coalesce(e.cancer_type, 'unknown') AS cancer_type,
    enc.id AS encounter_id,
    r.milestone_type AS milestone_type,
    toString(enc.date) AS encounter_date,
    enc.text AS text,
    enc.flags AS flags
ORDER BY patient_id, episode_id, encounter_date
"""

# Map reviewed milestone_type -> NCDA role + outcome
_MILESTONE_ROLE = {
    "referral": ("ftr", None),
    "referral_sent": ("ftr", None),
    "first_seen": ("seen", None),
    "diagnosis_confirmed": ("dx", None),    # outcome inferred from text below
    "benign_closure": ("dx", "cancer_excluded"),
    "outcome_letter": ("dx", None),         # outcome inferred from text below
    "treatment_started": ("treatment", None),
}

_MALIGNANT_PHRASES = (
    "malignant", "carcinoma", "adenocarcinoma", "lymphoma", "melanoma",
    "sarcoma", "confirmed cancer", "new diagnosis", "positive biopsy",
)
_BENIGN_PHRASES = (
    "benign", "no malignancy", "all clear", "cancer excluded",
    "cancer ruled out", "discharged", "no evidence of cancer",
)


def _infer_outcome(milestone_type: str, text: str) -> str | None:
    if milestone_type == "benign_closure":
        return "cancer_excluded"
    if milestone_type not in ("diagnosis_confirmed", "outcome_letter"):
        return None
    lower = (text or "").lower()
    if any(p in lower for p in _MALIGNANT_PHRASES):
        return "cancer_found"
    if any(p in lower for p in _BENIGN_PHRASES):
        return "cancer_excluded"
    return "cancer_found"  # conservative default: assume cancer found


def _milestone_to_role_row(r: dict) -> dict:
    mtype = r["milestone_type"]
    role, fixed_outcome = _MILESTONE_ROLE.get(mtype, ("none", None))
    outcome = fixed_outcome or _infer_outcome(mtype, r.get("text") or "")
    return {
        "patient_id": r["patient_id"],
        "encounter_id": r["encounter_id"],
        "encounter_date": r.get("encounter_date"),
        "text": r.get("text") or "",
        "flags": r.get("flags"),
        "role": role,
        "outcome": outcome,
        "episode_id": r.get("episode_id"),
        "cancer_type": r.get("cancer_type"),
        "source": "gold",
    }


# ---------------------------------------------------------------------------
# Silver label reader
# ---------------------------------------------------------------------------

def _latest_silver_dir(root: Path) -> Path | None:
    base = root / "artifacts" / "ncda_silver"
    if not base.exists():
        return None
    dirs = sorted(base.iterdir(), reverse=True)
    return dirs[0] if dirs else None


def _load_silver(silver_path: Path) -> list[dict]:
    if silver_path.suffix == ".parquet":
        import pandas as pd
        df = pd.read_parquet(silver_path)
        return df.to_dict(orient="records")
    rows = []
    with silver_path.open() as f:
        for line in f:
            rows.append(json.loads(line))
    return rows


# ---------------------------------------------------------------------------
# Neo4j connection
# ---------------------------------------------------------------------------

def _connect():
    uri = (
        os.environ.get("NEO4J_PATIENT_URI", "").strip()
        or os.environ.get("NEO4J_URI", "").strip()
    )
    user = (
        os.environ.get("NEO4J_PATIENT_USER", "").strip()
        or os.environ.get("NEO4J_USER", "").strip()
    )
    pw = (
        os.environ.get("NEO4J_PATIENT_PASSWORD", "").strip()
        or os.environ.get("NEO4J_PASSWORD", "").strip()
    )
    if not all([uri, user, pw]):
        raise SystemExit("ERROR: NEO4J credentials missing.")
    return GraphDatabase.driver(uri, auth=(user, pw))


# ---------------------------------------------------------------------------
# Role-score conversion (for linkage feature extraction)
# ---------------------------------------------------------------------------

def _role_row_to_role_score(row: dict, confidence: float = 1.0) -> RoleScore:
    role = row.get("role", "none")
    probs = {"ftr": 0.05, "seen": 0.05, "dx": 0.05, "treatment": 0.05, "none": 0.05}
    probs[role] = confidence
    return RoleScore(
        encounter_id=str(row["encounter_id"]),
        encounter_date=str(row.get("encounter_date") or ""),
        role_probabilities=probs,
        outcome=row.get("outcome"),
        outcome_probability=confidence if role == "dx" else None,
        text=row.get("text"),
        flags=row.get("flags"),
    )


# ---------------------------------------------------------------------------
# Linkage training pair construction
# ---------------------------------------------------------------------------

def _to_date(v: str | None) -> date | None:
    if not v:
        return None
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def _build_linkage_rows(
    gold_by_episode: dict[tuple[str, str], list[dict]],
) -> list[dict]:
    """Build labelled pair rows for linkage training.

    Positive (1): FTR + Dx in the same reviewed episode.
    Negative (0): FTR from one episode + Dx from a DIFFERENT episode of the
                  same patient, or randomly sampled cross-patient pair.
    """
    # Collect FTR and Dx role scores per episode
    ep_ftrs: dict[tuple[str, str], list[dict]] = {}
    ep_dxs: dict[tuple[str, str], list[dict]] = {}
    for ep_key, rows in gold_by_episode.items():
        ftrs = [r for r in rows if r.get("role") == "ftr"]
        dxs = [r for r in rows if r.get("role") == "dx"]
        if ftrs:
            ep_ftrs[ep_key] = ftrs
        if dxs:
            ep_dxs[ep_key] = dxs

    positives: list[dict] = []
    negatives: list[dict] = []

    # Positive pairs: same episode FTR x Dx
    for ep_key, ftrs in ep_ftrs.items():
        dxs = ep_dxs.get(ep_key, [])
        for ftr in ftrs:
            for dx in dxs:
                pair, ctx = _make_pair_and_ctx(ftr, dx, gold_by_episode[ep_key])
                if pair is None:
                    continue
                feats = _safe_features(pair, ctx)
                positives.append({"features": feats, "label": 1, "weight": 1.0})

    # Negative pairs: same-patient cross-episode
    # Group episodes by patient
    by_patient: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for ep_key in gold_by_episode:
        by_patient[ep_key[0]].append(ep_key)

    for pid, ep_keys in by_patient.items():
        if len(ep_keys) < 2:
            continue
        for i, ep_a in enumerate(ep_keys):
            for ep_b in ep_keys[i + 1 :]:
                ftrs_a = ep_ftrs.get(ep_a, [])
                dxs_b = ep_dxs.get(ep_b, [])
                ftrs_b = ep_ftrs.get(ep_b, [])
                dxs_a = ep_dxs.get(ep_a, [])
                for ftr in ftrs_a:
                    for dx in dxs_b:
                        pair, ctx = _make_pair_and_ctx(ftr, dx, [])
                        if pair is None:
                            continue
                        feats = _safe_features(pair, ctx)
                        negatives.append({"features": feats, "label": 0, "weight": 1.0})
                for ftr in ftrs_b:
                    for dx in dxs_a:
                        pair, ctx = _make_pair_and_ctx(ftr, dx, [])
                        if pair is None:
                            continue
                        feats = _safe_features(pair, ctx)
                        negatives.append({"features": feats, "label": 0, "weight": 1.0})

    # Cross-patient negatives: pair FTR from each episode with Dx from other patients
    all_ftrs = [r for ftrs in ep_ftrs.values() for r in ftrs]
    all_dxs = [r for dxs in ep_dxs.values() for r in dxs]
    import random
    rng = random.Random(42)
    cross_sample = min(len(positives) * 3, 200)
    for _ in range(cross_sample):
        ftr = rng.choice(all_ftrs)
        dx = rng.choice(all_dxs)
        if ftr.get("patient_id") == dx.get("patient_id"):
            continue
        pair, ctx = _make_pair_and_ctx(ftr, dx, [])
        if pair is None:
            continue
        feats = _safe_features(pair, ctx)
        negatives.append({"features": feats, "label": 0, "weight": 0.5})

    print(f"  Linkage pairs: {len(positives)} positive, {len(negatives)} negative")
    return positives + negatives


def _make_pair_and_ctx(
    ftr_row: dict,
    dx_row: dict,
    episode_rows: list[dict],
) -> tuple[CandidatePair | None, PairContext]:
    ftr_score = _role_row_to_role_score(ftr_row, 0.9)
    dx_score = _role_row_to_role_score(dx_row, 0.9)
    fd = _to_date(ftr_row.get("encounter_date"))
    dd = _to_date(dx_row.get("encounter_date"))
    if fd is None or dd is None:
        return None, PairContext(ftr_encounter=ftr_score, dx_encounter=dx_score, intervening=[])
    gap = (dd - fd).days
    pair = CandidatePair(
        patient_id=str(ftr_row.get("patient_id", "")),
        ftr_encounter_id=str(ftr_row["encounter_id"]),
        dx_encounter_id=str(dx_row["encounter_id"]),
        ftr_role_p=0.9,
        dx_role_p=0.9,
        dx_outcome=dx_row.get("outcome"),
        dx_outcome_p=0.9 if dx_row.get("outcome") else None,
        gap_days=gap,
        ftr_date=ftr_row.get("encounter_date"),
        dx_date=dx_row.get("encounter_date"),
    )
    intervening = [
        _role_row_to_role_score(r, 0.7)
        for r in episode_rows
        if r["encounter_id"] not in (ftr_row["encounter_id"], dx_row["encounter_id"])
    ]
    ctx = PairContext(
        ftr_encounter=ftr_score,
        dx_encounter=dx_score,
        intervening=intervening,
        recurrent_ftr=False,
    )
    return pair, ctx


def _safe_features(pair: CandidatePair, ctx: PairContext) -> dict[str, float]:
    from services.analysis_worker.app.ncda_detector.linkage_features import (
        gap_features,
        intervening_histogram,
        recurrent_ftr_feature,
        role_probability_features,
    )
    out: dict[str, float] = {}
    out.update(gap_features(pair))
    out.update(role_probability_features(pair))
    out.update(intervening_histogram(ctx))
    out.update(recurrent_ftr_feature(ctx))
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _balanced_role_classifier():
    """Balanced-weight role classifier with higher iteration ceiling."""
    from sklearn.linear_model import LogisticRegression
    return LogisticRegression(max_iter=2000, class_weight="balanced")


def _downsample_none_silver(silver_rows: list[dict], ratio: int = 4) -> list[dict]:
    """Keep all non-none silver rows; downsample none to ratio * non-none count.

    This prevents the classifier from learning to always predict 'none'.
    A ratio of 4 means up to 4 'none' rows per non-none row.
    """
    import random
    non_none = [r for r in silver_rows if r.get("role") != "none"]
    none_rows = [r for r in silver_rows if r.get("role") == "none"]
    target = min(len(none_rows), ratio * max(len(non_none), 1))
    sampled_none = random.Random(42).sample(none_rows, target)
    result = non_none + sampled_none
    print(f"  Silver after downsampling: {len(non_none)} non-none + {len(sampled_none)} none = {len(result)}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--silver-dir",
        type=Path,
        default=None,
        help="Path to a specific silver-label run dir (default: latest).",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / "artifacts" / "ncda_models",
        help="Directory for trained artifacts.",
    )
    parser.add_argument(
        "--none-ratio",
        type=int,
        default=4,
        help="Max ratio of 'none' silver rows to non-none (default 4).",
    )
    args = parser.parse_args()

    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- 1. Load silver labels ---
    silver_dir = args.silver_dir or _latest_silver_dir(ROOT)
    if silver_dir is None:
        raise SystemExit(
            "No silver-label artifact found. Run build_silver_labels.py first."
        )
    silver_file = next(
        (p for p in silver_dir.iterdir() if p.suffix in (".parquet", ".jsonl")), None
    )
    if silver_file is None:
        raise SystemExit(f"No labels file in {silver_dir}")
    print(f"Loading silver labels from {silver_file} ...")
    all_silver = _load_silver(silver_file)
    print(f"  {len(all_silver)} silver rows (raw)")
    silver_rows = _downsample_none_silver(all_silver, ratio=args.none_ratio)

    # --- 2. Pull gold from Neo4j ---
    print("Pulling gold reviewed milestones from Neo4j ...")
    driver = _connect()
    try:
        with driver.session() as session:
            raw_gold = [dict(r) for r in session.run(_GOLD_QUERY)]
    finally:
        driver.close()

    gold_rows = [_milestone_to_role_row(r) for r in raw_gold]
    print(f"  {len(gold_rows)} gold milestone rows from {len({r['episode_id'] for r in gold_rows})} episodes")

    # --- 3. Train role classifier ---
    role_artifact = out_dir / "role.joblib"
    print(f"\nTraining role classifier -> {role_artifact} ...")
    result = train_role_classifier(
        gold_rows,
        silver_rows,
        artifact_path=role_artifact,
        classifier_factory=_balanced_role_classifier,
    )
    print("  Role metrics (training set):")
    for label, m in sorted(result.role_metrics.items()):
        print(f"    {label:<12} P={m['precision']:.2f}  R={m['recall']:.2f}  F1={m['f1']:.2f}  n={m['support']}")
    if result.outcome_metrics:
        print("  Dx-outcome metrics (training set):")
        for label, m in sorted(result.outcome_metrics.items()):
            print(f"    {label:<20} P={m['precision']:.2f}  R={m['recall']:.2f}  F1={m['f1']:.2f}")

    # --- 4. Build linkage training pairs from gold episodes ---
    gold_by_episode: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in gold_rows:
        gold_by_episode[(r["patient_id"], str(r.get("episode_id") or ""))].append(r)

    print("\nBuilding linkage training pairs ...")
    linkage_rows = _build_linkage_rows(gold_by_episode)

    if len(linkage_rows) < 4:
        print("  WARNING: too few linkage pairs to train a meaningful classifier; using gap stub.")
        return 0

    # --- 5. Train linkage classifier ---
    linkage_artifact = out_dir / "linkage.joblib"
    print(f"Training linkage classifier -> {linkage_artifact} ...")
    lr = train_linkage_classifier(linkage_rows, artifact_path=linkage_artifact)
    print(f"  Training accuracy: {lr.metrics.get('training_accuracy', 0):.3f}")
    print(f"  Training AUC:      {lr.metrics.get('training_auc', 0):.3f}")
    print(f"  Positives: {lr.n_positive}  Negatives: {lr.n_negative}")

    # --- 6. Write manifest ---
    manifest = {
        "role_artifact": str(role_artifact),
        "linkage_artifact": str(linkage_artifact),
        "n_gold": len(gold_rows),
        "n_silver": len(silver_rows),
        "n_linkage_positive": lr.n_positive,
        "n_linkage_negative": lr.n_negative,
        "role_metrics": result.role_metrics,
        "linkage_metrics": lr.metrics,
    }
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"\nManifest written: {manifest_path}")
    print("\nDone. Re-run the dry run with:")
    print(f"  python scripts/ncda/dry_run_reviewed.py --role-model {role_artifact} --linkage-model {linkage_artifact}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
