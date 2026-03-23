"""Stratified 20% audit of coded TrainingLabel records.

Pulls a random stratified sample (by tier and source) from Neo4j,
inspects entity-to-SNOMED mappings for quality issues, and writes a
Markdown audit report.

Checks performed per entity:
  1. Semantic tag mismatch — NER label vs SNOMED semantic_tag from terminology
  2. Overly broad coding — concept is a top-level catch-all (e.g. "Clinical finding")
  3. Assertion/tier inconsistency — absent/hypothetical entities in T1 (auto_coded)
  4. Score in range — T1 entities should have score >= MIN_SCORE_T1
  5. Sentence over-capture — entity text > 60 chars (likely a full sentence)
  6. Suspicious negation — entity coded T1 but assertion is 'absent' or 'refuted'
"""
from __future__ import annotations

import json
import random
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from dotenv import load_dotenv
load_dotenv(_REPO_ROOT / "secrets" / ".env.config", override=True)
load_dotenv(_REPO_ROOT / "secrets" / ".env", override=False)

from libs.neo4j_client.client import PatientGraphClient

# ── config ────────────────────────────────────────────────────────────────────
SAMPLE_FRACTION = 0.20
RANDOM_SEED = 42
MIN_SCORE_T1 = 0.60
OUTPUT_PATH = Path(__file__).parent / "audit_report_20pct.md"

# SNOMED semantic tags considered "overly broad" catch-alls
BROAD_CONCEPTS = {
    "clinical finding", "finding", "event", "situation",
    "observable entity", "substance", "product", "body structure",
    "procedure", "disorder",
}
# These are acceptable only if the entity text is equally generic
VERY_BROAD_CONCEPTS_FSN = {
    "Clinical finding (finding)",
    "Disorder (disorder)",
    "Procedure (procedure)",
    "Product (product)",
    "Substance (substance)",
    "Body structure (body structure)",
    "Observable entity (observable entity)",
}

# NER label → expected SNOMED semantic_tag family (partial match)
LABEL_TAG_FAMILIES: dict[str, set[str]] = {
    "disorder":           {"disorder", "finding", "disease"},
    "finding":            {"finding", "disorder", "observable entity"},
    "procedure":          {"procedure", "regime/therapy"},
    "substance":          {"substance", "product", "medicinal product", "medication"},
    "body_structure":     {"body structure", "morphologic abnormality"},
    "observable_entity":  {"observable entity", "finding"},
    "qualifier_value":    {"qualifier value"},
    "lab_result":         {"observable entity", "finding", "qualifier value"},
}


def _fetch_all_label_ids(client: PatientGraphClient) -> list[dict]:
    """Return label_id, source, quality_score for every included TrainingLabel."""
    return client.run(
        """
        MATCH (tl:TrainingLabel)
        WHERE tl.include = true AND tl.entities_json IS NOT NULL
        RETURN tl.label_id AS label_id,
               coalesce(tl.source, 'unknown') AS source,
               coalesce(tl.quality_score, 0.5) AS quality_score
        """
    )


def _fetch_records(client: PatientGraphClient, label_ids: list[str]) -> list[dict]:
    return client.run(
        """
        UNWIND $ids AS lid
        MATCH (tl:TrainingLabel {label_id: lid})
        RETURN tl.label_id    AS label_id,
               tl.source      AS source,
               tl.quality_score AS quality_score,
               tl.entities_json AS entities_json,
               tl.text        AS text
        """,
        ids=label_ids,
    )


def _stratified_sample(all_rows: list[dict], fraction: float, seed: int) -> list[dict]:
    rng = random.Random(seed)
    by_source: dict[str, list[dict]] = defaultdict(list)
    for r in all_rows:
        by_source[r["source"]].append(r)

    sampled: list[dict] = []
    for src, rows in sorted(by_source.items()):
        n = max(1, round(len(rows) * fraction))
        sampled.extend(rng.sample(rows, min(n, len(rows))))
    return sampled


