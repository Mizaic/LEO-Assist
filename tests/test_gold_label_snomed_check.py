"""Unit tests for scripts/lib/gold_label_snomed_check.py.

These tests stub out the production TerminologyClient and exercise the
candidate-selection logic so we can guarantee:
- top-1 with the wrong tag is skipped in favour of a later candidate
  with the right tag (e.g. fluoxetine -> medicinal_product vs
  substance);
- proposals with no candidates clearing the surface-match bar are
  rejected with a structured reason;
- raw lab-value qualifier proposals (e.g. "5.14 10^9/L") are rejected;
- semantic-tag synonyms (substance <-> medicinal_product) are matched
  with `tag_synonym=True` so reviewers can spot them;
- empty input is handled defensively.

The validator is pure-Python and independent of network state once the
TerminologyClient is stubbed.
"""

from __future__ import annotations

from typing import Any

from libs.terminology.client import ResolvedTerm
from libs.training.gold_label_snomed_check import (
    surface_match_score,
    validate_proposal,
    validate_proposals_batch,
)


class _StubClient:
    """Minimal stand-in for libs.terminology.client.TerminologyClient.

    `responses` maps surface_text -> list[ResolvedTerm] returned by
    the resolver. Anything not in `responses` is treated as a
    no-candidate result.
    """

    def __init__(self, responses: dict[str, list[ResolvedTerm]]):
        self._responses = responses

    def resolve(
        self,
        terms: list[str],
        expected_tags: dict[str, str] | None = None,
    ) -> dict[str, list[ResolvedTerm]]:
        return {term: list(self._responses.get(term, [])) for term in terms}


def _make(
    text: str,
    concept_id: str,
    tag: str,
    term: str,
    score: float,
    *,
    had_exact_match: bool = False,
    vector_raw: float = 0.0,
    lexical_raw: float = 0.0,
) -> ResolvedTerm:
    return ResolvedTerm(
        text=text,
        concept_id=concept_id,
        term=term,
        semantic_tag=tag,
        score=score,
        had_exact_match=had_exact_match,
        vector_raw=vector_raw,
        lexical_raw=lexical_raw,
        raw={},
    )


def test_surface_match_score_is_containment_not_jaccard() -> None:
    """Surface tokens fully contained in a longer SNOMED term -> 1.0."""
    sm = surface_match_score(
        "Mean cell volume",
        "Erythrocyte mean corpuscular volume determination (procedure)",
    )
    # tokens(surface) = {mean, cell, volume};
    # tokens(term)    = {erythrocyte, mean, corpuscular, volume, determination}
    # containment    = |{mean,volume}| / |{mean,cell,volume}| = 2/3
    assert 0.6 < sm < 0.7


def test_validate_accepts_top_match_with_exact_tag() -> None:
    """Iron deficiency anaemia <-> Iron deficiency anemia (UK/US spelling)."""
    client = _StubClient(
        {
            "Iron deficiency anaemia": [
                _make(
                    "Iron deficiency anaemia",
                    "87522002",
                    "disorder",
                    "Iron deficiency anemia (disorder)",
                    1.30,
                ),
            ]
        }
    )
    out = validate_proposal("Iron deficiency anaemia", "disorder", client)
    assert out.accepted is True
    assert out.concept_id == "87522002"
    assert out.snomed_term == "Iron deficiency anemia"
    assert out.semantic_tag == "disorder"
    assert out.tag_synonym is False


def test_validate_skips_top1_wrong_tag_and_picks_substance() -> None:
    """fluoxetine -> medicinal_product first, substance second; pick #2."""
    client = _StubClient(
        {
            "fluoxetine": [
                _make(
                    "fluoxetine",
                    "53640004",
                    "medicinal_product",
                    "Product containing fluoxetine (medicinal product)",
                    1.10,
                ),
                _make(
                    "fluoxetine",
                    "372767007",
                    "substance",
                    "Fluoxetine (substance)",
                    1.08,
                ),
                _make(
                    "fluoxetine",
                    "776003008",
                    "product",
                    "Fluoxetine (product)",
                    0.92,
                ),
            ]
        }
    )
    out = validate_proposal("fluoxetine", "substance", client)
    assert out.accepted is True
    assert out.concept_id == "372767007", "must skip the medicinal_product top-1"
    assert out.semantic_tag == "substance"
    assert out.tag_synonym is False


