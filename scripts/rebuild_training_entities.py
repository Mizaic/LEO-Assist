"""Rebuild entities_json for all included TrainingLabels using LLM extraction.

Part of the Gold Training Dataset Rebuild. Re-extracts clinical entities from
encounter text using the Bedrock LLM extractor (same prompt/model as the coding
pipeline) and writes the new entities_json back to Neo4j.

Features
--------
- Checkpointing: writes processed label_ids to a local file so it can resume
  after interruption.
- Configurable concurrency via --workers (default 50).
- Adaptive rate-limit handling with exponential backoff.
- Progress reporting every N labels.

Usage
-----
    python scripts/rebuild_training_entities.py [--workers 50] [--dry-run] [--checkpoint rebuild_checkpoint.txt]
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import logging
import os
import re
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env")

from neo4j import GraphDatabase

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sentence splitter (inline to avoid heavy dependencies like spacy/medspacy)
# ---------------------------------------------------------------------------

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


@dataclass(frozen=True)
class SentenceChunk:
    sentence_id: str
    text: str
    start: int
    end: int


def split_sentences(text: str) -> list[SentenceChunk]:
    parts = _SENTENCE_SPLIT.split(text)
    chunks: list[SentenceChunk] = []
    offset = 0
    for idx, part in enumerate(parts):
        stripped = part.strip()
        if not stripped:
            offset += len(part) + 1
            continue
        start = text.find(stripped, offset)
        if start < 0:
            start = offset
        end = start + len(stripped)
        chunks.append(SentenceChunk(sentence_id=f"s{idx}", text=stripped, start=start, end=end))
        offset = end
    return chunks


# ---------------------------------------------------------------------------
# LLM extraction (uses boto3 Bedrock directly)
# ---------------------------------------------------------------------------

from libs.prompts.registry import get_prompt

SYSTEM_PROMPT = get_prompt("extraction", version=1)

_VALID_ASSERTIONS = frozenset({
    "present", "absent", "refuted", "possible", "historical",
    "hypothetical", "family", "declined", "cancelled",
})

_SNOMED_TAG_TO_LABEL = {
    "qualifier value": "qualifier_value",
    "observable entity": "observable_entity",
    "body structure": "body_structure",
    "tumor staging": "tumor_staging",
    "assessment scale": "assessment_scale",
    "staging scale": "staging_scale",
    "regime/therapy": "regime_therapy",
    "record artifact": "record_artifact",
    "physical object": "physical_object",
    "morphologic abnormality": "morphologic_abnormality",
    "clinical drug": "clinical_drug",
    "medicinal product": "medicinal_product",
    "qualifier": "qualifier_value",
}


def _tag_to_label(tag: str) -> str:
    key = tag.strip().lower()
    candidate = _SNOMED_TAG_TO_LABEL.get(key, key.replace(" ", "_"))
    return candidate


def _resolve_char_start(text: str, span_text: str, hint: int = 0) -> int | None:
    pos = text.find(span_text)
    if pos != -1:
        return pos
    pos = text.lower().find(span_text.lower())
    if pos != -1:
        return pos
    return None


# ---------------------------------------------------------------------------
# Throttle-aware concurrency
# ---------------------------------------------------------------------------

class _RateLimiter:
    def __init__(self, max_concurrent: int) -> None:
        self._sem = threading.Semaphore(max_concurrent)
        self._lock = threading.Lock()
        self._throttle_count = 0

    def acquire(self) -> None:
        self._sem.acquire()

    def release(self) -> None:
        self._sem.release()

    def on_throttle(self) -> None:
        with self._lock:
            self._throttle_count += 1


# ---------------------------------------------------------------------------
# Per-label extraction worker
# ---------------------------------------------------------------------------

_LLM_RETRIES = 4
_LLM_BACKOFF_BASE = 0.6


def _extract_one_label(
    bedrock_client,
    model_id: str,
    label_id: str,
    text: str,
    limiter: _RateLimiter,
) -> tuple[str, list[dict] | None]:
    """Extract entities from one TrainingLabel's text.

    Returns (label_id, entities_list) or (label_id, None) on failure.
    """
    sentences = split_sentences(text)
    if not sentences:
        return label_id, []

    user_prompt = (
        f"Extract clinical entities from sentences below.\n\n"
        f"Encounter text:\n{text}\n\n"
        f"Sentences:\n{json.dumps([{'sentence_id': s.sentence_id, 'text': s.text} for s in sentences], ensure_ascii=False)}"
    )

    raw_text = ""
    for attempt in range(_LLM_RETRIES + 1):
        limiter.acquire()
        try:
            response = bedrock_client.converse(
                modelId=model_id,
                system=[{"text": SYSTEM_PROMPT}],
                messages=[{"role": "user", "content": [{"text": user_prompt}]}],
                inferenceConfig={"maxTokens": 2048, "temperature": 0.0},
            )
            content = response.get("output", {}).get("message", {}).get("content", [])
            raw_text = "\n".join(
                item["text"] for item in (content or [])
                if isinstance(item, dict) and "text" in item
            ).strip()
            break
        except Exception as exc:
            msg = str(exc).lower()
            throttled = any(m in msg for m in ("429", "rate limit", "throttle", "too many requests"))
            if throttled:
                limiter.on_throttle()
            if attempt >= _LLM_RETRIES:
                logger.warning("LLM call failed for %s after %d retries: %s", label_id[:8], _LLM_RETRIES, exc)
                return label_id, None
            delay = _LLM_BACKOFF_BASE * (2 ** attempt)
            if throttled:
                delay *= 2.0
            time.sleep(delay)
        finally:
            limiter.release()

    # Parse JSON response
    parsed: dict = {}
    if raw_text:
        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", raw_text, re.DOTALL)
            if match:
                try:
                    parsed = json.loads(match.group(0))
                except json.JSONDecodeError:
                    pass
    if not isinstance(parsed, dict):
        parsed = {}

    # Build entity dicts
    sent_map = {s.sentence_id: s for s in sentences}
    entities: list[dict] = []

    for row in parsed.get("terms", []):
        if not isinstance(row, dict):
            continue
        sid = str(row.get("sentence_id", "")).strip()
        term_text = str(row.get("text", "")).strip()
        if not sid or not term_text:
            continue
        sent = sent_map.get(sid)
        if not sent:
            continue

        assertion = str(row.get("assertion", "present")).strip().lower()
        if assertion not in _VALID_ASSERTIONS:
            assertion = "present"

        semantic_tag = str(row.get("semantic_tag", "finding")).strip()
        label = _tag_to_label(semantic_tag)

        start = _resolve_char_start(text, term_text, hint=sent.start if sent else 0)
        if start is None:
            start = sent.start if sent else 0
        end = start + len(term_text)

        entity: dict = {
            "text": term_text,
            "label": label,
            "start": start,
            "end": end,
            "assertion": assertion,
        }

        lookup_term = str(row.get("lookup_term", "")).strip()
        if lookup_term and lookup_term != term_text:
            entity["lookup_term"] = lookup_term

        value = str(row.get("value", "") or "").strip()
        unit = str(row.get("unit", "") or "").strip()
        ref_range = str(row.get("reference_range", "") or "").strip()
        if value:
            entity["value"] = value
        if unit:
            entity["unit"] = unit
        if ref_range:
            entity["reference_range"] = ref_range

        entities.append(entity)

    return label_id, entities


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild TrainingLabel entities via LLM extraction")
    parser.add_argument("--workers", type=int, default=50, help="Concurrent LLM calls (default 50)")
    parser.add_argument("--dry-run", action="store_true", help="Extract but don't write to Neo4j")
    parser.add_argument("--checkpoint", default="rebuild_checkpoint.txt", help="Checkpoint file path")
    parser.add_argument("--limit", type=int, default=0, help="Process only N labels (0 = all)")
    args = parser.parse_args()

    # Neo4j
    neo4j_uri = os.getenv("NEO4J_URI", "")
    neo4j_user = os.getenv("NEO4J_USER", "neo4j")
    neo4j_pwd = os.getenv("NEO4J_PASSWORD", "")
    if not neo4j_uri or not neo4j_pwd:
        logger.error("NEO4J_URI / NEO4J_PASSWORD not set")
        sys.exit(1)

    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_pwd))
    driver.verify_connectivity()
    logger.info("Connected to Neo4j at %s", neo4j_uri)

    # Bedrock
    import boto3
    model_id = os.getenv("AWS_SMALL_MODEL", os.getenv("AWS_BEDROCK_MODEL", ""))
    region = os.getenv("AWS_DEFAULT_REGION", "eu-west-2")
    if not model_id:
        logger.error("AWS_SMALL_MODEL / AWS_BEDROCK_MODEL not set")
        sys.exit(1)
    bedrock = boto3.client("bedrock-runtime", region_name=region)
    logger.info("Using Bedrock model: %s (region: %s)", model_id, region)

    # Load checkpoint
    checkpoint_path = Path(args.checkpoint)
    done_ids: set[str] = set()
    if checkpoint_path.exists():
        done_ids = set(checkpoint_path.read_text().strip().splitlines())
        logger.info("Resuming from checkpoint: %d labels already processed", len(done_ids))

    # Fetch all included labels
    with driver.session() as session:
        rows = list(session.run(
            "MATCH (t:TrainingLabel) "
            "WHERE t.include = true AND t.text IS NOT NULL "
            "RETURN t.label_id AS label_id, t.text AS text "
            "ORDER BY t.created_at ASC"
        ))
    total_all = len(rows)

    # Filter out already-done
    labels = [(str(r["label_id"]), str(r["text"])) for r in rows if str(r["label_id"]) not in done_ids]
    if args.limit > 0:
        labels = labels[:args.limit]

    logger.info(
        "Labels: %d total, %d already checkpointed, %d to process",
        total_all, len(done_ids), len(labels),
    )

    if not labels:
        logger.info("Nothing to do.")
        driver.close()
        return

    # Process
    limiter = _RateLimiter(args.workers)
    processed = 0
    errors = 0
    start_time = time.time()

    checkpoint_file = open(checkpoint_path, "a")

    def _worker(label_id: str, text: str):
        return _extract_one_label(bedrock, model_id, label_id, text, limiter)

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(_worker, lid, txt): lid for lid, txt in labels}

        for future in concurrent.futures.as_completed(futures):
            try:
                label_id, entities = future.result()
            except Exception:
                logger.warning("Future raised unexpectedly", exc_info=True)
                errors += 1
                processed += 1
                continue

            if entities is None:
                errors += 1
                processed += 1
                continue

            if not args.dry_run:
                try:
                    with driver.session() as session:
                        session.run(
                            "MATCH (t:TrainingLabel {label_id: $label_id}) "
                            "SET t.entities_json = $entities_json, "
                            "    t.updated_at = datetime()",
                            label_id=label_id,
                            entities_json=json.dumps(entities),
                        )
                except Exception:
                    logger.warning("Neo4j write failed for %s", label_id[:8], exc_info=True)
                    errors += 1
                    processed += 1
                    continue

            checkpoint_file.write(label_id + "\n")
            checkpoint_file.flush()
            processed += 1

            if processed % 100 == 0 or processed == len(labels):
                elapsed = time.time() - start_time
                rate = processed / max(elapsed, 0.001)
                remaining = len(labels) - processed
                eta = int(remaining / rate) if rate > 0 else 0
                logger.info(
                    "Progress: %d/%d (%.1f%%) | errors=%d | %.1f labels/min | ETA %ds",
                    processed, len(labels), 100 * processed / len(labels),
                    errors, rate * 60, eta,
                )

    checkpoint_file.close()
    elapsed = time.time() - start_time
    logger.info(
        "Done. Processed %d labels in %.1fs (%.1f/min). Errors: %d",
        processed, elapsed, processed / max(elapsed, 0.001) * 60, errors,
    )
    driver.close()


if __name__ == "__main__":
    main()
