from __future__ import annotations

from libs.auth.org_scope import CallerScope
from services.analytics_api.app.routers import audit


def test_audit_summary_guards_empty_temporal_strings(monkeypatch):
    class _FakeClient:
        def run(self, query, **kwargs):
            assert "trim(coalesce(toString(ep.referral_date), '')) = ''" in query
            assert "trim(coalesce(toString(ep.first_presentation_date), '')) = ''" in query
            assert "referral_date_value IS NOT NULL" in query
            return [
                {
                    "ep_status": "completed",
                    "fp_date": "2025-01-01",
                    "ref_date": "2025-01-05",
                    "sn": True,
                    "diag_date": "2025-01-20",
                    "diag_is_inferred": False,
                    "is_confirmed": True,
                    "consultation_count": 2,
                }
            ]

        def close(self):
            return None

    monkeypatch.setattr(audit, "PatientGraphClient", _FakeClient)
    scope = CallerScope(
        email="qa@example.com",
        is_admin=False,
        org_ids=["org-1"],
        scope_type="gp",
        primary_org_id="org-1",
    )

    result = audit.audit_summary(scope=scope, org_id="org-1")
    assert result["total_episodes"] == 1
    assert result["confirmed_cancers"] == 1
    assert result["median_di_days"] == 19.0
