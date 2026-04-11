#!/usr/bin/env python3
"""Mine ALL encounters for cancer exclusion / all-clear / negative findings.

Uses two Neo4j indexes in parallel:
  - encounter_text_index  (FULLTEXT)  — exact / Lucene phrase matches
  - encounter_vector_index (VECTOR)   — semantic similarity via Bio_ClinicalBERT

Pipeline:
  1. Fulltext search: run each keyword phrase against the fulltext index
  2. Vector search:   run each semantic phrase against the vector index
  3. Merge & deduplicate encounters from both tiers
  4. De-identify each encounter
  5. Split into sentences with character offsets
  6. Resolve entities via terminology API (batched)
  7. Infer assertion (absent / family / historical / present)
  8. Write JSONL output

Usage:
    python scripts/semantic_exclusion_search.py
    python scripts/semantic_exclusion_search.py --skip-resolve   # no terminology API needed
    python scripts/semantic_exclusion_search.py --vector-k 200 --ft-limit 500
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env")

from neo4j import GraphDatabase

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ─── Fulltext search phrases (Lucene syntax for encounter_text_index) ────────
# These are run as Lucene queries against the fulltext index.
# Quoted strings = phrase match; unquoted = AND-ed tokens.
FULLTEXT_QUERIES = [
    # Explicit exclusion
    '"no evidence of malignancy"',
    '"no evidence of cancer"',
    '"cancer excluded"',
    '"malignancy excluded"',
    '"cancer ruled out"',
    '"ruled out cancer"',
    '"all clear"',
    '"given the all clear"',
    '"no malignancy"',
    '"not malignant"',
    '"non malignant"',
    '"no cancer"',
    # Benign / negative results
    '"benign" AND "biopsy"',
    '"benign" AND "lesion"',
    '"benign" AND "tumour"',
    '"benign" AND "tumor"',
    '"benign" AND "polyp"',
    '"negative biopsy"',
    '"biopsy negative"',
    '"biopsy benign"',
    '"no dysplasia"',
    '"fibroadenoma"',
    # Negative investigations
    '"normal colonoscopy"',
    '"colonoscopy normal"',
    '"mammogram normal"',
    '"normal mammogram"',
    '"CT normal"',
    '"MRI normal"',
    '"no lesion"',
    '"no mass"',
    '"no tumour"',
    '"no tumor"',
    '"PSA normal"',
    '"chest x-ray clear"',
    '"chest x-ray normal"',
    '"FIT negative"',
    '"FIT normal"',
    # Discharge from cancer pathway
    '"discharged from oncology"',
    '"discharged from 2WW"',
    '"removed from cancer register"',
    '"stepped down" AND "cancer"',
    '"no further follow up" AND "cancer"',
    '"no further follow-up" AND "cancer"',
    # Screening
    '"bowel screening" AND "normal"',
    '"breast screening" AND "normal"',
    '"cervical screening" AND "negative"',
    '"HPV negative"',
    # GP reassurance
    '"no sinister features"',
    '"unlikely malignancy"',
    '"no red flag"',
    '"no red flags"',
    '"no concerning features"',
    '"reassured" AND "not cancer"',
    '"cancer not suspected"',
    # Surveillance / remission
    '"no recurrence"',
    '"no evidence of recurrence"',
    '"remission"',
    '"in remission"',
    '"complete remission"',
    '"five year" AND "no recurrence"',
]


# ─── Vector search phrases (semantic, embedded via Bio_ClinicalBERT) ─────────
VECTOR_PHRASES = [
    # Explicit exclusion / all-clear
    "cancer excluded no malignancy all clear",
    "negative biopsy result no cancer",
    "given the all clear no evidence of malignancy",
    "ruled out cancer benign result",
    "no evidence of malignancy biopsy negative",
    "cancer ruled out discharged",
    "all clear from cancer screening",
    "no malignancy confirmed benign",
    # Negative investigations / test results
    "normal colonoscopy no polyps no malignancy",
    "CT scan normal no lesion no mass",
    "mammogram normal no suspicious findings",
    "chest X-ray clear no lung mass",
    "PSA normal within range",
    "negative FIT test normal bowel screening",
    "MRI no evidence of tumour",
    "ultrasound benign cyst no solid mass",
    "biopsy showed benign tissue no dysplasia",
    # Discharge from cancer pathway
    "discharged from 2WW clinic no cancer found",
    "discharged from oncology no further follow up",
    "removed from cancer register",
    "stepped down from cancer pathway",
    "no longer under oncology care",
    # Benign / non-malignant findings
    "benign lesion confirmed not malignant",
    "fibroadenoma benign breast lump",
    "benign polyp removed no dysplasia",
    "inflammatory changes not malignant",
    "lipoma benign soft tissue",
    # GP reassurance / exclusion language
    "no sinister features reassured",
    "unlikely malignancy no red flag symptoms",
    "no concerning features low risk cancer",
    "reassured not cancer safety netting advice given",
    "cancer not suspected watchful waiting",
    # Screening programmes
    "bowel cancer screening result normal",
    "breast screening mammogram normal",
    "cervical screening negative HPV",
    # Surveillance / remission
    "no signs of recurrence surveillance normal",
    "remission confirmed annual review",
    "cancer follow up no evidence of recurrence",
    "five year review no recurrence discharged",
]


# ─── Assertion inference ─────────────────────────────────────────────────────
_NEGATED_RE = re.compile(
    r"\b(no evidence of|no fam|rule out|unlikely|excluded|not |negative|"
    r"no malignancy|all clear|benign|non.malignant|no recurrence|"
    r"normal result|no suspicious|no sinister|no cancer|ruled out|"
    r"no lesion|no mass|no tumour|no tumor|no dysplasia|cancer excluded)\b",
    re.IGNORECASE,
)
_FAMILY_RE = re.compile(
    r"\b(family history|fam hx|fam hist|maternal|paternal|FH )\b",
    re.IGNORECASE,
)
_HISTORICAL_RE = re.compile(
    r"\b(history of|past medical history|previous|previously|had|remission)\b",
    re.IGNORECASE,
)

_SENTENCE_SEP = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])|[\r\n]+|\s*;\s*")


def _infer_assertion(text: str) -> str:
    if _NEGATED_RE.search(text):
        return "absent"
    if _FAMILY_RE.search(text):
        return "family"
    if _HISTORICAL_RE.search(text):
        return "historical"
    return "present"


def _split_sentences(text: str) -> list[tuple[int, int, str]]:
    """Return [(start, end, sentence_text), ...] with character offsets."""
    parts = _SENTENCE_SEP.split(text)
    result: list[tuple[int, int, str]] = []
    pos = 0
    for part in parts:
        p = part.strip()
        if len(p) < 10:
            pos += len(part)
            continue
        idx = text.find(p, pos)
        if idx >= 0:
            result.append((idx, idx + len(p), p))
            pos = idx + len(p)
        else:
            pos += len(part)
    return result


# ─── Sub-phrase patterns for entity extraction ───────────────────────────────
_ENTITY_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    (
        re.compile(r"\b(no evidence of \w[\w\s]{0,30})", re.I),
        "finding",
        "oncology_exclusion",
    ),
    (re.compile(r"\b(all clear)\b", re.I), "finding", "oncology_exclusion"),
    (re.compile(r"\b(cancer excluded)\b", re.I), "finding", "oncology_exclusion"),
    (re.compile(r"\b(malignancy excluded)\b", re.I), "finding", "oncology_exclusion"),
    (re.compile(r"\b(cancer ruled out)\b", re.I), "finding", "oncology_exclusion"),
    (re.compile(r"\b(ruled out cancer)\b", re.I), "finding", "oncology_exclusion"),
    (re.compile(r"\b(no malignancy)\b", re.I), "finding", "oncology_exclusion"),
    (re.compile(r"\b(not malignant)\b", re.I), "finding", "oncology_exclusion"),
    (re.compile(r"\b(non.malignant)\b", re.I), "finding", "oncology_exclusion"),
    (re.compile(r"\b(benign \w[\w\s]{0,20})", re.I), "finding", "oncology_exclusion"),
    (re.compile(r"\b(negative biopsy)\b", re.I), "finding", "oncology_exclusion"),
    (re.compile(r"\b(biopsy negative)\b", re.I), "finding", "oncology_exclusion"),
    (re.compile(r"\b(biopsy benign)\b", re.I), "finding", "oncology_exclusion"),
    (re.compile(r"\b(no dysplasia)\b", re.I), "finding", "oncology_exclusion"),
    (re.compile(r"\b(fibroadenoma)\b", re.I), "finding", "oncology_exclusion"),
    (re.compile(r"\b(no recurrence)\b", re.I), "finding", "oncology_surveillance"),
    (re.compile(r"\b(in remission)\b", re.I), "finding", "oncology_surveillance"),
    (re.compile(r"\b(complete remission)\b", re.I), "finding", "oncology_surveillance"),
    (re.compile(r"\b(no sinister features)\b", re.I), "finding", "oncology_exclusion"),
    (re.compile(r"\b(unlikely malignancy)\b", re.I), "finding", "oncology_exclusion"),
    (re.compile(r"\b(no red flags?)\b", re.I), "finding", "oncology_exclusion"),
    (
        re.compile(r"\b(no concerning features)\b", re.I),
        "finding",
        "oncology_exclusion",
    ),
    (
        re.compile(r"\b(normal colonoscopy)\b", re.I),
        "procedure",
        "investigation_negative",
    ),
    (
        re.compile(r"\b(colonoscopy normal)\b", re.I),
        "procedure",
        "investigation_negative",
    ),
    (
        re.compile(r"\b(mammogram normal)\b", re.I),
        "procedure",
        "investigation_negative",
    ),
    (
        re.compile(r"\b(normal mammogram)\b", re.I),
        "procedure",
        "investigation_negative",
    ),
    (
        re.compile(r"\b(CT (?:scan )?normal)\b", re.I),
        "procedure",
        "investigation_negative",
    ),
    (re.compile(r"\b(MRI normal)\b", re.I), "procedure", "investigation_negative"),
    (
        re.compile(r"\b(chest [xX]-?ray (?:clear|normal))\b", re.I),
        "procedure",
        "investigation_negative",
    ),
    (
        re.compile(r"\b(PSA normal)\b", re.I),
        "observable entity",
        "investigation_negative",
    ),
    (
        re.compile(r"\b(FIT (?:negative|normal))\b", re.I),
        "procedure",
        "screening_negative",
    ),
    (re.compile(r"\b(HPV negative)\b", re.I), "procedure", "screening_negative"),
    (
        re.compile(r"\b(discharged from (?:oncology|2WW|cancer)[\w\s]{0,20})", re.I),
        "situation",
        "pathway_discharge",
    ),
    (
        re.compile(r"\b(removed from cancer register)\b", re.I),
        "situation",
        "pathway_discharge",
    ),
    (
        re.compile(r"\b(no further follow.up[\w\s]{0,20})", re.I),
        "situation",
        "pathway_discharge",
    ),
    (re.compile(r"\b(2[wW]{2} \w[\w\s]{0,20})", re.I), "procedure", "referral"),
    (re.compile(r"\b(fast track \w[\w\s]{0,20})", re.I), "procedure", "referral"),
    (re.compile(r"\b(breast ca(?:ncer)?)\b", re.I), "disorder", "oncology_diagnosis"),
    (re.compile(r"\b(lung ca(?:ncer)?)\b", re.I), "disorder", "oncology_diagnosis"),
    (re.compile(r"\b(bowel ca(?:ncer)?)\b", re.I), "disorder", "oncology_diagnosis"),
    (
        re.compile(r"\b(colorectal ca(?:ncer)?)\b", re.I),
        "disorder",
        "oncology_diagnosis",
    ),
    (re.compile(r"\b(prostate ca(?:ncer)?)\b", re.I), "disorder", "oncology_diagnosis"),
    (re.compile(r"\b(skin ca(?:ncer)?)\b", re.I), "disorder", "oncology_diagnosis"),
    (re.compile(r"\b(melanoma)\b", re.I), "disorder", "oncology_diagnosis"),
    (re.compile(r"\b(lymphoma)\b", re.I), "disorder", "oncology_diagnosis"),
    (re.compile(r"\b(leukaemia|leukemia)\b", re.I), "disorder", "oncology_diagnosis"),
    (
        re.compile(r"\b(malignant? neoplasm[\w\s]{0,20})", re.I),
        "disorder",
        "oncology_diagnosis",
    ),
    (
        re.compile(r"\b(fam(?:ily)? h(?:istory|x)[\w\s]{0,20})", re.I),
        "situation",
        "family_history",
    ),
    (re.compile(r"\b(lump \w[\w\s]{0,15})", re.I), "finding", "clinical_observations"),
    (re.compile(r"\b(skin changes?)\b", re.I), "finding", "clinical_observations"),
]


def _extract_entities(sentence_text: str) -> list[dict]:
    """Extract entities from sentence text using pattern matching."""
    entities: list[dict] = []
    seen_spans: set[tuple[int, int]] = set()
    for pat, sem_tag, domain in _ENTITY_PATTERNS:
        for m in pat.finditer(sentence_text):
            span = (m.start(1), m.end(1))
            if span in seen_spans:
                continue
            overlap = any(s[0] < span[1] and span[0] < s[1] for s in seen_spans)
            if overlap:
                continue
            seen_spans.add(span)
            entities.append(
                {
                    "text": m.group(1).strip(),
                    "start": span[0],
                    "end": span[1],
                    "lookup_term": m.group(1).strip().lower(),
                    "semantic_tag": sem_tag,
                    "assertion": _infer_assertion(sentence_text),
                    "domain": domain,
                    "snomed_id": None,
                    "snomed_term": None,
                    "resolver_score": None,
                }
            )
    entities.sort(key=lambda e: e["start"])
    return entities


def _resolve_batch(terms: list[str], api_url: str) -> dict[str, list[dict]]:
    """Resolve a batch of terms via the terminology API."""
    import httpx

    if not terms:
        return {}
    unique = list(dict.fromkeys(terms))
    try:
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(
                f"{api_url.rstrip('/')}/terminology/resolve",
                json={"terms": unique},
            )
            resp.raise_for_status()
            return resp.json().get("results", {})
    except Exception as e:
        log.warning("Terminology resolve failed: %s", e)
        return {}


# ─── Neo4j search tiers ─────────────────────────────────────────────────────


def _fulltext_search(
    driver, queries: list[str], limit_per_query: int
) -> dict[str, dict]:
    """Run Lucene fulltext queries, return dict keyed by encounter_id."""
    results: dict[str, dict] = {}
    for query in queries:
        try:
            with driver.session() as s:
                rows = s.run(
                    "CALL db.index.fulltext.queryNodes('encounter_text_index', $q, {limit: $lim}) "
                    "YIELD node, score "
                    "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e) WHERE e = node "
                    "RETURN toString(e.id) AS encounter_id, toString(p.id) AS patient_id, "
                    "e.text AS text, toString(e.date) AS encounter_date, score, 'fulltext' AS source",
                    q=query,
                    lim=limit_per_query,
                ).data()
            for r in rows:
                eid = r.get("encounter_id") or ""
                if eid not in results or r.get("score", 0) > results[eid].get(
                    "ft_score", 0
                ):
                    results[eid] = {
                        "encounter_id": eid,
                        "patient_id": r.get("patient_id", ""),
                        "text": r.get("text", ""),
                        "encounter_date": str(r.get("encounter_date") or "")[:10],
                        "ft_score": float(r.get("score", 0)),
                        "vec_score": results.get(eid, {}).get("vec_score", 0.0),
                        "source": "fulltext",
                    }
        except Exception as e:
            log.warning("Fulltext query failed for '%s': %s", query[:40], e)
    return results


def _vector_search(driver, phrases: list[str], embedder, top_k: int) -> dict[str, dict]:
    """Run vector similarity queries, return dict keyed by encounter_id."""
    results: dict[str, dict] = {}
    for phrase in phrases:
        emb = embedder.encode([phrase])[0]
        try:
            with driver.session() as s:
                rows = s.run(
                    "CALL db.index.vector.queryNodes('encounter_vector_index', $k, $emb) "
                    "YIELD node, score "
                    "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e) WHERE e = node "
                    "RETURN toString(e.id) AS encounter_id, toString(p.id) AS patient_id, "
                    "e.text AS text, toString(e.date) AS encounter_date, score, 'vector' AS source",
                    emb=emb,
                    k=top_k,
                ).data()
            for r in rows:
                eid = r.get("encounter_id") or ""
                vec_score = float(r.get("score", 0))
                if eid not in results:
                    results[eid] = {
                        "encounter_id": eid,
                        "patient_id": r.get("patient_id", ""),
                        "text": r.get("text", ""),
                        "encounter_date": str(r.get("encounter_date") or "")[:10],
                        "ft_score": 0.0,
                        "vec_score": vec_score,
                        "source": "vector",
                    }
                elif vec_score > results[eid].get("vec_score", 0):
                    results[eid]["vec_score"] = vec_score
                    if results[eid]["source"] == "fulltext":
                        results[eid]["source"] = "both"
        except Exception as e:
            log.warning("Vector query failed for '%s': %s", phrase[:40], e)
    return results


# ─── Main ────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--vector-k",
        type=int,
        default=200,
        help="Top-k per vector phrase (default 200)",
    )
    parser.add_argument(
        "--ft-limit",
        type=int,
        default=500,
        help="Limit per fulltext query (default 500)",
    )
    parser.add_argument(
        "--output", type=str, default="exports/exclusion_entities.jsonl"
    )
    parser.add_argument(
        "--skip-resolve", action="store_true", help="Skip terminology API resolution"
    )
    parser.add_argument(
        "--terminology-url",
        type=str,
        default=os.getenv("TERMINOLOGY_API_URL", "http://localhost:8001"),
    )
    parser.add_argument(
        "--resolve-batch", type=int, default=50, help="Terms per resolve API call"
    )
    args = parser.parse_args()

    uri = os.environ.get("NEO4J_URI")
    user = os.environ.get("NEO4J_USER")
    password = os.environ.get("NEO4J_PASSWORD")
    if not all([uri, user, password]):
        log.error("Set NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD in secrets/.env")
        sys.exit(1)

    driver = GraphDatabase.driver(
        uri, auth=(user, password), max_connection_lifetime=300
    )

    # ── Tier 1: Fulltext search ──────────────────────────────────────────────
    log.info(
        "Tier 1 — fulltext search (%d queries, limit %d each)",
        len(FULLTEXT_QUERIES),
        args.ft_limit,
    )
    t0 = time.time()
    ft_results = _fulltext_search(driver, FULLTEXT_QUERIES, args.ft_limit)
    log.info(
        "  Fulltext found %d unique encounters in %.1fs",
        len(ft_results),
        time.time() - t0,
    )

    # ── Tier 2: Vector search ────────────────────────────────────────────────
    log.info(
        "Tier 2 — vector search (%d phrases, top-k %d each)",
        len(VECTOR_PHRASES),
        args.vector_k,
    )
    from scripts.embedding_utils import load_vector_settings, TextEmbedder

    settings = load_vector_settings()
    embedder = TextEmbedder(settings)

    t1 = time.time()
    vec_results = _vector_search(driver, VECTOR_PHRASES, embedder, args.vector_k)
    log.info(
        "  Vector found %d unique encounters in %.1fs",
        len(vec_results),
        time.time() - t1,
    )

    # ── Merge ────────────────────────────────────────────────────────────────
    merged: dict[str, dict] = {}
    for eid, rec in ft_results.items():
        merged[eid] = rec
    for eid, rec in vec_results.items():
        if eid in merged:
            merged[eid]["vec_score"] = max(
                merged[eid].get("vec_score", 0), rec["vec_score"]
            )
            merged[eid]["source"] = "both"
        else:
            merged[eid] = rec

    ft_only = sum(1 for r in merged.values() if r["source"] == "fulltext")
    vec_only = sum(1 for r in merged.values() if r["source"] == "vector")
    both = sum(1 for r in merged.values() if r["source"] == "both")
    log.info(
        "Merged: %d unique encounters (fulltext-only=%d, vector-only=%d, both=%d)",
        len(merged),
        ft_only,
        vec_only,
        both,
    )

    # ── Process encounters ───────────────────────────────────────────────────
    from libs.utils.deidentify import deidentify_text

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    all_encounters = sorted(merged.values(), key=lambda r: r["encounter_date"])
    written = 0
    entity_count = 0
    resolve_cache: dict[str, list[dict]] = {}
    t2 = time.time()

    with open(out_path, "w", encoding="utf-8") as f:
        for i, enc in enumerate(all_encounters, 1):
            text = enc.get("text") or ""
            deid = deidentify_text(text)
            sentences = _split_sentences(deid)

            for sent_idx, (sent_start, sent_end, sent_text) in enumerate(sentences):
                entities = _extract_entities(sent_text)
                if not entities:
                    continue

                # Terminology resolution
                if not args.skip_resolve and entities:
                    terms_to_resolve = [
                        e["lookup_term"]
                        for e in entities
                        if e["lookup_term"] not in resolve_cache
                    ]
                    if terms_to_resolve:
                        for batch_start in range(
                            0, len(terms_to_resolve), args.resolve_batch
                        ):
                            batch = terms_to_resolve[
                                batch_start : batch_start + args.resolve_batch
                            ]
                            resolved = _resolve_batch(batch, args.terminology_url)
                            resolve_cache.update(resolved)

                    for ent in entities:
                        candidates = resolve_cache.get(ent["lookup_term"], [])
                        if candidates:
                            best = candidates[0]
                            ent["snomed_id"] = best.get("snomed_concept_id")
                            ent["snomed_term"] = best.get("snomed_term")
                            ent["resolver_score"] = float(best.get("score", 0))

                record = {
                    "encounter_id": enc["encounter_id"],
                    "patient_id": enc["patient_id"],
                    "encounter_date": enc["encounter_date"],
                    "sentence_id": f"s{sent_idx}",
                    "sentence_text": sent_text,
                    "entities": entities,
                    "_search_source": enc["source"],
                    "_ft_score": enc.get("ft_score", 0),
                    "_vec_score": enc.get("vec_score", 0),
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                written += 1
                entity_count += len(entities)

            if i % 500 == 0:
                elapsed = time.time() - t2
                log.info(
                    "  Processed %d / %d encounters  (%d records, %d entities, %.0f enc/s)",
                    i,
                    len(all_encounters),
                    written,
                    entity_count,
                    i / elapsed,
                )

    elapsed = time.time() - t2
    log.info(
        "Done — %d records, %d entities from %d encounters in %.1fs",
        written,
        entity_count,
        len(all_encounters),
        elapsed,
    )
    log.info("Output: %s", out_path)

    # Summary stats
    log.info("--- Summary ---")
    log.info("  Fulltext queries       : %d", len(FULLTEXT_QUERIES))
    log.info("  Vector phrases         : %d", len(VECTOR_PHRASES))
    log.info("  Encounters (fulltext)  : %d", len(ft_results))
    log.info("  Encounters (vector)    : %d", len(vec_results))
    log.info("  Encounters (merged)    : %d", len(merged))
    log.info("  Sentences with entities: %d", written)
    log.info("  Total entities         : %d", entity_count)
    if not args.skip_resolve:
        resolved_count = sum(1 for v in resolve_cache.values() if v)
        log.info(
            "  Terms resolved (SNOMED): %d / %d", resolved_count, len(resolve_cache)
        )

    driver.close()


if __name__ == "__main__":
    main()
