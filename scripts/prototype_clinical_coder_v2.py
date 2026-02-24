"""Hybrid clinical coder prototype with confidence gating and LLM fallback."""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from neo4j import GraphDatabase
from neo4j.exceptions import ClientError

try:  # pragma: no cover
    import boto3
except Exception:  # pragma: no cover
    boto3 = None

from embedding_utils import TextEmbedder, load_vector_settings

LOGGER = logging.getLogger("prototype_clinical_coder")

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "services" / "terminology" / "data" / "training" / "surface_forms_4202301609.jsonl"
DEFAULT_OUTPUT = ROOT / "services" / "terminology" / "data" / "training" / "surface_forms_4202301609.prototype_coding.jsonl"
DEFAULT_REPORT = ROOT / "services" / "terminology" / "data" / "training" / "surface_forms_4202301609.prototype_report.json"
DEFAULT_LOW_CONF = ROOT / "services" / "terminology" / "data" / "training" / "surface_forms_4202301609.prototype_low_confidence.jsonl"

READ_CODE_RE = re.compile(r"\b[A-Za-z0-9.]{4,8}\b")
PUNCT_RE = re.compile(r"[^a-z0-9 ]+")
SPACE_RE = re.compile(r"\s+")
TOKEN_RE = re.compile(r"[a-z0-9]+")

EXACT_QUERY = """
MATCH (t:Term {normalized_form: $normalized})-[:DESCRIBES]->(c:Concept)
WHERE c.active = true
OPTIONAL MATCH (c)-[:MAPS_TO_READ]->(rd:ReadCode)
WITH c, collect(rd.code) AS read_codes
RETURN c.id AS concept_id, c.fsn AS fsn, c.semantic_tag AS semantic_tag, read_codes, 1.0 AS score
LIMIT $k
"""
FULLTEXT_QUERY = """
CALL db.index.fulltext.queryNodes("term_fulltext", $ft_query) YIELD node, score
MATCH (node)-[:DESCRIBES]->(c:Concept)
WHERE c.active = true
OPTIONAL MATCH (c)-[:MAPS_TO_READ]->(rd:ReadCode)
WITH c, max(score) AS best_score, collect(rd.code) AS read_codes
RETURN c.id AS concept_id, c.fsn AS fsn, c.semantic_tag AS semantic_tag, read_codes, best_score AS score
ORDER BY best_score DESC LIMIT $k
"""
VECTOR_QUERY = """
CALL db.index.vector.queryNodes($index_name, $k, $embedding) YIELD node, score
MATCH (node)-[:DESCRIBES]->(c:Concept)
WHERE c.active = true
OPTIONAL MATCH (c)-[:MAPS_TO_READ]->(rd:ReadCode)
WITH c, max(score) AS best_score, collect(rd.code) AS read_codes
RETURN c.id AS concept_id, c.fsn AS fsn, c.semantic_tag AS semantic_tag, read_codes, best_score AS score
ORDER BY best_score DESC LIMIT $k
"""


@dataclass
class Stats:
    rows: int = 0
    entities: int = 0
    mapped_entities: int = 0
    no_candidate: int = 0
    high_conf: int = 0
    medium_conf: int = 0
    low_conf: int = 0
    hitl_required: int = 0
    llm_invoked: int = 0
    llm_accepted: int = 0
    read_code_in_sentence: int = 0
    read_map_hit_top1: int = 0

    def as_dict(self) -> dict[str, Any]:
        hit_rate = self.read_map_hit_top1 / self.read_code_in_sentence if self.read_code_in_sentence else 0.0
        return {
            "rows": self.rows,
            "entities": self.entities,
            "mapped_entities": self.mapped_entities,
            "no_candidate": self.no_candidate,
            "high_conf": self.high_conf,
            "medium_conf": self.medium_conf,
            "low_conf": self.low_conf,
            "hitl_required": self.hitl_required,
            "llm_invoked": self.llm_invoked,
            "llm_accepted": self.llm_accepted,
            "read_code_in_sentence": self.read_code_in_sentence,
            "read_map_hit_top1": self.read_map_hit_top1,
            "read_map_hit_rate": round(hit_rate, 4),
        }


def normalize(text: str) -> str:
    return SPACE_RE.sub(" ", PUNCT_RE.sub(" ", text.lower().strip())).strip()