def test_validate_rejects_raw_lab_value_qualifier_value() -> None:
    """5.14 10^9/L: top hit is just the unit -> insufficient surface match."""
    client = _StubClient(
        {
            "5.14 10^9/L": [
                _make(
                    "5.14 10^9/L",
                    "1348323004",
                    "qualifier_value",
                    "10^9/liter (qualifier value)",
                    0.40,
                ),
            ]
        }
    )
    out = validate_proposal("5.14 10^9/L", "qualifier_value", client)
    assert out.accepted is False
    # Score is well below default 0.6 floor.
    assert out.reason in {"low_resolver_score", "low_surface_match"}


def test_validate_rejects_qualifier_with_wrong_domain_tag() -> None:
    """< 0.2 10^9/L: top hit is foundation_metadata_concept; tag mismatches."""
    client = _StubClient(
        {
            "< 0.2 10^9/L": [
                _make(
                    "< 0.2 10^9/L",
                    "609431004",
                    "foundation_metadata_concept",
                    "Concept model domain (foundation metadata concept)",
                    0.96,
                ),
                _make(
                    "< 0.2 10^9/L",
                    "33822009",
                    "religion_philosophy",
                    "Buddhism (religion/philosophy)",
                    0.95,
                ),
            ]
        }
    )
    out = validate_proposal("< 0.2 10^9/L", "qualifier_value", client)
    assert out.accepted is False
    assert out.reason == "tag_mismatch_all"


def test_validate_rejects_drifted_top1_with_low_surface_overlap() -> None:
    """Co-existing benign naevus: Present <-> Melanocytic nevus of skin.

    Surface overlap is poor and there is no embedding signal so the
    proposal must be rejected, even though the misleading fused
    resolver score is 1.30.
    """
    client = _StubClient(
        {
            "Co-existing benign naevus: Present": [
                _make(
                    "Co-existing benign naevus: Present",
                    "400010006",
                    "disorder",
                    "Melanocytic nevus of skin (disorder)",
                    1.30,
                ),
            ]
        }
    )
    out = validate_proposal(
        "Co-existing benign naevus: Present", "disorder", client
    )
    assert out.accepted is False
    assert out.reason in {"low_surface_match", "low_signal"}


def test_validate_accepts_known_uk_us_spelling_via_normalisation() -> None:
    """anaem -> anem normalisation lets the surface_match score clear bar."""
    client = _StubClient(
        {
            "anaemia": [
                _make("anaemia", "271737000", "disorder", "Anemia (disorder)", 1.30),
            ]
        }
    )
    out = validate_proposal("anaemia", "disorder", client)
    assert out.accepted is True
    assert out.concept_id == "271737000"


def test_validate_no_candidates_returns_no_candidates_reason() -> None:
    client = _StubClient({})
    out = validate_proposal("totally made up phrase", "finding", client)
    assert out.accepted is False
    assert out.reason == "no_candidates"


def test_validate_empty_input_short_circuits() -> None:
    client = _StubClient({})
    out = validate_proposal("", "disorder", client)
    assert out.accepted is False
    assert out.reason == "empty_input"
    out = validate_proposal("Anaemia", "", client)
    assert out.accepted is False
    assert out.reason == "empty_input"


def test_batch_resolves_unique_pairs_only() -> None:
    """Same surface seen twice should hit the resolver once."""

    call_count = {"n": 0}

    class Counting(_StubClient):
        def resolve(self, terms: list[str], expected_tags: dict[str, str] | None = None):  # type: ignore[override]
            call_count["n"] += 1
            return super().resolve(terms, expected_tags)

    client = Counting(
        {
            "Anaemia": [
                _make("Anaemia", "271737000", "disorder", "Anemia (disorder)", 1.30),
            ]
        }
    )
    pairs = [("Anaemia", "disorder"), ("Anaemia", "disorder")]
    out = validate_proposals_batch(pairs, client)
    assert call_count["n"] == 1
    assert len(out) == 1
    assert out[("Anaemia", "disorder")].accepted is True


