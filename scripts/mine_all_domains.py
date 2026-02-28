#!/usr/bin/env python3
"""Mine all domains from raw Encounter.text — gold-standard NER training set builder.

Source of truth: raw Encounter.text + encounter metadata from Neo4j only.
Existing :DOCUMENTS / :HAS_<semantic_tag> graph links are NOT used as labels.

Output (exports/ner/all_domains/):
    domain_<domain>.jsonl         — per-domain canonical records
    domain_entities_merged.jsonl  — merged canonical records (all domains)
    domain_entities_rejected.jsonl — records that failed validation
    checkpoint.json               — resumable progress file
    summary.json                  — aggregate run statistics
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import logging
import os
import re
import sys
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from libs.ner.domain_loader import (
    DomainSearchConfig,
    default_config_dir,
    dump_expanded_domains,
    expand_domains_with_kg,
    load_domain_configs,
)
from libs.ner.deid_validator import DeIdValidator, sanitise_record_metadata
from libs.ner.precision_gates import check_record_entities
from libs.ner.relation_builder import build_relations
from libs.ner.schema_mapper import map_raw_record
from libs.utils.deidentify import deidentify_text
from scripts.embedding_utils import TextEmbedder, load_vector_settings

load_dotenv(ROOT / "secrets" / ".env")

from neo4j import GraphDatabase  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

_SENTENCE_SEP = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])|[\r\n]+|\s*;\s*")

_deid_validator = DeIdValidator()


# ---------------------------------------------------------------------------
# Sentence splitter
# ---------------------------------------------------------------------------

def _split_sentences(text: str) -> list[tuple[int, int, str]]:
    parts = _SENTENCE_SEP.split(text)
    out: list[tuple[int, int, str]] = []
    pos = 0
    for part in parts:
        p = part.strip()
        if len(p) < 5:
            pos += len(part)
            continue
        idx = text.find(p, pos)
        if idx < 0:
            pos += len(part)
            continue
        out.append((idx, idx + len(p), p))
        pos = idx + len(p)
    return out


# ---------------------------------------------------------------------------
# Assertion inference from sentence context
# ---------------------------------------------------------------------------

def _infer_assertion(text: str) -> str:
    t = text.lower()
    if re.search(
        r"\b(no evidence of|ruled out|excluded|all clear|negative|no malignancy|not malignant|no recurrence)\b",
        t,
    ):
        return "absent"
    if re.search(r"\b(family history|fam hx|fh )\b", t):
        return "family"
    if re.search(r"\b(history of|previous|past medical history|in remission)\b", t):
        return "historical"
    return "present"


# ---------------------------------------------------------------------------
# Domain cache
# ---------------------------------------------------------------------------

def _load_or_build_domain_cache(
    expanded_cache_path: Path,
    config_dir: Path,
    desc_depth: int,
    desc_limit: int,
    force_rebuild: bool,
) -> dict[str, DomainSearchConfig]:
    if expanded_cache_path.exists() and not force_rebuild:
        logger.info("Loading expanded domain cache: %s", expanded_cache_path)
        raw = json.loads(expanded_cache_path.read_text(encoding="utf-8"))
        domains: dict[str, DomainSearchConfig] = {}
        for name, cfg in raw.items():
            domains[name] = DomainSearchConfig(
                domain_name=cfg["domain_name"],
                source_file=cfg["source_file"],
                description=cfg.get("description", ""),
                semantic_tags=cfg.get("semantic_tags", []),
                milestone_type=cfg.get("milestone_type"),
                concept_ids=cfg.get("concept_ids", []),
                concepts=[],
                surface_forms=cfg.get("surface_forms", []),
                fulltext_queries=cfg.get("fulltext_queries", []),
                vector_phrases=cfg.get("vector_phrases", []),
                entity_patterns=cfg.get("entity_patterns", []),
                concept_map=cfg.get("concept_map", {}),
                stats=cfg.get("stats", {}),
            )
        return domains

    logger.info("Expanded domain cache not found. Building from configs + KG...")
    domains = load_domain_configs(config_dir)
    expand_domains_with_kg(
        domains,
        include_descendants=True,
        descendant_depth=desc_depth,
        descendant_limit=desc_limit,
    )
    dump_expanded_domains(domains, expanded_cache_path)
    return domains


# ---------------------------------------------------------------------------
# Neo4j search helpers — raw Encounter.text only, no coded graph links
# ---------------------------------------------------------------------------

def _search_fulltext_for_domain(
    driver,
    domain_name: str,
    queries: list[str],
    limit_per_query: int,
) -> dict[str, dict[str, Any]]:
    hits: dict[str, dict[str, Any]] = {}
    for q in queries:
        with driver.session() as s:
            rows = list(
                s.run(
                    """
                    CALL db.index.fulltext.queryNodes('encounter_text_index', $q, {limit: $lim})
                    YIELD node, score
                    MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e)
                    WHERE e = node
                    RETURN toString(e.id) AS encounter_id,
                           toString(p.id) AS patient_id,
                           toString(e.date) AS encounter_date,
                           e.text AS text,
                           score AS score
                    """,
                    q=q,
                    lim=limit_per_query,
                )
            )
        for r in rows:
            eid = r["encounter_id"]
            score = float(r["score"] or 0.0)
            prev = hits.get(eid)
            if prev is None or score > prev["ft_score"]:
                hits[eid] = {
                    "encounter_id": eid,
                    "patient_id": r["patient_id"] or "",
                    "encounter_date": str(r["encounter_date"] or "")[:10],
                    "text": r["text"] or "",
                    "domains": {domain_name},
                    "ft_score": score,
                    "vec_score": 0.0,
                    "source": "fulltext",
                }
            else:
                prev["domains"].add(domain_name)
    return hits


def _search_vector_for_domain(
    driver,
    embedder: TextEmbedder,
    domain_name: str,
    phrases: list[str],
    top_k: int,
    embed_lock: threading.Lock | None = None,
) -> dict[str, dict[str, Any]]:
    hits: dict[str, dict[str, Any]] = {}
    for phrase in phrases:
        if embed_lock is None:
            emb = embedder.encode([phrase])[0]
        else:
            with embed_lock:
                emb = embedder.encode([phrase])[0]
        with driver.session() as s:
            rows = list(
                s.run(
                    """
                    CALL db.index.vector.queryNodes('encounter_vector_index', $k, $embedding)
                    YIELD node, score
                    MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e)
                    WHERE e = node
                    RETURN toString(e.id) AS encounter_id,
                           toString(p.id) AS patient_id,
                           toString(e.date) AS encounter_date,
                           e.text AS text,
                           score AS score
                    """,
                    k=top_k,
                    embedding=emb,
                )
            )
        for r in rows:
            eid = r["encounter_id"]
            score = float(r["score"] or 0.0)
            prev = hits.get(eid)
            if prev is None or score > prev["vec_score"]:
                hits[eid] = {
                    "encounter_id": eid,
                    "patient_id": r["patient_id"] or "",
                    "encounter_date": str(r["encounter_date"] or "")[:10],
                    "text": r["text"] or "",
                    "domains": {domain_name},
                    "ft_score": 0.0,
                    "vec_score": score,
                    "source": "vector",
                }
            else:
                prev["domains"].add(domain_name)
    return hits


def _merge_hits(
    all_hits: dict[str, dict[str, Any]],
    domain_hits: dict[str, dict[str, Any]],
) -> None:
    for eid, rec in domain_hits.items():
        if eid not in all_hits:
            all_hits[eid] = rec
            continue
        existing = all_hits[eid]
        existing["domains"].update(rec["domains"])
        existing["ft_score"] = max(existing["ft_score"], rec["ft_score"])
        existing["vec_score"] = max(existing["vec_score"], rec["vec_score"])
        if existing["source"] != rec["source"]:
            existing["source"] = "both"


# ---------------------------------------------------------------------------
# Pattern compilation
# ---------------------------------------------------------------------------

def _compile_patterns(domains: dict[str, DomainSearchConfig]) -> dict[str, list[re.Pattern[str]]]:
    compiled: dict[str, list[re.Pattern[str]]] = {}
    for dname, cfg in domains.items():
        compiled[dname] = [re.compile(pat, re.IGNORECASE) for pat in cfg.entity_patterns]
    return compiled


# ---------------------------------------------------------------------------
# Terminology resolution
# ---------------------------------------------------------------------------

def _resolve_unknown_terms(
    client: httpx.Client,
    api_url: str,
    terms: list[str],
    batch_size: int,
) -> dict[str, list[dict[str, Any]]]:
    resolved: dict[str, list[dict[str, Any]]] = {}
    unique = list(dict.fromkeys(t for t in terms if t.strip()))
    for i in range(0, len(unique), batch_size):
        batch = unique[i : i + batch_size]
        resp = client.post(
            f"{api_url.rstrip('/')}/terminology/resolve",
            json={"terms": batch},
            timeout=60.0,
        )
        resp.raise_for_status()
        resolved.update(resp.json().get("results", {}))
    return resolved


def _search_single_domain(
    *,
    dname: str,
    cfg: DomainSearchConfig,
    driver,
    embedder: TextEmbedder,
    args: argparse.Namespace,
    embed_lock: threading.Lock | None = None,
) -> tuple[str, dict[str, dict[str, Any]], dict[str, Any], float, str | None]:
    started = time.time()
    try:
        ft_queries = cfg.fulltext_queries[: args.max_fulltext_per_domain]
        vec_phrases = cfg.vector_phrases[: args.max_vector_per_domain]

        ft_hits = _search_fulltext_for_domain(driver, dname, ft_queries, args.ft_limit)
        vec_hits = _search_vector_for_domain(
            driver, embedder, dname, vec_phrases, args.vector_k, embed_lock=embed_lock
        )

        merged_domain_hits: dict[str, dict[str, Any]] = {}
        _merge_hits(merged_domain_hits, ft_hits)
        _merge_hits(merged_domain_hits, vec_hits)
        for rec in merged_domain_hits.values():
            rec["domains"].add(dname)

        stats = {
            "concepts": len(cfg.concept_ids),
            "surface_forms": len(cfg.surface_forms),
            "fulltext_queries": len(ft_queries),
            "vector_phrases": len(vec_phrases),
            "encounters_fulltext": len(ft_hits),
            "encounters_vector": len(vec_hits),
            "encounters_merged": len(merged_domain_hits),
        }
        return dname, merged_domain_hits, stats, time.time() - started, None
    except Exception as exc:  # pragma: no cover - runtime/network path
        return dname, {}, {}, time.time() - started, str(exc)


# ---------------------------------------------------------------------------
# Main extraction loop
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-dir", default=str(default_config_dir(ROOT)))
    parser.add_argument("--expanded-cache", default=str(ROOT / "exports" / "ner" / "expanded_domains.json"))
    parser.add_argument("--rebuild-cache", action="store_true")
    parser.add_argument(
        "--run-dir",
        default="",
        help=(
            "Output folder for this run. Defaults to exports/ner/runs/<run_id> where "
            "run_id is generated from the current timestamp. Pass an explicit path to "
            "resume a specific run (checkpoint within the folder is used automatically)."
        ),
    )
    parser.add_argument("--run-id", default="", help="Explicit run ID label (used in folder name).")
    parser.add_argument("--vector-k", type=int, default=250)
    parser.add_argument("--ft-limit", type=int, default=600)
    parser.add_argument("--max-fulltext-per-domain", type=int, default=200)
    parser.add_argument("--max-vector-per-domain", type=int, default=150)
    parser.add_argument("--search-workers", type=int, default=1, help="Parallel domain search workers.")
    parser.add_argument("--search-auto-ramp", action="store_true", help="Auto ramp domain-search workers up/down.")
    parser.add_argument("--search-min-workers", type=int, default=2, help="Min workers when auto-ramp enabled.")
    parser.add_argument("--search-max-workers", type=int, default=10, help="Max workers when auto-ramp enabled.")
    parser.add_argument(
        "--search-ramp-up-below-sec",
        type=float,
        default=8.0,
        help="Ramp up workers when wave avg latency is below this threshold.",
    )
    parser.add_argument(
        "--search-ramp-down-above-sec",
        type=float,
        default=25.0,
        help="Ramp down workers when wave avg latency is above this threshold.",
    )
    parser.add_argument("--search-max-retries", type=int, default=1, help="Retry count for failed domain searches.")
    parser.add_argument("--desc-depth", type=int, default=2)
    parser.add_argument("--desc-limit", type=int, default=200)
    parser.add_argument("--skip-resolve", action="store_true")
    parser.add_argument("--resolve-batch", type=int, default=50)
    parser.add_argument("--max-encounters", type=int, default=0, help="0 = process all")
    parser.add_argument("--terminology-url", default=os.getenv("TERMINOLOGY_API_URL", "http://localhost:8001"))
    args = parser.parse_args()

    # Resolve run directory — each run gets its own folder so outputs are never mixed.
    if args.run_dir:
        out_dir = Path(args.run_dir)
    else:
        import datetime
        run_id = args.run_id or datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = ROOT / "exports" / "ner" / "runs" / run_id

    out_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = out_dir / "checkpoint.json"
    logger.info("Run output dir: %s", out_dir)

    domains = _load_or_build_domain_cache(
        expanded_cache_path=Path(args.expanded_cache),
        config_dir=Path(args.config_dir),
        desc_depth=args.desc_depth,
        desc_limit=args.desc_limit,
        force_rebuild=args.rebuild_cache,
    )
    logger.info("Loaded %d domain configs", len(domains))

    # Neo4j connection
    uri = os.environ.get("NEO4J_URI", "")
    user = os.environ.get("NEO4J_USER", "")
    password = os.environ.get("NEO4J_PASSWORD", "")
    if not all([uri, user, password]):
        raise RuntimeError("Missing NEO4J_URI/NEO4J_USER/NEO4J_PASSWORD")

    driver = GraphDatabase.driver(
        uri,
        auth=(user, password),
        liveness_check_timeout=5,
        max_connection_lifetime=300,
    )

    vector_settings = load_vector_settings()
    embedder = TextEmbedder(vector_settings)
    embedder.encode(["warm-up"])
    logger.info("Vector embedder ready: %s (%s)", vector_settings.model_name, vector_settings.device)

    all_hits: dict[str, dict[str, Any]] = {}
    domain_stats: dict[str, dict[str, Any]] = {}

    # ---- Search phase ----
    search_start = time.time()
    ordered_domains = sorted(domains.items())
    retry_counts: dict[str, int] = defaultdict(int)
    pending: list[tuple[str, DomainSearchConfig]] = list(ordered_domains)
    completed = 0
    min_workers = max(1, args.search_min_workers if args.search_auto_ramp else args.search_workers)
    max_workers = max(min_workers, args.search_max_workers if args.search_auto_ramp else args.search_workers)
    workers = max(min_workers, min(max_workers, args.search_workers))
    embed_lock = threading.Lock()

    while pending:
        wave = pending[:workers]
        pending = pending[workers:]
        wave_started = time.time()
        logger.info(
            "search wave: size=%d workers=%d pending_after_wave=%d",
            len(wave),
            workers,
            len(pending),
        )

        wave_results: list[tuple[str, dict[str, dict[str, Any]], dict[str, Any], float, str | None]] = []
        if workers == 1:
            for dname, cfg in wave:
                logger.info("[%d/%d] searching domain: %s", completed + 1, len(ordered_domains), dname)
                wave_results.append(
                    _search_single_domain(
                        dname=dname,
                        cfg=cfg,
                        driver=driver,
                        embedder=embedder,
                        args=args,
                        embed_lock=embed_lock,
                    )
                )
        else:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                future_map = {
                    pool.submit(
                        _search_single_domain,
                        dname=dname,
                        cfg=cfg,
                        driver=driver,
                        embedder=embedder,
                        args=args,
                        embed_lock=embed_lock,
                    ): dname
                    for dname, cfg in wave
                }
                for fut in as_completed(future_map):
                    wave_results.append(fut.result())

        failures = 0
        latencies: list[float] = []
        for dname, merged_domain_hits, stats, elapsed, err in sorted(wave_results, key=lambda x: x[0]):
            latencies.append(elapsed)
            if err:
                failures += 1
                retry_counts[dname] += 1
                if retry_counts[dname] <= args.search_max_retries:
                    logger.warning(
                        "domain search failed (%s) retry=%d/%d: %s",
                        dname,
                        retry_counts[dname],
                        args.search_max_retries,
                        err,
                    )
                    pending.append((dname, domains[dname]))
                else:
                    logger.error("domain search failed permanently (%s): %s", dname, err)
                continue

            _merge_hits(all_hits, merged_domain_hits)
            domain_stats[dname] = stats
            completed += 1
            logger.info(
                "[%d/%d] searched domain=%s hits=%d elapsed=%.2fs",
                completed,
                len(ordered_domains),
                dname,
                stats.get("encounters_merged", 0),
                elapsed,
            )

        avg_latency = (sum(latencies) / len(latencies)) if latencies else 0.0
        if args.search_auto_ramp and pending:
            if failures > 0 or avg_latency >= args.search_ramp_down_above_sec:
                next_workers = max(min_workers, workers - 1)
                if next_workers != workers:
                    logger.info(
                        "ramp-down workers %d -> %d (failures=%d avg_latency=%.2fs)",
                        workers,
                        next_workers,
                        failures,
                        avg_latency,
                    )
                workers = next_workers
            elif avg_latency <= args.search_ramp_up_below_sec:
                next_workers = min(max_workers, workers + 1)
                if next_workers != workers:
                    logger.info(
                        "ramp-up workers %d -> %d (avg_latency=%.2fs)",
                        workers,
                        next_workers,
                        avg_latency,
                    )
                workers = next_workers

        logger.info(
            "wave complete in %.2fs | avg_domain_latency=%.2fs failures=%d",
            time.time() - wave_started,
            avg_latency,
            failures,
        )

    logger.info("Search complete in %.1fs; unique encounters=%d", time.time() - search_start, len(all_hits))

    # ---- Extraction phase ----
    pattern_map = _compile_patterns(domains)

    encounters = sorted(all_hits.values(), key=lambda x: (x["encounter_date"], x["encounter_id"]))
    if args.max_encounters > 0:
        encounters = encounters[: args.max_encounters]

    # Resume within a run: pick up from checkpoint in this run's folder.
    # Because each run has its own folder, resume is safe — we only append to
    # files in this run dir, never touching another run's output.
    start_idx = 0
    extracted_records = 0
    extracted_entities = 0
    rejected_records = 0
    resolved_terms = 0
    unresolved_terms = 0
    deid_leak_counts: dict[str, int] = {}
    precision_reject_counts: dict[str, int] = {}
    domain_entity_counts: dict[str, int] = defaultdict(int)
    domain_record_counts: dict[str, int] = defaultdict(int)

    resuming = checkpoint_path.exists()
    if resuming:
        cp = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        start_idx = int(cp.get("last_index", 0))
        extracted_records = int(cp.get("records", 0))
        extracted_entities = int(cp.get("entities", 0))
        resolved_terms = int(cp.get("resolved_terms", 0))
        unresolved_terms = int(cp.get("unresolved_terms", 0))
        if start_idx >= len(encounters):
            logger.info(
                "Run already complete (checkpoint=%d >= encounters=%d). Nothing to do.",
                start_idx, len(encounters),
            )
            driver.close()
            return
        logger.info("Resuming run from index=%d / %d encounters", start_idx, len(encounters))

    # Each run always writes its own isolated files.
    # Fresh start → "w"; resuming within same run dir → "a" (append to existing partial output).
    file_mode = "a" if resuming else "w"
    per_domain_handles: dict[str, Any] = {}
    for dname in domains:
        per_domain_handles[dname] = open(out_dir / f"domain_{dname}.jsonl", file_mode, encoding="utf-8")
    merged_path = out_dir / "domain_entities_merged.jsonl"
    rejected_path = out_dir / "domain_entities_rejected.jsonl"
    merged_fh = open(merged_path, file_mode, encoding="utf-8")
    rejected_fh = open(rejected_path, file_mode, encoding="utf-8")

    try:
        http_client = httpx.Client() if not args.skip_resolve else None
        process_start = time.time()

        for i in range(start_idx, len(encounters)):
            enc = encounters[i]
            raw_text = enc.get("text") or ""

            # ---- Strict de-id before any processing ----
            deid_text = deidentify_text(raw_text)
            sentences = _split_sentences(deid_text)

            for sent_idx, (_, _, sent_text) in enumerate(sentences):
                by_domain_entities: dict[str, list[dict[str, Any]]] = defaultdict(list)
                unknown_terms: list[str] = []

                for dname in enc["domains"]:
                    cfg = domains[dname]
                    patterns = pattern_map[dname]
                    seen_spans: set[tuple[int, int]] = set()
                    for pat in patterns:
                        for m in pat.finditer(sent_text):
                            span = (m.start(), m.end())
                            if span in seen_spans:
                                continue
                            seen_spans.add(span)
                            phrase = sent_text[span[0] : span[1]]
                            key = phrase.lower().strip()
                            mapped = cfg.concept_map.get(key)
                            entity = {
                                "text": phrase,
                                "start": span[0],
                                "end": span[1],
                                "lookup_term": key,
                                "label": (mapped or {}).get("semantic_tag") or "finding",
                                "assertion": _infer_assertion(sent_text),
                                "domain": dname,
                                "snomed_id": (mapped or {}).get("concept_id"),
                                "snomed_term": (mapped or {}).get("preferred_term"),
                                "resolver_score": 1.0 if mapped else None,
                                "confidence": 1.0 if mapped else 0.0,
                            }
                            if not mapped:
                                unknown_terms.append(key)
                            by_domain_entities[dname].append(entity)

                # Terminology resolution for unresolved terms
                resolved_map: dict[str, list[dict[str, Any]]] = {}
                if http_client and unknown_terms:
                    try:
                        resolved_map = _resolve_unknown_terms(
                            http_client,
                            args.terminology_url,
                            unknown_terms,
                            args.resolve_batch,
                        )
                    except Exception as exc:
                        logger.warning("resolve failed for sentence: %s", exc)

                # Apply resolution results
                for dname, ents in by_domain_entities.items():
                    for ent in ents:
                        if ent["snomed_id"] is None:
                            candidates = resolved_map.get(ent["lookup_term"], [])
                            if candidates:
                                best = candidates[0]
                                ent["snomed_id"] = best.get("snomed_concept_id")
                                ent["snomed_term"] = best.get("snomed_term")
                                ent["resolver_score"] = float(best.get("score", 0.0))
                                ent["confidence"] = float(best.get("score", 0.0))
                                resolved_terms += 1
                            else:
                                unresolved_terms += 1

                # Build raw record for schema mapper
                if not any(by_domain_entities.values()):
                    continue

                all_entities_raw: list[dict[str, Any]] = [
                    ent
                    for ents in by_domain_entities.values()
                    for ent in ents
                ]

                raw_record = {
                    "encounter_id": enc["encounter_id"],
                    "patient_id": enc["patient_id"],
                    "encounter_date": enc["encounter_date"],
                    "sentence_id": f"s{sent_idx}",
                    "text": sent_text,
                    "entities": all_entities_raw,
                    "relations": [],
                    "_search_source": enc["source"],
                    "_ft_score": enc["ft_score"],
                    "_vec_score": enc["vec_score"],
                }

                # ---- Schema mapping ----
                canonical, reject_reasons = map_raw_record(raw_record, source_origin="mined_raw")
                if not canonical:
                    rejected_records += 1
                    rejected_fh.write(
                        json.dumps({"raw": raw_record, "reasons": reject_reasons}, ensure_ascii=False) + "\n"
                    )
                    continue

                # ---- Relation extraction ----
                canonical = build_relations(canonical)

                # ---- Precision hardening ----
                precision_reasons = check_record_entities(canonical)
                if precision_reasons:
                    rejected_records += 1
                    for r in precision_reasons:
                        precision_reject_counts[r] = precision_reject_counts.get(r, 0) + 1
                    rejected_fh.write(
                        json.dumps({"raw": raw_record, "reasons": precision_reasons}, ensure_ascii=False) + "\n"
                    )
                    continue

                # ---- De-id final validation ----
                canonical = sanitise_record_metadata(canonical)
                deid_issues = _deid_validator.check_record(canonical)
                if deid_issues:
                    rejected_records += 1
                    for issue in deid_issues:
                        deid_leak_counts[issue.issue_type] = deid_leak_counts.get(issue.issue_type, 0) + 1
                    rejected_fh.write(
                        json.dumps(
                            {"raw": raw_record, "reasons": [i.issue_type for i in deid_issues]},
                            ensure_ascii=False,
                        ) + "\n"
                    )
                    continue

                # ---- Write outputs ----
                extracted_records += 1
                extracted_entities += len(canonical["entities"])

                # Per-domain files
                domains_in_record = {e.get("domain") for e in canonical["entities"] if e.get("domain")}
                for dname in domains_in_record:
                    if dname in per_domain_handles:
                        per_domain_handles[dname].write(json.dumps(canonical, ensure_ascii=False) + "\n")
                        domain_record_counts[dname] += 1
                    for ent in canonical["entities"]:
                        if ent.get("domain") == dname:
                            domain_entity_counts[dname] += 1

                merged_fh.write(json.dumps(canonical, ensure_ascii=False) + "\n")

            # ---- Checkpoint ----
            if (i + 1) % 200 == 0:
                elapsed = time.time() - process_start
                logger.info(
                    "Processed %d/%d | records=%d entities=%d rejected=%d | %.1f enc/s",
                    i + 1,
                    len(encounters),
                    extracted_records,
                    extracted_entities,
                    rejected_records,
                    (i + 1 - start_idx) / max(elapsed, 0.1),
                )
                checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
                checkpoint_path.write_text(
                    json.dumps(
                        {
                            "last_index": i + 1,
                            "records": extracted_records,
                            "entities": extracted_entities,
                            "rejected_records": rejected_records,
                            "resolved_terms": resolved_terms,
                            "unresolved_terms": unresolved_terms,
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )

        if http_client:
            http_client.close()

        summary = {
            "schema_version": "v1",
            "source": "raw_encounter_text_only",
            "searched_domains": len(domains),
            "encounters_considered": len(encounters),
            "records_written": extracted_records,
            "entities_written": extracted_entities,
            "records_rejected": rejected_records,
            "resolved_terms": resolved_terms,
            "unresolved_terms": unresolved_terms,
            "deid_leak_counts": deid_leak_counts,
            "precision_reject_counts": precision_reject_counts,
            "domain_search_stats": domain_stats,
            "domain_entity_counts": dict(sorted(domain_entity_counts.items())),
            "domain_record_counts": dict(sorted(domain_record_counts.items())),
            "paths": {
                "out_dir": str(out_dir),
                "merged_jsonl": str(merged_path),
                "rejected_jsonl": str(rejected_path),
                "checkpoint": str(checkpoint_path),
            },
        }
        summary_path = out_dir / "summary.json"
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(
            "Mining complete: records=%d entities=%d rejected=%d",
            extracted_records,
            extracted_entities,
            rejected_records,
        )
        logger.info("Summary: %s", summary_path)

    finally:
        for fh in per_domain_handles.values():
            fh.close()
        merged_fh.close()
        rejected_fh.close()
        driver.close()


if __name__ == "__main__":
    main()