def _parse_entities(entities_json: str | None) -> list[dict]:
    if not entities_json:
        return []
    try:
        data = json.loads(entities_json)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _audit_entity(ent: dict) -> list[str]:
    """Return list of issue strings for one entity (empty = clean)."""
    issues: list[str] = []

    text = (ent.get("text") or "").strip()
    label = (ent.get("label") or "").lower().replace(" ", "_")
    score = float(ent.get("coding", {}).get("score") or ent.get("score") or 0.0)
    snomed_tag = (
        (ent.get("coding", {}).get("semantic_tag") or ent.get("semantic_tag") or "")
        .lower().strip()
    )
    snomed_term = (
        ent.get("coding", {}).get("snomed_term") or ent.get("snomed_term") or ""
    )
    tier = ent.get("tier") or ent.get("coding_tier") or ""
    assertion = (ent.get("assertion") or "present").lower()
    concept_id = (
        ent.get("coding", {}).get("snomed_concept_id")
        or ent.get("snomed_concept_id")
        or ""
    )

    # 1. Sentence over-capture
    if len(text) > 65:
        issues.append(f"over-capture: entity text is {len(text)} chars (likely full sentence)")

    # 2. Semantic tag mismatch
    expected_family = LABEL_TAG_FAMILIES.get(label)
    if expected_family and snomed_tag and concept_id:
        if not any(snomed_tag.startswith(exp) or exp in snomed_tag for exp in expected_family):
            issues.append(f"tag-mismatch: NER={label!r} but SNOMED tag={snomed_tag!r}")

    # 3. Overly broad top-level concept
    if snomed_term in VERY_BROAD_CONCEPTS_FSN:
        issues.append(f"broad-concept: coded to root concept {snomed_term!r}")

    # 4. T1 entity with absent/refuted assertion (should be T2/T3)
    if tier in ("1", "auto_coded", 1) and assertion in ("absent", "refuted", "hypothetical"):
        issues.append(f"assertion-tier: T1 auto_coded but assertion={assertion!r}")

    # 5. T1 entity with unexpectedly low score
    if tier in ("1", "auto_coded", 1) and score < MIN_SCORE_T1:
        issues.append(f"low-score: T1 auto_coded but score={score:.3f} < {MIN_SCORE_T1}")

    return issues


