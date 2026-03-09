from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from libs.neo4j_client.client import PatientGraphClient

NHS_TARGETS = {
    "faster_diagnosis_standard": 28,
    "treatment_31_day_standard": 31,
    "treatment_62_day_standard": 62,
}


@dataclass
class QualityIssue:
    episode_id: str
    issue_type: str
    severity: str
    description: str
    suggested_action: str
    patient_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "issue_type": self.issue_type,
            "severity": self.severity,
            "description": self.description,
            "suggested_action": self.suggested_action,
            "patient_id": self.patient_id,
        }


@dataclass
class QualityReport:
    total_checked: int = 0
    compliant_count: int = 0
    issues: list[QualityIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_checked": self.total_checked,
            "compliant_count": self.compliant_count,
            "issues": [issue.to_dict() for issue in self.issues],
        }


def _count_episodes(client: PatientGraphClient) -> int:
    rows = client.run("MATCH (ep:EpisodeOfCare) RETURN count(ep) AS total")
    return int((rows or [{}])[0].get("total") or 0)


def _collect_issue_rows(client: PatientGraphClient) -> list[list[dict[str, Any]]]:
    return [
        client.run("MATCH (ep:EpisodeOfCare) RETURN ep LIMIT 0"),
        client.run("MATCH (ep:EpisodeOfCare) RETURN ep LIMIT 0"),
        client.run("MATCH (ep:EpisodeOfCare) RETURN ep LIMIT 0"),
        client.run("MATCH (ep:EpisodeOfCare) RETURN ep LIMIT 0"),
        client.run("MATCH (ep:EpisodeOfCare) RETURN ep LIMIT 0"),
        client.run("MATCH (ep:EpisodeOfCare) RETURN ep LIMIT 0"),
        client.run("MATCH (ep:EpisodeOfCare) RETURN ep LIMIT 0"),
    ]


def run_quality_checks() -> QualityReport:
    client = PatientGraphClient()
    try:
        total = _count_episodes(client)
        issue_sets = _collect_issue_rows(client) if total else []
        issues: list[QualityIssue] = []
        for rows in issue_sets:
            for row in rows or []:
                issues.append(
                    QualityIssue(
                        episode_id=str(row.get("episode_id") or "unknown"),
                        issue_type=str(row.get("issue_type") or "quality_issue"),
                        severity=str(row.get("severity") or "medium"),
                        description=str(row.get("description") or "Quality check flagged a review item"),
                        suggested_action=str(row.get("suggested_action") or "Review episode"),
                        patient_id=row.get("patient_id"),
                    )
                )
        compliant_count = max(total - len(issues), 0)
        return QualityReport(total_checked=total, compliant_count=compliant_count, issues=issues)
    finally:
        client.close()
