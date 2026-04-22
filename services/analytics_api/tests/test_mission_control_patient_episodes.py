"""VT-DAEE0DFD: GET /mission-control/patients/{patient_id}/episodes.

Verifies the new per-patient drawer endpoint that returns the full
EpisodeOfCare list regardless of cohort filter (DI-5E47FA5D).

Test cases:
  TC-001  shape and projection match the cohort list per-episode shape
  TC-002  all lifecycle buckets (in_review, active, confirmed_cancer,
          cancer_excluded, closed) are returned -- no cohort predicate
  TC-003  malformed patient id -> HTTP 400
  TC-004  out-of-scope / unknown patient -> HTTP 404
  TC-005  empty episode list returned for a known patient with no
          episodes (200, episodes=[])
  TC-006  Cypher does NOT reference any cohort filter helpers
          (lifecycle bucket / pathway / review / cancer_types /
          closure_reasons) -- static-source guarantee
"""

from __future__ import annotations

import inspect

import pytest
from fastapi import HTTPException

from libs.auth.org_scope import CallerScope


# ---------------------------------------------------------------------------
# Shared fakes
# ---------------------------------------------------------------------------


class _FakeClient:
    """In-memory PatientGraphClient stub.

    `responses` is a list of dicts that will be returned in order for
    each `.run(...)` call. The endpoint only issues one query per
    request, so this is normally a list of a single dict.
    """

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def run(self, query, **kwargs):
        self.calls.append((query, kwargs))
        if not self.responses:
            return []
        return self.responses.pop(0)

    def close(self):
        return None


def _scope() -> CallerScope:
    return CallerScope(
        email="qa@example.com",
        is_admin=False,
        org_ids=["org-1"],
        scope_type="gp",
        primary_org_id="org-1",
    )


