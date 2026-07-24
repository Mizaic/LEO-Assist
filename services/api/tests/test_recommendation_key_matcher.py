"""Tests for recommendation_key_matcher.py -- DI-42246DA7 / DO-F8C56339.

Covers:
  - text_similarity(): token-overlap scoring, stopword handling
  - match_recommendation_keys(): exact-number continuity, text-similarity
    fallback (floor + margin), the ambiguous floor-but-not-margin case,
    and first-ingest (no old_recs) behaviour.
"""

from __future__ import annotations

from app.services.recommendation_key_matcher import (
    NewRecommendation,
    OldRecommendation,
    match_recommendation_keys,
    text_similarity,
)

# NG12 1.2.9-flavoured fixtures -- reused across this file.
_NG12_1_2_9_TEXT = (
    "Consider non-urgent, direct access upper gastrointestinal endoscopy "
    "in people aged 55 or over if they have unexplained haemoptysis, or "
    "upper abdominal pain with low haemoglobin levels."
)


class TestTextSimilarity:
    def test_identical_text_scores_one(self):
        assert text_similarity(_NG12_1_2_9_TEXT, _NG12_1_2_9_TEXT) == 1.0

    def test_completely_unrelated_text_scores_zero(self):
        score = text_similarity(
            "Offer an urgent chest X-ray for suspected lung cancer.",
            "Refer people with unexplained rectal bleeding.",
        )
        assert score == 0.0

    def test_stopwords_alone_do_not_drive_similarity(self):
        """Two sentences sharing only stopwords should score zero, not a
        false-positive match on "the of with any"."""
        score = text_similarity(
            "the of with any following",
            "and or in to for is are",
        )
        assert score == 0.0

    def test_empty_text_scores_zero(self):
        assert text_similarity("", "some text here") == 0.0
        assert text_similarity("some text here", "") == 0.0

    def test_mostly_overlapping_text_scores_high(self):
        """A minor rewording (renumbering-flavoured) still scores high."""
        original = "Offer an urgent direct access chest X-ray for smokers."
        reworded = "Offer an urgent, direct-access chest X-ray for smokers."
        assert text_similarity(original, reworded) > 0.8


