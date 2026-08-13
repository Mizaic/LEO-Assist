"""Tests for milestone-scoped SBAR playback."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from libs.patient_documents.milestone_sbar import (
    MilestoneSbarError,
    milestone_types_up_to,
    resolve_episode_encounters,
)


def test_milestone_types_up_to_referral():
    types = milestone_types_up_to("referral")
    assert "first_presentation" in types
    assert "referral" in types
    assert "first_seen" not in types


def test_milestone_types_up_to_unknown_raises():
    with pytest.raises(MilestoneSbarError, match="Unknown milestone_type"):
        milestone_types_up_to("not_a_milestone")


def test_resolve_episode_encounters_deduplicates():
    client = MagicMock()
    client.run.return_value = [
        {"encounter_id": "e1", "milestone_type": "referral"},
        {"encounter_id": "e1", "milestone_type": "referral_sent"},
        {"encounter_id": "e2", "milestone_type": "first_seen"},
    ]
    ids = resolve_episode_encounters(
        client,
        episode_id="ep1",
        milestone_type="first_seen",
    )
    assert ids == ["e1", "e2"]


def test_resolve_episode_encounters_requires_data():
    client = MagicMock()
    client.run.return_value = []
    with pytest.raises(MilestoneSbarError, match="No encounters"):
        resolve_episode_encounters(
            client,
            episode_id="ep1",
            milestone_type="referral",
        )
