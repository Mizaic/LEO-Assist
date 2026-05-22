"""Restore NG12 guidance rule coverage.

Operations:
  report              -- show gap analysis for a guideline chapter
  restore-originals   -- DANGEROUS: revert to earliest generated rule; prefer undo-approved
  generate-missing    -- LLM-generate rules for recs with no linked rule

Usage:
  python scripts/restore_ng12_guidance_rules.py report
  python scripts/restore_ng12_guidance_rules.py restore-originals --apply
  python scripts/restore_ng12_guidance_rules.py generate-missing
"""

from __future__ import annotations

import argparse
import logging
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from libs.neo4j_client.client import KnowledgeGraphClient  # noqa: E402

logger = logging.getLogger(__name__)

_FETCH_REC_RULES = """
MATCH (g:Guideline {id: $guideline_id})-[:HAS_RECOMMENDATION]->(r:Recommendation)
WHERE ($chapter_filter IS NULL OR r.id CONTAINS $chapter_filter)
  AND coalesce(r.isNormative, false) = true
OPTIONAL MATCH (r)-[:HAS_RULE]->(rule:AppropriatenessRule)
RETURN r.id AS rec_id,
       r.title AS title,
       collect({
         id: rule.id,
         status: rule.status,
         created: toString(rule.createdAt)
       }) AS rules
ORDER BY r.title
"""

_UPDATE_RULE_STATUS = """
MATCH (rule:AppropriatenessRule {id: $rule_id})
SET rule.status = $status,
    rule.reviewedAt = datetime(),
    rule.reviewedBy = $reviewer
MERGE (audit:GuidanceAuditEvent {id: $event_id})
ON CREATE SET
    audit.ruleId = $rule_id,
    audit.action = $action,
    audit.reviewer = $reviewer,
    audit.reason = $reason,
    audit.timestamp = datetime(),
    audit.immutable = true
MERGE (rule)-[:HAS_AUDIT_EVENT]->(audit)
RETURN rule.id AS id
"""


@dataclass(frozen=True)
class RuleRow:
    rec_id: str
    title: str
    rules: tuple[dict[str, Any], ...]


def _load_rows(client: KnowledgeGraphClient, guideline_id: str, chapter: str | None) -> list[RuleRow]:
    chapter_filter = f":{chapter}:" if chapter else None
    rows = client.run(
        _FETCH_REC_RULES,
        guideline_id=guideline_id,
        chapter_filter=chapter_filter,
    )
    out: list[RuleRow] = []
    for row in rows or []:
        rules = tuple(
            r for r in (row.get("rules") or []) if r.get("id")
        )
        out.append(
            RuleRow(
                rec_id=str(row.get("rec_id") or ""),
                title=str(row.get("title") or ""),
                rules=rules,
            )
        )
    return out


def _pick_canonical_rule(rules: tuple[dict[str, Any], ...]) -> dict[str, Any] | None:
    candidates = [
        rule
        for rule in rules
        if str(rule.get("status") or "") != "rejected" and rule.get("id")
    ]
    if not candidates:
        return None
    base_rules = [rule for rule in candidates if ":edit:" not in str(rule.get("id"))]
    pool = base_rules or candidates
    return sorted(pool, key=lambda rule: str(rule.get("created") or ""))[0]


def report_rows(rows: list[RuleRow]) -> dict[str, int]:
    stats = {
        "total_recs": len(rows),
        "no_rules": 0,
        "has_active": 0,
        "multiple_active": 0,
        "only_superseded_or_rejected": 0,
    }
    for row in rows:
        statuses = [str(rule.get("status") or "") for rule in row.rules]
        active_count = sum(1 for status in statuses if status == "active")
        if not row.rules:
            stats["no_rules"] += 1
        elif active_count == 0:
            stats["only_superseded_or_rejected"] += 1
        else:
            stats["has_active"] += 1
            if active_count > 1:
                stats["multiple_active"] += 1
    return stats


def restore_originals(
    client: KnowledgeGraphClient,
    rows: list[RuleRow],
    *,
    apply: bool,
    reviewer: str,
) -> dict[str, int]:
    changed = {"activated": 0, "superseded": 0, "skipped": 0}
    for row in rows:
        canonical = _pick_canonical_rule(row.rules)
        if canonical is None:
            changed["skipped"] += 1
            continue
        canonical_id = str(canonical["id"])
        active_ids = [
            str(rule["id"])
            for rule in row.rules
            if str(rule.get("status") or "") == "active"
        ]
        if active_ids == [canonical_id]:
            changed["skipped"] += 1
            continue
        if not apply:
            logger.info(
                "[dry-run] %s -> activate %s; supersede %s",
                row.title,
                canonical_id,
                [rid for rid in active_ids if rid != canonical_id],
            )
            changed["activated"] += 1
            changed["superseded"] += len(active_ids)
            continue
        for rule in row.rules:
            rule_id = str(rule.get("id") or "")
            if not rule_id:
                continue
            target_status = "active" if rule_id == canonical_id else "superseded"
            if str(rule.get("status") or "") == target_status:
                continue
            client.run(
                _UPDATE_RULE_STATUS,
                rule_id=rule_id,
                status=target_status,
                reviewer=reviewer,
                action="restore_original",
                reason="Restore earliest generated NG12 rule for recommendation",
                event_id=str(uuid.uuid4()),
            )
            if target_status == "active":
                changed["activated"] += 1
            else:
                changed["superseded"] += 1
    return changed


def generate_missing(guideline_id: str) -> list[str]:
    from services.api.app.services.guidance_rule_generator import GuidanceRuleGenerator

    client = KnowledgeGraphClient()
    try:
        generator = GuidanceRuleGenerator(client._driver)
        return generator.generate_rules_for_guideline(
            guideline_id,
            only_without_rules=True,
        )
    finally:
        client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore NG12 guidance rule coverage")
    parser.add_argument(
        "command",
        choices=("report", "restore-originals", "generate-missing"),
    )
    parser.add_argument("--guideline-id", default="NG12")
    parser.add_argument("--chapter", default="CH002", help="Chapter id filter, e.g. CH002")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write changes (default dry-run). restore-originals requires --i-understand-overwrites-edits",
    )
    parser.add_argument(
        "--i-understand-overwrites-edits",
        action="store_true",
        help="Required with restore-originals --apply; overwrites approved edit rules.",
    )
    parser.add_argument("--reviewer", default="restore_ng12_script")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    if args.command == "generate-missing":
        rule_ids = generate_missing(args.guideline_id)
        logger.info("Generated %d pending_review rules", len(rule_ids))
        return

    client = KnowledgeGraphClient()
    try:
        rows = _load_rows(client, args.guideline_id, args.chapter)
        stats = report_rows(rows)
        logger.info("Coverage report for %s (%s): %s", args.guideline_id, args.chapter, stats)
        if args.command == "report":
            missing = [row.title for row in rows if not row.rules]
            if missing:
                logger.info("No rules (%d): %s", len(missing), ", ".join(missing[:20]))
            return
        if args.command == "restore-originals" and args.apply:
            if not args.i_understand_overwrites_edits:
                parser.error(
                    "restore-originals --apply requires --i-understand-overwrites-edits"
                )
        result = restore_originals(
            client,
            [row for row in rows if row.rules],
            apply=args.apply,
            reviewer=args.reviewer,
        )
        logger.info(
            "restore-originals %s result: %s",
            "applied" if args.apply else "dry-run",
            result,
        )
    finally:
        client.close()


if __name__ == "__main__":
    main()
