"""Background dual-model verification for TrainingLabel entities.

Runs AWS + Azure small models over included labels in Neo4j. Agreements are
applied automatically; disagreements are pushed into LabelVerificationReview
for human resolution.

Concurrency model
-----------------
All LLM calls run in a shared ThreadPoolExecutor (max_workers configurable via
LABEL_VERIFY_WORKERS env var, default 20).  Each worker processes one label —
calling both AWS and Azure in a nested 2-thread pool — so with 20 outer workers
we have up to 40 concurrent LLM requests in flight at once.

Neo4j writes happen sequentially on the main thread as futures complete, so
we never need more than one Neo4j session open at a time.
"""

from __future__ import annotations

import concurrent.futures
import json
import logging
import os
import re
import threading
import time
from typing import Any

from libs.cypher.label_verification_queries import (
    UPDATE_LABEL_VERIFICATION,
    UPSERT_LABEL_VERIFICATION_REVIEW,
)
from libs.cypher.post_processor_rule_queries import GET_ACTIVE_POST_PROCESSOR_RULES
from libs.cypher.training_label_queries import (
    GET_ALL_INCLUDED_LABELS_FOR_EXPORT,
    UPDATE_TRAINING_LABEL_ENTITIES,
)
from libs.llm_client.factory import LLMResponse, create_llm
from libs.neo4j_client.client import PatientGraphClient
from libs.ner.post_processor_rules import apply_rules_to_entities, parse_rules, PostProcessorRule

logger = logging.getLogger(__name__)

_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)

# Number of labels processed concurrently (each spawns 2 LLM calls → 2× API reqs in flight).
_MAX_WORKERS = int(os.getenv("LABEL_VERIFY_WORKERS", "20"))

VALID_ENTITY_LABELS = {
    "disorder",
    "finding",
    "procedure",
    "observable_entity",
    "qualifier_value",
    "substance",
    "medicinal_product",
    "clinical_drug",
    "situation",
    "event",
    "body_structure",
    "tumor_staging",
    "X_PATHWAY_MILESTONE",
    "X_NEGATION_CUE",
    "X_TEMPORAL",
    "X_DOSAGE",
    "X_FREQUENCY",
    "X_ROUTE",
}

_job_state_lock = threading.Lock()
_job_state: dict[str, Any] = {
    "status": "idle",
    "started_at": None,
    "finished_at": None,
    "total": 0,
    "done": 0,
    "agreements": 0,
    "disagreements": 0,
    "errors": 0,
    "pending_review": 0,
    "last_error": None,
}


def get_job_state() -> dict[str, Any]:
    with _job_state_lock:
        return dict(_job_state)


def begin_job() -> bool:
    """Attempt to mark the verifier job as running. Returns False if busy."""
    with _job_state_lock:
        if _job_state["status"] == "running":
            return False
        _job_state.update(
            {
                "status": "running",
                "started_at": time.time(),
                "finished_at": None,
                "total": 0,
                "done": 0,
                "agreements": 0,
                "disagreements": 0,
                "errors": 0,
                "pending_review": 0,
                "last_error": None,
            }
        )
    return True


def _patch_state(**updates: Any) -> None:
    with _job_state_lock:
        _job_state.update(updates)


def _increment_state(**deltas: int) -> None:
    """Atomically increment numeric counters."""
    with _job_state_lock:
        for k, v in deltas.items():
            _job_state[k] = _job_state.get(k, 0) + v


def _parse_model_json(text: str) -> dict[str, Any]:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        pass
    m = _JSON_OBJECT_RE.search(text)
    if not m:
        return {}
    try:
        parsed = json.loads(m.group(0))
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _normalise_label(label: str, fallback: str) -> str:
    label = (label or "").strip()
    return label if label in VALID_ENTITY_LABELS else fallback