def build_fulltext_queries(mention: str) -> list[str]:
    escaped = "".join(f"\\{c}" if c in r'+-!(){}[]^"~*?:\/' else c for c in mention.strip())
    if not escaped:
        return []
    tokens = TOKEN_RE.findall(normalize(mention))
    token_q = " AND ".join(tokens)
    return [escaped] + ([token_q] if token_q and token_q != escaped else [])


def load_neo4j_config() -> tuple[str, str, str]:
    load_dotenv(ROOT / "secrets" / ".env")
    uri = os.environ.get("CODING_GRAPH_NEO4J_URI", "")
    user = os.environ.get("CODING_GRAPH_NEO4J_USERNAME", "")
    password = os.environ.get("CODING_GRAPH_NEO4J_PASSWORD", "")
    if not all([uri, user, password]):
        raise RuntimeError("Missing Neo4j env vars in secrets/.env")
    return uri, user, password


def _parse_json_object(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        return json.loads(m.group(0)) if m else {}


def _fetch(session, mention: str, normalized: str, args, embedding: list[float] | None) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}

    def push(rec: dict[str, Any], branch: str) -> None:
        cid = rec["concept_id"]
        base = merged.setdefault(
            cid,
            {
                "concept_id": cid,
                "fsn": rec.get("fsn"),
                "semantic_tag": rec.get("semantic_tag"),
                "read_codes": sorted(set(rec.get("read_codes", []))),
                "lexical_raw": 0.0,
                "vector_raw": 0.0,
            },
        )
        if branch == "lexical":
            base["lexical_raw"] = max(base["lexical_raw"], float(rec.get("score", 0.0)))
        if branch == "vector":
            base["vector_raw"] = max(base["vector_raw"], float(rec.get("score", 0.0)))

    for rec in session.run(EXACT_QUERY, normalized=normalized, k=args.k_exact):
        push(dict(rec), "lexical")
    for q in build_fulltext_queries(mention):
        try:
            for rec in session.run(FULLTEXT_QUERY, ft_query=q, k=args.k_fulltext):
                push(dict(rec), "lexical")
        except ClientError:
            continue
    if args.mode == "hybrid" and embedding:
        try:
            for rec in session.run(VECTOR_QUERY, index_name=args.vector_index_name, k=args.k_vector, embedding=embedding):
                push(dict(rec), "vector")
        except ClientError:
            pass

    if not merged:
        return []
    max_lex = max(v["lexical_raw"] for v in merged.values()) or 1.0
    max_vec = max(v["vector_raw"] for v in merged.values()) or 1.0
    out = []
    for c in merged.values():
        c["lexical_norm"] = c["lexical_raw"] / max_lex if max_lex else 0.0
        c["vector_norm"] = c["vector_raw"] / max_vec if max_vec else 0.0
        out.append(c)
    return out


def _band(scored: list[dict[str, Any]]) -> tuple[str, list[str]]:
    if not scored:
        return "no_candidate", ["no_candidates"]
    top = scored[0]["score"]
    second = scored[1]["score"] if len(scored) > 1 else 0.0
    margin = top - second
    reasons = []
    if margin < 0.15:
        reasons.append("weak_margin")
    if top < 0.60:
        reasons.append("low_top_score")
    if top >= 1.25 and margin >= 0.25:
        return "high", reasons
    if top >= 0.85 and margin >= 0.12:
        return "medium", reasons
    return "low", reasons or ["low_confidence"]


