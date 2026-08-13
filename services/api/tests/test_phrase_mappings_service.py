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


def test_publish_rejects_same_person() -> None:
    client = MagicMock()
    client.run.return_value = [_row()]
    with patch.object(service, "_kg_client", return_value=client):
        with pytest.raises(HTTPException) as exc:
            service.publish("psa", "engineer@example.com")
    assert exc.value.status_code == 403
    assert client.run.call_count == 1


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