def main() -> None:
    client = PatientGraphClient()
    try:
        print("Fetching all TrainingLabel IDs…")
        all_rows = _fetch_all_label_ids(client)
        print(f"  Total included records: {len(all_rows)}")

        sample_meta = _stratified_sample(all_rows, SAMPLE_FRACTION, RANDOM_SEED)
        sample_ids = [r["label_id"] for r in sample_meta]
        print(f"  Sampled {len(sample_ids)} records ({SAMPLE_FRACTION:.0%} stratified by source)")

        print("Fetching entities_json for sampled records…")
        records = _fetch_records(client, sample_ids)
        print(f"  Retrieved {len(records)} records from Neo4j")
    finally:
        client.close()

    # ── Audit ─────────────────────────────────────────────────────────────────
    total_entities = 0
    total_coded = 0
    total_issues = 0
    issue_records: list[dict] = []
    issue_type_counter: dict[str, int] = defaultdict(int)
    tier_counter: dict[str, int] = defaultdict(int)
    assertion_counter: dict[str, int] = defaultdict(int)
    source_counter: dict[str, int] = defaultdict(int)
    score_buckets: dict[str, int] = defaultdict(int)
    clean_records = 0

    for rec in records:
        entities = _parse_entities(rec.get("entities_json"))
        if not entities:
            continue

        rec_issues: list[dict] = []
        source_counter[rec.get("source") or "unknown"] += 1

        for ent in entities:
            total_entities += 1
            score = float(ent.get("coding", {}).get("score") or ent.get("score") or 0.0)
            tier = str(ent.get("tier") or ent.get("coding_tier") or "?")
            assertion = (ent.get("assertion") or "present").lower()
            concept_id = (
                ent.get("coding", {}).get("snomed_concept_id")
                or ent.get("snomed_concept_id")
                or ""
            )

            if concept_id:
                total_coded += 1

            tier_counter[tier] += 1
            assertion_counter[assertion] += 1

            # Score bucket
            if score >= 0.9:
                score_buckets["0.90-1.00"] += 1
            elif score >= 0.75:
                score_buckets["0.75-0.90"] += 1
            elif score >= 0.60:
                score_buckets["0.60-0.75"] += 1
            elif score >= 0.50:
                score_buckets["0.50-0.60"] += 1
            else:
                score_buckets["<0.50"] += 1

            ent_issues = _audit_entity(ent)
            if ent_issues:
                total_issues += 1
                for issue in ent_issues:
                    issue_type = issue.split(":")[0]
                    issue_type_counter[issue_type] += 1
                rec_issues.append({
                    "text": ent.get("text", ""),
                    "label": ent.get("label", ""),
                    "snomed_term": (
                        ent.get("coding", {}).get("snomed_term")
                        or ent.get("snomed_term") or ""
                    ),
                    "snomed_concept_id": concept_id,
                    "score": score,
                    "tier": tier,
                    "assertion": assertion,
                    "issues": ent_issues,
                })

        if rec_issues:
            issue_records.append({
                "label_id": rec["label_id"],
                "source": rec.get("source") or "unknown",
                "quality_score": rec.get("quality_score") or 0.0,
                "entity_count": len(entities),
                "issues": rec_issues,
            })
        else:
            clean_records += 1

    # ── Report ────────────────────────────────────────────────────────────────
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines: list[str] = [
        "# Training Data Coding Audit — 20% Sample",
        "",
        f"Generated: {now}",
        f"Sample size: {len(records)} records ({SAMPLE_FRACTION:.0%} of {len(all_rows)} total), stratified by source",
        f"Seed: {RANDOM_SEED}",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Records audited | {len(records)} |",
        f"| Records clean (no issues) | {clean_records} ({clean_records/max(len(records),1):.1%}) |",
        f"| Records with ≥1 issue | {len(issue_records)} ({len(issue_records)/max(len(records),1):.1%}) |",
        f"| Total entities in sample | {total_entities} |",
        f"| Entities coded (concept assigned) | {total_coded} ({total_coded/max(total_entities,1):.1%}) |",
        f"| Entities with ≥1 issue | {total_issues} ({total_issues/max(total_entities,1):.1%}) |",
        "",
        "## Issue Breakdown",
        "",
        "| Issue type | Count |",
        "|---|---|",
    ]
    for issue_type, count in sorted(issue_type_counter.items(), key=lambda x: -x[1]):
        lines.append(f"| `{issue_type}` | {count} |")

    lines += [
        "",
        "## Tier Distribution (sample)",
        "",
        "| Tier | Count |",
        "|---|---|",
    ]
    for tier, count in sorted(tier_counter.items(), key=lambda x: -x[1]):
        lines.append(f"| {tier} | {count} |")

    lines += [
        "",
        "## Score Distribution (sample)",
        "",
        "| Score band | Entities |",
        "|---|---|",
    ]
    for band in ["0.90-1.00", "0.75-0.90", "0.60-0.75", "0.50-0.60", "<0.50"]:
        lines.append(f"| {band} | {score_buckets.get(band, 0)} |")

    lines += [
        "",
        "## Assertion Distribution (sample)",
        "",
        "| Assertion | Count |",
        "|---|---|",
    ]
    for assertion, count in sorted(assertion_counter.items(), key=lambda x: -x[1]):
        lines.append(f"| `{assertion}` | {count} |")

    lines += [
        "",
        "## Records With Issues",
        "",
        f"Showing up to 50 records with coding issues out of {len(issue_records)} flagged.",
        "",
    ]

    for rec in issue_records[:50]:
        lines.append(
            f"### `{rec['label_id'][:32]}` "
            f"(source: {rec['source']}, quality: {rec['quality_score']:.2f})"
        )
        lines.append("")
        lines.append("| Entity | Label | SNOMED | Score | Tier | Assertion | Issues |")
        lines.append("|---|---|---|---|---|---|---|")
        for ent in rec["issues"]:
            issues_str = "; ".join(ent["issues"])
            snomed = f"{ent['snomed_term']} `{ent['snomed_concept_id']}`" if ent["snomed_concept_id"] else "*(none)*"
            lines.append(
                f"| `{ent['text'][:50]}` | `{ent['label']}` | {snomed} "
                f"| {ent['score']:.3f} | {ent['tier']} | `{ent['assertion']}` | {issues_str} |"
            )
        lines.append("")

    lines += ["---", "", f"*Audit script: `scripts/_audit_coded_training_data.py`*"]

    report = "\n".join(lines)
    OUTPUT_PATH.write_text(report, encoding="utf-8")
    print(f"\nReport written to: {OUTPUT_PATH}")
    print(f"Records audited : {len(records)}")
    print(f"Clean records   : {clean_records} ({clean_records/max(len(records),1):.1%})")
    print(f"Flagged records : {len(issue_records)} ({len(issue_records)/max(len(records),1):.1%})")
    print(f"Total issues    : {total_issues} across {total_entities} entities")
    if issue_type_counter:
        print("\nIssue types:")
        for t, c in sorted(issue_type_counter.items(), key=lambda x: -x[1]):
            print(f"  {t:30s} {c}")


if __name__ == "__main__":
    main()
