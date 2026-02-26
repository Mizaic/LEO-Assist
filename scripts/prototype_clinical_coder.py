"""Prototype hybrid clinical coder against surface-form JSONL."""

import argparse
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from neo4j import GraphDatabase
from neo4j.exceptions import ClientError

try:  # pragma: no cover - optional runtime dependency
    import boto3
except Exception:  # pragma: no cover
    boto3 = None

from embedding_utils import TextEmbedder, load_vector_settings

if __name__ == "__main__":
    from prototype_clinical_coder_v2 import main as _main

    _main()
    raise SystemExit(0)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = (
    ROOT
    / "services"
    / "terminology"
    / "data"
    / "training"
    / "surface_forms_4202301609.jsonl"
)
DEFAULT_OUTPUT = (
    ROOT
    / "services"
    / "terminology"
    / "data"
    / "training"
    / "surface_forms_4202301609.prototype_coding.jsonl"
)
DEFAULT_REPORT = (
    ROOT
    / "services"
    / "terminology"
    / "data"
    / "training"
    / "surface_forms_4202301609.prototype_report.json"
)
DEFAULT_LOW_CONF = (
    ROOT
    / "services"
    / "terminology"
    / "data"
    / "training"
    / "surface_forms_4202301609.prototype_low_confidence.jsonl"
)

READ_CODE_RE = re.compile(r"\b[A-Za-z0-9.]{4,8}\b")
PUNCT_RE = re.compile(r"[^a-z0-9 ]+")
SPACE_RE = re.compile(r"\s+")
TOKEN_RE = re.compile(r"[a-z0-9]+")

EXACT_QUERY = """
MATCH (t:Term {normalized_form: $normalized})-[:DESCRIBES]->(c:Concept)
WHERE c.active = true
OPTIONAL MATCH (c)-[:MAPS_TO_READ]->(rd:ReadCode)
WITH c, collect(rd.code) AS read_codes
RETURN c.id AS concept_id, c.fsn AS fsn, c.semantic_tag AS semantic_tag,
       read_codes, 1.0 AS score
LIMIT $k
"""

FULLTEXT_QUERY = """
CALL db.index.fulltext.queryNodes("term_fulltext", $ft_query) YIELD node, score
MATCH (node)-[:DESCRIBES]->(c:Concept)
WHERE c.active = true
OPTIONAL MATCH (c)-[:MAPS_TO_READ]->(rd:ReadCode)
WITH c, max(score) AS best_score, collect(rd.code) AS read_codes
RETURN c.id AS concept_id, c.fsn AS fsn, c.semantic_tag AS semantic_tag,
       read_codes, best_score AS score
ORDER BY best_score DESC
LIMIT $k
"""

VECTOR_QUERY = """
CALL db.index.vector.queryNodes($index_name, $k, $embedding) YIELD node, score
MATCH (node)-[:DESCRIBES]->(c:Concept)
WHERE c.active = true
OPTIONAL MATCH (c)-[:MAPS_TO_READ]->(rd:ReadCode)
WITH c, max(score) AS best_score, collect(rd.code) AS read_codes
RETURN c.id AS concept_id, c.fsn AS fsn, c.semantic_tag AS semantic_tag,
       read_codes, best_score AS score
ORDER BY best_score DESC
LIMIT $k
"""


@dataclass
class PrototypeStats:
    rows: int = 0
    entities: int = 0
    mapped_entities: int = 0
    no_candidate: int = 0
    high_conf: int = 0
    medium_conf: int = 0
    low_conf: int = 0
    hitl_required: int = 0
    read_code_in_sentence: int = 0
    read_map_hit_top1: int = 0
    llm_invoked: int = 0
    llm_accepted: int = 0

    def as_dict(self) -> dict[str, Any]:
        read_hit_rate = (
            self.read_map_hit_top1 / self.read_code_in_sentence
            if self.read_code_in_sentence
            else 0.0
        )
        return {
            "rows": self.rows,
            "entities": self.entities,
            "mapped_entities": self.mapped_entities,
            "no_candidate": self.no_candidate,
            "high_conf": self.high_conf,
            "medium_conf": self.medium_conf,
            "low_conf": self.low_conf,
            "hitl_required": self.hitl_required,
            "read_code_in_sentence": self.read_code_in_sentence,
            "read_map_hit_top1": self.read_map_hit_top1,
            "read_map_hit_rate": round(read_hit_rate, 4),
            "llm_invoked": self.llm_invoked,
            "llm_accepted": self.llm_accepted,
        }


def normalize(text: str) -> str:
    x = text.lower().strip()
    x = PUNCT_RE.sub(" ", x)
    x = SPACE_RE.sub(" ", x)
    return x.strip()


def escape_lucene(text: str) -> str:
    escaped = []
    for ch in text:
        if ch in r'+-!(){}[]^"~*?:\/':
            escaped.append("\\")
        escaped.append(ch)
    return "".join(escaped)


def build_fulltext_queries(mention: str) -> list[str]:
    cleaned = mention.strip()
    if not cleaned:
        return []
    queries = [escape_lucene(cleaned)]
    tokens = TOKEN_RE.findall(normalize(cleaned))
    if tokens:
        token_q = " AND ".join(tokens)
        if token_q not in queries:
            queries.append(token_q)
    return queries


