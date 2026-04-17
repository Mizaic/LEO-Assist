"""VT-LEO-AI-138 -- Evidence-wins duplicate-episode resolver.

Pure-logic tests for ``libs.episodes.duplicate_resolver``. Exercises
clustering, evidence-text extraction, winner selection, tie-breakers,
and idempotency guarantees.
"""

from __future__ import annotations

from datetime import date

from libs.episodes.duplicate_resolver import (
    EpisodeRecord,
    cluster_episodes,
    evidence_cancer_type,
    pick_evidence_winner,
)


def _rec(
    episode_id: str,
    cancer_type: str,
    referral: str | None,
    *,
    texts: list[str] | None = None,
    treatments: int = 0,
    end: str | None = None,
    status: str = "completed",
) -> EpisodeRecord:
    return EpisodeRecord(
        episode_id=episode_id,
        cancer_type=cancer_type,
        referral_date=date.fromisoformat(referral) if referral else None,
        end_date=date.fromisoformat(end) if end else None,
        status=status,
        diagnosis_texts=texts or [],
        treatment_count=treatments,
    )


class TestClusterEpisodes:
    def test_within_window_clusters(self):
        records = [
            _rec("a", "breast", "2024-03-01"),
            _rec("b", "unknown", "2024-03-10"),
        ]
        clusters = cluster_episodes(records, same_episode_days=30)
        assert len(clusters) == 1
        assert {r.episode_id for r in clusters[0]} == {"a", "b"}

    def test_outside_window_separate(self):
        records = [
            _rec("a", "breast", "2024-01-01"),
            _rec("b", "breast", "2024-06-01"),
        ]
        clusters = cluster_episodes(records, same_episode_days=30)
        assert len(clusters) == 2

    def test_nss_included_in_cluster(self):
        """NSS episodes were previously skipped by the legacy merger;
        the evidence-wins cluster must include them."""
        records = [
            _rec("a", "breast", "2024-03-01"),
            _rec("b", "non_site_specific", "2024-03-05"),
        ]
        clusters = cluster_episodes(records, same_episode_days=30)
        assert len(clusters) == 1
        assert any(r.cancer_type == "non_site_specific" for r in clusters[0])

    def test_null_referral_uses_end_date(self):
        records = [
            _rec("a", "breast", "2024-03-01"),
            _rec("b", "breast", None, end="2024-03-10"),
        ]
        clusters = cluster_episodes(records, same_episode_days=30)
        assert len(clusters) == 1

    def test_no_anchor_becomes_singleton(self):
        records = [_rec("orphan", "breast", None)]
        clusters = cluster_episodes(records, same_episode_days=30)
        assert clusters == [[records[0]]]


class TestEvidenceCancerType:
    def test_dominant_breast_text_wins(self):
        texts = [
            "Fast track referral for suspected breast cancer; nipple discharge",
            "Mammogram followed by lumpectomy and letrozole started.",
        ]
        assert evidence_cancer_type(texts) == "breast"

    def test_empty_text_unknown(self):
        assert evidence_cancer_type([]) == "unknown"
        assert evidence_cancer_type(["", None, "   "]) == "unknown"

    def test_ambiguous_tie_returns_unknown(self):
        texts = ["Bronchoscopy findings", "Colonoscopy findings"]
        assert evidence_cancer_type(texts) == "unknown"

    def test_nss_does_not_win(self):
        """Non-site-specific must never be the dominant evidence type."""
        texts = ["Fast track 2WW non specific symptoms"]
        assert evidence_cancer_type(texts) == "unknown"


class TestPickEvidenceWinner:
    def test_single_record_no_decision(self):
        decision = pick_evidence_winner([_rec("a", "breast", "2024-03-01")])
        assert decision is None

    def test_evidence_matches_primary(self):
        cluster = [
            _rec(
                "a",
                "breast",
                "2024-03-01",
                texts=["mammogram booked; lumpectomy completed"],
            ),
            _rec("b", "unknown", "2024-03-05"),
        ]
        decision = pick_evidence_winner(cluster)
        assert decision is not None
        assert decision.primary_id == "a"
        assert decision.duplicates == ["b"]
        assert decision.evidence_cancer_type == "breast"
        assert "Evidence-wins merge" in decision.reasoning

    def test_treatment_tie_breaker(self):
        cluster = [
            _rec("a", "breast", "2024-03-01", texts=["breast"]),
            _rec("b", "breast", "2024-03-05", texts=["breast"], treatments=3),
        ]
        decision = pick_evidence_winner(cluster)
        assert decision is not None
        assert decision.primary_id == "b"

    def test_earliest_referral_tie_breaker(self):
        cluster = [
            _rec("a", "breast", "2024-03-10", texts=["breast"]),
            _rec("b", "breast", "2024-03-01", texts=["breast"]),
        ]
        decision = pick_evidence_winner(cluster)
        assert decision is not None
        assert decision.primary_id == "b"

    def test_ambiguous_no_merge(self):
        """Cluster with no cancer-type evidence anywhere is not merged."""
        cluster = [
            _rec("a", "unknown", "2024-03-01"),
            _rec("b", "unknown", "2024-03-05"),
        ]
        assert pick_evidence_winner(cluster) is None

    def test_idempotent_decision(self):
        cluster = [
            _rec("a", "breast", "2024-03-01", texts=["mammogram", "lumpectomy"]),
            _rec("b", "unknown", "2024-03-05"),
        ]
        first = pick_evidence_winner(cluster)
        second = pick_evidence_winner(cluster)
        assert first == second

    def test_reasoning_contains_cluster_size_and_evidence(self):
        cluster = [
            _rec("a", "breast", "2024-03-01", texts=["breast lumpectomy"]),
            _rec("b", "unknown", "2024-03-05"),
            _rec("c", "non_site_specific", "2024-03-10"),
        ]
        decision = pick_evidence_winner(cluster)
        assert decision is not None
        assert "Cluster size 3" in decision.reasoning
        assert "breast" in decision.reasoning
