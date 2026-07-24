"""Unit tests for nice_list_parser.parse_recommendation_list_structure.

Uses the REAL NICE Syndication API HTML for NG12 1.2.9, extracted from
the raw-HTML fixture already checked into the repo
(``reports/nice_ng12_raw/ng12_full.json``) -- confirmed live against the
API per the highlight-to-build wizard plan's "Ingestion" section. This
fixture's actual markup has four top-level pathways (not six -- that
figure elsewhere in this codebase's test fixtures is illustrative prose,
not this archived raw-HTML snapshot), two of which carry a nested "any
of the following" AT_LEAST list.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from app.services.nice_list_parser import parse_recommendation_list_structure

_FIXTURE_PATH = (
    Path(__file__).resolve().parents[3] / "reports" / "nice_ng12_raw" / "ng12_full.json"
)


def _load_1_2_9_article():
    """Extract the 1.2.9 ``<article>`` tag from the real archived NG12 fixture."""
    with _FIXTURE_PATH.open() as f:
        data = json.load(f)
    # Chapter 2 = "Recommendations organised by site of cancer";
    # section 1 = "1.2 Upper gastrointestinal tract cancers".
    section = data["chapters"][2]["sections"][1]
    soup = BeautifulSoup(section["content_html"], "html.parser")
    article = soup.find("article", id="ng12-1_2_9")
    assert article is not None, "fixture layout changed -- re-locate the 1.2.9 article"
    return article


@pytest.fixture()
def article_and_text():
    article = _load_1_2_9_article()
    flattened_text = article.get_text(" ", strip=True)
    return article, flattened_text


class TestParseRecommendationListStructure:
    def test_returns_four_top_level_pathways(self, article_and_text):
        article, flattened_text = article_and_text
        structure = parse_recommendation_list_structure(article, flattened_text)
        assert structure is not None
        assert len(structure["items"]) == 4

    def test_lead_text_is_the_intro_sentence(self, article_and_text):
        article, flattened_text = article_and_text
        structure = parse_recommendation_list_structure(article, flattened_text)
        assert "stomach cancer" in structure["lead_text"]
        # Real NICE markup uses a non-breaking space ("55\xa0or over").
        assert "55" in structure["lead_text"]
        assert "over" in structure["lead_text"]

    def test_simple_pathway_has_no_children_and_clean_text(self, article_and_text):
        article, flattened_text = article_and_text
        structure = parse_recommendation_list_structure(article, flattened_text)
        pathway_1 = structure["items"][0]
        assert pathway_1["text"] == "treatment-resistant dyspepsia"
        assert "children" not in pathway_1

    def test_dangling_comma_connector_stripped_with_no_space(self, article_and_text):
        article, flattened_text = article_and_text
        structure = parse_recommendation_list_structure(article, flattened_text)
        pathway_2 = structure["items"][1]
        # Real NICE markup: "...levels,or" (no space before "or").
        assert pathway_2["text"] == "upper abdominal pain with low haemoglobin levels"

    def test_pathway_with_nested_at_least_list_own_text_excludes_children(
        self, article_and_text
    ):
        article, flattened_text = article_and_text
        structure = parse_recommendation_list_structure(article, flattened_text)
        pathway_3 = structure["items"][2]
        assert pathway_3["text"] == "raised platelet count with any of the following:"
        assert [c["text"] for c in pathway_3["children"]] == [
            "nausea",
            "vomiting",
            "weight loss",
            "reflux",
            "dyspepsia",
            "upper abdominal pain",
        ]

    def test_trailing_connector_stripped_from_misplaced_nested_last_item(
        self, article_and_text
    ):
        """The real markup nests item 4's boundary connector inside item 3's
        OWN nested list's last <li> ("upper abdominal pain, or") -- the
        cleaner must strip it there, not just on top-level items."""
        article, flattened_text = article_and_text
        structure = parse_recommendation_list_structure(article, flattened_text)
        last_child = structure["items"][2]["children"][-1]
        assert last_child["text"] == "upper abdominal pain"
        assert "or" not in last_child["text"].split()

    def test_second_nested_pathway_children(self, article_and_text):
        article, flattened_text = article_and_text
        structure = parse_recommendation_list_structure(article, flattened_text)
        pathway_4 = structure["items"][3]
        assert pathway_4["text"] == "nausea or vomiting with any of the following:"
        child_texts = [c["text"] for c in pathway_4["children"]]
        assert child_texts[:3] == ["weight loss", "reflux", "dyspepsia"]
        # Trailing citation is a separate, later concern -- not stripped here.
        assert "upper abdominal pain" in child_texts[3]

    def test_every_node_offset_round_trips_against_flattened_text(
        self, article_and_text
    ):
        """start/end must be exact -- no fuzzy re-matching between the tree
        and the verbatim string (per this module's docstring)."""
        article, flattened_text = article_and_text
        structure = parse_recommendation_list_structure(article, flattened_text)

        def _check(node):
            assert flattened_text[node["start"] : node["end"]] == node["text"]
            for child in node.get("children", []):
                _check(child)

        for item in structure["items"]:
            _check(item)

    def test_offsets_are_monotonically_increasing_across_siblings(
        self, article_and_text
    ):
        article, flattened_text = article_and_text
        structure = parse_recommendation_list_structure(article, flattened_text)
        starts = [item["start"] for item in structure["items"]]
        assert starts == sorted(starts)
        assert len(set(starts)) == len(starts)

    def test_returns_none_for_a_plain_sentence_with_no_list(self):
        html = (
            "<article class='numbered-paragraph'><h5>1.2.8</h5>"
            "<p>Consider non-urgent, direct access upper gastrointestinal "
            "endoscopy in people with haematemesis.</p></article>"
        )
        article = BeautifulSoup(html, "html.parser").find("article")
        flattened_text = article.get_text(" ", strip=True)
        assert parse_recommendation_list_structure(article, flattened_text) is None

    def test_returns_none_when_article_has_no_ul_at_all(self):
        html = (
            "<article class='numbered-paragraph'><p>No lists here at all.</p></article>"
        )
        article = BeautifulSoup(html, "html.parser").find("article")
        assert (
            parse_recommendation_list_structure(article, "No lists here at all.")
            is None
        )
