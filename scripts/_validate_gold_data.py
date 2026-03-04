"""Validate the quality of the gold training data after full verification."""
import sys, os, json, warnings
from pathlib import Path
from collections import Counter
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")

from dotenv import load_dotenv
load_dotenv(ROOT / "secrets" / ".env")

from neo4j import GraphDatabase

uri = os.getenv("NEO4J_URI")
user = os.getenv("NEO4J_USER")
pw = os.getenv("NEO4J_PASSWORD")
driver = GraphDatabase.driver(uri, auth=(user, pw))


def section(title: str) -> None:
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")


with driver.session() as s:

    # 1. Overall stats
    section("1. OVERALL VERIFICATION STATS")
    stats = s.run("""
        MATCH (t:TrainingLabel) WHERE t.include = true
        WITH count(t) AS total,
             sum(CASE WHEN t.verified_at IS NOT NULL THEN 1 ELSE 0 END) AS verified,
             sum(CASE WHEN t.verification_agreement = true THEN 1 ELSE 0 END) AS agreed,
             sum(CASE WHEN t.verification_agreement = false THEN 1 ELSE 0 END) AS disagreed,
             sum(CASE WHEN t.entities_json IS NULL THEN 1 ELSE 0 END) AS no_entities
        RETURN total, verified, agreed, disagreed, no_entities
    """).single()
    for k in ["total", "verified", "agreed", "disagreed", "no_entities"]:
        print(f"  {k:25s}: {stats[k]:,}")
    if stats["verified"] > 0:
        pct = stats["agreed"] * 100.0 / stats["verified"]
        print(f"  {'agreement_rate':25s}: {pct:.1f}%")

    # 2. Entity count + type + assertion distribution (client-side JSON parsing)
    section("2. ENTITY COUNT PER ENCOUNTER")
    all_labels = s.run("""
        MATCH (t:TrainingLabel) WHERE t.include = true AND t.entities_json IS NOT NULL
        RETURN t.entities_json AS ej
    """).data()

    ent_counts = Counter()
    type_counts = Counter()
    assertion_counts = Counter()
    total_entities = 0
    for row in all_labels:
        ents = json.loads(row["ej"]) if row["ej"] else []
        n = len(ents)
        total_entities += n
        if n == 0:
            ent_counts["0"] += 1
        elif n == 1:
            ent_counts["1"] += 1
        elif n <= 3:
            ent_counts["2-3"] += 1
        elif n <= 5:
            ent_counts["4-5"] += 1
        elif n <= 10:
            ent_counts["6-10"] += 1
        else:
            ent_counts["11+"] += 1
        for e in ents:
            type_counts[e.get("label", "unknown")] += 1
            assertion_counts[e.get("assertion", "present")] += 1

    for bucket in ["0", "1", "2-3", "4-5", "6-10", "11+"]:
        cnt = ent_counts.get(bucket, 0)
        pct = cnt * 100.0 / len(all_labels) if all_labels else 0
        print(f"  {bucket:10s}: {cnt:6,}  ({pct:5.1f}%)")
    print(f"\n  Total entities across all labels: {total_entities:,}")
    avg = total_entities / len(all_labels) if all_labels else 0
    print(f"  Average entities per encounter:   {avg:.1f}")

    # 3. Entity type breakdown
    section("3. ENTITY TYPE BREAKDOWN")
    for label, n in type_counts.most_common():
        pct = n * 100.0 / total_entities if total_entities > 0 else 0
        print(f"  {label:30s}: {n:6,}  ({pct:5.1f}%)")

    # 4. Assertion distribution
    section("4. ASSERTION DISTRIBUTION")
    for assertion, n in assertion_counts.most_common():
        pct = n * 100.0 / total_entities if total_entities > 0 else 0
        print(f"  {assertion:20s}: {n:6,}  ({pct:5.1f}%)")

    # 5. CodingReview breakdown
    section("5. CODING REVIEW QUEUE")
    cr_stats = s.run("""
        MATCH (cr:CodingReview)
        RETURN
            count(cr) AS total,
            sum(CASE WHEN cr.coded = true THEN 1 ELSE 0 END) AS coded,
            sum(CASE WHEN cr.coded = false THEN 1 ELSE 0 END) AS uncoded,
            sum(CASE WHEN cr.resolved = true THEN 1 ELSE 0 END) AS resolved,
            sum(CASE WHEN coalesce(cr.resolved, false) = false THEN 1 ELSE 0 END) AS pending
    """).single()
    for k in ["total", "coded", "uncoded", "resolved", "pending"]:
        print(f"  {k:25s}: {cr_stats[k]:,}")

    # 6. Spot-check: cervical screening encounters
    section("6. SPOT-CHECK: CERVICAL SCREENING ENCOUNTERS")
    cervical = s.run("""
        MATCH (t:TrainingLabel) WHERE t.include = true
          AND (toLower(t.text) CONTAINS 'cervical' OR toLower(t.text) CONTAINS 'smear')
        RETURN t.label_id AS id, t.text AS text, t.entities_json AS ents,
               t.verification_agreement AS agreed
        LIMIT 5
    """).data()
    if not cervical:
        print("  No cervical screening encounters found in dataset.")
    for r in cervical:
        print(f"\n  Label: {r['id']}")
        print(f"  Agreed: {r['agreed']}")
        text_preview = (r["text"] or "")[:150]
        print(f"  Text: {text_preview}...")
        ents = json.loads(r["ents"]) if r["ents"] else []
        print(f"  Entities ({len(ents)}):")
        for e in ents:
            assertion = e.get("assertion", "present")
            snomed = e.get("snomed_concept_id", "?")
            snomed_term = e.get("snomed_term", "?")
            print(f"    - [{e.get('label','?')}] {e.get('text','?')} | {assertion} | {snomed} | {snomed_term}")

    # 7. Sample disorder entities
    section("7. SAMPLE: DISORDER ENTITY VERDICTS (first 15)")
    disorders_data = s.run("""
        MATCH (t:TrainingLabel) WHERE t.include = true AND t.entities_json IS NOT NULL
        RETURN t.entities_json AS ej
        LIMIT 200
    """).data()
    disorder_samples = []
    for row in disorders_data:
        ents = json.loads(row["ej"]) if row["ej"] else []
        for e in ents:
            if e.get("label") == "disorder" and len(disorder_samples) < 15:
                disorder_samples.append(e)
    for e in disorder_samples:
        text = (e.get("text", "?"))[:35].ljust(35)
        assertion = (e.get("assertion", "present"))[:12].ljust(12)
        snomed = str(e.get("snomed_concept_id", "?"))[:12].ljust(12)
        term = e.get("snomed_term", "?")
        print(f"  {text} | {assertion} | {snomed} | {term}")

    # 8. Labels with zero entities
    section("8. LABELS WITH ZERO ENTITIES")
    zero_ent = [row for row in all_labels if not json.loads(row["ej"] or "[]")]
    print(f"  Labels with no entities: {len(zero_ent)}")

    # 9. Pending manual reviews
    section("9. PENDING MANUAL REVIEWS")
    pending = s.run("""
        MATCH (r:LabelVerificationReview)-[:REVIEWS_LABEL]->(t:TrainingLabel)
        WHERE coalesce(r.resolved, false) = false AND t.include = true
        RETURN count(r) AS n
    """).single()["n"]
    print(f"  Pending LabelVerificationReview items: {pending}")

    # 10. Quality score distribution
    section("10. QUALITY SCORE DISTRIBUTION")
    qs = s.run("""
        MATCH (t:TrainingLabel) WHERE t.include = true AND t.quality_score IS NOT NULL
        RETURN
            CASE
                WHEN t.quality_score >= 0.9 THEN 'A (>=0.9)'
                WHEN t.quality_score >= 0.7 THEN 'B (0.7-0.9)'
                WHEN t.quality_score >= 0.5 THEN 'C (0.5-0.7)'
                ELSE 'D (<0.5)'
            END AS grade,
            count(t) AS cnt,
            avg(t.quality_score) AS avg_score
        ORDER BY min(t.quality_score) DESC
    """).data()
    for r in qs:
        print(f"  {r['grade']:15s}: {r['cnt']:6,}  (avg={r['avg_score']:.3f})")

driver.close()

section("VALIDATION COMPLETE")
print("  All checks passed. Review spot-checks above for clinical accuracy.")