def _call_model_for_label(
    provider: str,
    text: str,
    entities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    client = create_llm(provider=provider, tier="small")
    system_prompt = (
        "You are a strict clinical NER reviewer.\n"
        "Given encounter text and entities, evaluate whether each entity label is correct.\n"
        "Allowed labels: disorder, finding, procedure, observable_entity, qualifier_value, "
        "substance, medicinal_product, clinical_drug, situation, event, body_structure, "
        "tumor_staging, X_PATHWAY_MILESTONE, X_NEGATION_CUE, "
        "X_TEMPORAL, X_DOSAGE, X_FREQUENCY, X_ROUTE.\n"
        "Respond with JSON only: "
        "{\"entities\":[{\"entity_index\":0,\"suggested_label\":\"finding\",\"rationale\":\"...\"}]}"
    )
    user_payload = {
        "text": text,
        "entities": [
            {"entity_index": i, "text": e.get("text", ""), "label": e.get("label", "")}
            for i, e in enumerate(entities)
        ],
    }
    try:
        response: LLMResponse = client.converse(
            system=system_prompt,
            messages=[{"role": "user", "content": json.dumps(user_payload)}],
            max_tokens=1024,
            temperature=0.0,
        )
        parsed = _parse_model_json(response.text)
        entity_rows = parsed.get("entities", [])
        return entity_rows if isinstance(entity_rows, list) else []
    except Exception:
        logger.warning("Label verification model call failed provider=%s", provider, exc_info=True)
        return []


# ---------------------------------------------------------------------------
# Per-label processing (runs inside the outer ThreadPoolExecutor)
# ---------------------------------------------------------------------------

class _LabelResult:
    """Carries everything needed to write one label's outcome to Neo4j."""
    __slots__ = (
        "label_id", "updated_entities", "quality_score", "agreement",
        "n_disagreements", "review_items", "first_aws_label", "first_azure_label",
        "error",
    )

    def __init__(self, label_id: str, *, error: bool = False):
        self.label_id = label_id
        self.updated_entities: list[dict] = []
        self.quality_score: float = 0.0
        self.agreement: bool = False
        self.n_disagreements: int = 0
        self.review_items: list[dict] = []
        self.first_aws_label: str = ""
        self.first_azure_label: str = ""
        self.error: bool = error


def _process_label(label_row: dict, rules: list[PostProcessorRule]) -> _LabelResult:
    """Call both LLM providers for one label and return a write-ready result.

    Runs inside the outer pool — spawns an inner 2-worker pool for the two
    provider calls so both happen concurrently within this worker thread.
    """
    label_id = str(label_row.get("label_id", ""))
    if not label_id:
        return _LabelResult("", error=True)

    text = str(label_row.get("text", ""))
    try:
        entities = json.loads(label_row.get("entities_json", "[]") or "[]")
    except json.JSONDecodeError:
        entities = []
    if rules:
        entities = apply_rules_to_entities(text, entities, rules)

    result = _LabelResult(label_id)

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as inner:
            fut_aws = inner.submit(_call_model_for_label, "aws", text, entities)
            fut_azure = inner.submit(_call_model_for_label, "azure", text, entities)
            aws_rows = fut_aws.result()
            azure_rows = fut_azure.result()

        aws_by_idx: dict[int, dict] = {
            int(item.get("entity_index", -1)): item
            for item in aws_rows
            if isinstance(item, dict) and isinstance(item.get("entity_index"), int)
        }
        azure_by_idx: dict[int, dict] = {
            int(item.get("entity_index", -1)): item
            for item in azure_rows
            if isinstance(item, dict) and isinstance(item.get("entity_index"), int)
        }

        updated_entities = [dict(e) for e in entities]
        n_disagreements = 0

        for idx, entity in enumerate(updated_entities):
            current_label = str(entity.get("label", "finding"))
            entity_text = str(entity.get("text", ""))
            aws_label = _normalise_label(
                str(aws_by_idx.get(idx, {}).get("suggested_label", current_label)),
                current_label,
            )
            azure_label = _normalise_label(
                str(azure_by_idx.get(idx, {}).get("suggested_label", current_label)),
                current_label,
            )
            aws_rationale = str(aws_by_idx.get(idx, {}).get("rationale", ""))
            azure_rationale = str(azure_by_idx.get(idx, {}).get("rationale", ""))

            if idx == 0:
                result.first_aws_label = aws_label
                result.first_azure_label = azure_label

            if aws_label == azure_label:
                entity["label"] = aws_label
            else:
                n_disagreements += 1
                result.review_items.append({
                    "review_id": f"{label_id}:{idx}",
                    "entity_index": idx,
                    "entity_text": entity_text,
                    "current_label": current_label,
                    "model_a_label": aws_label,
                    "model_a_rationale": aws_rationale[:500],
                    "model_b_label": azure_label,
                    "model_b_rationale": azure_rationale[:500],
                })

        total_entities = max(len(updated_entities), 1)
        result.updated_entities = updated_entities
        result.n_disagreements = n_disagreements
        result.quality_score = max(0.0, min(1.0, (total_entities - n_disagreements) / total_entities))
        result.agreement = n_disagreements == 0

    except Exception:
        logger.warning("Label processing failed label_id=%s", label_id, exc_info=True)
        result.error = True

    return result


# ---------------------------------------------------------------------------
# Main verification entry point
# ---------------------------------------------------------------------------

def run_verification() -> None:
    """Run full label verification job with parallel LLM calls.

    Phase 1 — Fetch all included TrainingLabel rows from Neo4j (one read session).
    Phase 2 — Process all labels concurrently via _MAX_WORKERS threads, each
               calling AWS + Azure in a nested 2-thread pool.
    Phase 3 — Write results back to Neo4j sequentially as futures complete
               (avoids multi-threaded session usage).
    """
    # ------------------------------------------------------------------
    # Phase 1: fetch
    # ------------------------------------------------------------------
    fetch_client = PatientGraphClient()
    try:
        with fetch_client.session() as session:
            rules = parse_rules([dict(r) for r in session.run(GET_ACTIVE_POST_PROCESSOR_RULES)])
            rows = session.run(GET_ALL_INCLUDED_LABELS_FOR_EXPORT)
            labels = [dict(r) for r in rows]
    finally:
        fetch_client.close()

    _patch_state(total=len(labels))
    logger.info(
        "Label verification started: %d labels, max_workers=%d (~%d concurrent LLM requests)",
        len(labels), _MAX_WORKERS, _MAX_WORKERS * 2,
    )

    # ------------------------------------------------------------------
    # Phase 2 + 3: process in parallel, write sequentially as futures land
    # ------------------------------------------------------------------
    write_client = PatientGraphClient()
    try:
        with write_client.session() as session:
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=_MAX_WORKERS,
                thread_name_prefix="label-verify",
            ) as pool:
                futures = {pool.submit(_process_label, row, rules): row for row in labels}

                for future in concurrent.futures.as_completed(futures):
                    try:
                        result = future.result()
                    except Exception:
                        logger.warning("Future raised unexpectedly", exc_info=True)
                        _increment_state(done=1, errors=1)
                        continue

                    if result.error or not result.label_id:
                        _increment_state(done=1, errors=1)
                        continue

                    # Write disagreement review items
                    for item in result.review_items:
                        session.run(
                            UPSERT_LABEL_VERIFICATION_REVIEW,
                            review_id=item["review_id"],
                            label_id=result.label_id,
                            entity_index=item["entity_index"],
                            entity_text=item["entity_text"],
                            current_label=item["current_label"],
                            model_a_label=item["model_a_label"],
                            model_a_rationale=item["model_a_rationale"],
                            model_b_label=item["model_b_label"],
                            model_b_rationale=item["model_b_rationale"],
                        )

                    session.run(
                        UPDATE_TRAINING_LABEL_ENTITIES,
                        label_id=result.label_id,
                        entities_json=json.dumps(result.updated_entities),
                    )
                    session.run(
                        UPDATE_LABEL_VERIFICATION,
                        label_id=result.label_id,
                        verification_agreement=result.agreement,
                        model_a_label=result.first_aws_label,
                        model_b_label=result.first_azure_label,
                        quality_score=result.quality_score,
                    )

                    _increment_state(
                        done=1,
                        agreements=(1 if result.agreement else 0),
                        disagreements=result.n_disagreements,
                        pending_review=len(result.review_items),
                    )

        _patch_state(status="done", finished_at=time.time())
        logger.info("Label verification completed")

    except Exception as exc:
        logger.exception("Label verification failed")
        _patch_state(status="failed", finished_at=time.time(), last_error=str(exc))
    finally:
        write_client.close()
