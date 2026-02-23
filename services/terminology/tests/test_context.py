"""Tests for UK GP context rules loaded into medspaCy ConText.

These tests verify the context_rules.json file is valid JSON and contains
the expected categories and UK-specific rules.
"""

import json
from pathlib import Path

import pytest


RULES_PATH = (
    Path(__file__).resolve().parents[1]
    / "nlp"
    / "resources"
    / "en_gb"
    / "context_rules.json"
)


@pytest.fixture(scope="module")
def rules():
    with open(RULES_PATH) as f:
        data = json.load(f)
    return data["context_rules"]


def test_rules_file_loads(rules):
    assert len(rules) > 0


def test_all_rules_have_required_keys(rules):
    for rule in rules:
        assert "category" in rule
        assert "literal" in rule
        assert "direction" in rule


def test_contains_negation_rules(rules):
    neg = [r for r in rules if r["category"] == "NEGATED_EXISTENCE"]
    assert len(neg) > 10


def test_contains_uk_specific_negation(rules):
    neg_literals = {
        r["literal"] for r in rules if r["category"] == "NEGATED_EXISTENCE"
    }
    assert "NAD" in neg_literals
    assert "nil" in neg_literals
    assert "NKA" in neg_literals


def test_contains_possible_existence(rules):
    poss = [r for r in rules if r["category"] == "POSSIBLE_EXISTENCE"]
    assert len(poss) > 5
    poss_literals = {r["literal"] for r in poss}
    assert "? prefix" in poss_literals or "query" in poss_literals


def test_contains_historical(rules):
    hist = [r for r in rules if r["category"] == "HISTORICAL"]
    assert len(hist) > 3
    hist_literals = {r["literal"] for r in hist}
    assert "PHx" in hist_literals


def test_contains_hypothetical(rules):
    hypo = [r for r in rules if r["category"] == "HYPOTHETICAL"]
    assert len(hypo) > 5
    hypo_literals = {r["literal"] for r in hypo}
    assert "consider" in hypo_literals
    assert "2ww" in hypo_literals


def test_contains_family(rules):
    fam = [r for r in rules if r["category"] == "FAMILY"]
    assert len(fam) > 0
    fam_literals = {r["literal"] for r in fam}
    assert "FHx" in fam_literals


def test_contains_resolved(rules):
    res = [r for r in rules if r["category"] == "RESOLVED"]
    assert len(res) > 5
    res_literals = {r["literal"] for r in res}
    assert "resolved" in res_literals
    assert "settled" in res_literals
    assert "improved" in res_literals


def test_valid_directions(rules):
    valid = {"FORWARD", "BACKWARD", "TERMINATE"}
    for rule in rules:
        assert rule["direction"] in valid, (
            f"Invalid direction '{rule['direction']}' in rule '{rule['literal']}'"
        )
