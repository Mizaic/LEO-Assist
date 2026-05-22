from services.api.app.services._logic_tree import (
    extract_satisfying_concept_sets,
    extract_satisfying_pathways,
)


def concept(concept_id: str, term: str) -> dict:
    return {
        "kind": "CONCEPT",
        "criterion": {
            "snomed_concept_id": concept_id,
            "preferred_term": term,
        },
    }


def age_40() -> dict:
    return {
        "kind": "DEMOGRAPHIC",
        "field": "age",
        "operator": ">=",
        "value": 40,
        "unit": "years",
    }


def age_lt_50() -> dict:
    return {
        "kind": "DEMOGRAPHIC",
        "field": "age",
        "operator": "<",
        "value": 50,
        "unit": "years",
    }


def age_gte_50() -> dict:
    return {
        "kind": "DEMOGRAPHIC",
        "field": "age",
        "operator": ">=",
        "value": 50,
        "unit": "years",
    }


def ids(trigger_sets: list[list[dict]]) -> list[list[str]]:
    return [[trigger["concept_id"] for trigger in group] for group in trigger_sets]


def test_extract_satisfying_concept_sets_returns_each_top_level_pathway() -> None:
    tree = {
        "kind": "OR",
        "children": [
            {
                "kind": "AND",
                "children": [
                    age_40(),
                    {
                        "kind": "AT_LEAST",
                        "min": 2,
                        "children": [
                            concept("1", "Cough"),
                            concept("2", "Fatigue"),
                            concept("3", "Dyspnea"),
                        ],
                    },
                ],
            },
            {
                "kind": "AND",
                "children": [
                    age_40(),
                    concept("4", "Smoking"),
                    {
                        "kind": "AT_LEAST",
                        "min": 1,
                        "children": [
                            concept("1", "Cough"),
                            concept("2", "Fatigue"),
                        ],
                    },
                ],
            },
        ],
    }

    assert ids(extract_satisfying_concept_sets(tree)) == [["1", "2"], ["4", "1"]]


def test_extract_satisfying_concept_sets_keeps_global_prerequisites() -> None:
    tree = {
        "kind": "AND",
        "children": [
            concept("0", "Previous abnormal result"),
            {
                "kind": "OR",
                "children": [
                    concept("1", "Cough"),
                    concept("2", "Finger clubbing"),
                ],
            },
        ],
    }

    assert ids(extract_satisfying_concept_sets(tree)) == [["0", "1"], ["0", "2"]]


def test_extract_satisfying_pathways_keeps_demographic_alternatives() -> None:
    tree = {
        "kind": "AND",
        "children": [
            concept("1", "Breast lump"),
            {
                "kind": "OR",
                "children": [age_lt_50(), age_gte_50()],
            },
        ],
    }

    pathways = extract_satisfying_pathways(tree)

    assert ids([p["triggers"] for p in pathways]) == [["1"], ["1"]]
    assert [
        [
            (constraint["field"], constraint["operator"], constraint["value"])
            for constraint in p["demographic_constraints"]
        ]
        for p in pathways
    ] == [[("age", "<", 50)], [("age", ">=", 50)]]
