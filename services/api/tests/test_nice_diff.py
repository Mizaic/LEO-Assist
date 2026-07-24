"""Tests for nice_diff.py's diff computation -- DO-EC41233C / DI-9D0DF618.

Covers:
  - _compute_diff(): added/removed/modified/unchanged classification.
  - _compute_possible_moves(): the ambiguous "floor cleared, margin not"
    pairing surfaced for GuidelineChangesDrawer's explicit yes/no gate
    (nice-renumber-ambiguous-prompt).
"""

from __future__ import annotations

from app.routers.nice_diff import _compute_diff, _compute_possible_moves

_NG12_1_2_9_TEXT = (
    "Consider non-urgent, direct access upper gastrointestinal endoscopy "
    "in people aged 55 or over if they have unexplained haemoptysis."
)


class TestComputeDiff:
    def test_unchanged_recommendation_is_not_added_removed_or_modified(self):
        stored = [{"number": "1.2.9", "text": _NG12_1_2_9_TEXT}]
        remote = [{"number": "1.2.9", "text": _NG12_1_2_9_TEXT}]

        diff = _compute_diff(stored, remote)

        assert diff["added"] == []
        assert diff["removed"] == []
        assert diff["modified"] == []
        assert diff["unchanged_count"] == 1

    def test_whitespace_only_change_counts_as_unchanged(self):
        stored = [{"number": "1.2.9", "text": "Offer  a scan."}]
        remote = [{"number": "1.2.9", "text": "Offer a scan."}]

        diff = _compute_diff(stored, remote)

        assert diff["unchanged_count"] == 1
        assert diff["modified"] == []

    def test_genuine_text_change_is_modified_not_added_and_removed(self):
        stored = [{"number": "1.2.9", "text": "Offer a scan."}]
        remote = [{"number": "1.2.9", "text": "Offer an urgent scan."}]

        diff = _compute_diff(stored, remote)

        assert len(diff["modified"]) == 1
        assert diff["modified"][0]["old_text"] == "Offer a scan."
        assert diff["modified"][0]["new_text"] == "Offer an urgent scan."
        assert diff["added"] == []
        assert diff["removed"] == []

    def test_new_number_with_no_stored_counterpart_is_added(self):
        stored = []
        remote = [{"number": "1.2.9", "text": _NG12_1_2_9_TEXT}]

        diff = _compute_diff(stored, remote)

        assert len(diff["added"]) == 1
        assert diff["added"][0]["number"] == "1.2.9"

    def test_stored_number_missing_from_remote_is_removed(self):
        stored = [{"number": "1.2.9", "text": _NG12_1_2_9_TEXT}]
        remote = []

        diff = _compute_diff(stored, remote)

        assert len(diff["removed"]) == 1
        assert diff["removed"][0]["number"] == "1.2.9"
        assert diff["removed"][0]["rules"] == []

    def test_response_always_includes_possible_moves_key(self):
        """Even with no ambiguous pairings, the field is present (an empty
        list, not absent) so the frontend never has to guard against a
        missing key."""
        diff = _compute_diff([], [])
        assert diff["possible_moves"] == []


class TestComputePossibleMoves:
    def test_exact_renumber_pair_with_no_competing_candidate_is_not_ambiguous(self):
        """A single, near-identical renumber pair clears both floor and
        margin (nothing else to compete against) -- confident, not
        ambiguous, so it must NOT appear in possible_moves (it's already
        safely resolved by the ingest-time matcher with no admin input
        needed)."""
        removed = [{"number": "1.2.9", "text": _NG12_1_2_9_TEXT}]
        added = [
            {
                "number": "1.2.10",
                "text": _NG12_1_2_9_TEXT.replace("non-urgent,", "non-urgent"),
            }
        ]

        moves = _compute_possible_moves(added, removed)

        assert moves == []

    def test_unrelated_added_and_removed_produce_no_possible_move(self):
        removed = [{"number": "1.2.9", "text": _NG12_1_2_9_TEXT}]
        added = [
            {
                "number": "1.5.1",
                "text": "Refer immediately for suspected colorectal cancer.",
            }
        ]

        moves = _compute_possible_moves(added, removed)

        assert moves == []

    def test_two_plausible_old_candidates_surface_an_ambiguous_move(self):
        removed = [
            {
                "number": "1.3.1",
                "text": "Offer an urgent chest X-ray for suspected lung cancer "
                "in smokers with a persistent cough.",
            },
            {
                "number": "1.3.2",
                "text": "Offer an urgent chest X-ray for suspected lung cancer "
                "in ex-smokers with a persistent cough and weight loss.",
            },
        ]
        added = [
            {
                "number": "1.3.9",
                "text": "Offer an urgent chest X-ray for suspected lung cancer "
                "in smokers or ex-smokers with a persistent cough.",
            }
        ]

        moves = _compute_possible_moves(added, removed)

        assert len(moves) == 1
        assert moves[0]["added_number"] == "1.3.9"
        assert moves[0]["removed_number"] in {"1.3.1", "1.3.2"}
        assert 0 <= moves[0]["score"] <= 1

    def test_no_added_or_removed_recs_returns_empty_list(self):
        assert _compute_possible_moves([], []) == []