def _llm_choose(model_id: str, region: str, sentence: str, mention: str, modifiers: dict[str, Any], candidates: list[dict[str, Any]]) -> tuple[str | None, float | None, str]:
    if boto3 is None:  # pragma: no cover
        return None, None, "boto3_not_available"
    client = boto3.client("bedrock-runtime", region_name=region)
    prompt = (
        "Choose one concept_id from candidates, or NONE. Do not invent IDs.\n"
        "Return strict JSON: {\"selected_concept_id\":\"...|NONE\",\"confidence\":0-1,\"reason\":\"...\"}.\n\n"
        f"Sentence: {sentence}\nMention: {mention}\nModifiers: {json.dumps(modifiers)}\n"
        f"Candidates: {json.dumps([{'concept_id': c['concept_id'], 'fsn': c.get('fsn'), 'semantic_tag': c.get('semantic_tag')} for c in candidates])}"
    )
    resp = client.converse(
        modelId=model_id,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"temperature": 0.0, "maxTokens": 250},
    )
    content = resp.get("output", {}).get("message", {}).get("content", [])
    text = "\n".join(str(part.get("text", "")) for part in content if isinstance(part, dict)).strip()
    parsed = _parse_json_object(text)
    cid = str(parsed.get("selected_concept_id", "")).strip()
    if not cid or cid.upper() == "NONE":
        return None, None, text
    conf = parsed.get("confidence")
    return cid, float(conf) if isinstance(conf, (int, float)) else None, text


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    p.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    p.add_argument("--low-confidence-output", type=Path, default=DEFAULT_LOW_CONF)
    p.add_argument("--mode", choices=("lexical", "hybrid"), default="hybrid")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--k-exact", type=int, default=30)
    p.add_argument("--k-fulltext", type=int, default=40)
    p.add_argument("--k-vector", type=int, default=40)
    p.add_argument("--top-k-out", type=int, default=5)
    p.add_argument("--vector-index-name", default="term_embedding_idx")
    p.add_argument("--w-lexical", type=float, default=0.6)
    p.add_argument("--w-vector", type=float, default=0.4)
    p.add_argument("--use-llm-fallback", action="store_true")
    p.add_argument("--llm-model-env", default="AWS_SMALL_MODEL")
    p.add_argument("--llm-region", default=os.environ.get("AWS_DEFAULT_REGION", "eu-west-2"))
    p.add_argument("--llm-confidence-threshold", type=float, default=0.70)
    p.add_argument("--log-every", type=int, default=25)
    p.add_argument("--verbose", action="store_true")
    return p.parse_args()


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
        datefmt="%H:%M:%S",
    )


