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


class TestMultiDistinctTypeGuard:
    """R-LEO-AI-097 / DI-LEO-AI-137 -- two or more episodes in a cluster
    with distinct, non-NSS cancer_types must NOT collapse unless the
    diagnosis text uniquely corroborates one of them.

    These are pattern-level regressions. They describe a class of
    clinical scenario (parallel 2WW pathways referred on the same day),
    not a specific patient: two distinct cancer-type referrals on the
    same day with no diagnosis text yet are common in primary care
    (a skin lesion + a breast lump, a colorectal + a urological
    referral, etc.).
    """

    def test_two_distinct_known_types_no_text_skips_merge(self):
        """Two episodes with distinct known cancer_types and no text
        evidence -- the resolver must skip the merge and surface the
        cluster for review rather than alphabetically choose a winner."""
        cluster = [
            _rec("a", "breast", "2024-10-31"),
            _rec("b", "melanoma", "2024-10-31"),
        ]
        assert pick_evidence_winner(cluster) is None

    def test_two_distinct_known_types_alphabetical_first_does_not_win(self):
        """Regression: alphabetical fallback (`sorted(known_types)[0]`)
        is unsafe when both cancer types are real. Prove that 'breast'
        does not silently swallow 'melanoma' / 'cervical' / 'colorectal'
        regardless of episode_id ordering."""
        for losing_type in ("melanoma", "cervical", "colorectal", "endometrial"):
            cluster = [
                _rec("primary_b", "breast", "2024-10-31"),
                _rec("dup_x", losing_type, "2024-10-31"),
            ]
            assert pick_evidence_winner(cluster) is None, (
                f"expected skip for distinct types breast vs {losing_type}"
            )

    def test_three_distinct_known_types_no_text_skips_merge(self):
        cluster = [
            _rec("a", "breast", "2024-10-31"),
            _rec("b", "melanoma", "2024-10-31"),
            _rec("c", "colorectal", "2024-10-31"),
        ]
        assert pick_evidence_winner(cluster) is None

    def test_two_distinct_types_text_uniquely_identifies_one_merges(self):
        """Diagnosis text uniquely names one cancer_type -- merge
        proceeds because there IS a deterministic winner. Equivalent to
        a real diagnosis later corroborating one referral."""
        cluster = [
            _rec(
                "a",
                "breast",
                "2024-10-31",
                texts=["mammogram, lumpectomy completed, letrozole started"],
            ),
            _rec("b", "melanoma", "2024-10-31"),
        ]
        decision = pick_evidence_winner(cluster)
        assert decision is not None
        assert decision.primary_id == "a"
        assert decision.evidence_cancer_type == "breast"

    def test_distinct_types_with_text_naming_outsider_skips(self):
        """Diagnosis text fires on a cancer type that is NOT one of the
        cluster's members -- the resolver cannot map the text evidence
        onto any cluster episode, so it must skip the merge."""
        cluster = [
            _rec(
                "a",
                "breast",
                "2024-10-31",
                texts=["bronchoscopy showed lung lesion"],
            ),
            _rec("b", "melanoma", "2024-10-31"),
        ]
        assert pick_evidence_winner(cluster) is None

    def test_text_uniquely_identifies_one_of_three_distinct_types_merges(self):
        """When diagnosis text uniquely names ONE of the cluster's
        distinct cancer types, that episode wins and the others are
        merged into it -- the text provides a deterministic signal."""
        cluster = [
            _rec("a", "breast", "2024-10-31"),
            _rec("b", "melanoma", "2024-10-31"),
            _rec(
                "c",
                "colorectal",
                "2024-10-31",
                texts=["colonoscopy showed sigmoid adenocarcinoma"],
            ),
        ]
        decision = pick_evidence_winner(cluster)
        assert decision is not None
        assert decision.primary_id == "c"
        assert decision.evidence_cancer_type == "colorectal"

    def test_one_known_plus_nss_still_merges(self):
        """Single recognised cancer_type plus NSS shadows is still safe
        to merge -- this is the primary use case (DI-LEO-AI-137 NSS
        shadow collapse). Guard must not regress this behaviour."""
        cluster = [
            _rec("primary", "breast", "2024-10-31"),
            _rec("nss1", "non_site_specific", "2024-10-31"),
            _rec("nss2", "non_site_specific", "2024-11-01"),
        ]
        decision = pick_evidence_winner(cluster)
        assert decision is not None
        assert decision.primary_id == "primary"
        assert set(decision.duplicates) == {"nss1", "nss2"}

    def test_one_known_plus_unknown_still_merges(self):
        cluster = [
            _rec("primary", "lung", "2024-04-09"),
            _rec("dup", "unknown", "2024-04-10"),
        ]
        decision = pick_evidence_winner(cluster)
        assert decision is not None
        assert decision.primary_id == "primary"
        assert decision.duplicates == ["dup"]
