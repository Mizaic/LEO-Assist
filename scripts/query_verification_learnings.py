"""Query Neo4j for verification learnings: HITL resolutions, agreements, and disagreement patterns.

Outputs a summary of what was resolved, how, and common patterns that can inform
few-shot examples and deterministic rules.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from libs.neo4j_client.client import PatientGraphClient


def main() -> None:
    client = PatientGraphClient()

    print("=" * 80)
    print("1. HITL RESOLUTIONS (human-resolved disagreements)")
    print("=" * 80)
    with client.session() as session:
        rows = list(session.run("""
            MATCH (r:LabelVerificationReview)-[:REVIEWS_LABEL]->(t:TrainingLabel)
            WHERE r.resolved = true
              AND r.resolved_by IS NOT NULL
              AND NOT r.resolved_by STARTS WITH 'auto_triage:'
            RETURN
                r.entity_text AS entity_text,
                r.current_label AS original_label,
                r.model_a_label AS aws_label,
                r.model_b_label AS azure_label,
                r.resolved_label AS resolved_label,
                r.resolved_by AS resolved_by,
                substring(t.text, 0, 120) AS encounter_snippet
            ORDER BY r.resolved_at DESC
            LIMIT 100
        """))
    print(f"  Found {len(rows)} HITL resolutions\n")
    for r in rows:
        print(f"  Entity: {r['entity_text']!r}")
        print(f"    Original: {r['original_label']}  AWS: {r['aws_label']}  Azure: {r['azure_label']}")
        print(f"    RESOLVED: {r['resolved_label']}  by: {r['resolved_by']}")
        print(f"    Context: {r['encounter_snippet']!r}")
        print()

    print("=" * 80)
    print("2. HITL RESOLUTION PATTERNS (grouped by original -> resolved)")
    print("=" * 80)
    with client.session() as session:
        rows = list(session.run("""
            MATCH (r:LabelVerificationReview)
            WHERE r.resolved = true
              AND r.resolved_by IS NOT NULL
              AND NOT r.resolved_by STARTS WITH 'auto_triage:'
            WITH r.current_label AS from_label,
                 r.resolved_label AS to_label,
                 count(r) AS n,
                 collect(r.entity_text)[0..3] AS examples
            RETURN from_label, to_label, n, examples
            ORDER BY n DESC
        """))
    for r in rows:
        print(f"  {r['from_label']} -> {r['to_label']}  (n={r['n']})  examples: {r['examples']}")
    print()

    print("=" * 80)
    print("3. AUTO-RESOLVED PATTERNS (terminology API or LLM tie-break)")
    print("=" * 80)
    with client.session() as session:
        rows = list(session.run("""
            MATCH (r:LabelVerificationReview)
            WHERE r.resolved = true
              AND r.resolved_by IS NOT NULL
              AND r.resolved_by STARTS WITH 'auto_triage:'
            WITH r.auto_resolve_method AS method,
                 r.current_label AS from_label,
                 r.resolved_label AS to_label,
                 count(r) AS n,
                 collect(r.entity_text)[0..3] AS examples,
                 collect(r.auto_resolve_reason)[0..2] AS reasons
            RETURN method, from_label, to_label, n, examples, reasons
            ORDER BY n DESC
        """))
    if not rows:
        print("  No auto-resolved items found.\n")
    for r in rows:
        print(f"  [{r['method']}] {r['from_label']} -> {r['to_label']}  (n={r['n']})")
        print(f"    examples: {r['examples']}")
        print(f"    reasons: {r['reasons']}")
        print()

    print("=" * 80)
    print("4. MODEL ACCURACY ON RESOLVED DISAGREEMENTS")
    print("=" * 80)
    with client.session() as session:
        rows = list(session.run("""
            MATCH (r:LabelVerificationReview)
            WHERE r.resolved = true
              AND r.model_a_was_correct IS NOT NULL
            RETURN
                count(r) AS total,
                sum(CASE WHEN r.model_a_was_correct THEN 1 ELSE 0 END) AS aws_correct,
                sum(CASE WHEN r.model_b_was_correct THEN 1 ELSE 0 END) AS azure_correct,
                sum(CASE WHEN r.model_a_was_correct AND r.model_b_was_correct THEN 1 ELSE 0 END) AS both_correct,
                sum(CASE WHEN NOT r.model_a_was_correct AND NOT r.model_b_was_correct THEN 1 ELSE 0 END) AS both_wrong
        """))
    if rows:
        r = rows[0]
        total = r["total"] or 0
        print(f"  Total resolved: {total}")
        if total:
            print(f"  AWS correct: {r['aws_correct']} ({100*r['aws_correct']/total:.1f}%)")
            print(f"  Azure correct: {r['azure_correct']} ({100*r['azure_correct']/total:.1f}%)")
            print(f"  Both correct: {r['both_correct']} ({100*r['both_correct']/total:.1f}%)")
            print(f"  Both wrong: {r['both_wrong']} ({100*r['both_wrong']/total:.1f}%)")
    print()

    print("=" * 80)
    print("5. AGREEMENT LABEL DISTRIBUTION (what models agreed on)")
    print("=" * 80)
    with client.session() as session:
        rows = list(session.run("""
            MATCH (t:TrainingLabel)
            WHERE t.include = true
              AND t.verified_at IS NOT NULL
              AND t.verification_agreement = true
            WITH t.model_a_label AS agreed_label, count(t) AS n
            RETURN agreed_label, n
            ORDER BY n DESC
        """))
    for r in rows:
        print(f"  {r['agreed_label']}: {r['n']}")
    print()

    print("=" * 80)
    print("6. MOST COMMON DISAGREEMENT PAIRS (what models fight about)")
    print("=" * 80)
    with client.session() as session:
        rows = list(session.run("""
            MATCH (r:LabelVerificationReview)
            WITH
                CASE WHEN r.model_a_label < r.model_b_label
                     THEN r.model_a_label + ' vs ' + r.model_b_label
                     ELSE r.model_b_label + ' vs ' + r.model_a_label
                END AS pair,
                count(r) AS n,
                collect(r.entity_text)[0..3] AS examples
            RETURN pair, n, examples
            ORDER BY n DESC
            LIMIT 20
        """))
    for r in rows:
        print(f"  {r['pair']}: {r['n']}  examples: {r['examples']}")
    print()

    print("=" * 80)
    print("7. PENDING HITL ITEMS BY LABEL PAIR")
    print("=" * 80)
    with client.session() as session:
        rows = list(session.run("""
            MATCH (r:LabelVerificationReview)-[:REVIEWS_LABEL]->(t:TrainingLabel)
            WHERE coalesce(r.resolved, false) = false
              AND t.include = true
            WITH
                CASE WHEN r.model_a_label < r.model_b_label
                     THEN r.model_a_label + ' vs ' + r.model_b_label
                     ELSE r.model_b_label + ' vs ' + r.model_a_label
                END AS pair,
                count(r) AS n,
                collect(r.entity_text)[0..5] AS examples
            RETURN pair, n, examples
            ORDER BY n DESC
        """))
    for r in rows:
        print(f"  {r['pair']}: {r['n']}  examples: {r['examples']}")

    client.close()


if __name__ == "__main__":
    main()