def load_neo4j_config() -> tuple[str, str, str]:
    load_dotenv(ROOT / "secrets" / ".env")
    uri = os.environ.get("KNOWLEDGE_GRAPH_NEO4J_URI", "")
    user = os.environ.get("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "")
    password = os.environ.get("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "")
    if not all([uri, user, password]):
        raise RuntimeError("Missing Neo4j env vars in secrets/.env")
    return uri, user, password


def extract_read_codes(sentence: str) -> set[str]:
    codes: set[str] = set()
    for token in READ_CODE_RE.findall(sentence):
        if any(ch.isdigit() for ch in token) and len(token) >= 4:
            codes.add(token)
    return codes


def concept_type_hint(sentence: str, entity_type: str) -> str | None:
    s = sentence.lower()
    if entity_type in {"referral", "intervention"}:
        return "procedure"
    if entity_type in {"symptom", "sign"}:
        return "finding"
    if entity_type in {"diagnosis"}:
        return "disorder"
    if "refer" in s or "vaccin" in s or "surgery" in s:
        return "procedure"
    if "pain" in s or "swelling" in s:
        return "finding"
    return None


def semantic_tag_match(expected_tag: str | None, actual_tag: str | None) -> bool:
    if not expected_tag or not actual_tag:
        return False
    return expected_tag.lower().strip() == actual_tag.lower().strip()


def _merge_candidate(
    sink: dict[str, dict[str, Any]], rec: dict[str, Any], branch: str
) -> None:
    cid = rec["concept_id"]
    if cid not in sink:
        sink[cid] = {
            "concept_id": cid,
            "fsn": rec.get("fsn"),
            "semantic_tag": rec.get("semantic_tag"),
            "read_codes": sorted(set(rec.get("read_codes", []))),
            "lexical_raw": 0.0,
            "vector_raw": 0.0,
        }
    if branch == "lexical":
        sink[cid]["lexical_raw"] = max(sink[cid]["lexical_raw"], float(rec["score"]))
    if branch == "vector":
        sink[cid]["vector_raw"] = max(sink[cid]["vector_raw"], float(rec["score"]))


def fetch_candidates(
    session,
    mention: str,
    normalized: str,
    mode: str,
    k_exact: int,
    k_fulltext: int,
    k_vector: int,
    vector_index_name: str,
    mention_embedding: list[float] | None,
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for rec in session.run(EXACT_QUERY, normalized=normalized, k=k_exact):
        _merge_candidate(merged, dict(rec), "lexical")

    for ft_query in build_fulltext_queries(mention):
        try:
            for rec in session.run(FULLTEXT_QUERY, ft_query=ft_query, k=k_fulltext):
                _merge_candidate(merged, dict(rec), "lexical")
        except ClientError:
            continue

    if mode == "hybrid" and mention_embedding:
        try:
            for rec in session.run(
                VECTOR_QUERY,
                index_name=vector_index_name,
                k=k_vector,
                embedding=mention_embedding,
            ):
                _merge_candidate(merged, dict(rec), "vector")
        except ClientError:
            pass

    if not merged:
        return []
    max_lex = max(v["lexical_raw"] for v in merged.values()) or 1.0
    max_vec = max(v["vector_raw"] for v in merged.values()) or 1.0
    out = []
    for c in merged.values():
        c["lexical_norm"] = c["lexical_raw"] / max_lex if max_lex > 0 else 0.0
        c["vector_norm"] = c["vector_raw"] / max_vec if max_vec > 0 else 0.0
        out.append(c)
    return out


def score_candidate(
    candidate: dict[str, Any],
    sentence: str,
    entity: dict[str, Any],
    sentence_read_codes: set[str],
    w_lexical: float,
    w_vector: float,
) -> float:
    score = (w_lexical * candidate["lexical_norm"]) + (w_vector * candidate["vector_norm"])
    expected_tag = entity.get("snomed_semantic_tag")
    actual_tag = candidate.get("semantic_tag")
    if semantic_tag_match(
        str(expected_tag) if expected_tag is not None else None,
        str(actual_tag) if actual_tag is not None else None,
    ):
        score += 0.2
    hint = concept_type_hint(sentence, str(entity.get("type", "")).lower())
    if hint and actual_tag and hint == str(actual_tag).lower():
        score += 0.15
    read_codes = set(str(x) for x in candidate.get("read_codes", []) if x)
    if sentence_read_codes and (sentence_read_codes & read_codes):
        score += 1.5
    return score


def confidence_from_rank(scored: list[dict[str, Any]]) -> tuple[str, list[str]]:
    if not scored:
        return "no_candidate", ["no_candidates"]
    top = scored[0]["score"]
    second = scored[1]["score"] if len(scored) > 1 else 0.0
    margin = top - second
    reasons: list[str] = []
    if margin < 0.15:
        reasons.append("weak_margin")
    if top < 0.60:
        reasons.append("low_top_score")
    if top >= 1.25 and margin >= 0.25:
        return "high", reasons
    if top >= 0.85 and margin >= 0.12:
        return "medium", reasons
    return "low", reasons or ["low_confidence"]


def _parse_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return {}
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return {}


def llm_disambiguate(
    model_id: str,
    region: str,
    sentence: str,
    mention: str,
    modifiers: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> tuple[str | None, float | None, str]:
    if boto3 is None:  # pragma: no cover
        return None, None, "boto3_not_available"
    client = boto3.client("bedrock-runtime", region_name=region)
    candidate_payload = [
        {
            "concept_id": c.get("concept_id"),
            "fsn": c.get("fsn"),
            "semantic_tag": c.get("semantic_tag"),
        }
        for c in candidates
    ]
    prompt = (
        "Choose one concept_id from candidates or NONE.\n"
        "Do not invent concept IDs.\n"
        "Return strict JSON: {\"selected_concept_id\":\"...|NONE\",\"confidence\":0-1,\"reason\":\"...\"}.\n\n"
        f"Sentence: {sentence}\nMention: {mention}\n"
        f"Modifiers: {json.dumps(modifiers)}\n"
        f"Candidates: {json.dumps(candidate_payload)}"
    )
    resp = client.converse(
        modelId=model_id,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"temperature": 0.0, "maxTokens": 250},
    )
    content = resp.get("output", {}).get("message", {}).get("content", [])
    text = "\n".join(str(part.get("text", "")) for part in content if isinstance(part, dict)).strip()
    parsed = _parse_json_object(text)
    concept_id = str(parsed.get("selected_concept_id", "")).strip()
    if not concept_id or concept_id.upper() == "NONE":
        return None, None, text
    conf = parsed.get("confidence")
    conf_val = float(conf) if isinstance(conf, (int, float)) else None
    return concept_id, conf_val, text


def build_entity_result(
    session,
    sentence: str,
    entity: dict[str, Any],
    args: argparse.Namespace,
    mention_embedding: list[float] | None,
    llm_model_id: str,
) -> tuple[dict[str, Any], bool, bool]:
    mention = str(entity.get("text", "")).strip()
    normalized = normalize(mention)
    sentence_read_codes = extract_read_codes(sentence)
    raw_candidates = fetch_candidates(
        session,
        mention,
        normalized,
        args.mode,
        args.k_exact,
        args.k_fulltext,
        args.k_vector,
        args.vector_index_name,
        mention_embedding,
    )
    scored = []
    for c in raw_candidates:
        scored.append(
            {
                "concept_id": c["concept_id"],
                "fsn": c.get("fsn"),
                "semantic_tag": c.get("semantic_tag"),
                "read_codes": c.get("read_codes", []),
                "lexical_norm": round(c["lexical_norm"], 6),
                "vector_norm": round(c["vector_norm"], 6),
                "score": round(
                    score_candidate(
                        c,
                        sentence,
                        entity,
                        sentence_read_codes,
                        args.w_lexical,
                        args.w_vector,
                    ),
                    6,
                ),
            }
        )
    scored.sort(key=lambda x: x["score"], reverse=True)
    selected = scored[0] if scored else None
    confidence_band, reasons = confidence_from_rank(scored)
    used_llm = False
    llm_accepted = False

    modifiers = {
        "clinical_status": entity.get("clinical_status"),
        "negation": entity.get("negation"),
        "uncertainty": entity.get("uncertainty"),
        "temporal": entity.get("temporal"),
        "attributes": entity.get("attributes"),
    }
    llm_meta: dict[str, Any] | None = None
    if args.use_llm_fallback and confidence_band in {"low", "no_candidate"} and scored:
        used_llm = True
        llm_choice, llm_conf, llm_raw = llm_disambiguate(
            llm_model_id, args.llm_region, sentence, mention, modifiers, scored[: args.top_k_out]
        )
        candidate_ids = {c["concept_id"] for c in scored[: args.top_k_out]}
        if llm_choice in candidate_ids and (llm_conf or 0.0) >= args.llm_confidence_threshold:
            selected = next(c for c in scored if c["concept_id"] == llm_choice)
            confidence_band = "medium"
            reasons.append("llm_fallback_accept")
            llm_accepted = True
        llm_meta = {
            "selected_concept_id": llm_choice,
            "confidence": llm_conf,
            "accepted": llm_accepted,
            "raw_response": llm_raw,
        }

    requires_hitl = confidence_band in {"low", "no_candidate"}
    result = {
        "mention": mention,
        "mention_type": entity.get("type"),
        "expected_semantic_tag": entity.get("snomed_semantic_tag"),
        "modifiers": modifiers,
        "sentence_read_codes": sorted(sentence_read_codes),
        "selected": selected,
        "confidence_band": confidence_band,
        "confidence_reasons": reasons,
        "requires_hitl": requires_hitl,
        "decision_source": "llm_fallback" if llm_accepted else "retrieval",
        "candidates": scored[: args.top_k_out],
    }
    if llm_meta:
        result["llm_fallback"] = llm_meta
    return result, used_llm, llm_accepted


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--low-confidence-output", type=Path, default=DEFAULT_LOW_CONF)
    parser.add_argument("--mode", choices=("lexical", "hybrid"), default="hybrid")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--k-exact", type=int, default=30)
    parser.add_argument("--k-fulltext", type=int, default=40)
    parser.add_argument("--k-vector", type=int, default=40)
    parser.add_argument("--top-k-out", type=int, default=5)
    parser.add_argument("--vector-index-name", default="term_embedding_idx")
    parser.add_argument("--w-lexical", type=float, default=0.6)
    parser.add_argument("--w-vector", type=float, default=0.4)
    parser.add_argument("--use-llm-fallback", action="store_true")
    parser.add_argument("--llm-model-env", default="AWS_SMALL_MODEL")
    parser.add_argument("--llm-region", default=os.environ.get("AWS_DEFAULT_REGION", "eu-west-2"))
    parser.add_argument("--llm-confidence-threshold", type=float, default=0.70)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    uri, user, password = load_neo4j_config()
    driver = GraphDatabase.driver(uri, auth=(user, password))
    stats = PrototypeStats()
    results: list[dict[str, Any]] = []
    low_conf_rows: list[dict[str, Any]] = []

    llm_model_id = ""
    if args.use_llm_fallback:
        load_dotenv(ROOT / "secrets" / ".env")
        llm_model_id = os.environ.get(args.llm_model_env, "").strip()
        if not llm_model_id:
            raise RuntimeError(f"Missing env var {args.llm_model_env} for LLM fallback")

    embedder = None
    if args.mode == "hybrid":
        embedder = TextEmbedder(load_vector_settings())

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
                sentence_result = {"date": row.get("date"), "sentence": sentence, "entity_results": []}
                sentence_codes = extract_read_codes(sentence)
                if sentence_codes:
                    stats.read_code_in_sentence += 1

                for entity in entities:
                    stats.entities += 1
                    mention = str(entity.get("text", "")).strip()
                    mention_embedding = None
                    if args.mode == "hybrid" and embedder and mention:
                        mention_embedding = embedder.encode([mention])[0]
                    er, used_llm, llm_accepted = build_entity_result(
                        session, sentence, entity, args, mention_embedding, llm_model_id
                    )
                    if used_llm:
                        stats.llm_invoked += 1
                    if llm_accepted:
                        stats.llm_accepted += 1
                    if not er["candidates"]:
                        stats.no_candidate += 1
                    else:
                        stats.mapped_entities += 1
                        top_codes = set((er["selected"] or {}).get("read_codes", []))
                        if sentence_codes and (sentence_codes & top_codes):
                            stats.read_map_hit_top1 += 1
                    if er["confidence_band"] == "high":
                        stats.high_conf += 1
                    elif er["confidence_band"] == "medium":
                        stats.medium_conf += 1
                    else:
                        stats.low_conf += 1
                    if er["requires_hitl"]:
                        stats.hitl_required += 1
                        low_conf_rows.append({"date": row.get("date"), "sentence": sentence, "entity_result": er})
                    sentence_result["entity_results"].append(er)
                results.append(sentence_result)
                if stats.rows % 50 == 0:
                    print(f"Processed {stats.rows} rows...")
    finally:
        driver.close()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as out:
        for row in results:
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
    with args.low_confidence_output.open("w", encoding="utf-8") as low_out:
        for row in low_conf_rows:
            low_out.write(json.dumps(row, ensure_ascii=False) + "\n")

    report = stats.as_dict()
    report["input"] = str(args.input)
    report["output"] = str(args.output)
    report["low_confidence_output"] = str(args.low_confidence_output)
    report["mode"] = args.mode
    report["weights"] = {"lexical": args.w_lexical, "vector": args.w_vector}
    report["notes"] = [
        "Semantic tag is a weak prior only.",
        "Context modifiers are preserved from source labels.",
        "Traversal remains bounded to retrieval + shallow scoring features.",
    ]
    with args.report.open("w", encoding="utf-8") as rep:
        json.dump(report, rep, indent=2)
    print("Prototype complete.")
    print(json.dumps(report, indent=2))


if False and __name__ == "__main__":
    main()
"""Prototype hybrid clinical coder against surface-form JSONL.

Pipeline:
1) lexical retrieval (exact + fulltext)
2) optional vector retrieval
3) branch-score normalization and weighted fusion
4) clinical rerank + confidence banding
5) optional constrained LLM fallback for low/no-candidate
6) HITL flagging for unresolved cases

Context modifiers are preserved from source labels and never overwritten.
"""

import argparse
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from neo4j import GraphDatabase
from neo4j.exceptions import ClientError

try:  # pragma: no cover - optional runtime dependency
    import boto3
except Exception:  # pragma: no cover
    boto3 = None

from embedding_utils import TextEmbedder, load_vector_settings


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = (
    ROOT
    / "services"
    / "terminology"
    / "data"
    / "training"
    / "surface_forms_4202301609.jsonl"
)
DEFAULT_OUTPUT = (
    ROOT
    / "services"
    / "terminology"
    / "data"
    / "training"
    / "surface_forms_4202301609.prototype_coding.jsonl"
)
DEFAULT_REPORT = (
    ROOT
    / "services"
    / "terminology"
    / "data"
    / "training"
    / "surface_forms_4202301609.prototype_report.json"
)
DEFAULT_LOW_CONF = (
    ROOT
    / "services"
    / "terminology"
    / "data"
    / "training"
    / "surface_forms_4202301609.prototype_low_confidence.jsonl"
)

READ_CODE_RE = re.compile(r"\b[A-Za-z0-9.]{4,8}\b")
PUNCT_RE = re.compile(r"[^a-z0-9 ]+")
SPACE_RE = re.compile(r"\s+")
TOKEN_RE = re.compile(r"[a-z0-9]+")

EXACT_QUERY = """
MATCH (t:Term {normalized_form: $normalized})-[:DESCRIBES]->(c:Concept)
WHERE c.active = true
OPTIONAL MATCH (c)-[:MAPS_TO_READ]->(rd:ReadCode)
WITH c, collect(rd.code) AS read_codes
RETURN c.id AS concept_id, c.fsn AS fsn, c.semantic_tag AS semantic_tag,
       read_codes, 1.0 AS score
LIMIT $k
"""

FULLTEXT_QUERY = """
CALL db.index.fulltext.queryNodes("term_fulltext", $ft_query) YIELD node, score
MATCH (node)-[:DESCRIBES]->(c:Concept)
WHERE c.active = true
OPTIONAL MATCH (c)-[:MAPS_TO_READ]->(rd:ReadCode)
WITH c, max(score) AS best_score, collect(rd.code) AS read_codes
RETURN c.id AS concept_id, c.fsn AS fsn, c.semantic_tag AS semantic_tag,
       read_codes, best_score AS score
ORDER BY best_score DESC
LIMIT $k
"""

VECTOR_QUERY = """
CALL db.index.vector.queryNodes($index_name, $k, $embedding) YIELD node, score
MATCH (node)-[:DESCRIBES]->(c:Concept)
WHERE c.active = true
OPTIONAL MATCH (c)-[:MAPS_TO_READ]->(rd:ReadCode)
WITH c, max(score) AS best_score, collect(rd.code) AS read_codes
RETURN c.id AS concept_id, c.fsn AS fsn, c.semantic_tag AS semantic_tag,
       read_codes, best_score AS score
ORDER BY best_score DESC
LIMIT $k
"""


@dataclass
class PrototypeStats:
    rows: int = 0
    entities: int = 0
    mapped_entities: int = 0
    no_candidate: int = 0
    high_conf: int = 0
    medium_conf: int = 0
    low_conf: int = 0
    hitl_required: int = 0
    read_code_in_sentence: int = 0
    read_map_hit_top1: int = 0
    llm_invoked: int = 0
    llm_accepted: int = 0

    def as_dict(self) -> dict[str, Any]:
        read_hit_rate = (
            self.read_map_hit_top1 / self.read_code_in_sentence
            if self.read_code_in_sentence
            else 0.0
        )
        return {
            "rows": self.rows,
            "entities": self.entities,
            "mapped_entities": self.mapped_entities,
            "no_candidate": self.no_candidate,
            "high_conf": self.high_conf,
            "medium_conf": self.medium_conf,
            "low_conf": self.low_conf,
            "hitl_required": self.hitl_required,
            "read_code_in_sentence": self.read_code_in_sentence,
            "read_map_hit_top1": self.read_map_hit_top1,
            "read_map_hit_rate": round(read_hit_rate, 4),
            "llm_invoked": self.llm_invoked,
            "llm_accepted": self.llm_accepted,
        }


def normalize(text: str) -> str:
    x = text.lower().strip()
    x = PUNCT_RE.sub(" ", x)
    x = SPACE_RE.sub(" ", x)
    return x.strip()


def escape_lucene(text: str) -> str:
    escaped = []
    for ch in text:
        if ch in r'+-!(){}[]^"~*?:\/':
            escaped.append("\\")
        escaped.append(ch)
    return "".join(escaped)


def build_fulltext_queries(mention: str) -> list[str]:
    cleaned = mention.strip()
    if not cleaned:
        return []
    queries = [escape_lucene(cleaned)]
    tokens = TOKEN_RE.findall(normalize(cleaned))
    if tokens:
        token_q = " AND ".join(tokens)
        if token_q not in queries:
            queries.append(token_q)
    return queries


def load_neo4j_config() -> tuple[str, str, str]:
    load_dotenv(ROOT / "secrets" / ".env")
    uri = os.environ.get("KNOWLEDGE_GRAPH_NEO4J_URI", "")
    user = os.environ.get("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "")
    password = os.environ.get("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "")
    if not all([uri, user, password]):
        raise RuntimeError("Missing Neo4j env vars in secrets/.env")
    return uri, user, password


def extract_read_codes(sentence: str) -> set[str]:
    codes: set[str] = set()
    for token in READ_CODE_RE.findall(sentence):
        if any(ch.isdigit() for ch in token) and len(token) >= 4:
            codes.add(token)
    return codes


def concept_type_hint(sentence: str, entity_type: str) -> str | None:
    s = sentence.lower()
    if entity_type in {"referral", "intervention"}:
        return "procedure"
    if entity_type in {"symptom", "sign"}:
        return "finding"
    if entity_type in {"diagnosis"}:
        return "disorder"
    if "refer" in s or "vaccin" in s or "surgery" in s:
        return "procedure"
    if "pain" in s or "swelling" in s:
        return "finding"
    return None


def semantic_tag_match(expected_tag: str | None, actual_tag: str | None) -> bool:
    if not expected_tag or not actual_tag:
        return False
    return expected_tag.lower().strip() == actual_tag.lower().strip()


def _merge_candidate(
    sink: dict[str, dict[str, Any]],
    rec: dict[str, Any],
    branch: str,
) -> None:
    cid = rec["concept_id"]
    if cid not in sink:
        sink[cid] = {
            "concept_id": cid,
            "fsn": rec.get("fsn"),
            "semantic_tag": rec.get("semantic_tag"),
            "read_codes": sorted(set(rec.get("read_codes", []))),
            "lexical_raw": 0.0,
            "vector_raw": 0.0,
        }
    if branch == "lexical":
        sink[cid]["lexical_raw"] = max(
            sink[cid]["lexical_raw"], float(rec.get("score", 0.0))
        )
    elif branch == "vector":
        sink[cid]["vector_raw"] = max(
            sink[cid]["vector_raw"], float(rec.get("score", 0.0))
        )


def fetch_candidates(
    session,
    mention: str,
    normalized: str,
    mode: str,
    k_exact: int,
    k_fulltext: int,
    k_vector: int,
    vector_index_name: str,
    mention_embedding: list[float] | None,
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}

    for rec in session.run(EXACT_QUERY, normalized=normalized, k=k_exact):
        _merge_candidate(merged, dict(rec), "lexical")

    for ft_query in build_fulltext_queries(mention):
        try:
            for rec in session.run(FULLTEXT_QUERY, ft_query=ft_query, k=k_fulltext):
                _merge_candidate(merged, dict(rec), "lexical")
        except ClientError:
            continue

    if mode == "hybrid" and mention_embedding:
        try:
            vec_rows = session.run(
                VECTOR_QUERY,
                index_name=vector_index_name,
                k=k_vector,
                embedding=mention_embedding,
            )
            for rec in vec_rows:
                _merge_candidate(merged, dict(rec), "vector")
        except ClientError:
            pass

    if not merged:
        return []

    max_lex = max(v["lexical_raw"] for v in merged.values()) or 1.0
    max_vec = max(v["vector_raw"] for v in merged.values()) or 1.0
    out = []
    for c in merged.values():
        c["lexical_norm"] = c["lexical_raw"] / max_lex if max_lex > 0 else 0.0
        c["vector_norm"] = c["vector_raw"] / max_vec if max_vec > 0 else 0.0
        out.append(c)
    return out


def score_candidate(
    candidate: dict[str, Any],
    sentence: str,
    entity: dict[str, Any],
    sentence_read_codes: set[str],
    w_lexical: float,
    w_vector: float,
) -> float:
    fused = (w_lexical * candidate["lexical_norm"]) + (
        w_vector * candidate["vector_norm"]
    )
    score = fused

    expected_tag = entity.get("snomed_semantic_tag")
    actual_tag = candidate.get("semantic_tag")
    if semantic_tag_match(
        str(expected_tag) if expected_tag is not None else None,
        str(actual_tag) if actual_tag is not None else None,
    ):
        score += 0.2

    hint = concept_type_hint(sentence, str(entity.get("type", "")).lower())
    if hint and actual_tag and hint == str(actual_tag).lower():
        score += 0.15

    read_codes = set(str(x) for x in candidate.get("read_codes", []) if x)
    if sentence_read_codes and (sentence_read_codes & read_codes):
        score += 1.5

    attrs = entity.get("attributes") or {}
    if isinstance(attrs, dict) and attrs.get("laterality"):
        fsn = str(candidate.get("fsn", "") or "")
        if len(fsn) > 20:
            score += 0.03
    return score


def confidence_from_rank(scored: list[dict[str, Any]]) -> tuple[str, list[str]]:
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


def _parse_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return {}
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return {}


def llm_disambiguate(
    model_id: str,
    region: str,
    sentence: str,
    mention: str,
    modifiers: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> tuple[str | None, float | None, str]:
    if boto3 is None:  # pragma: no cover
        return None, None, "boto3_not_available"
    client = boto3.client("bedrock-runtime", region_name=region)
    candidate_payload = [
        {
            "concept_id": c.get("concept_id"),
            "fsn": c.get("fsn"),
            "semantic_tag": c.get("semantic_tag"),
        }
        for c in candidates
    ]
    prompt = (
        "You are disambiguating SNOMED concept candidates.\n"
        "Choose one concept_id from candidates, or NONE.\n"
        "Do not infer new candidates.\n"
        "Return strict JSON: {\"selected_concept_id\":\"...|NONE\",\"confidence\":0-1,\"reason\":\"...\"}\n\n"
        f"Sentence: {sentence}\n"
        f"Mention: {mention}\n"
        f"Modifiers: {json.dumps(modifiers, ensure_ascii=False)}\n"
        f"Candidates: {json.dumps(candidate_payload, ensure_ascii=False)}"
    )
    resp = client.converse(
        modelId=model_id,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"temperature": 0.0, "maxTokens": 250},
    )
    content = (
        resp.get("output", {})
        .get("message", {})
        .get("content", [])
    )
    text = "\n".join(
        str(part.get("text", "")) for part in content if isinstance(part, dict)
    ).strip()
    parsed = _parse_json_object(text)
    concept_id = str(parsed.get("selected_concept_id", "")).strip()
    if not concept_id or concept_id.upper() == "NONE":
        return None, None, text
    conf = parsed.get("confidence")
    conf_val = float(conf) if isinstance(conf, (int, float)) else None
    return concept_id, conf_val, text


def build_entity_result(
    session,
    sentence: str,
    entity: dict[str, Any],
    mode: str,
    k_exact: int,
    k_fulltext: int,
    k_vector: int,
    top_k_out: int,
    vector_index_name: str,
    mention_embedding: list[float] | None,
    w_lexical: float,
    w_vector: float,
    use_llm_fallback: bool,
    llm_model_id: str,
    llm_region: str,
    llm_conf_threshold: float,
) -> tuple[dict[str, Any], bool, bool]:
    mention = str(entity.get("text", "")).strip()
    normalized = normalize(mention)
    sentence_read_codes = extract_read_codes(sentence)
    raw_candidates = fetch_candidates(
        session=session,
        mention=mention,
        normalized=normalized,
        mode=mode,
        k_exact=k_exact,
        k_fulltext=k_fulltext,
        k_vector=k_vector,
        vector_index_name=vector_index_name,
        mention_embedding=mention_embedding,
    )

    scored = []
    for c in raw_candidates:
        item = {
            "concept_id": c["concept_id"],
            "fsn": c.get("fsn"),
            "semantic_tag": c.get("semantic_tag"),
            "read_codes": c.get("read_codes", []),
            "lexical_norm": round(c["lexical_norm"], 6),
            "vector_norm": round(c["vector_norm"], 6),
        }
        item["score"] = round(
            score_candidate(
                candidate=c,
                sentence=sentence,
                entity=entity,
                sentence_read_codes=sentence_read_codes,
                w_lexical=w_lexical,
                w_vector=w_vector,
            ),
            6,
        )
        scored.append(item)

    scored.sort(key=lambda x: x["score"], reverse=True)
    selected = scored[0] if scored else None
    confidence_band, reasons = confidence_from_rank(scored)
    used_llm = False
    llm_accepted = False

    modifiers = {
        "clinical_status": entity.get("clinical_status"),
        "negation": entity.get("negation"),
        "uncertainty": entity.get("uncertainty"),
        "temporal": entity.get("temporal"),
        "attributes": entity.get("attributes"),
    }

    llm_meta: dict[str, Any] | None = None
    if use_llm_fallback and confidence_band in {"low", "no_candidate"} and scored:
        used_llm = True
        llm_choice, llm_conf, raw = llm_disambiguate(
            model_id=llm_model_id,
            region=llm_region,
            sentence=sentence,
            mention=mention,
            modifiers=modifiers,
            candidates=scored[:top_k_out],
        )
        candidate_ids = {c["concept_id"] for c in scored[:top_k_out]}
        if llm_choice in candidate_ids and (llm_conf or 0.0) >= llm_conf_threshold:
            for c in scored:
                if c["concept_id"] == llm_choice:
                    selected = c
                    confidence_band = "medium"
                    reasons.append("llm_fallback_accept")
                    llm_accepted = True
                    break
        llm_meta = {
            "selected_concept_id": llm_choice,
            "confidence": llm_conf,
            "accepted": llm_accepted,
            "raw_response": raw,
        }

    requires_hitl = confidence_band in {"low", "no_candidate"}
    result = {
        "mention": mention,
        "mention_type": entity.get("type"),
        "expected_semantic_tag": entity.get("snomed_semantic_tag"),
        "modifiers": modifiers,
        "sentence_read_codes": sorted(sentence_read_codes),
        "selected": selected,
        "confidence_band": confidence_band,
        "confidence_reasons": reasons,
        "requires_hitl": requires_hitl,
        "decision_source": "llm_fallback" if llm_accepted else "retrieval",
        "candidates": scored[:top_k_out],
    }
    if llm_meta is not None:
        result["llm_fallback"] = llm_meta
    return result, used_llm, llm_accepted


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--low-confidence-output", type=Path, default=DEFAULT_LOW_CONF)
    parser.add_argument("--mode", choices=("lexical", "hybrid"), default="hybrid")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--k-exact", type=int, default=30)
    parser.add_argument("--k-fulltext", type=int, default=40)
    parser.add_argument("--k-vector", type=int, default=40)
    parser.add_argument("--top-k-out", type=int, default=5)
    parser.add_argument("--vector-index-name", default="term_embedding_idx")
    parser.add_argument("--w-lexical", type=float, default=0.6)
    parser.add_argument("--w-vector", type=float, default=0.4)
    parser.add_argument("--use-llm-fallback", action="store_true")
    parser.add_argument("--llm-model-env", default="AWS_SMALL_MODEL")
    parser.add_argument("--llm-region", default=os.environ.get("AWS_DEFAULT_REGION", "eu-west-2"))
    parser.add_argument("--llm-confidence-threshold", type=float, default=0.70)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    uri, user, password = load_neo4j_config()
    driver = GraphDatabase.driver(uri, auth=(user, password))
    stats = PrototypeStats()
    results: list[dict[str, Any]] = []
    low_conf_rows: list[dict[str, Any]] = []

    llm_model_id = ""
    if args.use_llm_fallback:
        load_dotenv(ROOT / "secrets" / ".env")
        llm_model_id = os.environ.get(args.llm_model_env, "").strip()
        if not llm_model_id:
            raise RuntimeError(
                f"--use-llm-fallback set but env var {args.llm_model_env} is missing"
            )

    embedder = None
    if args.mode == "hybrid":
        vector_settings = load_vector_settings()
        embedder = TextEmbedder(vector_settings)

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
                sentence_result = {
                    "date": row.get("date"),
                    "sentence": sentence,
                    "entity_results": [],
                }
                sentence_codes = extract_read_codes(sentence)
                if sentence_codes:
                    stats.read_code_in_sentence += 1

                for entity in entities:
                    stats.entities += 1
                    mention = str(entity.get("text", "")).strip()
                    mention_embedding = None
                    if args.mode == "hybrid" and embedder is not None and mention:
                        mention_embedding = embedder.encode([mention])[0]

                    er, used_llm, llm_accepted = build_entity_result(
                        session=session,
                        sentence=sentence,
                        entity=entity,
                        mode=args.mode,
                        k_exact=args.k_exact,
                        k_fulltext=args.k_fulltext,
                        k_vector=args.k_vector,
                        top_k_out=args.top_k_out,
                        vector_index_name=args.vector_index_name,
                        mention_embedding=mention_embedding,
                        w_lexical=args.w_lexical,
                        w_vector=args.w_vector,
                        use_llm_fallback=args.use_llm_fallback,
                        llm_model_id=llm_model_id,
                        llm_region=args.llm_region,
                        llm_conf_threshold=args.llm_confidence_threshold,
                    )

                    if used_llm:
                        stats.llm_invoked += 1
                    if llm_accepted:
                        stats.llm_accepted += 1

                    if not er["candidates"]:
                        stats.no_candidate += 1
                    else:
                        stats.mapped_entities += 1
                        top = er["selected"] or {}
                        top_codes = set(top.get("read_codes", []))
                        if sentence_codes and (sentence_codes & top_codes):
                            stats.read_map_hit_top1 += 1

                    band = er["confidence_band"]
                    if band == "high":
                        stats.high_conf += 1
                    elif band == "medium":
                        stats.medium_conf += 1
                    else:
                        stats.low_conf += 1

                    if er["requires_hitl"]:
                        stats.hitl_required += 1
                        low_conf_rows.append(
                            {
                                "date": row.get("date"),
                                "sentence": sentence,
                                "entity_result": er,
                            }
                        )
                    sentence_result["entity_results"].append(er)

                results.append(sentence_result)
                if stats.rows % 50 == 0:
                    print(f"Processed {stats.rows} rows...")
    finally:
        driver.close()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as out:
        for row in results:
            out.write(json.dumps(row, ensure_ascii=False) + "\n")

    with args.low_confidence_output.open("w", encoding="utf-8") as low_out:
        for row in low_conf_rows:
            low_out.write(json.dumps(row, ensure_ascii=False) + "\n")

    report = stats.as_dict()
    report["input"] = str(args.input)
    report["output"] = str(args.output)
    report["low_confidence_output"] = str(args.low_confidence_output)
    report["mode"] = args.mode
    report["weights"] = {"lexical": args.w_lexical, "vector": args.w_vector}
    report["notes"] = [
        "Semantic tag is a weak prior only.",
        "Context modifiers are preserved from source labels.",
        "Traversal remains bounded to retrieval + shallow scoring features.",
    ]
    with args.report.open("w", encoding="utf-8") as rep:
        json.dump(report, rep, indent=2)

    print("Prototype complete.")
    print(json.dumps(report, indent=2))


if False and __name__ == "__main__":
    main()
"""Prototype clinical coder against surface-form training JSONL.

Design goals:
- Hybrid retrieval: exact normalized term + Neo4j fulltext.
- Conservative rerank: semantic tag is a weak prior only.
- Modifier safety: preserve negation/uncertainty/temporality/planned/current/historic
  exactly from input labels; do not overwrite with graph inference.
- Bounded graph use: 0-1 hop features only; no deep traversal.

Outputs:
- JSONL with per-entity coding proposal and preserved modifiers.
- JSON summary with prototype metrics.
"""

import argparse
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from neo4j import GraphDatabase
from neo4j.exceptions import ClientError


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = (
    ROOT
    / "services"
    / "terminology"
    / "data"
    / "training"
    / "surface_forms_4202301609.jsonl"
)
DEFAULT_OUTPUT = (
    ROOT
    / "services"
    / "terminology"
    / "data"
    / "training"
    / "surface_forms_4202301609.prototype_coding.jsonl"
)
DEFAULT_REPORT = (
    ROOT
    / "services"
    / "terminology"
    / "data"
    / "training"
    / "surface_forms_4202301609.prototype_report.json"
)

READ_CODE_RE = re.compile(r"\b[A-Za-z0-9.]{4,8}\b")
PUNCT_RE = re.compile(r"[^a-z0-9 ]+")
SPACE_RE = re.compile(r"\s+")
TOKEN_RE = re.compile(r"[a-z0-9]+")


EXACT_QUERY = """
MATCH (t:Term {normalized_form: $normalized})-[:DESCRIBES]->(c:Concept)
WHERE c.active = true
OPTIONAL MATCH (c)-[:MAPS_TO_READ]->(rd:ReadCode)
WITH c, collect(rd.code) AS read_codes
RETURN c.id AS concept_id,
       c.fsn AS fsn,
       c.semantic_tag AS semantic_tag,
       read_codes,
       1.0 AS retrieval_score,
       "exact" AS retrieval_source
LIMIT $k
"""

FULLTEXT_QUERY = """
CALL db.index.fulltext.queryNodes("term_fulltext", $ft_query) YIELD node, score
MATCH (node)-[:DESCRIBES]->(c:Concept)
WHERE c.active = true
OPTIONAL MATCH (c)-[:MAPS_TO_READ]->(rd:ReadCode)
WITH c, max(score) AS best_score, collect(rd.code) AS read_codes
RETURN c.id AS concept_id,
       c.fsn AS fsn,
       c.semantic_tag AS semantic_tag,
       read_codes,
       best_score AS retrieval_score,
       "fulltext" AS retrieval_source
ORDER BY best_score DESC
LIMIT $k
"""


@dataclass
class PrototypeStats:
    rows: int = 0
    entities: int = 0
    no_candidates: int = 0
    mapped_candidates: int = 0
    read_code_in_sentence: int = 0
    read_map_hit_top1: int = 0

    def as_dict(self) -> dict[str, Any]:
        read_hit_rate = (
            self.read_map_hit_top1 / self.read_code_in_sentence
            if self.read_code_in_sentence
            else 0.0
        )
        return {
            "rows": self.rows,
            "entities": self.entities,
            "no_candidates": self.no_candidates,
            "mapped_candidates": self.mapped_candidates,
            "read_code_in_sentence": self.read_code_in_sentence,
            "read_map_hit_top1": self.read_map_hit_top1,
            "read_map_hit_rate": round(read_hit_rate, 4),
        }


def normalize(text: str) -> str:
    x = text.lower().strip()
    x = PUNCT_RE.sub(" ", x)
    x = SPACE_RE.sub(" ", x)
    return x.strip()


def escape_lucene(text: str) -> str:
    """Escape Lucene query-parser special characters."""
    # Lucene special chars: + - && || ! ( ) { } [ ] ^ " ~ * ? : \ /
    escaped = []
    for ch in text:
        if ch in r'+-!(){}[]^"~*?:\/':
            escaped.append("\\")
        escaped.append(ch)
    return "".join(escaped)


def build_fulltext_queries(mention: str) -> list[str]:
    """Build progressively safer fulltext queries for Neo4j/Lucene."""
    cleaned = mention.strip()
    if not cleaned:
        return []
    q1 = escape_lucene(cleaned)
    tokens = TOKEN_RE.findall(normalize(cleaned))
    token_query = " AND ".join(tokens) if tokens else ""
    queries = [q1]
    if token_query and token_query not in queries:
        queries.append(token_query)
    return queries


def load_neo4j_config() -> tuple[str, str, str]:
    load_dotenv(ROOT / "secrets" / ".env")
    uri = os.environ.get("KNOWLEDGE_GRAPH_NEO4J_URI", "")
    user = os.environ.get("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "")
    password = os.environ.get("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "")
    if not all([uri, user, password]):
        raise RuntimeError("Missing Neo4j env vars in secrets/.env")
    return uri, user, password


def extract_read_codes(sentence: str) -> set[str]:
    codes: set[str] = set()
    for token in READ_CODE_RE.findall(sentence):
        # Keep a conservative code-like shape to avoid random words.
        if any(ch.isdigit() for ch in token) and len(token) >= 4:
            codes.add(token)
    return codes


def concept_type_hint(sentence: str, entity_type: str) -> str | None:
    s = sentence.lower()
    if entity_type in {"referral", "intervention"}:
        return "procedure"
    if entity_type in {"symptom", "sign"}:
        return "finding"
    if entity_type in {"diagnosis"}:
        return "disorder"
    if "refer" in s or "vaccin" in s or "surgery" in s:
        return "procedure"
    if "pain" in s or "swelling" in s:
        return "finding"
    return None


def semantic_tag_match(expected_tag: str | None, actual_tag: str | None) -> bool:
    if not expected_tag or not actual_tag:
        return False
    return expected_tag.lower().strip() == actual_tag.lower().strip()


def score_candidate(
    candidate: dict[str, Any],
    sentence: str,
    entity: dict[str, Any],
    sentence_read_codes: set[str],
) -> float:
    score = float(candidate.get("retrieval_score", 0.0))
    expected_tag = entity.get("snomed_semantic_tag")
    actual_tag = candidate.get("semantic_tag")

    # Semantic tag is useful but often imperfect; keep it weak.
    if semantic_tag_match(
        str(expected_tag) if expected_tag is not None else None,
        str(actual_tag) if actual_tag is not None else None,
    ):
        score += 0.25

    hint = concept_type_hint(sentence, str(entity.get("type", "")).lower())
    if hint and actual_tag and hint == str(actual_tag).lower():
        score += 0.2

    read_codes = set(str(x) for x in candidate.get("read_codes", []) if x)
    if sentence_read_codes and (sentence_read_codes & read_codes):
        score += 2.0

    # If laterality is explicitly present, mild preference for concepts
    # with a longer, likely more specific FSN string.
    attrs = entity.get("attributes") or {}
    if isinstance(attrs, dict) and attrs.get("laterality"):
        fsn = str(candidate.get("fsn", "") or "")
        if len(fsn) > 20:
            score += 0.05

    return score


def fetch_candidates(
    session,
    mention: str,
    normalized: str,
    k_exact: int,
    k_fulltext: int,
) -> list[dict[str, Any]]:
    candidates: dict[str, dict[str, Any]] = {}

    for rec in session.run(EXACT_QUERY, normalized=normalized, k=k_exact):
        cid = rec["concept_id"]
        candidates[cid] = dict(rec)

    for ft_query in build_fulltext_queries(mention):
        try:
            fulltext_rows = session.run(
                FULLTEXT_QUERY, ft_query=ft_query, k=k_fulltext
            )
            for rec in fulltext_rows:
                cid = rec["concept_id"]
                if cid not in candidates:
                    candidates[cid] = dict(rec)
                else:
                    # Keep best retrieval score/source footprint.
                    existing = candidates[cid]
                    if rec["retrieval_score"] > existing.get("retrieval_score", 0):
                        existing["retrieval_score"] = rec["retrieval_score"]
                        existing["retrieval_source"] = "hybrid"
                    codes = set(existing.get("read_codes", [])) | set(
                        rec.get("read_codes", [])
                    )
                    existing["read_codes"] = sorted(codes)
        except ClientError:
            # Fall through to next safer query variant.
            continue

    return list(candidates.values())


def build_entity_result(
    session,
    sentence: str,
    entity: dict[str, Any],
    k_exact: int,
    k_fulltext: int,
    top_k_out: int,
) -> dict[str, Any]:
    mention = str(entity.get("text", "")).strip()
    normalized = normalize(mention)
    sentence_read_codes = extract_read_codes(sentence)
    raw_candidates = fetch_candidates(
        session=session,
        mention=mention,
        normalized=normalized,
        k_exact=k_exact,
        k_fulltext=k_fulltext,
    )

    scored: list[dict[str, Any]] = []
    for c in raw_candidates:
        out = {
            "concept_id": c.get("concept_id"),
            "fsn": c.get("fsn"),
            "semantic_tag": c.get("semantic_tag"),
            "retrieval_source": c.get("retrieval_source"),
            "retrieval_score": float(c.get("retrieval_score", 0.0)),
            "read_codes": c.get("read_codes", []),
        }
        out["score"] = score_candidate(out, sentence, entity, sentence_read_codes)
        scored.append(out)

    scored.sort(key=lambda x: x["score"], reverse=True)
    selected = scored[0] if scored else None

    # Preserve all context modifiers from source labels.
    modifiers = {
        "clinical_status": entity.get("clinical_status"),
        "negation": entity.get("negation"),
        "uncertainty": entity.get("uncertainty"),
        "temporal": entity.get("temporal"),
        "attributes": entity.get("attributes"),
    }

    return {
        "mention": mention,
        "mention_type": entity.get("type"),
        "expected_semantic_tag": entity.get("snomed_semantic_tag"),
        "modifiers": modifiers,
        "sentence_read_codes": sorted(sentence_read_codes),
        "selected": selected,
        "candidates": scored[:top_k_out],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--k-exact", type=int, default=30)
    parser.add_argument("--k-fulltext", type=int, default=40)
    parser.add_argument("--top-k-out", type=int, default=5)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    uri, user, password = load_neo4j_config()
    driver = GraphDatabase.driver(uri, auth=(user, password))
    stats = PrototypeStats()
    results: list[dict[str, Any]] = []

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
                sentence_result = {
                    "date": row.get("date"),
                    "sentence": sentence,
                    "entity_results": [],
                }
                sentence_codes = extract_read_codes(sentence)
                if sentence_codes:
                    stats.read_code_in_sentence += 1

                for entity in entities:
                    stats.entities += 1
                    er = build_entity_result(
                        session=session,
                        sentence=sentence,
                        entity=entity,
                        k_exact=args.k_exact,
                        k_fulltext=args.k_fulltext,
                        top_k_out=args.top_k_out,
                    )
                    if not er["candidates"]:
                        stats.no_candidates += 1
                    else:
                        stats.mapped_candidates += 1
                        top = er["selected"] or {}
                        top_codes = set(top.get("read_codes", []))
                        if sentence_codes and (sentence_codes & top_codes):
                            stats.read_map_hit_top1 += 1
                    sentence_result["entity_results"].append(er)

                results.append(sentence_result)
                if stats.rows % 50 == 0:
                    print(f"Processed {stats.rows} rows...")
    finally:
        driver.close()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as out:
        for row in results:
            out.write(json.dumps(row, ensure_ascii=False) + "\n")

    report = stats.as_dict()
    report["input"] = str(args.input)
    report["output"] = str(args.output)
    report["notes"] = [
        "Semantic tag used as weak prior only.",
        "Context modifiers are preserved from source labels.",
        "Traversal constrained to 0-1 hop signals via retrieved Concept metadata.",
    ]
    with args.report.open("w", encoding="utf-8") as rep:
        json.dump(report, rep, indent=2)

    print("Prototype complete.")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
