"""Tests for replaying reviewed EpisodeOfCare rows.

Atlas trace:
  DI: DI-8A5FCF4F (Defence-in-depth episode detector with coverage fail-safe)
"""

from __future__ import annotations

from services.analysis_worker.app.episode_detector_v2.reviewed_replay import (
    load_reviewed_episode_replay,
)


class _Client:
    def run(self, query: str, **params):
        assert "reviewed_at IS NOT NULL" in query
        assert params == {"patient_id": "p-1"}
        return [
            {
                "episode_id": "ep-reviewed",
                "site_key": "breast",
                "suspected_site": "Breast",
                "status": "closed_benign",
                "intent": None,
                "start_date": "2025-01-10",
                "end_date": None,
                "encounter_ids": ["enc-1", "enc-2"],
            }
        ]


def test_reviewed_episode_replay_preserves_curated_episode():
    episodes = load_reviewed_episode_replay(_Client(), patient_id="p-1")

    assert len(episodes) == 1
    episode = episodes[0]
    assert episode.episode_id == "ep-reviewed"
    assert episode.site_key == "breast"
    assert episode.status == "closed_benign"
    assert episode.intent == "ruled_out"
    assert episode.encounter_ids == ["enc-1", "enc-2"]
    assert episode.confidence_tier == "auto"
    assert episode.needs_human_review is False
    assert episode.generator_consensus == ["reviewed_episode_replay"]