class TestMatchRecommendationKeys:
    def test_first_ingest_mints_fresh_keys_for_everything(self):
        """No old_recs at all (first-ever ingest) -- every new rec gets a
        fresh key, no fallback attempted."""
        new_recs = [
            NewRecommendation(ref="r1", number="1.2.8", text="Offer a scan."),
            NewRecommendation(ref="r2", number="1.2.9", text=_NG12_1_2_9_TEXT),
        ]
        results = match_recommendation_keys(new_recs, old_recs=[])

        assert len(results) == 2
        assert results["r1"].renumbered_from is None
        assert results["r2"].renumbered_from is None
        assert results["r1"].recommendation_key != results["r2"].recommendation_key

    def test_exact_number_match_carries_key_forward(self):
        """Nothing moved -- number match is the cheap, common path."""
        old_recs = [
            OldRecommendation(
                number="1.2.9", text=_NG12_1_2_9_TEXT, recommendation_key="key-129"
            )
        ]
        new_recs = [NewRecommendation(ref="r1", number="1.2.9", text=_NG12_1_2_9_TEXT)]

        results = match_recommendation_keys(new_recs, old_recs)

        assert results["r1"].recommendation_key == "key-129"
        assert results["r1"].renumbered_from is None
        assert results["r1"].ambiguous_candidate_number is None

    def test_renumbered_recommendation_carries_key_forward_via_similarity(self):
        """1.2.9 moved to 1.2.10 with only trivial wording drift -- no
        number match, but text similarity clears floor + margin."""
        old_recs = [
            OldRecommendation(
                number="1.2.9", text=_NG12_1_2_9_TEXT, recommendation_key="key-129"
            )
        ]
        reworded = _NG12_1_2_9_TEXT.replace("non-urgent,", "non-urgent")
        new_recs = [NewRecommendation(ref="r1", number="1.2.10", text=reworded)]

        results = match_recommendation_keys(new_recs, old_recs)

        assert results["r1"].recommendation_key == "key-129"
        assert results["r1"].renumbered_from == "1.2.9"
        assert results["r1"].ambiguous_candidate_number is None

    def test_unrelated_new_number_never_falls_back_to_unrelated_old_rec(self):
        """No plausible candidate at all -- mints a fresh key, same as
        today's safe default (falls through to normal supersede)."""
        old_recs = [
            OldRecommendation(
                number="1.2.9", text=_NG12_1_2_9_TEXT, recommendation_key="key-129"
            )
        ]
        new_recs = [
            NewRecommendation(
                ref="r1",
                number="1.5.1",
                text="Refer immediately for suspected colorectal cancer.",
            )
        ]

        results = match_recommendation_keys(new_recs, old_recs)

        assert results["r1"].recommendation_key != "key-129"
        assert results["r1"].renumbered_from is None
        assert results["r1"].ambiguous_candidate_number is None

    def test_true_split_fails_floor_check_by_construction(self):
        """One recommendation becomes two, each contributing only half of
        the original's distinct content words -- each half scores ~50%
        similarity, below the absolute floor, so neither silently wins
        the old key (there is only one old candidate, so the margin
        check alone -- which needs a runner-up to compare against --
        cannot be relied on to catch this; the floor is what rejects a
        genuine 50/50 split)."""
        original_text = (
            "Offer surveillance colonoscopy for adenoma and refer for "
            "genetic counselling for suspected Lynch syndrome."
        )
        old_recs = [
            OldRecommendation(
                number="1.4.1", text=original_text, recommendation_key="key-141"
            )
        ]
        new_recs = [
            NewRecommendation(
                ref="split-a",
                number="1.4.1a",
                text="Offer surveillance colonoscopy for adenoma and refer.",
            ),
            NewRecommendation(
                ref="split-b",
                number="1.4.1b",
                text="Genetic counselling for suspected Lynch syndrome.",
            ),
        ]

        results = match_recommendation_keys(new_recs, old_recs)

        for ref in ("split-a", "split-b"):
            assert results[ref].recommendation_key != "key-141"
            assert results[ref].renumbered_from is None

    def test_floor_cleared_but_margin_not_surfaces_ambiguous_candidate(self):
        """Two old recs are both plausibly similar to one new rec, close
        enough to each other that neither wins outright -- flagged as
        ambiguous rather than silently picking the top scorer."""
        old_recs = [
            OldRecommendation(
                number="1.3.1",
                text="Offer an urgent chest X-ray for suspected lung cancer "
                "in smokers with a persistent cough.",
                recommendation_key="key-131",
            ),
            OldRecommendation(
                number="1.3.2",
                text="Offer an urgent chest X-ray for suspected lung cancer "
                "in ex-smokers with a persistent cough and weight loss.",
                recommendation_key="key-132",
            ),
        ]
        new_recs = [
            NewRecommendation(
                ref="r1",
                number="1.3.9",
                text="Offer an urgent chest X-ray for suspected lung cancer "
                "in smokers or ex-smokers with a persistent cough.",
            )
        ]

        results = match_recommendation_keys(new_recs, old_recs)

        result = results["r1"]
        assert result.renumbered_from is None
        assert result.ambiguous_candidate_number in {"1.3.1", "1.3.2"}
        assert result.ambiguous_score is not None
        assert result.recommendation_key not in {"key-131", "key-132"}

    def test_exact_matched_old_number_is_never_a_fallback_target(self):
        """An old rec that legitimately kept its number must never also be
        claimed by a *different* new rec via the similarity fallback."""
        old_recs = [
            OldRecommendation(
                number="1.2.9", text=_NG12_1_2_9_TEXT, recommendation_key="key-129"
            ),
        ]
        new_recs = [
            # Keeps its number -- exact match, claims key-129 legitimately.
            NewRecommendation(ref="unchanged", number="1.2.9", text=_NG12_1_2_9_TEXT),
            # New number, near-identical text -- must NOT also claim
            # key-129 via similarity, since 1.2.9 isn't orphaned.
            NewRecommendation(ref="lookalike", number="1.2.99", text=_NG12_1_2_9_TEXT),
        ]

        results = match_recommendation_keys(new_recs, old_recs)

        assert results["unchanged"].recommendation_key == "key-129"
        assert results["lookalike"].recommendation_key != "key-129"

    def test_two_new_recs_never_claim_the_same_old_key(self):
        """Two new recommendations both plausibly similar to the same
        orphaned old rec -- only the stronger match may claim it."""
        old_recs = [
            OldRecommendation(
                number="1.2.9", text=_NG12_1_2_9_TEXT, recommendation_key="key-129"
            ),
        ]
        near_identical = _NG12_1_2_9_TEXT.replace("non-urgent,", "non-urgent")
        new_recs = [
            NewRecommendation(ref="r1", number="1.2.10", text=near_identical),
            NewRecommendation(ref="r2", number="1.2.11", text=near_identical),
        ]

        results = match_recommendation_keys(new_recs, old_recs)

        keys = [results["r1"].recommendation_key, results["r2"].recommendation_key]
        assert keys.count("key-129") <= 1
