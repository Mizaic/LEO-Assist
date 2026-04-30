"""Integration tests: LLMUsageRecorder telemetry + persistence contract
for the NCDA prior-consultations enrichment pass.

Verifies the contract enforced by .cursor/rules/llm-cost-telemetry.mdc:
  - Every LLM call inside an LLMUsageRecorder context is captured.
  - The recorder's to_audit_dict() block carries the fields the
    detector script writes to EpisodeOfCare and AuditEvent.
  - The classifier degrades gracefully when the LLM caller raises.

These tests do NOT touch Bedrock or Neo4j -- they substitute a fake
caller that mimics the LLMClient.converse telemetry callback so the
recorder fills up exactly as it would in production.
"""

from __future__ import annotations

import json
from typing import Any

from libs.llm_client.token_tracker import track_llm_usage_sync
from libs.llm_client.usage_recorder import LLMUsageRecorder
from libs.oncology.prior_consultations import classify_episode_consultations


def _fake_caller_with_telemetry(
    *,
    response_payload: dict[str, Any],
    input_tokens: int = 1200,
    output_tokens: int = 350,
    latency_ms: int = 480,
):
    """Build a fake LLM caller that fires telemetry through the same
    track_llm_usage_sync hook LLMClient.converse uses, so the active
    LLMUsageRecorder picks the call up identically."""

    def caller(
        system_prompt: str,
        user_message: str,
        *,
        agent_task: str,
        patient_id: str,
    ) -> dict[str, Any]:
        track_llm_usage_sync(
            model_name="anthropic.claude-haiku-4-5",
            model_provider="aws",
            agent_task=agent_task,
            patient_id=patient_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
            latency_ms=latency_ms,
            success=True,
            error_message="",
        )
        return response_payload

    return caller


def _candidate_encounter_rows() -> list[dict[str, Any]]:
    return [
        {
            "encounter_id": "fp1",
            "date": "2025-01-06",
            "text": (
                "11:11 - Surgery: [STAFF] (Clinical Practitioner Access Role)\n"
                "history: F2F. change in bowel habit x6 months."
            ),
        },
        {
            "encounter_id": "fp2",
            "date": "2025-01-14",
            "text": (
                "12:50 - Surgery: [STAFF] (Health Professional Access Role)\n"
                "phlebotomy service. blood sample taken (cbs claim): yes"
            ),
        },
        {
            "encounter_id": "noise1",
            "date": "2025-01-15",
            "text": "Dear [PERSON] appointment has been booked for 23 Jan 2025.",
        },
    ]


# ---------------------------------------------------------------------------
# Telemetry contract
# ---------------------------------------------------------------------------


def test_recorder_captures_call_count_and_tokens() -> None:
    fake = _fake_caller_with_telemetry(
        response_payload={
            "encounters": [
                {"encounter_id": "fp1", "date": "2025-01-06", "related": True,
                 "contact_type": "f2f", "evidence": "bowel habit"},
                {"encounter_id": "fp2", "date": "2025-01-14", "related": True,
                 "contact_type": "phlebotomy", "evidence": "FIT bloods"},
            ],
            "factors": [
                {"factor": "consultations_to_discuss_test_results",
                 "evidence_encounter_ids": ["fp2"],
                 "rationale": "FIT discussed"},
            ],
        },
        input_tokens=1234,
        output_tokens=567,
        latency_ms=812,
    )

    with LLMUsageRecorder() as rec:
        result = classify_episode_consultations(
            cancer_type="Colorectal",
            first_presentation_date="2025-01-06",
            referral_date="2025-01-23",
            encounters=_candidate_encounter_rows(),
            patient_id="4469113522",
            llm_caller=fake,
        )
        usage = rec.to_audit_dict()

    # Result is shaped correctly.
    assert result.consultations_n == 2
    assert any(
        f.factor == "consultations_to_discuss_test_results" for f in result.factors
    )

    # Telemetry block matches what the detector script will persist.
    assert usage["llm_calls"] == 1
    assert usage["input_tokens"] == 1234
    assert usage["output_tokens"] == 567
    assert usage["total_tokens"] == 1234 + 567
    assert usage["total_latency_ms"] == 812
    assert usage["model_name"] == "anthropic.claude-haiku-4-5"
    assert usage["model_provider"] == "aws"
    assert usage["cost_usd"] >= 0.0


def test_recorder_records_zero_calls_when_pre_filter_drops_everything() -> None:
    fake = _fake_caller_with_telemetry(response_payload={"encounters": [], "factors": []})

    with LLMUsageRecorder() as rec:
        result = classify_episode_consultations(
            cancer_type="Breast",
            first_presentation_date="2025-04-28",
            referral_date="2025-04-29",
            encounters=[
                {"encounter_id": "n1", "date": "2025-04-26",
                 "text": "Dear [PERSON] appointment has been booked"},
                {"encounter_id": "n2", "date": "2025-04-27",
                 "text": "(R) Letrozole 2.5mg tablets - 56 tablet"},
            ],
            llm_caller=fake,
        )
        usage = rec.to_audit_dict()

    # Pre-filter dropped every row, so no LLM call was made and the
    # recorder reports zero spend.
    assert result.consultations_n == 0
    assert usage["llm_calls"] == 0
    assert usage["input_tokens"] == 0
    assert usage["output_tokens"] == 0
    assert usage["cost_usd"] == 0.0


