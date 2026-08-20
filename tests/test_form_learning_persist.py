"""VT for DI-0C766F85 and DI-4A012A59 -- persist learned form knowledge."""

from __future__ import annotations

from unittest.mock import MagicMock

from libs.cypher.form_learning_queries import (
    LIST_EXTRACTION_FEW_SHOTS,
    LIST_FORM_FINGERPRINTS,
    UPSERT_EXTRACTION_FEW_SHOT,
    UPSERT_FORM_FINGERPRINT,
)
from libs.pipeline.document_quality import form_fingerprint, score_document_quality
from libs.pipeline.extraction_learning_store import (
    learned_few_shots,
    persist_review_learning,
    reset_learned_few_shots,
    set_learning_writers,
)
from libs.pipeline.extraction_review_store import (
    PersistReviewRequest,
    persist_extraction_review_task,
    resume_extraction_review,
)
from libs.pipeline.form_fingerprint_registry import (
    known_fingerprints,
    reset_registry,
    set_persisted_loader,
)

UNIQUE_FORM = (
    "Appendix Z: Unique persist form\n" "Please tick the box\n" "Rare finding [X]\n"
)


def test_upsert_queries_target_knowledge_nodes_not_prompt_config() -> None:
    assert "FormFingerprint" in UPSERT_FORM_FINGERPRINT
    assert "ExtractionFewShot" in UPSERT_EXTRACTION_FEW_SHOT
    assert "PromptConfig" not in UPSERT_FORM_FINGERPRINT
    assert "PromptConfig" not in UPSERT_EXTRACTION_FEW_SHOT
    assert "FormFingerprint" in LIST_FORM_FINGERPRINTS
    assert "ExtractionFewShot" in LIST_EXTRACTION_FEW_SHOTS


def test_learned_fingerprint_survives_registry_reset() -> None:
    reset_registry()
    reset_learned_few_shots()
    fp = form_fingerprint(UNIQUE_FORM)
    persist_review_learning(
        fingerprint_name=f"learned-{fp}",
        fingerprint=fp,
        few_shot={"input": "Rare finding [X]", "deidentified": True},
    )
    saved = known_fingerprints()
    reset_registry()
    set_persisted_loader(lambda: [(name, value) for name, value in saved.items()])
    scored = score_document_quality(
        UNIQUE_FORM,
        few_shot_max_similarity=0.80,
        known_fingerprints=known_fingerprints(),
    )
    assert scored.form_fingerprint_id == f"learned-{fp}"
    assert "unknown_form_template" not in scored.quality_reasons


def test_deidentified_few_shot_survives_memory_reset() -> None:
    reset_learned_few_shots()
    written: list[dict] = []
    persist_review_learning(
        fingerprint_name="learned-abc",
        fingerprint="abc",
        few_shot={
            "input": "NHS_NUMBER rare finding",
            "output": '{"terms":[]}',
            "deidentified": True,
            "category": "form:checkbox",
        },
        write_few_shot=written.append,
    )
    reset_learned_few_shots()
    assert learned_few_shots() == []
    persist_review_learning(
        fingerprint_name="learned-abc",
        fingerprint="abc",
        few_shot=written[0],
    )
    pool = learned_few_shots()
    assert pool[0]["deidentified"] is True
    assert "NHS_NUMBER" in pool[0]["input"]
    assert written[0]["deidentified"] is True


def test_resume_writes_fingerprint_and_few_shot() -> None:
    from libs.pipeline.document_quality import score_document_quality as score

    reset_registry()
    reset_learned_few_shots()
    quality = score(UNIQUE_FORM, few_shot_max_similarity=0.10, known_fingerprints={})
    task = persist_extraction_review_task(
        PersistReviewRequest(
            run_id="run-learn",
            patient_id="p1",
            plan_definition_id="pd-referral-assessment",
            step_id="act-ref-extract",
            next_action_id="act-ref-post-process",
            quality=quality,
            draft_entities=[{"text": "Rare finding"}],
        )
    )
    client = MagicMock()
    client.run.side_effect = [
        [{"status": "pending", "resumed_at": None, **task}],
        [{"step_id": "act-ref-extract"}],
        [{"task_id": task["task_id"], "status": "resolved"}],
    ]
    fingerprints: list[tuple[str, str]] = []
    few_shots: list[dict] = []
    set_learning_writers(
        write_fingerprint=lambda name, value: fingerprints.append((name, value)),
        write_few_shot=few_shots.append,
    )

    resume_extraction_review(
        client,
        task_id=task["task_id"],
        source_text="Ms Smith NHS 943 476 5919\n" + UNIQUE_FORM,
        reviewed_entities=[{"text": "Rare finding"}],
        publish=lambda _message: None,
    )
    assert fingerprints
    assert fingerprints[0][0].startswith("learned-")
    assert few_shots
    assert few_shots[0]["deidentified"] is True
    assert "943 476 5919" not in few_shots[0]["input"]
