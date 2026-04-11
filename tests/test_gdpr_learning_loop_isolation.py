from __future__ import annotations

from libs.cypher import gold_label_queries as glq
from libs.cypher import training_candidate_queries as tcq

FORBIDDEN = ("patient_id", "patient_id_hash", "encounter_id", "tenant_id", "org_id")


def test_training_candidate_queries_exclude_forbidden_identifiers() -> None:
    joined = "\n".join(
        [
            tcq.UPSERT_TRAINING_CANDIDATE,
            tcq.GET_TRAINING_CANDIDATES_PAGE,
            tcq.GET_TRAINING_CANDIDATE_BY_ID,
        ]
    )
    for token in FORBIDDEN:
        assert token not in joined


def test_gold_label_queries_exclude_forbidden_identifiers() -> None:
    joined = "\n".join(
        [
            glq.UPSERT_GOLD_LABEL,
            glq.GET_GOLD_LABELS_PAGE,
            glq.GET_GOLD_LABEL_BY_ID,
            glq.GET_ALL_GOLD_LABELS_FOR_EXPORT,
        ]
    )
    for token in FORBIDDEN:
        assert token not in joined