def test_synonym_tag_match_flagged_for_review() -> None:
    """If only a synonym tag is available, accept but mark tag_synonym=True."""
    client = _StubClient(
        {
            "amoxicillin": [
                _make(
                    "amoxicillin",
                    "27658006",
                    "medicinal_product",
                    "Amoxicillin (product)",
                    1.30,
                ),
            ]
        }
    )
    out = validate_proposal("amoxicillin", "substance", client)
    assert out.accepted is True
    assert out.tag_synonym is True
    assert out.reason.endswith("_synonym_tag")
    assert out.reason.startswith("accepted_")


def test_validate_rejects_single_shared_stopword_like_token() -> None:
    """cancer free <-> Seizure free: only 'free' shared, surface_match
    is 0.5 which is below the SURFACE branch floor and there is no
    embedding signal, so the proposal is rejected.
    """
    client = _StubClient(
        {
            "cancer free": [
                _make(
                    "cancer free",
                    "370994008",
                    "finding",
                    "Seizure free (finding)",
                    1.05,
                ),
            ]
        }
    )
    out = validate_proposal("cancer free", "finding", client)
    assert out.accepted is False
    assert out.reason in {"low_surface_match", "low_signal"}
    assert out.debug.get("rank1_concept_id") == "370994008"
    assert out.debug.get("rank1_term") == "Seizure free"


def test_single_token_surface_still_acceptable_under_token_floor() -> None:
    """Single-meaningful-token surfaces (e.g. 'fluoxetine') must still
    be acceptable when containment is 1.0; floor must not apply here.
    """
    client = _StubClient(
        {
            "fluoxetine": [
                _make(
                    "fluoxetine",
                    "372767007",
                    "substance",
                    "Fluoxetine (substance)",
                    1.30,
                ),
            ]
        }
    )
    out = validate_proposal("fluoxetine", "substance", client)
    assert out.accepted is True
    assert out.concept_id == "372767007"


def test_semantic_branch_accepts_lexicon_gap_with_high_vector_raw() -> None:
    """primary lung mass <-> Lung mass.

    Surface_match is 2/3 (lung+mass shared out of {primary,lung,mass})
    and embedding similarity is high (vector_raw >= 0.92). SEMANTIC
    branch accepts the lexicon-gap mapping.
    """
    client = _StubClient(
        {
            "primary lung mass": [
                _make(
                    "primary lung mass",
                    "309529002",
                    "disorder",
                    "Lung mass (disorder)",
                    1.30,
                    vector_raw=0.95,
                ),
            ]
        }
    )
    out = validate_proposal("primary lung mass", "disorder", client)
    assert out.accepted is True
    assert out.concept_id == "309529002"
    assert out.reason == "accepted_semantic"


def test_semantic_branch_rejected_when_surface_match_too_low() -> None:
    """nipple inversion on the right breast <-> Pendulous right breast.

    High vector_raw (0.95) but only sm=0.5 ({right,breast} of
    {nipple,inversion,right,breast}). Below the SEMANTIC branch's
    surface-overlap floor of 0.66. Rejected.
    """
    client = _StubClient(
        {
            "nipple inversion on the right breast": [
                _make(
                    "nipple inversion on the right breast",
                    "15954861000119106",
                    "finding",
                    "Pendulous right breast (finding)",
                    1.286,
                    vector_raw=0.954,
                ),
            ]
        }
    )
    out = validate_proposal(
        "nipple inversion on the right breast", "finding", client
    )
    assert out.accepted is False


