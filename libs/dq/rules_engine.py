"""DQ Rules Engine -- loads rules.yaml and evaluates each rule against Neo4j."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from libs.dq._models import DQCheckResult

logger = logging.getLogger(__name__)

_RULES_PATH = Path(__file__).parent / "rules.yaml"


def load_rules() -> list[dict]:
    """Load and return all rules from rules.yaml."""
    with open(_RULES_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("rules", [])


def _evaluate_rule(rule: dict, client: Any) -> DQCheckResult:
    """Execute a single rule's Cypher and return a DQCheckResult."""
    from libs.neo4j_client.client import run_with_retry

    rule_id = rule["id"]
    dimension = rule["dimension"]
    severity = rule["severity"]
    threshold = int(rule.get("threshold", 0))
    description = rule["description"]
    cypher = rule.get("cypher", "")

    violations = 0
    samples: list[dict] = []
    try:
        rows = run_with_retry(client, cypher) if cypher else []
        violations = len(rows)
        samples = [dict(r) for r in rows[:5]]
    except Exception as exc:
        logger.warning("Rule %s evaluation failed: %s", rule_id, exc)
        return DQCheckResult(
            rule_id=rule_id,
            dimension=dimension,
            severity=severity,
            status="warn",
            violation_count=0,
            threshold=threshold,
            sample_violations=[{"error": str(exc)}],
            description=description,
        )

    if violations == 0:
        status = "pass"
    elif violations <= threshold:
        status = "warn"
    else:
        status = "fail"

    return DQCheckResult(
        rule_id=rule_id,
        dimension=dimension,
        severity=severity,
        status=status,
        violation_count=violations,
        threshold=threshold,
        sample_violations=samples,
        description=description,
    )


def run_all_rules(client: Any) -> list[DQCheckResult]:
    """Evaluate all configured DQ rules and return a scorecard."""
    rules = load_rules()
    results = []
    for rule in rules:
        result = _evaluate_rule(rule, client)
        results.append(result)
        logger.info(
            "DQ rule %s [%s] status=%s violations=%d",
            result.rule_id,
            result.dimension,
            result.status,
            result.violation_count,
        )
    return results


def scorecard_summary(results: list[DQCheckResult]) -> dict:
    """Return aggregate pass/warn/fail counts from a scorecard."""
    counts = {"pass": 0, "warn": 0, "fail": 0}
    critical_fails = []
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
        if r.status == "fail" and r.severity == "critical":
            critical_fails.append(r.rule_id)
    return {
        "total": len(results),
        **counts,
        "critical_failures": critical_fails,
        "overall": "fail" if counts["fail"] > 0 else (
            "warn" if counts["warn"] > 0 else "pass"
        ),
    }
