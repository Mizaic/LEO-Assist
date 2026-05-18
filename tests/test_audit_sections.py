"""Unit tests for NCDA audit section query contracts."""

from __future__ import annotations

from services.analytics_api.app.routers import _audit_sections as mod


class FakeCancerStageClient:
    """Return canned rows while retaining generated Cypher for assertions."""

    def __init__(self) -> None:
        self.queries: list[str] = []

    def run(self, query: str, **params):  # noqa: ANN001, ANN202, ARG002
        self.queries.append(query)
        if "RETURN stage_group" in query and "ORDER BY stage_group" in query:
            return [{"stage_group": "early", "n": 2}, {"stage_group": "unknown", "n": 1}]
        if "AS staging_system" in query:
            return [{"staging_system": "TNM", "n": 2}]
        if "AS staging_source" in query:
            return [{"staging_source": "encounter_text", "n": 2}]
        if "staging_value AS cancer_stage_group" in query:
            return [{"cancer_stage_group": "T1N0M0", "stage_group": "early", "n": 2}]
        if "collect({stage_group: stage_group, n: n})" in query:
            return [
                {"cancer_type": "breast", "stage_group": "early", "n": 2, "pct": 100.0}
            ]
        if "AS denom" in query:
            return [{"denom": 3}]
        if "AS numer" in query:
            return [{"numer": 2}]
        return []


class FakePlaceClient:
    """Return canned place rows while retaining generated Cypher."""

    def __init__(self) -> None:
        self.queries: list[str] = []

    def run(self, query: str, **params):  # noqa: ANN001, ANN202, ARG002
        self.queries.append(query)
        return [
            {"place": "GP surgery", "n": 3},
            {"place": "A&E", "n": 1},
        ]


class FakeNSSOutcomeClient:
    """Return canned NSS outcome rows while retaining generated Cypher."""

    def __init__(self) -> None:
        self.queries: list[str] = []

    def run(self, query: str, **params):  # noqa: ANN001, ANN202
        self.queries.append(query)
        assert params["nss_id"] == "1556551000000104"
        return [
            {"eid": "nss-1", "outcome": "No cancer diagnosed"},
            {"eid": "nss-2", "outcome": "No cancer diagnosed"},
        ]


class FakeFastTrackReferralClient:
    """Return coded and text-inferred FTR rows while retaining generated Cypher."""

    def __init__(self) -> None:
        self.queries: list[str] = []

    def run(self, query: str, **params):  # noqa: ANN001, ANN202
        self.queries.append(query)
        assert "1556551000000104" in params["ftr_ids"]
        return [
            {"episode_id": "coded", "cids": ["276341000000100"], "texts": []},
            {"episode_id": "text-breast", "cids": [], "texts": ["Refer 2ww breast"]},
            {
                "episode_id": "text-skin",
                "cids": [],
                "texts": ["PRISM 2WW Dermatology questionnaire"],
            },
        ]


def test_place_of_presentation_reads_episode_stored_typo_property() -> None:
    client = FakePlaceClient()

    result = mod._q_place(
        "MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) WHERE true ",
        {},
        client,
    )

    generated = "\n".join(client.queries)
    assert "ep.place_of_presentation" in generated
    assert "ep.place_of_presetnation" in generated
    assert result == [
        {"place": "GP surgery", "n": 3, "pct": 75.0},
        {"place": "A&E", "n": 1, "pct": 25.0},
    ]


def test_nss_outcomes_classifies_benign_pathways_as_no_cancer() -> None:
    client = FakeNSSOutcomeClient()

    result = mod._q_nss_outcomes(
        "MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) WHERE true ",
        {},
        client,
    )

    generated = "\n".join(client.queries)
    assert "toString(c.conceptId) = $nss_id" in generated
    assert "AND ep.nss_referral = true" in generated
    assert "ELSE 'No cancer diagnosed'" in generated
    assert result == {
        "total_nss": 2,
        "cancer_diagnosed_n": 0,
        "outcomes": [{"outcome": "No cancer diagnosed", "n": 2}],
    }


def test_fast_track_referrals_infer_missing_sites_from_referral_text() -> None:
    client = FakeFastTrackReferralClient()

    result = mod._q_fast_track_referrals(
        "MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) WHERE true ",
        {},
        client,
    )

    generated = "\n".join(client.queries)
    assert "coalesce(ep.cohort, '') IN ['1a', '1b']" in generated
    assert "collect(DISTINCT enc.text) AS texts" in generated
    assert result == [
        {
            "referral_site": "Breast",
            "concept_id": "276341000000100",
            "n": 2,
            "pct": 66.7,
        },
        {
            "referral_site": "Skin",
            "concept_id": "276281000000104",
            "n": 1,
            "pct": 33.3,
        },
    ]


def test_cancer_stage_uses_episode_staging_datashape() -> None:
    client = FakeCancerStageClient()

    result = mod._q_cancer_stage(
        "MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) WHERE true ",
        {},
        client,
    )

    generated = "\n".join(client.queries)
    assert "ep.staging_early_late" in generated
    assert "ep.staging_value" in generated
    assert "ep.staging_system" in generated
    assert "ep.staging_source" in generated
    assert "ep.cancer_stage" not in generated

    assert result["rows"] == [
        {"stage_group": "early", "n": 2, "pct": 66.7},
        {"stage_group": "unknown", "n": 1, "pct": 33.3},
    ]
    assert result["coverage_numerator"] == 2
    assert result["coverage_denominator"] == 3
    assert result["by_stage_group_detail"] == [
        {
            "cancer_stage_group": "T1N0M0",
            "staging_value": "T1N0M0",
            "stage_group": "early",
            "n": 2,
        }
    ]
    assert result["by_cancer_type"] == [
        {"cancer_type": "Breast", "stage_group": "early", "n": 2, "pct": 100.0}
    ]
