"""Tests for SPoA / RAS Validation Lab scenario materialisation."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from libs.validation_lab.models import (
    AgConversationTurn,
    EncounterSpec,
    PmhItem,
    ValidationCaseSpec,
)
from libs.validation_lab.scaffold import (
    _resolve_referral_submission_text,
    materialise_case,
)


def test_ras_referral_composes_reason_and_verbalised_pmh() -> None:
    spec = ValidationCaseSpec(
        case_id="ras-1",
        title="RAS case",
        case_type="referral",
        scenario_type="ras_referral",
        reason_for_submission="Please assess lower GI symptoms",
        pmh=[PmhItem(category="condition", concept_id="c1", term="Asthma")],
    )
    pools = {
        "c1": {"surface_forms": ["asthma"], "synonyms": [], "preferred_term": "Asthma"}
    }
    with patch(
        "libs.validation_lab.scaffold.compose_submission_text",
        return_value="Please assess lower GI symptoms\n\nPast medical history: asthma.",
    ) as compose:
        text = _resolve_referral_submission_text(spec, knowledge_client=MagicMock())
    assert "Please assess lower GI symptoms" in text
    assert "asthma" in text.lower()
    compose.assert_called_once()
    assert compose.call_args.kwargs["pmh"] == spec.pmh


def test_generic_referral_still_uses_picker_terms() -> None:
    spec = ValidationCaseSpec(
        case_id="gen-1",
        title="Generic",
        case_type="referral",
        scenario_type="generic",
        referral_text="Referral body",
        pmh=[PmhItem(category="condition", concept_id="c1", term="Asthma (disorder)")],
    )
    text = _resolve_referral_submission_text(spec)
    assert "Past medical history: Asthma (disorder)." in text
    assert "Referral body" in text


def test_materialise_ras_without_gp_encounter_auto_builds() -> None:
    client = MagicMock()
    client.run.return_value = [
        {
            "patient_id": "lab-ras-2:patient",
            "practice_id": "lab-ras-2:practice",
            "episode_id": "lab-ras-2:episode-primary",
        }
    ]
    spec = ValidationCaseSpec(
        case_id="ras-2",
        title="RAS",
        case_type="referral",
        scenario_type="ras_referral",
        reason_for_submission="Reason",
        referral_text="unused when reason set",
    )
    with (
        patch(
            "libs.validation_lab.scaffold.scaffold_referral",
            return_value=["chunk-1"],
        ),
        patch(
            "libs.validation_lab.scaffold.compose_submission_text",
            return_value="Reason",
        ),
    ):
        graph = materialise_case(client, spec, knowledge_client=MagicMock())
    assert graph["gp_encounter_id"] == "lab-ras-2:gp-consultation"
    assert graph["practice_id"]


def test_materialise_ras_writes_gp_and_epr() -> None:
    client = MagicMock()
    session = MagicMock()
    client.session.return_value.__enter__.return_value = session
    client.run.return_value = [
        {
            "patient_id": "lab-ras-3:patient",
            "practice_id": "lab-ras-3:practice",
            "episode_id": "lab-ras-3:episode-primary",
        }
    ]
    spec = ValidationCaseSpec(
        case_id="ras-3",
        title="RAS",
        case_type="referral",
        scenario_type="ras_referral",
        reason_for_submission="Reason",
        gp_encounter=EncounterSpec(text="GP note about cough"),
        pmh=[],
    )
    with (
        patch(
            "libs.validation_lab.scaffold.scaffold_referral",
            return_value=["chunk-1"],
        ),
        patch(
            "libs.validation_lab.scaffold.compose_submission_text",
            return_value="Reason",
        ),
    ):
        graph = materialise_case(client, spec, knowledge_client=MagicMock())
    assert graph["gp_encounter_id"] == "lab-ras-3:gp-consultation"
    assert graph["practice_id"]
    assert graph["submission_text"] == "Reason"


def test_spo_ag_injects_verbalised_pmh_into_first_requester() -> None:
    from libs.validation_lab.ag_scaffold import _spo_ag_thread

    spec = ValidationCaseSpec(
        case_id="ag-1",
        title="SPoA A&G",
        case_type="ag",
        scenario_type="spo_ag",
        reason_for_submission="Please advise",
        pmh=[PmhItem(category="condition", concept_id="c1", term="Asthma")],
        ag_thread=[AgConversationTurn(category="REQUESTER", note="ignored")],
    )
    with patch(
        "libs.validation_lab.pmh_verbalisation.compose_submission_text",
        return_value="Please advise\n\nPast medical history: asthma.",
    ):
        turns = _spo_ag_thread(spec, knowledge_client=MagicMock())
    assert turns[0].category == "REQUESTER"
    assert "Please advise" in turns[0].note
    assert "asthma" in turns[0].note.lower()
