#!/usr/bin/env python3
"""Re-embed all Encounter nodes using Bio_ClinicalBERT and rebuild the vector index.

Steps:
  1. Confirm current state (index + vector coverage)
  2. Drop encounter_vector_index
  3. Clear Encounter.vector in batches
  4. Re-embed every Encounter.text using Bio_ClinicalBERT (batched, checkpointed)
  5. Recreate encounter_vector_index
  6. Run compatibility smoke-test

Usage:
    python scripts/reembed_encounters.py
    python scripts/reembed_encounters.py --embed-batch 64 --write-batch 200
    python scripts/reembed_encounters.py --resume   # skip already-written encounters
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env")

# Early CUDA check — before neo4j or other imports that might affect torch
import torch

_cuda_early = torch.cuda.is_available()
if _cuda_early:
    _cuda_dev = torch.cuda.get_device_name(0)
else:
    _cuda_dev = None

from neo4j import GraphDatabase

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Milestone anchor phrases used in the smoke-test ──────────────────────────
SMOKE_ANCHORS = [
    ("FAST_TRACK_REFERRAL", "Refer via 2WW fast track suspected cancer pathway"),
    ("FIRST_SEEN", "Seen in fast track suspected cancer clinic appointment"),
    ("DIAGNOSIS_CONFIRMED", "Confirmed diagnosis breast cancer malignancy"),
    ("FIRST_TREATMENT", "Started chemotherapy adjuvant cancer treatment"),
]


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _make_driver(uri: str, user: str, password: str):
    return GraphDatabase.driver(
        uri,
        auth=(user, password),
        max_connection_lifetime=300,
        liveness_check_timeout=5,
    )


def step1_confirm_state(driver) -> dict:
    log.info("Step 1 — checking current state")
    with driver.session() as s:
        idx = s.run(
            "SHOW INDEXES WHERE name = 'encounter_vector_index' AND type = 'VECTOR'"
        ).data()
        counts = s.run(
            "MATCH (e:Encounter) "
            "RETURN count(e) AS total, count(e.vector) AS with_vector"
        ).single()
        dim_row = s.run(
            "MATCH (e:Encounter) WHERE e.vector IS NOT NULL "
            "RETURN size(e.vector) AS dim LIMIT 1"
        ).single()

    total = counts["total"] if counts else 0
    with_vec = counts["with_vector"] if counts else 0
    dim = dim_row["dim"] if dim_row else None

    log.info("  Encounters total   : %d", total)
    log.info(
        "  With .vector       : %d (%.1f%%)", with_vec, 100 * with_vec / max(total, 1)
    )
    log.info("  Stored vector dim  : %s", dim)
    log.info("  Vector index       : %s", "EXISTS" if idx else "NOT FOUND")

    return {
        "total": total,
        "with_vector": with_vec,
        "stored_dim": dim,
        "index_exists": bool(idx),
    }


def step2_drop_index(driver):
    log.info("Step 2 — dropping encounter_vector_index")
    with driver.session() as s:
        s.run("DROP INDEX encounter_vector_index IF EXISTS")
    log.info("  Index dropped (or was not present)")


def step3_clear_vectors(driver, write_batch: int):
    log.info("Step 3 — clearing Encounter.vector property")
    cleared = 0
    while True:
        with driver.session() as s:
            result = s.run(
                "MATCH (e:Encounter) WHERE e.vector IS NOT NULL "
                "WITH e LIMIT $n "
                "REMOVE e.vector "
                "RETURN count(e) AS n",
                n=write_batch,
            ).single()
        n = result["n"] if result else 0
        cleared += n
        if n == 0:
            break
        log.info("  Cleared %d (total so far: %d)", n, cleared)
    log.info("  All vectors cleared (%d nodes)", cleared)


def step4_reembed(driver, embed_batch: int, write_batch: int, resume: bool):
    log.info("Step 4 — re-embedding encounters with Bio_ClinicalBERT")

    from scripts.embedding_utils import load_vector_settings, TextEmbedder

    settings = load_vector_settings()
    log.info("  Model  : %s", settings.model_name)
    log.info("  Device : %s", settings.device)
    log.info("  Dim    : %d", settings.dimension)

    embedder = TextEmbedder(settings)
    embedder.encode(["warm-up"])  # force model load before timing starts
    log.info("  Model loaded — starting embedding pass")

    # Fetch all encounter IDs (and texts) that still need vectors.
    # In --resume mode we skip those that already have e.vector set.
    filter_clause = "WHERE e.vector IS NULL" if resume else ""
    with driver.session() as s:
        total = s.run(
            f"MATCH (e:Encounter) {filter_clause} RETURN count(e) AS n"
        ).single()["n"]

    log.info("  Encounters to embed: %d", total)
    if total == 0:
        log.info("  Nothing to do.")
        return

    def _fetch(skip_val: int):
        with driver.session() as s:
            return s.run(
                f"MATCH (e:Encounter) {filter_clause} "
                "RETURN toString(e.id) AS eid, e.text AS txt "
                f"ORDER BY e.id SKIP {skip_val} LIMIT {write_batch}"
            ).data()

    def _write(payload: list):
        with driver.session() as s:
            s.run(
                "UNWIND $rows AS row "
                "MATCH (e:Encounter) WHERE toString(e.id) = row.eid "
                "SET e.vector = row.vec",
                rows=payload,
            )

    processed = 0
    t_start = time.time()
    skip = 0
    prev_write = None

    with ThreadPoolExecutor(max_workers=2) as ex:
        next_fetch = ex.submit(_fetch, 0)
        while True:
            rows = next_fetch.result()
            if not rows:
                break
            if prev_write:
                prev_write.result()

            skip += write_batch
            next_fetch = ex.submit(_fetch, skip)

            eids, texts = zip(*((r["eid"], r["txt"] or "") for r in rows))
            vectors: list[list[float]] = []
            for i in range(0, len(texts), embed_batch):
                chunk = texts[i : i + embed_batch]
                vectors.extend(embedder.encode(list(chunk)))

            payload = [{"eid": eid, "vec": vec} for eid, vec in zip(eids, vectors)]
            prev_write = ex.submit(_write, payload)

            processed += len(rows)
            elapsed = time.time() - t_start
            rate = processed / elapsed
            eta = (total - processed) / rate if rate > 0 else 0
            log.info(
                "  Embedded %d / %d  (%.0f enc/s  ETA %.0f min)",
                processed,
                total,
                rate,
                eta / 60,
            )

            if len(rows) < write_batch:
                break

        if prev_write:
            prev_write.result()

    log.info(
        "  Embedding complete — %d encounters written in %.1f min",
        processed,
        (time.time() - t_start) / 60,
    )


def step5_create_index(driver, dimension: int):
    log.info("Step 5 — creating encounter_vector_index (dim=%d, cosine)", dimension)
    with driver.session() as s:
        s.run(
            "CREATE VECTOR INDEX encounter_vector_index IF NOT EXISTS "
            "FOR (e:Encounter) ON (e.vector) "
            "OPTIONS {indexConfig: { "
            "  `vector.dimensions`: $dim, "
            "  `vector.similarity_function`: 'cosine' "
            "}}",
            dim=dimension,
        )
    # Wait for ONLINE
    for attempt in range(30):
        time.sleep(2)
        with driver.session() as s:
            row = s.run(
                "SHOW INDEXES YIELD name, state "
                "WHERE name = 'encounter_vector_index'"
            ).single()
        state = row["state"] if row else "UNKNOWN"
        log.info("  Index state: %s (attempt %d)", state, attempt + 1)
        if state == "ONLINE":
            break
    else:
        log.warning(
            "  Index did not reach ONLINE within 60 s — may still be populating"
        )


def step6_smoke_test(driver, dimension: int, verify: bool = False):
    log.info("Step 6 — smoke test (milestone anchor queries)")

    from scripts.embedding_utils import load_vector_settings, TextEmbedder

    settings = load_vector_settings()
    embedder = TextEmbedder(settings)

    all_ok = True
    for milestone, phrase in SMOKE_ANCHORS:
        emb = embedder.encode([phrase])[0]
        with driver.session() as s:
            rows = s.run(
                "CALL db.index.vector.queryNodes('encounter_vector_index', 5, $emb) "
                "YIELD node, score "
                "RETURN node.text AS txt, score ORDER BY score DESC",
                emb=emb,
            ).data()

        top_score = rows[0]["score"] if rows else 0.0
        log.info("  %-26s  top_score=%.4f  hits=%d", milestone, top_score, len(rows))
        if rows:
            snippet = (rows[0]["txt"] or "").replace("\n", " ")[:100]
            log.info("    -> %s", snippet)
        if verify and rows:
            for i, r in enumerate(rows[:2], 1):
                full = (r["txt"] or "").strip()
                log.info("    --- full hit #%d (score=%.4f) ---", i, r["score"])
                for line in full.split("\n")[:15]:
                    log.info("    %s", line[:120])
                if full.count("\n") >= 15:
                    log.info("    ... (truncated)")
        if top_score < 0.40:
            log.warning("  Low similarity score — check model compatibility")
            all_ok = False

    if all_ok:
        log.info("Smoke test PASSED — embeddings appear compatible")
    else:
        log.warning("Smoke test WARNINGS — review scores above")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────


def main():
    # Log early CUDA check (torch imported before neo4j)
    if _cuda_early:
        log.info("Early torch check: CUDA available — %s", _cuda_dev)
    else:
        log.info("Early torch check: CUDA NOT available (Python=%s)", sys.executable)

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--embed-batch",
        type=int,
        default=512,
        help="Texts per SentenceTransformer batch (512 for GPU, try 1024 for 12GB+ VRAM, 32 for CPU)",
    )
    parser.add_argument(
        "--write-batch",
        type=int,
        default=1024,
        help="Encounters per Neo4j fetch/write (default 1024, should match embed-batch for GPU)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip encounters that already have e.vector set (restart recovery)",
    )
    parser.add_argument(
        "--skip-clear",
        action="store_true",
        help="Skip clearing existing vectors (use with --resume)",
    )
    parser.add_argument(
        "--smoke-only",
        action="store_true",
        help="Run only the smoke test against the existing index",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="With --smoke-only: print full top-2 texts per anchor for manual review",
    )
    args = parser.parse_args()

    uri = os.environ["NEO4J_URI"]
    user = os.environ["NEO4J_USER"]
    password = os.environ["NEO4J_PASSWORD"]

    driver = _make_driver(uri, user, password)

    try:
        if args.smoke_only:
            from scripts.embedding_utils import load_vector_settings

            settings = load_vector_settings()
            step6_smoke_test(driver, settings.dimension, verify=args.verify)
            return

        state = step1_confirm_state(driver)

        if not args.resume:
            step2_drop_index(driver)
            if not args.skip_clear:
                step3_clear_vectors(driver, args.write_batch)

        step4_reembed(driver, args.embed_batch, args.write_batch, args.resume)

        from scripts.embedding_utils import load_vector_settings

        settings = load_vector_settings()
        step5_create_index(driver, settings.dimension)
        step6_smoke_test(
            driver, settings.dimension, verify=getattr(args, "verify", False)
        )

    finally:
        driver.close()


if __name__ == "__main__":
    main()