def test_semantic_branch_rejected_when_vector_raw_too_low() -> None:
    """rising PSA <-> Slow rising pulse.

    Misleading 1.30 fused score but low embedding similarity (different
    organ system). Must NOT be accepted under any branch.
    """
    client = _StubClient(
        {
            "rising PSA": [
                _make(
                    "rising PSA",
                    "271603009",
                    "finding",
                    "Slow rising pulse (finding)",
                    1.30,
                    vector_raw=0.42,
                ),
            ]
        }
    )
    out = validate_proposal("rising PSA", "finding", client)
    assert out.accepted is False


def test_exact_branch_accepts_regardless_of_surface_match() -> None:
    """When the resolver flags had_exact_match=True, accept directly.

    The exact branch matches normalised text against curated SurfaceForm
    or Term.normalized_form, the strongest possible signal short of a
    hand-coded mapping.
    """
    client = _StubClient(
        {
            "Type 2 diabetes mellitus": [
                _make(
                    "Type 2 diabetes mellitus",
                    "44054006",
                    "disorder",
                    "Diabetes mellitus type 2 (disorder)",
                    1.30,
                    had_exact_match=True,
                ),
            ]
        }
    )
    out = validate_proposal("Type 2 diabetes mellitus", "disorder", client)
    assert out.accepted is True
    assert out.concept_id == "44054006"
    assert out.reason == "accepted_exact"
    assert out.debug.get("had_exact_match") is True


def test_misleading_fused_score_alone_does_not_accept() -> None:
    """cancer free with a 1.30 fused score is still rejected when
    there is no exact match and no strong embedding signal.
    """
    client = _StubClient(
        {
            "cancer free": [
                _make(
                    "cancer free",
                    "370994008",
                    "finding",
                    "Seizure free (finding)",
                    1.30,
                    had_exact_match=False,
                    vector_raw=0.30,
                ),
            ]
        }
    )
    out = validate_proposal("cancer free", "finding", client)
    assert out.accepted is False


def test_validate_rejects_polarity_flip_no_hydrocephalus() -> None:
    """No hydrocephalus must NOT code to Hydrocephalus.

    Auto-applying this would assert the presence of a finding the
    clinician explicitly excluded - a clinically dangerous gold label.
    The polarity guard takes precedence over surface_match, resolver
    score, and the high-confidence override.
    """
    client = _StubClient(
        {
            "No hydrocephalus": [
                _make(
                    "No hydrocephalus",
                    "230745008",
                    "disorder",
                    "Hydrocephalus (disorder)",
                    1.30,
                ),
            ]
        }
    )
    out = validate_proposal("No hydrocephalus", "disorder", client)
    assert out.accepted is False
    assert out.reason == "polarity_mismatch"
    assert out.debug.get("rank1_concept_id") == "230745008"


def test_validate_accepts_negation_when_term_also_negates() -> None:
    """no cancer present <-> No evidence of cancer found is OK because
    both sides carry negation; polarity guard does not fire.
    """
    client = _StubClient(
        {
            "no cancer present": [
                _make(
                    "no cancer present",
                    "428251008",
                    "finding",
                    "No evidence of cancer found (finding)",
                    1.30,
                ),
            ]
        }
    )
    out = validate_proposal("no cancer present", "finding", client)
    assert out.accepted is True
    assert out.concept_id == "428251008"


def test_validate_picks_higher_surface_when_multiple_pass() -> None:
    """Two candidates with right tag: picks the higher surface_match."""
    client = _StubClient(
        {
            "Asthma": [
                _make(
                    "Asthma",
                    "111111111",
                    "disorder",
                    "Severe persistent asthma (disorder)",
                    1.10,
                ),
                _make(
                    "Asthma",
                    "195967001",
                    "disorder",
                    "Asthma (disorder)",
                    1.30,
                ),
            ]
        }
    )
    out = validate_proposal("Asthma", "disorder", client)
    assert out.accepted is True
    # 'Asthma' is contained 1/1 in 'Asthma' but 1/1 in 'Severe...asthma' too
    # -- tie on surface, tie-break by resolver score (1.30 > 1.10).
    assert out.concept_id == "195967001"


def _summary(items: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for item in items:
        out[item["label"]] = out.get(item["label"], 0) + 1
    return out
