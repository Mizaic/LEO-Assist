"""Verification tests for benign/normal qualifier episode closure.

Covers VT-LEO-AI-103 (DI-LEO-AI-103, R-LEO-AI-071).
"""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest

from services.analysis_worker.app.analyzers.anchor_detector import AnchorResult
from services.analysis_worker.app.analyzers.episode_builder import build_episodes


def _days_after(base: str, days: int) -> str:
    return (date.fromisoformat(base) + timedelta(days=days)).isoformat()


def _referral(enc_date: str) -> dict:
    return {
        "concept_id": 276341000000100,
        "concept_name": "Fast track referral for suspected breast cancer (procedure)",
        "encounter_date": enc_date,
        "encounter_id": f"enc-ref-{enc_date}",
        "assertion": "present",
    }


def _diagnosis(enc_date: str, concept_id: int, concept_name: str) -> dict:
    return {
        "concept_id": concept_id,
        "concept_name": concept_name,
        "encounter_date": enc_date,
        "encounter_id": f"enc-diag-{enc_date}",
        "assertion": "present",
    }


def _qualifier_side_effect(finding_rows: list[dict]):
    def _side_effect(query, **kwargs):
        if "MERGE (ep:EpisodeOfCare" in str(query):
            return []
        if "toLower(coalesce(c_f.semanticTag" in str(query):
            return finding_rows
        return []

    return _side_effect


def _find_episode_call(client: MagicMock, referral_date: str) -> dict | None:
    for call in client.run.call_args_list:
        args, kwargs = call
        if not args or "MERGE (ep:EpisodeOfCare" not in str(args[0]):
            continue
        if kwargs.get("referral_date") == referral_date:
            return kwargs
    return None


@pytest.mark.asyncio
async def test_site_matched_benign_qualifier_closes_open_episode():
    ref_date = "2024-07-01"
    qualifier_date = _days_after(ref_date, 25)
    anchors = AnchorResult(
        patient_id="test-patient",
        referral_anchors=[_referral(ref_date)],
    )
    client = MagicMock()
    client.run.side_effect = _qualifier_side_effect(
        [
            {
                "encounter_id": f"enc-q-{qualifier_date}",
                "encounter_date": qualifier_date,
                "concept_id": 89164003,
                "concept_name": "Breast lump (finding)",
            }
        ]
    )

    result = await build_episodes(
        "test-patient", anchors, client, domain_id="cancer_audit"
    )

    assert result.episodes_created == 1
    merge_kwargs = _find_episode_call(client, ref_date)
    assert merge_kwargs is not None
    assert merge_kwargs["status"] == "closed_benign_qualifier"
    assert merge_kwargs["end_date"] == qualifier_date
    assert merge_kwargs["hitl_flag"] is True
    assert "benign/normal qualifier" in str(merge_kwargs.get("hitl_reason") or "")


@pytest.mark.asyncio
async def test_site_mismatched_benign_qualifier_does_not_close_episode():
    ref_date = "2024-07-01"
    qualifier_date = _days_after(ref_date, 25)
    anchors = AnchorResult(
        patient_id="test-patient",
        referral_anchors=[_referral(ref_date)],
    )
    client = MagicMock()
    client.run.side_effect = _qualifier_side_effect(
        [
            {
                "encounter_id": f"enc-q-{qualifier_date}",
                "encounter_date": qualifier_date,
                "concept_id": 266569009,
                "concept_name": "Benign prostatic hyperplasia (disorder)",
            }
        ]
    )

    await build_episodes("test-patient", anchors, client, domain_id="cancer_audit")
    merge_kwargs = _find_episode_call(client, ref_date)
    assert merge_kwargs is not None
    assert merge_kwargs["status"] == "in_progress"
    assert merge_kwargs["end_date"] is None


@pytest.mark.asyncio
async def test_competing_cancer_diagnosis_suppresses_benign_qualifier_closure():  # noqa: E501
    ref_date = "2024-07-01"
    qualifier_date = _days_after(ref_date, 20)
    diagnosis_date = _days_after(ref_date, 30)
    anchors = AnchorResult(
        patient_id="test-patient",
        referral_anchors=[_referral(ref_date)],
        diagnosis_anchors=[
            _diagnosis(
                diagnosis_date,
                363358000,
                "Malignant neoplasm of lung (disorder)",
            )
        ],
    )
    client = MagicMock()
    client.run.side_effect = _qualifier_side_effect(
        [
            {
                "encounter_id": f"enc-q-{qualifier_date}",
                "encounter_date": qualifier_date,
                "concept_id": 89164003,
                "concept_name": "Breast lump (finding)",
            }
        ]
    )

    await build_episodes("test-patient", anchors, client, domain_id="cancer_audit")
    merge_kwargs = _find_episode_call(client, ref_date)
    assert merge_kwargs is not None
    # DI-LEO-AI-136: under the Pass 2 fallback, the competing cancer
    # diagnosis (lung) claims the breast referral because it is the
    # only unclaimed referral in window. The episode is therefore
    # ``completed`` not ``in_progress``. The original intent of the
    # test still holds: the benign breast qualifier MUST NOT close
    # this episode as benign when a competing cancer diagnosis exists.
    assert merge_kwargs["status"] != "closed_benign_qualifier"