def _episode_row(**overrides):
    """Build an EpisodeOfCare projection row matching _EPISODE_PROJECTION."""
    base = {
        "episode_id": "ep-1",
        "cancer_type": None,
        "condition_type": None,
        "status": "in_review",
        "cancer_stage": None,
        "referral_date": "2026-04-01",
        "end_date": None,
        "specialist_visit_date": None,
        "diagnostic_interval_days": None,
        "primary_care_interval_days": None,
        "inferred_outcome": None,
        "auto_close_reason": None,
        "reviewed_by": None,
        "reviewed_at": None,
        "audit_notes": None,
        "audit_flag": False,
        "linked_encounter_ids": [],
        "milestones": [],
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# TC-001: response shape mirrors the cohort list projection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_returns_full_projection_for_in_scope_patient(monkeypatch):
    """VT-DAEE0DFD-TC-001: response episodes match _EPISODE_PROJECTION."""
    from services.analytics_api.app.routers import mission_control as mc

    rows = [
        {
            "patient_id": "4181221113",
            "episodes": [_episode_row(episode_id="ep-A")],
        }
    ]
    fake = _FakeClient([rows])
    monkeypatch.setattr(mc, "PatientGraphClient", lambda: fake)

    result = await mc.get_patient_episodes(
        patient_id="4181221113", org_id="org-1", scope=_scope()
    )

    assert result["patient_id"] == "4181221113"
    assert len(result["episodes"]) == 1
    ep = result["episodes"][0]
    expected_keys = {
        "episode_id",
        "cancer_type",
        "condition_type",
        "status",
        "cancer_stage",
        "referral_date",
        "end_date",
        "specialist_visit_date",
        "diagnostic_interval_days",
        "primary_care_interval_days",
        "inferred_outcome",
        "auto_close_reason",
        "reviewed_by",
        "reviewed_at",
        "audit_notes",
        "audit_flag",
        "linked_encounter_ids",
        "milestones",
    }
    assert expected_keys.issubset(ep.keys())


# ---------------------------------------------------------------------------
# TC-002: all lifecycle buckets are returned -- no cohort filter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_returns_episodes_of_every_status(monkeypatch):
    """VT-DAEE0DFD-TC-002: in_review + active + confirmed_cancer all returned."""
    from services.analytics_api.app.routers import mission_control as mc

    rows = [
        {
            "patient_id": "4181221113",
            "episodes": [
                _episode_row(episode_id="ep-in-review", status="in_review"),
                _episode_row(episode_id="ep-active", status="active"),
                _episode_row(
                    episode_id="ep-confirmed",
                    status="confirmed_cancer",
                    cancer_type="lung",
                    cancer_stage="II",
                ),
                _episode_row(
                    episode_id="ep-excluded", status="cancer_excluded"
                ),
                _episode_row(
                    episode_id="ep-closed",
                    status="closed_no_cancer",
                    end_date="2026-03-30",
                ),
            ],
        }
    ]
    fake = _FakeClient([rows])
    monkeypatch.setattr(mc, "PatientGraphClient", lambda: fake)

    result = await mc.get_patient_episodes(
        patient_id="4181221113", org_id="org-1", scope=_scope()
    )

    statuses = {e["status"] for e in result["episodes"]}
    assert statuses == {
        "in_review",
        "active",
        "confirmed_cancer",
        "cancer_excluded",
        "closed_no_cancer",
    }


# ---------------------------------------------------------------------------
# TC-003: malformed patient id -> 400
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_malformed_patient_id_returns_400(monkeypatch):
    """VT-DAEE0DFD-TC-003: invalid patient_id raises HTTPException 400."""
    from services.analytics_api.app.routers import mission_control as mc

    monkeypatch.setattr(mc, "PatientGraphClient", lambda: _FakeClient([]))

    with pytest.raises(HTTPException) as exc:
        await mc.get_patient_episodes(
            patient_id="!!nope!!", org_id=None, scope=_scope()
        )
    assert exc.value.status_code == 400


# ---------------------------------------------------------------------------
# TC-004: out-of-scope / unknown patient -> 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_out_of_scope_patient_returns_404(monkeypatch):
    """VT-DAEE0DFD-TC-004: empty result rows -> HTTP 404."""
    from services.analytics_api.app.routers import mission_control as mc

    fake = _FakeClient([[]])
    monkeypatch.setattr(mc, "PatientGraphClient", lambda: fake)

    with pytest.raises(HTTPException) as exc:
        await mc.get_patient_episodes(
            patient_id="4181221113", org_id="org-1", scope=_scope()
        )
    assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# TC-005: known patient with no episodes returns 200 with empty list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_known_patient_with_no_episodes_returns_empty_list(monkeypatch):
    """VT-DAEE0DFD-TC-005: patient with no EoCs -> 200, episodes=[]."""
    from services.analytics_api.app.routers import mission_control as mc

    rows = [{"patient_id": "4181221113", "episodes": []}]
    fake = _FakeClient([rows])
    monkeypatch.setattr(mc, "PatientGraphClient", lambda: fake)

    result = await mc.get_patient_episodes(
        patient_id="4181221113", org_id="org-1", scope=_scope()
    )
    assert result == {"patient_id": "4181221113", "episodes": []}


# ---------------------------------------------------------------------------
# TC-006: static-source guarantee -- no cohort filter helpers used
# ---------------------------------------------------------------------------


def test_endpoint_does_not_apply_any_cohort_filter():
    """VT-DAEE0DFD-TC-006: Cypher must not call cohort-filter helpers.

    The whole point of DI-5E47FA5D is to bypass the dashboard cohort
    filter. Static-source assertion: the endpoint must not reference
    any of the cohort-filter helpers used by the patient list query.
    """
    from services.analytics_api.app.routers import mission_control as mc

    source = inspect.getsource(mc.get_patient_episodes)
    # Strip the docstring so explanatory text doesn't trip the check.
    code_lines = [
        ln for ln in source.splitlines()
        if not ln.lstrip().startswith(("#", '"""', "'''"))
    ]
    code_only = "\n".join(code_lines)

    forbidden_helpers = [
        "_apply_lifecycle_bucket_filter",
        "_apply_pathway_filter",
        "_apply_review_filter",
        "_apply_cancer_type_filter",
        "_apply_closure_reason_filter",
        "_build_filtered_base",
    ]
    for token in forbidden_helpers:
        assert token not in code_only, (
            f"get_patient_episodes must not call {token!r} "
            "(DI-5E47FA5D requires the drawer endpoint to bypass the "
            "cohort filter)"
        )

    # And it MUST mirror the shared projection so the per-episode
    # shape matches the cohort list endpoint.
    assert "_EPISODE_PROJECTION" in source
    assert "OPTIONAL MATCH (p)-[:HAS_EPISODE_OF_CARE]" in source
