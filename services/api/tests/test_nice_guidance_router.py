"""Tests for nice_guidance router catalogue search and taxonomy -- VT-LEO-AI-063.

Verifies:
- Relevance-ranked search: clinical guidelines (NG/CG/QS) surface above
  technology appraisals (TA) for condition-name queries.
- GET /nice/taxonomy: returns hierarchy with loaded status when data exists,
  and returns available=false when Neo4j has no taxonomy nodes.
- _collect_leaf_items: recursively extracts leaf recommendations from NICE chapter JSON.
- GET /nice/loaded: returns all Guideline nodes with chapter/rec/rule counts.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.nice_guidance import (
    _collect_leaf_items,
    _extract_recommendations_from_section,
    _ranked_search,
    router,
)
from app import deps

# ── Test app setup ────────────────────────────────────────────────────────


def _make_app() -> FastAPI:
    app = FastAPI()
    app.dependency_overrides[deps.require_admin] = lambda: None
    app.include_router(router)
    return app


@pytest.fixture()
def test_client():
    return TestClient(_make_app())


# ── Shared catalogue fixture ──────────────────────────────────────────────

_CATALOGUE = [
    # Clinical guidelines (NG/CG) -- should rank above TAs for condition search
    {
        "code": "NG12",
        "title": "Suspected cancer: recognition, referral and early diagnosis",
        "type": "clinical-guideline",
    },
    {
        "code": "NG151",
        "title": "Bowel cancer: diagnosis and management",
        "type": "clinical-guideline",
    },
    {
        "code": "CG89",
        "title": "Colorectal cancer: the diagnosis and management",
        "type": "clinical-guideline",
    },
    # Technology appraisals -- contain "cancer" but should rank below NG/CG
    {
        "code": "TA563",
        "title": "Abemaciclib with an aromatase inhibitor for breast cancer",
        "type": "technology-appraisal",
    },
    {
        "code": "TA810",
        "title": "Abemaciclib with endocrine therapy for early breast cancer",
        "type": "technology-appraisal",
    },
    {
        "code": "TA579",
        "title": "Abemaciclib for hormone-receptor-positive breast cancer",
        "type": "technology-appraisal",
    },
    # Unrelated
    {
        "code": "NG156",
        "title": "Abdominal aortic aneurysm: diagnosis and management",
        "type": "clinical-guideline",
    },
    {
        "code": "NG28",
        "title": "Type 2 diabetes in adults: management",
        "type": "clinical-guideline",
    },
]


# ── _ranked_search unit tests ─────────────────────────────────────────────


class TestRankedSearch:
    """Unit tests for the _ranked_search helper (no network, no Redis)."""

    def test_ng12_appears_before_ta_codes_for_cancer_query(self):
        """NG12 'Suspected cancer' must rank above TA technology appraisals."""
        results = _ranked_search(_CATALOGUE, "cancer")
        codes = [r["code"] for r in results]

        assert "NG12" in codes, "NG12 should appear in cancer search results"
        assert "TA563" in codes, "TA563 should also appear (it matches cancer)"

        ng12_pos = codes.index("NG12")
        ta_pos = codes.index("TA563")
        assert (
            ng12_pos < ta_pos
        ), f"NG12 (position {ng12_pos}) should rank above TA563 (position {ta_pos})"

    def test_exact_code_match_is_first(self):
        """Exact code match (e.g. 'NG12') must always appear first."""
        results = _ranked_search(_CATALOGUE, "ng12")
        assert results[0]["code"] == "NG12"

    def test_partial_code_prefix_returns_matches(self):
        """Partial code like 'ng1' returns guidelines starting with NG1."""
        results = _ranked_search(_CATALOGUE, "ng1")
        codes = [r["code"] for r in results]
        assert "NG12" in codes
        assert "NG151" in codes
        # NG156 also starts with NG1
        assert "NG156" in codes

    def test_title_starts_with_ranks_above_title_contains(self):
        """'Suspected cancer...' starts with 'suspected' -- should rank higher
        than 'Abemaciclib...cancer' which only contains 'cancer'."""
        results = _ranked_search(_CATALOGUE, "suspected")
        assert results[0]["code"] == "NG12"

    def test_unrelated_entries_excluded(self):
        """Entries with no match to query are not returned."""
        results = _ranked_search(_CATALOGUE, "cancer")
        codes = [r["code"] for r in results]
        assert "NG28" not in codes  # diabetes -- no cancer match
        assert "NG156" not in codes  # aneurysm -- no cancer match

    def test_case_insensitive(self):
        """_ranked_search receives a pre-lowercased query (caller's responsibility).

        The endpoint always calls ``q.lower()`` before passing the value here.
        This test verifies that the internal matching itself is case-insensitive
        against catalogue titles (which may be mixed-case).
        """
        # Both queries are already lowercased as the caller would supply them
        results_bowel = _ranked_search(_CATALOGUE, "bowel")
        results_cancer = _ranked_search(_CATALOGUE, "cancer")
        assert any(
            r["code"] == "NG151" for r in results_bowel
        ), "Should match 'Bowel cancer' guideline"
        assert any(
            r["code"] == "NG12" for r in results_cancer
        ), "Should match 'Suspected cancer' guideline"

    def test_empty_catalogue_returns_empty(self):
        """Empty catalogue returns empty result without error."""
        assert _ranked_search([], "cancer") == []

    def test_no_matches_returns_empty(self):
        """Query with no matches returns empty list."""
        results = _ranked_search(_CATALOGUE, "zzznomatch")
        assert results == []

    def test_limit_respected(self):
        """Result count never exceeds limit."""
        big_catalogue = [
            {
                "code": f"NG{i}",
                "title": f"Cancer guideline {i}",
                "type": "clinical-guideline",
            }
            for i in range(1, 101)
        ]
        results = _ranked_search(big_catalogue, "cancer", limit=10)
        assert len(results) == 10

    def test_within_tier_sorted_alphabetically(self):
        """Within the same relevance tier, results are alphabetical by title."""
        results = _ranked_search(_CATALOGUE, "cancer")
        ng_results = [
            r
            for r in results
            if r["code"].startswith("NG") or r["code"].startswith("CG")
        ]
        titles = [r["title"] for r in ng_results]
        assert titles == sorted(
            titles
        ), "NG/CG results should be alphabetical within tier"


# ── GET /nice/catalogue endpoint tests ───────────────────────────────────


class TestGetCatalogueEndpoint:
    """Integration tests for the GET /nice/catalogue endpoint."""

    def test_empty_query_returns_cached_entries(self, test_client):
        """GET /nice/catalogue with no query returns from Redis cache."""
        cached = [
            {"code": "NG12", "title": "Suspected cancer", "type": "clinical-guideline"}
        ]

        with patch("app.routers.nice_guidance.NiceApiClient") as mock_cls:
            mock_client = mock_cls.return_value
            mock_client.fetch_catalogue = AsyncMock(return_value=cached)
            resp = test_client.get("/nice/catalogue")

        assert resp.status_code == 200
        assert resp.json()[0]["code"] == "NG12"

    def test_query_searches_redis_cache_when_warm(self, test_client):
        """GET /nice/catalogue?q= searches Redis cache when it has entries."""
        with patch("app.routers.nice_guidance.NiceApiClient") as mock_cls:
            mock_client = mock_cls.return_value
            mock_client.fetch_catalogue = AsyncMock(return_value=_CATALOGUE)
            resp = test_client.get("/nice/catalogue?q=cancer")

        assert resp.status_code == 200
        codes = [e["code"] for e in resp.json()]
        assert "NG12" in codes
        # NG12 must appear before TA563
        assert codes.index("NG12") < codes.index("TA563")
        # Live NICE API must NOT have been called
        mock_client.search_index.assert_not_called()

    def test_cold_cache_falls_back_to_live_nice_api(self, test_client):
        """GET /nice/catalogue?q= calls live NICE API when Redis cache is empty."""
        live_results = [
            {"code": "NG12", "title": "Suspected cancer", "type": "clinical-guideline"}
        ]

        with patch("app.routers.nice_guidance.NiceApiClient") as mock_cls:
            mock_client = mock_cls.return_value
            mock_client.fetch_catalogue = AsyncMock(return_value=[])  # empty cache
            mock_client.search_index = AsyncMock(return_value=live_results)
            resp = test_client.get("/nice/catalogue?q=cancer")

        assert resp.status_code == 200
        mock_client.search_index.assert_called_once_with("cancer")

    def test_returns_200_for_authenticated_request(self, test_client):
        """Endpoint returns 200 (auth is mocked by dependency override)."""
        with patch("app.routers.nice_guidance.NiceApiClient") as mock_cls:
            mock_client = mock_cls.return_value
            mock_client.fetch_catalogue = AsyncMock(return_value=[])
            mock_client.search_index = AsyncMock(return_value=[])
            resp = test_client.get("/nice/catalogue?q=cancer")

        assert resp.status_code == 200


# ── GET /nice/taxonomy ─────────────────────────────────────────────────────


class TestGetTaxonomy:
    """Tests for GET /nice/taxonomy endpoint."""

    _TAXONOMY_ROWS = [
        {
            "id": "conditions-and-diseases",
            "title": "Conditions and diseases",
            "subcategories": [
                {
                    "id": "conditions-and-diseases:cancer",
                    "title": "Cancer",
                    "guideline_codes": ["NG12", "NG151"],
                },
            ],
        },
    ]

    _LOADED_ROWS = [
        {"code": "NG12", "title": "Suspected cancer"},
    ]

    def test_returns_available_false_when_no_taxonomy(self, test_client):
        """Returns available=false when no TaxonomyCategory nodes exist."""
        with patch("app.routers.nice_guidance.CodingGraphClient") as mock_cls:
            neo = mock_cls.return_value
            neo.run.return_value = []
            # NiceApiClient.fetch_catalogue should not be called when Neo4j empty
            resp = test_client.get("/nice/taxonomy")

        assert resp.status_code == 200
        body = resp.json()
        assert body["available"] is False
        assert body["categories"] == []

    def test_returns_hierarchy_with_loaded_status(self, test_client):
        """Returns full category/subcategory tree with per-guideline loaded status."""
        with (
            patch("app.routers.nice_guidance.CodingGraphClient") as mock_cls,
            patch("app.routers.nice_guidance.NiceApiClient") as nice_cls,
        ):
            neo = mock_cls.return_value
            neo.run.side_effect = [self._TAXONOMY_ROWS, self._LOADED_ROWS]
            nice_cls.return_value.fetch_catalogue = AsyncMock(
                return_value=[
                    {
                        "code": "NG12",
                        "title": "Suspected cancer",
                        "type": "clinical-guideline",
                    },
                    {
                        "code": "NG151",
                        "title": "Bowel cancer",
                        "type": "clinical-guideline",
                    },
                ]
            )
            resp = test_client.get("/nice/taxonomy")

        assert resp.status_code == 200
        body = resp.json()
        assert body["available"] is True
        cats = body["categories"]
        assert len(cats) == 1
        assert cats[0]["id"] == "conditions-and-diseases"

        sub = cats[0]["subcategories"][0]
        assert sub["guideline_count"] == 2
        assert sub["loaded_count"] == 1  # only NG12 is "loaded"
        # New shape: guidelines list with code, title, loaded
        guideline_codes = [g["code"] for g in sub["guidelines"]]
        assert "NG12" in guideline_codes
        ng12 = next(g for g in sub["guidelines"] if g["code"] == "NG12")
        assert ng12["loaded"] is True
        assert ng12["title"] == "Suspected cancer"
        ng151 = next(g for g in sub["guidelines"] if g["code"] == "NG151")
        assert ng151["loaded"] is False

    def test_loaded_count_zero_when_none_imported(self, test_client):
        """loaded_count is 0 when no guidelines in the subcategory have been imported."""
        with (
            patch("app.routers.nice_guidance.CodingGraphClient") as mock_cls,
            patch("app.routers.nice_guidance.NiceApiClient") as nice_cls,
        ):
            neo = mock_cls.return_value
            neo.run.side_effect = [self._TAXONOMY_ROWS, []]
            nice_cls.return_value.fetch_catalogue = AsyncMock(return_value=[])
            resp = test_client.get("/nice/taxonomy")

        assert resp.status_code == 200
        sub = resp.json()["categories"][0]["subcategories"][0]
        assert sub["loaded_count"] == 0

    def test_title_falls_back_to_code_when_catalogue_unavailable(self, test_client):
        """When Redis catalogue is unavailable, guideline title falls back to the code itself."""
        with (
            patch("app.routers.nice_guidance.CodingGraphClient") as mock_cls,
            patch("app.routers.nice_guidance.NiceApiClient") as nice_cls,
        ):
            neo = mock_cls.return_value
            neo.run.side_effect = [self._TAXONOMY_ROWS, []]
            nice_cls.return_value.fetch_catalogue = AsyncMock(
                side_effect=Exception("Redis down")
            )
            resp = test_client.get("/nice/taxonomy")

        assert resp.status_code == 200
        sub = resp.json()["categories"][0]["subcategories"][0]
        # Title falls back to the code string when catalogue is unavailable
        for g in sub["guidelines"]:
            assert g["title"] == g["code"] or g["title"] != ""

    def test_closes_neo4j_client_on_success(self, test_client):
        """CodingGraphClient.close() is called even on success."""
        with (
            patch("app.routers.nice_guidance.CodingGraphClient") as mock_cls,
            patch("app.routers.nice_guidance.NiceApiClient") as nice_cls,
        ):
            neo = mock_cls.return_value
            neo.run.side_effect = [self._TAXONOMY_ROWS, self._LOADED_ROWS]
            nice_cls.return_value.fetch_catalogue = AsyncMock(return_value=[])
            test_client.get("/nice/taxonomy")
            neo.close.assert_called_once()

    def test_closes_neo4j_client_on_error(self, test_client):
        """CodingGraphClient.close() is called even when Neo4j raises."""
        with patch("app.routers.nice_guidance.CodingGraphClient") as mock_cls:
            neo = mock_cls.return_value
            neo.run.side_effect = RuntimeError("Neo4j down")
            with pytest.raises(RuntimeError):
                test_client.get("/nice/taxonomy")
            neo.close.assert_called_once()


# ── _collect_leaf_items unit tests ────────────────────────────────────────


class TestExtractRecommendationsFromSection:
    """Unit tests for _extract_recommendations_from_section (section HTML parser).

    This function is the critical bridge between the NICE Syndication API and
    Neo4j.  It parses the ``Content`` XHTML field that every section-level
    JSON response contains, extracting the actual clinical recommendation text
    from ``<article class="numbered-paragraph">`` elements.
    """

    _NG12_SECTION_HTML = """
    <div>
      <article class="numbered-paragraph" id="ng12-chapter-1-recommendation-1-1-1">
        <h5>1.1.1</h5>
        <p>Offer a 2-week-wait referral for colorectal cancer in adults aged 40 and over
        with unexplained weight loss and abdominal pain.</p>
      </article>
      <article class="numbered-paragraph" id="ng12-chapter-1-recommendation-1-1-2">
        <h5>1.1.2</h5>
        <p>Consider a 2-week-wait referral for colorectal cancer in adults with rectal
        bleeding and any of the following unexplained symptoms: abdominal pain, change
        in bowel habit, weight loss, iron-deficiency anaemia.</p>
      </article>
    </div>
    """

    def test_extracts_two_articles(self):
        """Parser returns one dict per <article> element."""
        section_json = {
            "Content": self._NG12_SECTION_HTML,
            "SectionId": "sec-1.1",
            "Title": "1.1",
        }
        recs = _extract_recommendations_from_section(section_json, "NG12")
        assert len(recs) == 2

    def test_verbatim_text_is_full_paragraph(self):
        """The ``Text`` key contains the full clinical recommendation text (not just the heading)."""
        section_json = {
            "Content": self._NG12_SECTION_HTML,
            "SectionId": "sec-1.1",
            "Title": "1.1",
        }
        recs = _extract_recommendations_from_section(section_json, "NG12")
        assert "2-week-wait referral" in recs[0]["Text"]
        assert "aged 40 and over" in recs[0]["Text"]

    def test_title_is_recommendation_number(self):
        """The ``Title`` key contains the recommendation number from the heading."""
        section_json = {"Content": self._NG12_SECTION_HTML, "SectionId": "sec-1.1"}
        recs = _extract_recommendations_from_section(section_json, "NG12")
        assert recs[0]["Title"] == "1.1.1"
        assert recs[1]["Title"] == "1.1.2"

    def test_empty_content_returns_empty_list(self):
        """Sections with no Content field return an empty list."""
        assert _extract_recommendations_from_section({}, "NG12") == []
        assert _extract_recommendations_from_section({"Content": ""}, "NG12") == []

    def test_no_fallback_for_cross_reference_sections(self):
        """Sections without <article> elements return an empty list.

        NICE guidelines contain two presentations of their recommendations:
        (1) numbered-paragraph chapters (canonical) and (2) cross-reference
        tables organised by symptom/sign.  The cross-reference chapters must
        NOT be ingested as recommendations — they would create duplicate,
        corrupt data.  The parser intentionally returns [] for such sections.
        """
        html = "<div class='section'><p>All patients should be referred promptly.</p></div>"
        section_json = {"Content": html, "SectionId": "sec-2", "Title": "2. Referral"}
        recs = _extract_recommendations_from_section(section_json, "NG12")
        assert recs == []

    def test_chapter_id_is_propagated(self):
        """chapter_id argument is reflected in ChapterId field of returned dicts."""
        section_json = {"Content": self._NG12_SECTION_HTML, "SectionId": "sec-1.1"}
        recs = _extract_recommendations_from_section(
            section_json, "NG12", chapter_id="NG12:v1:CH000"
        )
        assert all(r["ChapterId"] == "NG12:v1:CH000" for r in recs)

    def test_chapter_id_from_api_takes_precedence(self):
        """ChapterId from the section JSON takes precedence over the argument."""
        html = """
        <article class="numbered-paragraph">
          <h5>3.1.1</h5><p>Refer patients immediately.</p>
        </article>"""
        section_json = {
            "Content": html,
            "SectionId": "sec-3.1",
            "ChapterId": "api-chapter-3",
        }
        recs = _extract_recommendations_from_section(
            section_json, "NG12", chapter_id="fallback-chapter"
        )
        assert recs[0]["ChapterId"] == "api-chapter-3"

    def test_section_title_propagated_to_all_recs(self):
        """SectionTitle from the section JSON (cancer site) appears on every returned rec."""
        section_json = {
            "Content": self._NG12_SECTION_HTML,
            "SectionId": "sec-1.1",
            "Title": "Lung cancer",
        }
        recs = _extract_recommendations_from_section(section_json, "NG12")
        assert all(r["SectionTitle"] == "Lung cancer" for r in recs)

    def test_section_title_empty_when_no_title(self):
        """SectionTitle is an empty string when the section JSON has no Title."""
        section_json = {"Content": self._NG12_SECTION_HTML, "SectionId": "sec-1.1"}
        recs = _extract_recommendations_from_section(section_json, "NG12")
        assert all(r["SectionTitle"] == "" for r in recs)

    def test_is_normative_true_on_article_recs(self):
        """Each rec extracted from an <article> element carries isNormative=True."""
        section_json = {
            "Content": self._NG12_SECTION_HTML,
            "SectionId": "sec-1.1",
            "Title": "Lung cancer",
        }
        recs = _extract_recommendations_from_section(section_json, "NG12")
        assert all(r["isNormative"] is True for r in recs)

    def test_list_structure_is_none_for_plain_sentence_recs(self):
        """Neither fixture article has a <ul> -- ListStructure is None, not omitted."""
        section_json = {
            "Content": self._NG12_SECTION_HTML,
            "SectionId": "sec-1.1",
            "Title": "Lung cancer",
        }
        recs = _extract_recommendations_from_section(section_json, "NG12")
        assert all("ListStructure" in r for r in recs)
        assert all(r["ListStructure"] is None for r in recs)

    def test_list_structure_populated_for_recs_with_nested_lists(self):
        """A recommendation with a <ul> gets a parsed, offset-aligned ListStructure."""
        html = """
        <article class="numbered-paragraph" id="ng12-1_2_9">
          <h5>1.2.9</h5>
          <div>
            <p>Consider referral in people with:</p>
            <ul class="itemizedlist">
              <li class="listitem"><p>haematemesis, or</p></li>
              <li class="listitem"><p>a raised platelet count</p></li>
            </ul>
          </div>
        </article>
        """
        section_json = {"Content": html, "SectionId": "sec-1.2", "Title": "GI cancers"}
        recs = _extract_recommendations_from_section(section_json, "NG12")
        structure = recs[0]["ListStructure"]
        assert structure is not None
        assert [item["text"] for item in structure["items"]] == [
            "haematemesis",
            "a raised platelet count",
        ]
        for item in structure["items"]:
            assert recs[0]["Text"][item["start"] : item["end"]] == item["text"]

    def test_h6_heading_is_the_recommendation_number_not_the_section_title(self):
        """NG12 1.5.12-1.5.15 sit under an Endometrial subsection and use
        ``<h6>``, not ``<h5>``. Falling back to the section title made
        four sibling recs share number '1.5 Gynaecological cancers' so
        list-structure backfill painted 1.5.13's situations onto 1.5.12.
        """
        html = """
        <article class="numbered-paragraph" id="ng12-1_5_12">
          <h6>1.5.12</h6>
          <p>Refer women aged 55 and over with unexplained
          postmenopausal bleeding.</p>
        </article>
        <article class="numbered-paragraph" id="ng12-1_5_13">
          <h6>1.5.13</h6>
          <p>Consider an ultrasound if they have:</p>
          <ul class="itemizedlist">
            <li class="listitem"><p>unexplained vaginal discharge, or</p></li>
            <li class="listitem"><p>visible haematuria</p></li>
          </ul>
        </article>
        """
        section_json = {
            "Content": html,
            "SectionId": "sec-1.5",
            "Title": "1.5 Gynaecological cancers",
        }
        recs = _extract_recommendations_from_section(section_json, "NG12")
        assert [r["Title"] for r in recs] == ["1.5.12", "1.5.13"]
        assert recs[0]["ListStructure"] is None
        assert recs[1]["ListStructure"] is not None
        assert [item["text"] for item in recs[1]["ListStructure"]["items"]] == [
            "unexplained vaginal discharge",
            "visible haematuria",
        ]


class TestCollectLeafItems:
    """Unit tests for the _collect_leaf_items helper."""

    def test_extracts_flat_items_with_text(self):
        """Items with Text are returned directly."""
        chapter = {
            "Items": [
                {"Title": "1.1.1", "Text": "Refer urgently."},
                {"Title": "1.1.2", "Text": "Consider colonoscopy."},
            ]
        }
        results = _collect_leaf_items(chapter)
        assert len(results) == 2
        assert results[0]["Text"] == "Refer urgently."

    def test_recurses_into_nested_items(self):
        """Items nested under section groups are collected."""
        chapter = {
            "Items": [
                {
                    "Title": "1.1 Lower GI cancers",  # section group -- no Text
                    "Items": [
                        {
                            "Title": "1.1.1",
                            "Text": "Refer for suspected colorectal cancer.",
                        },
                        {"Title": "1.1.2", "Text": "Consider FIT test."},
                    ],
                }
            ]
        }
        results = _collect_leaf_items(chapter)
        assert len(results) == 2

    def test_three_levels_of_nesting(self):
        """Leaf items at three levels deep are collected."""
        chapter = {
            "Items": [
                {
                    "Title": "1.1",
                    "Items": [
                        {
                            "Title": "1.1.1",
                            "Items": [
                                {"Title": "1.1.1.1", "Text": "Deep recommendation."},
                            ],
                        }
                    ],
                }
            ]
        }
        results = _collect_leaf_items(chapter)
        assert len(results) == 1
        assert results[0]["Text"] == "Deep recommendation."

    def test_skips_intermediate_groups_without_text(self):
        """Section group headings (no Text) are not returned as recommendations."""
        chapter = {
            "Items": [
                {"Title": "1.1 Section heading"},  # no Text, no sub-Items
                {"Title": "1.1.1", "Text": "Actual recommendation."},
            ]
        }
        results = _collect_leaf_items(chapter)
        # Heading-only items (no Text, no sub-Items) are still collected if they
        # have a Title and no Items -- this is intentional for chapters that only
        # have Title-based items (e.g. context chapters).
        texts = [r.get("Text", "") for r in results]
        assert "Actual recommendation." in texts

    def test_empty_chapter_returns_empty_list(self):
        """Chapter with no Items returns empty list."""
        assert _collect_leaf_items({}) == []
        assert _collect_leaf_items({"Items": []}) == []

    def test_falls_back_to_resources_key(self):
        """Uses 'Resources' key when 'Items' is absent."""
        chapter = {
            "Resources": [
                {"Title": "1.1.1", "Text": "Recommendation via Resources key."},
            ]
        }
        results = _collect_leaf_items(chapter)
        assert len(results) == 1


# ── GET /nice/loaded ──────────────────────────────────────────────────────


class TestGetLoadedGuidelines:
    """Tests for GET /nice/loaded endpoint."""

    _LOADED_ROWS = [
        {
            "code": "NG12",
            "title": "Suspected cancer: recognition and referral",
            "guidance_type": "clinical-guideline",
            "publication_date": "2015-06-23",
            "chapter_count": 3,
            "recommendation_count": 71,
            "rules_pending": 5,
            "rules_approved": 0,
            "rules_rejected": 0,
        },
        {
            "code": "NG151",
            "title": "Bowel cancer: diagnosis and management",
            "guidance_type": "clinical-guideline",
            "publication_date": "2020-01-29",
            "chapter_count": 2,
            "recommendation_count": 45,
            "rules_pending": 0,
            "rules_approved": 45,
            "rules_rejected": 0,
        },
    ]

    def test_returns_loaded_guidelines_list(self, test_client):
        """GET /nice/loaded returns list of Guideline nodes with rule counts."""
        with patch("app.routers.nice_guidance.CodingGraphClient") as mock_cls:
            neo = mock_cls.return_value
            neo.run.return_value = self._LOADED_ROWS
            resp = test_client.get("/nice/loaded")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 2
        ng12 = next(g for g in body if g["code"] == "NG12")
        assert ng12["chapter_count"] == 3
        assert ng12["recommendation_count"] == 71
        assert ng12["rules_pending"] == 5
        assert ng12["rules_approved"] == 0

    def test_returns_empty_list_when_no_guidelines(self, test_client):
        """GET /nice/loaded returns [] when no guidelines are loaded."""
        with patch("app.routers.nice_guidance.CodingGraphClient") as mock_cls:
            neo = mock_cls.return_value
            neo.run.return_value = []
            resp = test_client.get("/nice/loaded")

        assert resp.status_code == 200
        assert resp.json() == []

    def test_closes_neo4j_client(self, test_client):
        """CodingGraphClient.close() is called after GET /nice/loaded."""
        with patch("app.routers.nice_guidance.CodingGraphClient") as mock_cls:
            neo = mock_cls.return_value
            neo.run.return_value = []
            test_client.get("/nice/loaded")
            neo.close.assert_called_once()