def main() -> None:
    args = parse_args()
    _configure_logging(args.verbose)
    run_started = time.monotonic()
    LOGGER.info("Starting prototype run")
    LOGGER.info(
        "Config: mode=%s input=%s top_k=%s llm_fallback=%s",
        args.mode,
        args.input,
        args.top_k_out,
        args.use_llm_fallback,
    )

    uri, user, password = load_neo4j_config()
    driver = GraphDatabase.driver(uri, auth=(user, password))
    stats = Stats()
    results: list[dict[str, Any]] = []
    low_conf_rows: list[dict[str, Any]] = []

    llm_model_id = ""
    if args.use_llm_fallback:
        load_dotenv(ROOT / "secrets" / ".env")
        llm_model_id = os.environ.get(args.llm_model_env, "").strip()
        if not llm_model_id:
            raise RuntimeError(f"Missing env var {args.llm_model_env}")
        LOGGER.info("LLM fallback enabled via env var %s", args.llm_model_env)

    embedder = TextEmbedder(load_vector_settings()) if args.mode == "hybrid" else None
    if embedder is not None:
        LOGGER.info("Hybrid mode embedding model ready")

    try:
        with driver.session() as session, args.input.open("r", encoding="utf-8") as handle:
            for i, line in enumerate(handle, start=1):
                if args.limit is not None and i > args.limit:
                    break
                row = json.loads(line)
                sentence = str(row.get("sentence", "")).strip()
                entities = row.get("entities") or []
                if not isinstance(entities, list):
                    continue
                stats.rows += 1
                sent_codes = {t for t in READ_CODE_RE.findall(sentence) if any(ch.isdigit() for ch in t)}
                if sent_codes:
                    stats.read_code_in_sentence += 1
                sent_result = {"date": row.get("date"), "sentence": sentence, "entity_results": []}

                for entity in entities:
                    stats.entities += 1
                    mention = str(entity.get("text", "")).strip()
                    embedding = embedder.encode([mention])[0] if (embedder and mention) else None
                    raw = _fetch(session, mention, normalize(mention), args, embedding)
                    scored = []
                    for c in raw:
                        score = (args.w_lexical * c["lexical_norm"]) + (args.w_vector * c["vector_norm"])
                        scored.append(
                            {
                                "concept_id": c["concept_id"],
                                "fsn": c.get("fsn"),
                                "semantic_tag": c.get("semantic_tag"),
                                "read_codes": c.get("read_codes", []),
                                "lexical_norm": round(c["lexical_norm"], 6),
                                "vector_norm": round(c["vector_norm"], 6),
                                "score": round(score, 6),
                            }
                        )
                    scored.sort(key=lambda x: x["score"], reverse=True)
                    selected = scored[0] if scored else None
                    band, reasons = _band(scored)
                    modifiers = {
                        "clinical_status": entity.get("clinical_status"),
                        "negation": entity.get("negation"),
                        "uncertainty": entity.get("uncertainty"),
                        "temporal": entity.get("temporal"),
                        "attributes": entity.get("attributes"),
                    }
                    llm_meta = None
                    llm_accepted = False
                    if args.use_llm_fallback and band in {"low", "no_candidate"} and scored:
                        stats.llm_invoked += 1
                        try:
                            llm_choice, llm_conf, llm_raw = _llm_choose(
                                llm_model_id,
                                args.llm_region,
                                sentence,
                                mention,
                                modifiers,
                                scored[: args.top_k_out],
                            )
                        except Exception as exc:  # pragma: no cover - runtime/network path
                            LOGGER.warning("LLM fallback error for mention '%s': %s", mention, exc)
                            llm_choice, llm_conf, llm_raw = None, None, str(exc)
                        candidate_ids = {c["concept_id"] for c in scored[: args.top_k_out]}
                        if llm_choice in candidate_ids and (llm_conf or 0.0) >= args.llm_confidence_threshold:
                            selected = next(c for c in scored if c["concept_id"] == llm_choice)
                            band = "medium"
                            reasons.append("llm_fallback_accept")
                            llm_accepted = True
                            stats.llm_accepted += 1
                        llm_meta = {"selected_concept_id": llm_choice, "confidence": llm_conf, "accepted": llm_accepted, "raw_response": llm_raw}

                    requires_hitl = band in {"low", "no_candidate"}
                    er = {
                        "mention": mention,
                        "mention_type": entity.get("type"),
                        "expected_semantic_tag": entity.get("snomed_semantic_tag"),
                        "modifiers": modifiers,
                        "sentence_read_codes": sorted(sent_codes),
                        "selected": selected,
                        "confidence_band": band,
                        "confidence_reasons": reasons,
                        "requires_hitl": requires_hitl,
                        "decision_source": "llm_fallback" if llm_accepted else "retrieval",
                        "candidates": scored[: args.top_k_out],
                    }
                    if llm_meta:
                        er["llm_fallback"] = llm_meta
                    if not scored:
                        stats.no_candidate += 1
                    else:
                        stats.mapped_entities += 1
                        top_codes = set((selected or {}).get("read_codes", []))
                        if sent_codes & top_codes:
                            stats.read_map_hit_top1 += 1
                    if band == "high":
                        stats.high_conf += 1
                    elif band == "medium":
                        stats.medium_conf += 1
                    else:
                        stats.low_conf += 1
                    if requires_hitl:
                        stats.hitl_required += 1
                        low_conf_rows.append({"date": row.get("date"), "sentence": sentence, "entity_result": er})
                    sent_result["entity_results"].append(er)
                results.append(sent_result)
                if args.log_every > 0 and stats.rows % args.log_every == 0:
                    elapsed = time.monotonic() - run_started
                    LOGGER.info(
                        "Progress rows=%s entities=%s hitl=%s llm_invoked=%s llm_accepted=%s elapsed=%.1fs",
                        stats.rows,
                        stats.entities,
                        stats.hitl_required,
                        stats.llm_invoked,
                        stats.llm_accepted,
                        elapsed,
                    )
    finally:
        driver.close()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as out:
        for row in results:
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
    with args.low_confidence_output.open("w", encoding="utf-8") as out:
        for row in low_conf_rows:
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
    report = stats.as_dict()
    report["input"] = str(args.input)
    report["output"] = str(args.output)
    report["low_confidence_output"] = str(args.low_confidence_output)
    report["mode"] = args.mode
    report["weights"] = {"lexical": args.w_lexical, "vector": args.w_vector}
    with args.report.open("w", encoding="utf-8") as rep:
        json.dump(report, rep, indent=2)
    LOGGER.info("Completed prototype run in %.1fs", time.monotonic() - run_started)
    LOGGER.info("Output: %s", args.output)
    LOGGER.info("Low-confidence output: %s", args.low_confidence_output)
    LOGGER.info("Report: %s", args.report)
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
