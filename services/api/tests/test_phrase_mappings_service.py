"""VT for DI-6BD7B681: two-person publish; drafts are not live."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.services import phrase_mappings as service


def _row(**overrides: object) -> dict:
    base = {
        "phrase_key": "psa",
        "normalized": "psa",
        "status": "review",
        "draft_action": "map",
        "draft_author": "engineer@example.com",
        "draft_concept_id": "1030791000000100",
        "draft_concept_term": "Prostate specific antigen level",
        "draft_reason": "",
        "extracted_tag": "procedure",
        "sample_span": "PSA",
    }
    base.update(overrides)
    return base


def test_save_exclude_draft_requires_reason() -> None:
    with pytest.raises(HTTPException) as exc:
        service.save_draft(
            "psa",
            action="exclude",
            actor="engineer@example.com",
            reason="",
        )
    assert exc.value.status_code == 400


def test_dismiss_rejects_non_inbox_phrase() -> None:
    client = MagicMock()
    client.run.return_value = []
    with patch.object(service, "_kg_client", return_value=client):
        with pytest.raises(HTTPException) as exc:
            service.dismiss_phrase("psa", actor="curator@example.com")
    assert exc.value.status_code == 409


def test_dismiss_removes_inbox_phrase() -> None:
    client = MagicMock()
    client.run.return_value = [{"phrase_key": "psa", "normalized": "psa"}]
    with patch.object(service, "_kg_client", return_value=client):
        result = service.dismiss_phrase("PSA", actor="curator@example.com")
    assert result["phrase_key"] == "psa"
    query = str(client.run.call_args.args[0])
    assert "DETACH DELETE" in query
    assert client.run.call_args.kwargs["phrase_key"] == "psa"


def test_publish_rejects_same_person() -> None:
    client = MagicMock()
    client.run.return_value = [_row()]
    with patch.object(service, "_kg_client", return_value=client):
        with pytest.raises(HTTPException) as exc:
            service.publish("psa", "engineer@example.com")
    assert exc.value.status_code == 403
    assert client.run.call_count == 1


def test_publish_rejects_non_admin_same_person_with_reason() -> None:
    client = MagicMock()
    client.run.return_value = [_row()]
    with patch.object(service, "_kg_client", return_value=client):
        with pytest.raises(HTTPException) as exc:
            service.publish(
                "psa",
                "engineer@example.com",
                is_platform_admin=False,
                break_glass_reason="No second reviewer on duty tonight",
            )
    assert exc.value.status_code == 403
    assert client.run.call_count == 1


def test_publish_allows_admin_same_person_with_reason() -> None:
    client = MagicMock()
    client.run.side_effect = [
        [_row()],
        [{"phrase_key": "psa", "status": "closed", "draft_action": "map"}],
    ]
    with (
        patch.object(service, "_kg_client", return_value=client),
        patch.object(service, "_publish_map") as publish_map,
        patch("libs.auth.break_glass.emit_break_glass") as audit,
    ):
        result = service.publish(
            "psa",
            "engineer@example.com",
            is_platform_admin=True,
            break_glass_reason="No second reviewer on duty tonight",
        )
    publish_map.assert_called_once()
    audit.assert_called_once()
    assert result["status"] == "closed"


def test_publish_map_calls_upsert_then_close() -> None:
    client = MagicMock()
    client.run.side_effect = [
        [_row()],
        [{"phrase_key": "psa", "status": "closed", "draft_action": "map"}],
    ]
    with (
        patch.object(service, "_kg_client", return_value=client),
        patch.object(service, "_publish_map") as publish_map,
    ):
        result = service.publish("psa", "reviewer@example.com")
    publish_map.assert_called_once()
    assert result["status"] == "closed"


def test_ensure_creates_inbox_row_without_going_live() -> None:
    client = MagicMock()
    client.run.return_value = [_row(status="inbox", draft_action="")]
    with (
        patch.object(service, "_kg_client", return_value=client),
        patch.object(service, "_publish_map") as publish_map,
    ):
        result = service.ensure_phrase(
            "PSA",
            extracted_tag="procedure",
            extracted_source="llm",
            sample_span="PSA",
            sample_sentence="PSA is raised",
        )
    assert result["status"] == "inbox"
    publish_map.assert_not_called()
    query = str(client.run.call_args.args[0])
    assert "MERGE" in query
    assert "note_count = coalesce" not in query
    assert client.run.call_args.kwargs["extracted_source"] == "llm"


def test_ensure_deidentifies_sample_sentence_before_write() -> None:
    client = MagicMock()
    client.run.return_value = [
        {
            "phrase_key": "psa",
            "status": "inbox",
            "sample_sentence": "NHS No.: 718 563 0207. PSA is raised.",
        }
    ]
    with (
        patch.object(service, "_kg_client", return_value=client),
        patch.object(service, "_publish_map") as publish_map,
    ):
        result = service.ensure_phrase(
            "PSA",
            sample_sentence="NHS No.: 718 563 0207. PSA is raised.",
        )
    publish_map.assert_not_called()
    stored = client.run.call_args.kwargs["sample_sentence"]
    assert "718 563 0207" not in stored
    assert "[NHS_NUMBER]" in stored
    assert "718 563 0207" not in result["sample_sentence"]


def test_submit_one_moves_only_that_draft() -> None:
    client = MagicMock()
    client.run.return_value = [{"phrase_key": "psa", "status": "review"}]
    with patch.object(service, "_kg_client", return_value=client):
        result = service.submit_one("psa", "engineer@example.com")
    assert result["status"] == "review"
    query = str(client.run.call_args.args[0])
    assert "phrase_key" in query
    assert "draft_author" in query


def test_publish_exclude_does_not_run_on_save() -> None:
    client = MagicMock()
    client.run.return_value = [{"phrase_key": "psa", "status": "draft"}]
    with (
        patch.object(service, "_kg_client", return_value=client),
        patch.object(service, "_publish_exclude") as exclude,
    ):
        service.save_draft(
            "psa",
            action="exclude",
            actor="engineer@example.com",
            reason="admin leftover",
        )
    exclude.assert_not_called()
