"""SNOMED-grounded relation enrichment.

Atlas trace:
  UN: UN-19FDDE7E
  DI: DI-209F4326
  DO: DO-604CE96E
  VT: VT-E3682B7B
"""

from __future__ import annotations

from libs.pipeline_graph.subgraphs.snomed_enrichment import snomed_enrichment


def _jaundice_related(_ids: list[str]) -> dict:
    return {
        "24199005": {
            "finding_sites": [
                {
                    "id": "10200004",
                    "fsn": "Liver structure (body structure)",
                    "semantic_tag": "body structure",
                    "rel": "HAS_FINDING_SITE",
                }
            ],
            "associated_findings": [],
            "interprets_observables": [],
            "has_components": [],
            "interpreted_by_findings": [],
            "component_of_procedures": [],
            "procedure_sites": [],
        }
    }


def test_enrichment_adds_inferred_finding_site():
    out = snomed_enrichment(
        {
            "entities": [
                {
                    "text": "jaundice",
                    "label": "finding",
                    "concept_id": "24199005",
                }
            ]
        },
        fetch_related=_jaundice_related,
    )
    texts = [e["text"] for e in out["entities"]]
    assert "Liver structure" in texts
    site = next(e for e in out["entities"] if e["text"] == "Liver structure")
    assert site["inferred"] is True
    assert site["concept_id"] == "10200004"
    rels = out["entities"][0]["__snomed_relations"]
    assert rels[0]["type"] == "finding_site"
    assert rels[0]["target_idx"] == 1
    assert out["snomed_candidates"][0]["type"] == "finding_site"


def test_enrichment_links_two_coded_entities_without_inferring():
    def fetch(_ids: list[str]) -> dict:
        return {
            "365611000": {
                "interprets_observables": [
                    {
                        "id": "1022471000000107",
                        "fsn": "MCH (observable entity)",
                        "semantic_tag": "observable entity",
                        "rel": "INTERPRETS",
                    }
                ]
            }
        }

    out = snomed_enrichment(
        {
            "entities": [
                {
                    "text": "low MCH",
                    "label": "finding",
                    "concept_id": "365611000",
                },
                {
                    "text": "MCH",
                    "label": "observable_entity",
                    "concept_id": "1022471000000107",
                },
            ]
        },
        fetch_related=fetch,
    )
    assert len(out["entities"]) == 2
    rels = out["entities"][0]["__snomed_relations"]
    assert rels[0]["type"] == "interprets"
    assert rels[0]["target_idx"] == 1


def test_enrichment_skips_uncoded_entities():
    out = snomed_enrichment(
        {"entities": [{"text": "jaundice", "label": "finding"}]},
        fetch_related=lambda _ids: (_ for _ in ()).throw(AssertionError("no fetch")),
    )
    assert out["snomed_candidates"] == []
    assert "inferred" not in out["entities"][0]


def test_enrichment_skips_finding_finding_qualifies_style_neighbours():
    def fetch(_ids: list[str]) -> dict:
        return {
            "1": {
                "associated_findings": [
                    {
                        "id": "2",
                        "fsn": "Weight loss (finding)",
                        "semantic_tag": "finding",
                        "rel": "HAS_ASSOCIATED_FINDING",
                    }
                ]
            }
        }

    out = snomed_enrichment(
        {
            "entities": [
                {"text": "jaundice", "label": "finding", "concept_id": "1"},
                {"text": "weight loss", "label": "finding", "concept_id": "2"},
            ]
        },
        fetch_related=fetch,
    )
    rels = out["entities"][0].get("__snomed_relations") or []
    assert rels[0]["type"] == "associated_finding"
    assert rels[0]["target_idx"] == 1


def test_enrichment_reuses_letter_named_site_instead_of_inferring():
    out = snomed_enrichment(
        {
            "entities": [
                {
                    "text": "jaundice",
                    "label": "finding",
                    "concept_id": "24199005",
                },
                {"text": "liver", "label": "body_structure"},
            ]
        },
        fetch_related=_jaundice_related,
    )
    assert len(out["entities"]) == 2
    assert not out["entities"][1].get("inferred")
    rels = out["entities"][0]["__snomed_relations"]
    assert rels[0]["type"] == "finding_site"
    assert rels[0]["target_idx"] == 1
