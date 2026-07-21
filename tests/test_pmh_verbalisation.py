"""Tests for seeded PMH verbalisation (surface form / synonym / PT)."""

from __future__ import annotations

import random
from unittest.mock import MagicMock

from libs.validation_lab.models import PmhItem
from libs.validation_lab.pmh_verbalisation import (
    compose_submission_text,
    pick_verbalised_term,
    render_verbalised_pmh_narrative,
)


def test_pick_prefers_surface_form() -> None:
    pools = {
        "c1": {
            "surface_forms": ["tummy pain", "belly ache"],
            "synonyms": ["abdominal pain"],
            "preferred_term": "Abdominal pain",
        }
    }
    rng = random.Random(1)
    picked = pick_verbalised_term("c1", pools=pools, rng=rng)
    assert picked in {"tummy pain", "belly ache"}


def test_pick_falls_back_to_synonym_when_no_surface_forms() -> None:
    pools = {
        "c1": {
            "surface_forms": [],
            "synonyms": ["belly ache", "stomach pain"],
            "preferred_term": "Abdominal pain (finding)",
        }
    }
    rng = random.Random(2)
    picked = pick_verbalised_term("c1", pools=pools, rng=rng)
    assert picked in {"belly ache", "stomach pain"}


def test_pick_falls_back_to_stripped_preferred_term() -> None:
    pools = {
        "c1": {
            "surface_forms": [],
            "synonyms": [],
            "preferred_term": "Abdominal pain (finding)",
        }
    }
    rng = random.Random(3)
    picked = pick_verbalised_term("c1", pools=pools, rng=rng)
    assert picked == "Abdominal pain"


def test_seeded_pick_is_stable() -> None:
    pools = {
        "c1": {
            "surface_forms": ["a", "b", "c", "d"],
            "synonyms": [],
            "preferred_term": "X",
        }
    }
    first = pick_verbalised_term("c1", pools=pools, rng=random.Random("seed-1"))
    second = pick_verbalised_term("c1", pools=pools, rng=random.Random("seed-1"))
    third = pick_verbalised_term("c1", pools=pools, rng=random.Random("seed-2"))
    assert first == second
    assert first in {"a", "b", "c", "d"}
    assert third in {"a", "b", "c", "d"}


def test_render_verbalised_pmh_groups_categories() -> None:
    pmh = [
        PmhItem(category="condition", concept_id="c1", term="Asthma (disorder)"),
        PmhItem(category="medication", concept_id="c2", term="Salbutamol"),
    ]
    pools = {
        "c1": {"surface_forms": ["asthma"], "synonyms": [], "preferred_term": "Asthma"},
        "c2": {
            "surface_forms": [],
            "synonyms": [],
            "preferred_term": "Salbutamol (substance)",
        },
    }
    narrative = render_verbalised_pmh_narrative(pmh, seed="case-1", pools=pools)
    assert "Past medical history: asthma." in narrative
    assert "Current medications: Salbutamol." in narrative


def test_compose_submission_text_joins_reason_and_pmh() -> None:
    pmh = [PmhItem(category="condition", concept_id="c1", term="Asthma")]
    pools = {
        "c1": {"surface_forms": ["asthma"], "synonyms": [], "preferred_term": "Asthma"}
    }
    text = compose_submission_text(
        reason="Please advise on persistent cough",
        pmh=pmh,
        seed="case-1",
        pools=pools,
    )
    assert text.startswith("Please advise on persistent cough")
    assert "Past medical history: asthma." in text


def test_load_verbalisation_pools_from_client() -> None:
    from libs.validation_lab.pmh_verbalisation import load_verbalisation_pools

    client = MagicMock()
    client.run.side_effect = [
        [{"concept_id": "c1", "forms": ["tummy pain"]}],
        [{"concept_id": "c1", "forms": ["abdominal pain"]}],
        [{"concept_id": "c1", "term": "Abdominal pain (finding)"}],
    ]
    pools = load_verbalisation_pools(client, ["c1"])
    assert pools["c1"]["surface_forms"] == ["tummy pain"]
    assert pools["c1"]["synonyms"] == ["abdominal pain"]
    assert pools["c1"]["preferred_term"] == "Abdominal pain"
