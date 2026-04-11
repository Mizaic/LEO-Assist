"""Export deduplicated medspaCy TargetRules from reviewed anchor records.

Reads AnchorReview nodes from Neo4j (written by review_anchor_training.py)
and produces a JSON file containing per-domain TargetRule strings, deduplicated
by pattern content.

Only includes records where:
  - Both models agreed (consensus_agreement = true), OR
  - A human vote has been recorded (human_corrected = true)

NON_CANCER and AMBIGUOUS domains are excluded — they produce no useful rules.

Usage
-----
    python scripts/export_target_rules.py \\
        --output exports/training/target_rules_by_domain.json

    # Or read from a review results JSONL (skips Neo4j):
    python scripts/export_target_rules.py \\
        --from-file exports/training/anchor_review_results.jsonl \\
        --output   exports/training/target_rules_by_domain.json
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s"
)
logger = logging.getLogger("export_target_rules")

EXCLUDE_DOMAINS = {"NON_CANCER", "AMBIGUOUS", "DISAGREEMENT"}

# ──────────────────────────────────────────────────────────────────────────────
# Rule normalisation
# ──────────────────────────────────────────────────────────────────────────────

_LOWER_TOKENS_RE = re.compile(r"\{'LOWER':\s*'([^']+)'\}")


def _rule_signature(rule_str: str) -> str:
    """Return a normalised signature for deduplication.

    Extracts the lowercased token sequence so rules that differ only in their
    literal name or minor formatting collapse to the same signature.
    """
    tokens = _LOWER_TOKENS_RE.findall(rule_str.lower())
    return " ".join(tokens) if tokens else rule_str.lower().strip()


def _deduplicate_rules(rules: list[str]) -> list[str]:
    """Deduplicate rules by pattern signature, preserving insertion order."""
    seen: set[str] = set()
    result: list[str] = []
    for rule in rules:
        if not rule or not rule.strip():
            continue
        sig = _rule_signature(rule)
        if sig not in seen:
            seen.add(sig)
            result.append(rule.strip())
    return result


# ──────────────────────────────────────────────────────────────────────────────
# Source: Neo4j
# ──────────────────────────────────────────────────────────────────────────────


def _load_from_neo4j() -> dict[str, list[str]]:
    """Pull TargetRules from Neo4j via GET_REVIEWED_TARGET_RULES."""
    from libs.neo4j_client.client import PatientGraphClient
    from libs.cypher.anchor_review_queries import GET_REVIEWED_TARGET_RULES

    by_domain: dict[str, list[str]] = {}
    client = PatientGraphClient()
    try:
        with client.session() as session:
            rows = session.run(GET_REVIEWED_TARGET_RULES)
            for row in rows:
                domain = row["domain"]
                if not domain or domain in EXCLUDE_DOMAINS:
                    continue
                rules = list(row.get("rules_a") or []) + list(row.get("rules_b") or [])
                existing = by_domain.setdefault(domain, [])
                existing.extend(rules)
    finally:
        client.close()
    return by_domain


# ──────────────────────────────────────────────────────────────────────────────
# Source: JSONL file (anchor_review_results.jsonl)
# ──────────────────────────────────────────────────────────────────────────────


def _load_from_file(path: str) -> dict[str, list[str]]:
    """Load rules from a review results JSONL file."""
    by_domain: dict[str, list[str]] = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Determine authoritative domain
            if rec.get("human_domain"):
                domain = rec["human_domain"]
            elif rec.get("consensus_agreement") and rec.get("final_domain"):
                domain = rec["final_domain"]
            else:
                continue

            if not domain or domain in EXCLUDE_DOMAINS:
                continue

            existing = by_domain.setdefault(domain, [])
            for key in ("model_a_target_rule", "model_b_target_rule"):
                rule = rec.get(key, "")
                if rule and rule.strip():
                    existing.append(rule.strip())

    return by_domain


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────


def export_target_rules(
    from_file: str | None,
    output_path: str,
) -> dict[str, Any]:
    if from_file:
        logger.info("Loading rules from file: %s", from_file)
        raw_by_domain = _load_from_file(from_file)
    else:
        logger.info("Loading rules from Neo4j...")
        raw_by_domain = _load_from_neo4j()

    deduped: dict[str, list[str]] = {}
    for domain, rules in sorted(raw_by_domain.items()):
        deduped[domain] = _deduplicate_rules(rules)

    output = {
        "target_rules_by_domain": deduped,
        "total_domains": len(deduped),
        "total_rules": sum(len(v) for v in deduped.values()),
        "source": from_file or "neo4j",
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    logger.info("")
    logger.info("=" * 60)
    logger.info("TARGET RULES EXPORT")
    logger.info("=" * 60)
    for domain, rules in deduped.items():
        logger.info("  %-35s %4d rules", domain, len(rules))
    logger.info(
        "  Total: %d rules across %d domains",
        output["total_rules"],
        output["total_domains"],
    )
    logger.info("  Output: %s", output_path)
    logger.info("=" * 60)

    return output


def main():
    parser = argparse.ArgumentParser(
        description="Export deduplicated TargetRules by domain"
    )
    parser.add_argument(
        "--from-file",
        default=None,
        help="Read from an anchor_review_results.jsonl file instead of Neo4j",
    )
    parser.add_argument(
        "--output",
        default="exports/training/target_rules_by_domain.json",
        help="Output JSON path",
    )
    args = parser.parse_args()

    export_target_rules(from_file=args.from_file, output_path=args.output)


if __name__ == "__main__":
    main()
