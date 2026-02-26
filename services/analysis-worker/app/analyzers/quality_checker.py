"""Quality Checker.

Ported from VRB clinical-ai/app/agent/subagents/quality_checker.py.

Checks completed episodes for:
- Duration outliers (>= 2 std dev by cancer type)
- Missing milestones
- NHS wait time target breaches
- Low confidence flags
- Temporal anomalies
- Unactioned CSS alerts
- Coding contradictions

Persists findings as QualityIssue graph nodes for the review queue.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from uuid import uuid4

from libs.neo4j_client.client import PatientGraphClient

logger = logging.getLogger(__name__)

_PATIENT_LEVEL = "PATIENT_LEVEL"

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
    patient_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "patient_id": self.patient_id,
            "issue_type": self.issue_type,
            "severity": self.severity,
            "description": self.description,
            "suggested_action": self.suggested_action,
        }


@dataclass
class QualityReport:
    issues: List[QualityIssue] = field(default_factory=list)
    total_checked: int = 0
    compliant_count: int = 0
    summary: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "issues": [i.to_dict() for i in self.issues],
            "total_checked": self.total_checked,
            "compliant_count": self.compliant_count,
            "summary": self.summary,
        }


def run_quality_checks(
    patient_id: Optional[str] = None,
    org_id: Optional[str] = None,
    limit: int = 100,
) -> QualityReport:
    """Run comprehensive quality checks on cancer episodes."""
    report = QualityReport()
    client = PatientGraphClient()

    try:
        _count_episodes(client, report, patient_id, org_id)
        _check_outliers(client, report, patient_id, org_id, limit)
        _check_missing_milestones(client, report, patient_id, org_id, limit)
        _check_nhs_targets(client, report, patient_id, org_id)
        _check_low_confidence(client, report, patient_id, org_id, limit)
        _check_temporal_anomalies(client, report, patient_id, org_id, limit)
        _check_unactioned_css(client, report, patient_id, org_id)
        _check_coding_contradictions(client, report, patient_id, org_id)

        episode_ids_with_issues = {i.episode_id for i in report.issues}
        report.compliant_count = max(0, report.total_checked - len(episode_ids_with_issues))

        _persist_report(client, report, org_id)
    finally:
        client.close()

    logger.info(
        "Quality check complete: %d issues across %d episodes (%d compliant)",
        len(report.issues), report.total_checked, report.compliant_count,
    )
    return report


def _where(patient_id: Optional[str], org_id: Optional[str]) -> tuple[str, dict]:
    parts = []
    params: Dict[str, Any] = {}
    if patient_id:
        parts.append("ep.patient_id = $pid")
        params["pid"] = patient_id
    if org_id:
        parts.append("ep.tenantId = $org")
        params["org"] = org_id
    where = f"WHERE {' AND '.join(parts)}" if parts else ""
    return where, params


def _count_episodes(client: PatientGraphClient, report: QualityReport, pid: Optional[str], org: Optional[str]):
    where, params = _where(pid, org)
    rows = client.run(f"MATCH (ep:CancerEpisode) {where} RETURN count(ep) AS total", **params)
    report.total_checked = rows[0]["total"] if rows else 0
    report.summary["total_episodes"] = report.total_checked


def _check_outliers(client: PatientGraphClient, report: QualityReport, pid: Optional[str], org: Optional[str], limit: int):
    where, params = _where(pid, org)
    params["lim"] = limit
    rows = client.run(
        f"MATCH (ep:CancerEpisode) {where} "
        "WHERE ep.kpi_days_referral_to_diagnosis IS NOT NULL "
        "WITH ep.cancer_type AS ct, avg(ep.kpi_days_referral_to_diagnosis) AS m, "
        "     stDev(ep.kpi_days_referral_to_diagnosis) AS sd "
        "MATCH (ep2:CancerEpisode) WHERE ep2.cancer_type = ct "
        "AND ep2.kpi_days_referral_to_diagnosis > m + 2*sd "
        "RETURN ep2.episode_id AS episode_id, ep2.patient_id AS patient_id, "
        "       ep2.cancer_type AS cancer_type, ep2.kpi_days_referral_to_diagnosis AS days, "
        "       m AS mean_days, sd AS stddev_days LIMIT $lim",
        **params,
    )
    for r in rows:
        report.issues.append(QualityIssue(
            episode_id=r["episode_id"], patient_id=r.get("patient_id", ""),
            issue_type="outlier", severity="high",
            description=f"Duration {r['days']:.0f}d is >= 2 std dev above mean ({r['mean_days']:.0f} +/- {r['stddev_days']:.0f}) for {r['cancer_type']}",
            suggested_action="Review and reprocess this episode",
        ))


def _check_missing_milestones(client: PatientGraphClient, report: QualityReport, pid: Optional[str], org: Optional[str], limit: int):
    where, params = _where(pid, org)
    params["lim"] = limit
    rows = client.run(
        f"MATCH (ep:CancerEpisode) {where} "
        "WHERE ep.status = 'confirmed' "
        "OPTIONAL MATCH (enc:Encounter)-[r:IS_PART_OF]->(ep) "
        "WITH ep, collect(r.milestone_type) AS milestones "
        "WITH ep, milestones, "
        "  [m IN ['presentation','referral','diagnosis'] WHERE NOT m IN milestones] AS missing "
        "WHERE size(missing) > 0 "
        "RETURN ep.episode_id AS episode_id, ep.patient_id AS patient_id, "
        "       ep.cancer_type AS cancer_type, missing LIMIT $lim",
        **params,
    )
    for r in rows:
        missing_str = ", ".join(r.get("missing", []))
        report.issues.append(QualityIssue(
            episode_id=r["episode_id"], patient_id=r.get("patient_id", ""),
            issue_type="missing_milestone", severity="high",
            description=f"Missing milestones: {missing_str} for {r.get('cancer_type', 'Unknown')}",
            suggested_action="Review encounter timeline and fill missing milestones",
        ))


def _check_nhs_targets(client: PatientGraphClient, report: QualityReport, pid: Optional[str], org: Optional[str]):
    where, params = _where(pid, org)
    params["fds"] = NHS_TARGETS["faster_diagnosis_standard"]
    rows = client.run(
        f"MATCH (ep:CancerEpisode) {where} "
        "WHERE ep.status = 'confirmed' AND ep.kpi_days_referral_to_diagnosis IS NOT NULL "
        "AND ep.kpi_days_referral_to_diagnosis > $fds "
        "RETURN ep.episode_id AS episode_id, ep.patient_id AS patient_id, "
        "       ep.cancer_type AS cancer_type, ep.kpi_days_referral_to_diagnosis AS days "
        "LIMIT 100",
        **params,
    )
    for r in rows:
        report.issues.append(QualityIssue(
            episode_id=r["episode_id"], patient_id=r.get("patient_id", ""),
            issue_type="wait_time_breach", severity="high",
            description=f"Referral-to-diagnosis: {r['days']:.0f}d (target: {params['fds']}d) for {r.get('cancer_type', 'Unknown')}",
            suggested_action="Review for avoidable delays",
        ))


def _check_low_confidence(client: PatientGraphClient, report: QualityReport, pid: Optional[str], org: Optional[str], limit: int):
    where, params = _where(pid, org)
    params.update({"threshold": 70, "lim": limit})
    rows = client.run(
        f"MATCH (ep:CancerEpisode) {where} "
        "WHERE ep.confidence IS NOT NULL AND ep.confidence < $threshold "
        "RETURN ep.episode_id AS episode_id, ep.patient_id AS patient_id, "
        "       ep.cancer_type AS cancer_type, ep.confidence AS confidence LIMIT $lim",
        **params,
    )
    for r in rows:
        report.issues.append(QualityIssue(
            episode_id=r["episode_id"], patient_id=r.get("patient_id", ""),
            issue_type="low_confidence", severity="medium",
            description=f"Confidence {r.get('confidence', 'N/A')} below 70% for {r.get('cancer_type', 'Unknown')}",
            suggested_action="Review episode classification and evidence",
        ))


def _check_temporal_anomalies(client: PatientGraphClient, report: QualityReport, pid: Optional[str], org: Optional[str], limit: int):
    where, params = _where(pid, org)
    params["lim"] = limit
    rows = client.run(
        f"MATCH (ep:CancerEpisode) {where} "
        "WHERE ep.referral_date IS NOT NULL AND ep.diagnosis_date IS NOT NULL "
        "AND date(ep.diagnosis_date) < date(ep.referral_date) "
        "RETURN ep.episode_id AS episode_id, ep.patient_id AS patient_id, "
        "       ep.cancer_type AS cancer_type LIMIT $lim",
        **params,
    )
    for r in rows:
        report.issues.append(QualityIssue(
            episode_id=r["episode_id"], patient_id=r.get("patient_id", ""),
            issue_type="temporal_anomaly", severity="high",
            description=f"Diagnosis before referral for {r.get('cancer_type', 'Unknown')}",
            suggested_action="Review milestone dates and correct ordering",
        ))


def _check_unactioned_css(client: PatientGraphClient, report: QualityReport, pid: Optional[str], org: Optional[str]):
    if pid:
        match = "MATCH (a:CSSAlert) WHERE a.patient_id = $pid"
        params: Dict[str, Any] = {"pid": pid}
    elif org:
        match = "MATCH (a:CSSAlert) WHERE a.tenantId = $org"
        params = {"org": org}
    else:
        match = "MATCH (a:CSSAlert)"
        params = {}

    rows = client.run(
        f"{match} AND a.actioned = false AND a.severity = 'critical' "
        "RETURN a.episode_id AS episode_id, a.patient_id AS patient_id, "
        "       a.type AS rule_name LIMIT 200",
        **params,
    )
    for r in rows:
        report.issues.append(QualityIssue(
            episode_id=r.get("episode_id", _PATIENT_LEVEL),
            patient_id=r.get("patient_id", ""),
            issue_type="unactioned_css_alert", severity="high",
            description=f"Unactioned critical CSS alert: {r.get('rule_name', 'Unknown')}",
            suggested_action="Review CSS alert and action or document reason for no action",
        ))


def _check_coding_contradictions(client: PatientGraphClient, report: QualityReport, pid: Optional[str], org: Optional[str]):
    where, params = _where(pid, org)
    rows = client.run(
        f"MATCH (ep:CancerEpisode) {where} WHERE ep.status = 'confirmed' "
        "MATCH (ep)<-[:IS_PART_OF]-(enc:Encounter)-[r:DOCUMENTS]->(c) "
        "WHERE r.is_positive = true "
        "WITH ep, collect(c.conceptId) AS cids "
        "WHERE any(cid IN cids WHERE cid IN [415068001, 161451009]) "
        "  AND any(cid IN cids WHERE cid IN [182992009, 363679005, 108290001, 373808002, 363706009]) "
        "RETURN ep.episode_id AS episode_id, ep.patient_id AS patient_id, "
        "       ep.cancer_type AS cancer_type LIMIT 200",
        **params,
    )
    for r in rows:
        report.issues.append(QualityIssue(
            episode_id=r["episode_id"], patient_id=r.get("patient_id", ""),
            issue_type="coding_contradiction", severity="high",
            description=f"Contradictory codes for {r.get('cancer_type', 'Unknown')}: treatment co-exists with no-evidence-of-cancer",
            suggested_action="Review and correct conflicting codes",
        ))


def _persist_report(client: PatientGraphClient, report: QualityReport, org_id: Optional[str]):
    run_id = uuid4().hex[:12]
    for issue in report.issues:
        try:
            client.run(
                "MERGE (qi:QualityIssue {issue_id: $iid}) "
                "SET qi.run_id = $run, qi.episode_id = $eid, qi.patient_id = $pid, "
                "    qi.issue_type = $type, qi.severity = $sev, "
                "    qi.description = $desc, qi.suggested_action = $action, "
                "    qi.created_at = datetime()",
                iid=f"QI_{run_id}_{uuid4().hex[:8]}",
                run=run_id, eid=issue.episode_id, pid=issue.patient_id,
                type=issue.issue_type, sev=issue.severity,
                desc=issue.description, action=issue.suggested_action,
            )
        except Exception:
            logger.warning("Failed to persist quality issue", exc_info=True)