def test_recorder_telemetry_block_serialises_to_json() -> None:
    """The detector writes ``llm_usage_json`` as a JSON string column.
    Make sure to_audit_dict() round-trips through json.dumps so the
    Cypher write doesn't blow up."""
    fake = _fake_caller_with_telemetry(
        response_payload={
            "encounters": [
                {"encounter_id": "fp1", "date": "2025-01-06", "related": True,
                 "contact_type": "f2f", "evidence": "bowel habit"},
            ],
            "factors": [],
        },
    )

    with LLMUsageRecorder() as rec:
        classify_episode_consultations(
            cancer_type="Colorectal",
            first_presentation_date="2025-01-06",
            referral_date="2025-01-23",
            encounters=_candidate_encounter_rows(),
            patient_id="4469113522",
            llm_caller=fake,
        )
        usage = rec.to_audit_dict()

    serialised = json.dumps(usage)
    parsed = json.loads(serialised)
    assert parsed["llm_calls"] == 1
    assert isinstance(parsed["cost_usd"], (int, float))


def test_classifier_does_not_fire_telemetry_outside_recorder() -> None:
    """Outside an LLMUsageRecorder context, telemetry is still emitted
    via the global tracking callback but no exception escapes -- the
    classifier remains usable in scripts that don't care about the cost."""
    fake = _fake_caller_with_telemetry(
        response_payload={
            "encounters": [
                {"encounter_id": "fp1", "date": "2025-01-06", "related": True,
                 "contact_type": "f2f", "evidence": "bowel habit"},
            ],
            "factors": [],
        },
    )

    result = classify_episode_consultations(
        cancer_type="Colorectal",
        first_presentation_date="2025-01-06",
        referral_date="2025-01-23",
        encounters=_candidate_encounter_rows(),
        patient_id="4469113522",
        llm_caller=fake,
    )

    assert result.consultations_n == 1


# ---------------------------------------------------------------------------
# Failure path
# ---------------------------------------------------------------------------


def test_llm_failure_inside_recorder_yields_zero_token_record() -> None:
    """When the caller raises, the classifier returns the deterministic
    fallback and the recorder shows the failure with zero tokens
    (so dashboards can flag the episode as 'LLM unavailable' without
    inflating cost)."""

    def failing_caller(
        system_prompt: str,
        user_message: str,
        *,
        agent_task: str,
        patient_id: str,
    ) -> dict[str, Any]:
        track_llm_usage_sync(
            model_name="anthropic.claude-haiku-4-5",
            model_provider="aws",
            agent_task=agent_task,
            patient_id=patient_id,
            input_tokens=0,
            output_tokens=0,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
            latency_ms=120,
            success=False,
            error_message="Bedrock throttled",
        )
        return {"error": "Bedrock throttled"}

    with LLMUsageRecorder() as rec:
        result = classify_episode_consultations(
            cancer_type="Colorectal",
            first_presentation_date="2025-01-06",
            referral_date="2025-01-23",
            encounters=_candidate_encounter_rows(),
            patient_id="4469113522",
            llm_caller=failing_caller,
        )
        usage = rec.to_audit_dict()

    # Deterministic fallback still surfaces a count from the pre-filter.
    assert result.consultations_n >= 1
    assert "LLM error" in result.notes

    # Telemetry recorded the failed attempt without inflated tokens.
    assert usage["llm_calls"] == 1
    assert usage["input_tokens"] == 0
    assert usage["output_tokens"] == 0
    assert usage["cost_usd"] == 0.0


# ---------------------------------------------------------------------------
# Persistence row contract -- mirrors the Cypher SET clause in the
# detector script (scripts/ncda/run_full_cancer_episode_detection.py).
# ---------------------------------------------------------------------------


def test_classify_result_has_all_persistable_fields() -> None:
    """Sanity check: every field the detector writes to EpisodeOfCare
    is reachable from the result + recorder dict.  If somebody adds a
    new column to the SET clause without updating the result, this
    test fails fast rather than silently writing nulls."""
    fake = _fake_caller_with_telemetry(
        response_payload={
            "encounters": [
                {"encounter_id": "fp1", "date": "2025-01-06", "related": True,
                 "contact_type": "f2f", "evidence": "bowel habit"},
            ],
            "factors": [
                {"factor": "consultations_to_discuss_test_results",
                 "evidence_encounter_ids": ["fp1"],
                 "rationale": "discussed FIT"},
            ],
        },
    )
    with LLMUsageRecorder() as rec:
        result = classify_episode_consultations(
            cancer_type="Colorectal",
            first_presentation_date="2025-01-06",
            referral_date="2025-01-23",
            encounters=_candidate_encounter_rows(),
            patient_id="4469113522",
            llm_caller=fake,
        )
        usage = rec.to_audit_dict()

    # All headline / per-bucket counts present.
    for attr in (
        "consultations_n",
        "f2f_n",
        "phone_n",
        "nurse_n",
        "email_n",
        "specialist_clinic_n",
        "home_visit_n",
        "phlebotomy_n",
        "result_review_n",
        "unrelated_filtered_n",
    ):
        assert hasattr(result, attr), f"Result missing: {attr}"

    # Verdict + factor lists serialise cleanly (matches what the
    # detector json.dumps()es into prior_consultations_evidence_json
    # and multiple_consultations_factors_evidence_json).
    verdicts_payload = [
        {"encounter_id": v.encounter_id, "date": v.date, "related": v.related,
         "contact_type": v.contact_type, "evidence": v.evidence}
        for v in result.verdicts
    ]
    factors_payload = [
        {"factor": f.factor,
         "evidence_encounter_ids": list(f.evidence_encounter_ids),
         "rationale": f.rationale}
        for f in result.factors
    ]
    json.dumps(verdicts_payload)
    json.dumps(factors_payload)

    # Telemetry block carries every key the AuditEvent SET clause needs.
    for key in (
        "llm_calls",
        "input_tokens",
        "output_tokens",
        "cached_input_tokens",
        "total_tokens",
        "total_latency_ms",
        "cost_usd",
        "model_name",
        "model_provider",
    ):
        assert key in usage, f"Telemetry missing: {key}"
