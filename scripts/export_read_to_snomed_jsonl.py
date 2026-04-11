"""Export a clean Read-code to SNOMED-code JSONL mapping from DMWB MDB files.

This script performs a deterministic term-based link because the provided MDBs
do not expose a direct Read->SNOMED mapping table.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import boto3
from botocore.config import Config
import pyodbc
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE = ROOT / "external_content" / "trud-snomed-data-migration"
DEFAULT_READ_DB = DEFAULT_BASE / "DMWB NHS READ.mdb"
DEFAULT_SNOMED_DB = DEFAULT_BASE / "DMWB NHS SNOMED.mdb"
DEFAULT_OUT = DEFAULT_BASE / "read_to_snomed.clean.jsonl"
DEFAULT_OUT_WITH_AMBIGUITY = DEFAULT_BASE / "read_to_snomed.with_ambiguity.jsonl"
DEFAULT_OUT_API_RESOLVED = DEFAULT_BASE / "read_to_snomed.api_resolved.jsonl"
DEFAULT_OUT_LLM_RESOLVED = DEFAULT_BASE / "read_to_snomed.llm_resolved.jsonl"
ODBC_DRIVER = "{Microsoft Access Driver (*.mdb, *.accdb)}"
READ_CODE_RE = re.compile(r"^[A-Za-z0-9.]{3,8}$")
MULTISPACE_RE = re.compile(r"\s+")
PUNCT_RE = re.compile(r"[^a-z0-9 ]+")
FALLBACK_CONCEPT_TYPES = (
    "procedure",
    "situation",
    "finding",
    "disorder",
    "observable entity",
    "substance",
)


def log(message: str) -> None:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{stamp}] {message}", flush=True)


def decode_access_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-16le", errors="ignore").rstrip("\x00").strip()
    return str(value).strip()


def normalize_term(term: str) -> str:
    clean = term.lower().strip()
    clean = PUNCT_RE.sub(" ", clean)
    clean = MULTISPACE_RE.sub(" ", clean)
    return clean.strip()


def choose_read_term(t30: str, t60: str, t198: str) -> str:
    for candidate in (t60, t198, t30):
        value = candidate.strip()
        if value:
            return value
    return ""


def open_access_connection(db_path: Path) -> pyodbc.Connection:
    connection_string = f"DRIVER={ODBC_DRIVER};DBQ={db_path.resolve()};"
    return pyodbc.connect(connection_string)


def iter_read_rows(
    conn: pyodbc.Connection, table_name: str
) -> Iterable[tuple[str, str]]:
    query = f"SELECT [CUI], [T30], [T60], [T198] FROM [{table_name}]"
    cursor = conn.cursor()
    for row in cursor.execute(query):
        read_code = decode_access_value(row[0])
        if not READ_CODE_RE.match(read_code):
            continue
        read_term = choose_read_term(
            decode_access_value(row[1]),
            decode_access_value(row[2]),
            decode_access_value(row[3]),
        )
        if not read_term:
            continue
        yield read_code, read_term


def load_term_to_snomed(conn: pyodbc.Connection) -> dict[str, set[str]]:
    query = "SELECT [CUI], [TERM] " "FROM [SCT] " "WHERE [STAT] = 0"
    term_to_codes: dict[str, set[str]] = defaultdict(set)
    cursor = conn.cursor()
    for row in cursor.execute(query):
        snomed_code = decode_access_value(row[0])
        term = decode_access_value(row[1])
        if not snomed_code or not term:
            continue
        normalized = normalize_term(term)
        if not normalized:
            continue
        term_to_codes[normalized].add(snomed_code)
    return term_to_codes


def collect_candidate_map(
    read_conn: pyodbc.Connection,
    snomed_term_index: dict[str, set[str]],
) -> tuple[dict[str, set[str]], dict[str, str]]:
    read_code_to_candidates: dict[str, set[str]] = defaultdict(set)
    read_code_to_term: dict[str, str] = {}

    for table_name in ("RCT", "CTV3"):
        for read_code, read_term in iter_read_rows(read_conn, table_name):
            normalized_term = normalize_term(read_term)
            if not normalized_term:
                continue
            snomed_candidates = snomed_term_index.get(normalized_term)
            if not snomed_candidates:
                continue
            read_code_to_candidates[read_code].update(snomed_candidates)
            read_code_to_term.setdefault(read_code, read_term)
    return read_code_to_candidates, read_code_to_term


def build_clean_mapping(
    read_code_to_candidates: dict[str, set[str]],
    read_code_to_term: dict[str, str],
) -> list[dict[str, str]]:

    records: list[dict[str, str]] = []
    for read_code in sorted(read_code_to_candidates):
        candidates = read_code_to_candidates[read_code]
        if len(candidates) != 1:
            continue
        snomed_code = next(iter(candidates))
        records.append(
            {
                "read_code": read_code,
                "snomed_code": snomed_code,
                "read_term": read_code_to_term.get(read_code, ""),
                "method": "exact_term_match_active_sct",
            }
        )
    return records


def build_mapping_with_ambiguity(
    read_code_to_candidates: dict[str, set[str]],
    read_code_to_term: dict[str, str],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for read_code in sorted(read_code_to_candidates):
        candidates = sorted(read_code_to_candidates[read_code])
        candidate_count = len(candidates)
        if candidate_count == 1:
            mapping_status = "unambiguous"
            confidence = 1.0
            snomed_code = candidates[0]
        else:
            mapping_status = "ambiguous"
            confidence = 0.5
            snomed_code = None

        records.append(
            {
                "read_code": read_code,
                "read_term": read_code_to_term.get(read_code, ""),
                "mapping_status": mapping_status,
                "confidence": confidence,
                "candidate_count": candidate_count,
                "snomed_code": snomed_code,
                "snomed_candidates": candidates,
                "method": "exact_term_match_active_sct",
            }
        )
    return records


def search_snomed_api(
    session: requests.Session,
    api_url: str,
    api_key: str,
    term: str,
    concept_type: str,
    limit: int,
    similarity_threshold: float,
) -> list[dict[str, Any]]:
    headers = {"x-api-key": api_key, "Content-Type": "application/json"}
    concept_types = [concept_type]
    if concept_type == "all":
        concept_types = list(FALLBACK_CONCEPT_TYPES)

    merged: dict[str, dict[str, Any]] = {}
    for concept_type_value in concept_types:
        payload = {
            "query": term,
            "concept_type": concept_type_value,
            "limit": limit,
            "similarity_threshold": similarity_threshold,
        }
        response = session.post(api_url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            continue
        results = data.get("results", [])
        if not isinstance(results, list):
            continue
        for item in results:
            if not isinstance(item, dict):
                continue
            concept_id = item.get("conceptId")
            if concept_id is None:
                continue
            key = str(concept_id)
            existing = merged.get(key)
            if not existing:
                merged[key] = item
                continue
            old_score = float(existing.get("score", 0.0) or 0.0)
            new_score = float(item.get("score", 0.0) or 0.0)
            if new_score > old_score:
                merged[key] = item

    return sorted(
        merged.values(),
        key=lambda r: float(r.get("score", 0.0) or 0.0),
        reverse=True,
    )


def resolve_with_api(
    rows: list[dict[str, Any]],
    api_url: str,
    api_key: str,
    concept_type: str,
    api_limit: int,
    similarity_threshold: float,
    api_max_terms: int | None,
    log_every: int,
) -> list[dict[str, Any]]:
    resolved_rows: list[dict[str, Any]] = []
    cache: dict[str, list[dict[str, Any]]] = {}
    queried_terms = 0
    api_resolved_count = 0
    ambiguous_seen = 0

    log(
        f"API resolution start: rows={len(rows)} concept_type={concept_type} "
        f"threshold={similarity_threshold} api_max_terms={api_max_terms}"
    )
    with requests.Session() as session:
        for idx, row in enumerate(rows, start=1):
            if row["mapping_status"] == "unambiguous":
                row_out = dict(row)
                row_out["resolution_method"] = "exact_term_match_active_sct"
                resolved_rows.append(row_out)
                continue

            ambiguous_seen += 1
            term = str(row.get("read_term", "")).strip()
            if not term:
                row_out = dict(row)
                row_out["resolution_method"] = "unresolved_no_term"
                resolved_rows.append(row_out)
                continue

            if term not in cache:
                if api_max_terms is not None and queried_terms >= api_max_terms:
                    cache[term] = []
                else:
                    cache[term] = search_snomed_api(
                        session=session,
                        api_url=api_url,
                        api_key=api_key,
                        term=term,
                        concept_type=concept_type,
                        limit=api_limit,
                        similarity_threshold=similarity_threshold,
                    )
                    queried_terms += 1

            api_results = cache[term]
            candidate_set = set(str(c) for c in row.get("snomed_candidates", []))
            chosen: dict[str, Any] | None = None
            for item in api_results:
                concept_id = item.get("conceptId")
                if concept_id is None:
                    continue
                if str(concept_id) in candidate_set:
                    chosen = item
                    break

            row_out = dict(row)
            if chosen:
                row_out["mapping_status"] = "resolved_by_api"
                row_out["snomed_code"] = str(chosen.get("conceptId"))
                row_out["confidence"] = float(
                    chosen.get("score", row_out.get("confidence", 0.5))
                )
                row_out["resolution_method"] = (
                    "api_top_match_intersects_local_candidates"
                )
                api_resolved_count += 1
            else:
                row_out["resolution_method"] = "unresolved_api_no_intersection"
            row_out["api_candidate_count"] = len(api_results)
            row_out["api_candidates"] = [
                {
                    "conceptId": (
                        str(item.get("conceptId"))
                        if item.get("conceptId") is not None
                        else None
                    ),
                    "name": item.get("name", ""),
                    "score": item.get("score"),
                    "type": item.get("type", ""),
                }
                for item in api_results
            ]
            resolved_rows.append(row_out)
            if idx % log_every == 0:
                log(
                    f"API resolution progress: processed={idx}/{len(rows)} "
                    f"ambiguous_seen={ambiguous_seen} api_resolved={api_resolved_count} "
                    f"queried_terms={queried_terms} cached_terms={len(cache)}"
                )

    log(
        f"API resolution done: ambiguous_seen={ambiguous_seen} "
        f"api_resolved={api_resolved_count} queried_terms={queried_terms}"
    )
    return resolved_rows


def extract_bedrock_text(response: dict[str, Any]) -> str:
    content = response.get("output", {}).get("message", {}).get("content", [])
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if isinstance(item, dict) and "text" in item:
            parts.append(str(item["text"]))
    return "\n".join(parts).strip()


def parse_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if not stripped:
        return {}
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, re.DOTALL)
        if not match:
            return {}
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}


def llm_pick_concept_id(
    bedrock_client: Any,
    model_id: str,
    read_term: str,
    candidates: list[dict[str, Any]],
) -> tuple[str | None, float | None, str]:
    candidate_payload = [
        {
            "conceptId": (
                str(c.get("conceptId")) if c.get("conceptId") is not None else ""
            ),
            "name": str(c.get("name", "")),
            "type": str(c.get("type", "")),
            "score": c.get("score"),
        }
        for c in candidates
    ]
    prompt = (
        "You are disambiguating SNOMED candidates for a READ term.\n"
        "Select the best matching conceptId from the candidate list.\n"
        "Return strict JSON only with keys: conceptId, confidence, reason.\n"
        'If uncertain, return {"conceptId":"NONE","confidence":0.0,"reason":"..."}.\n\n'
        f"READ term: {read_term}\n"
        f"Candidates: {json.dumps(candidate_payload, ensure_ascii=False)}"
    )
    response = bedrock_client.converse(
        modelId=model_id,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": 220, "temperature": 0.0},
    )
    text = extract_bedrock_text(response)
    parsed = parse_json_object(text)
    concept_id = str(parsed.get("conceptId", "")).strip()
    if not concept_id or concept_id.upper() == "NONE":
        return None, None, text
    confidence_raw = parsed.get("confidence")
    confidence = None
    if isinstance(confidence_raw, (int, float)):
        confidence = float(confidence_raw)
    return concept_id, confidence, text


def resolve_with_llm(
    rows: list[dict[str, Any]],
    model_id: str,
    aws_region: str,
    llm_max_rows: int | None,
    log_every: int,
) -> list[dict[str, Any]]:
    bedrock = boto3.client(
        "bedrock-runtime",
        region_name=aws_region,
        config=Config(connect_timeout=10, read_timeout=30, retries={"max_attempts": 2}),
    )
    llm_rows: list[dict[str, Any]] = []
    llm_cache: dict[
        tuple[str, tuple[str, ...]], tuple[str | None, float | None, str]
    ] = {}
    llm_queried = 0
    llm_resolved = 0

    log(
        f"LLM resolution start: rows={len(rows)} model={model_id} "
        f"region={aws_region} llm_max_rows={llm_max_rows}"
    )
    for idx, row in enumerate(rows, start=1):
        row_out = dict(row)
        if row_out.get("mapping_status") in {"unambiguous", "resolved_by_api"}:
            row_out["llm_resolution_method"] = "not_required"
            llm_rows.append(row_out)
            continue

        api_candidates = row_out.get("api_candidates", [])
        if not isinstance(api_candidates, list):
            api_candidates = []
        if len(api_candidates) < 2:
            row_out["llm_resolution_method"] = "skipped_insufficient_api_candidates"
            llm_rows.append(row_out)
            continue

        local_set = set(str(c) for c in row_out.get("snomed_candidates", []))
        intersect = []
        for cand in api_candidates:
            concept_id = cand.get("conceptId")
            if concept_id is None:
                continue
            if str(concept_id) in local_set:
                intersect.append(cand)
        candidate_pool = intersect if len(intersect) >= 2 else api_candidates
        candidate_ids = tuple(
            str(c.get("conceptId"))
            for c in candidate_pool
            if c.get("conceptId") is not None
        )
        cache_key = (str(row_out.get("read_term", "")).strip().lower(), candidate_ids)

        if llm_max_rows is not None and llm_queried >= llm_max_rows:
            row_out["llm_resolution_method"] = "skipped_llm_max_rows_reached"
            llm_rows.append(row_out)
            continue

        if cache_key not in llm_cache:
            picked = llm_pick_concept_id(
                bedrock_client=bedrock,
                model_id=model_id,
                read_term=str(row_out.get("read_term", "")),
                candidates=candidate_pool,
            )
            llm_cache[cache_key] = picked
            llm_queried += 1

        concept_id, confidence, raw_response = llm_cache[cache_key]
        pool_ids = set(candidate_ids)
        if concept_id and concept_id in pool_ids:
            row_out["mapping_status"] = "resolved_by_llm"
            row_out["snomed_code"] = concept_id
            if confidence is not None:
                row_out["confidence"] = confidence
            row_out["llm_resolution_method"] = "bedrock_candidate_selection"
            row_out["llm_model"] = model_id
            llm_resolved += 1
        else:
            row_out["llm_resolution_method"] = "unresolved_llm_no_valid_choice"
        row_out["llm_raw_response"] = raw_response
        llm_rows.append(row_out)
        if idx % log_every == 0:
            log(
                f"LLM resolution progress: processed={idx}/{len(rows)} "
                f"llm_calls={llm_queried} llm_resolved={llm_resolved} "
                f"cache_entries={len(llm_cache)}"
            )

    log(
        f"LLM resolution done: llm_calls={llm_queried} llm_resolved={llm_resolved} "
        f"cache_entries={len(llm_cache)}"
    )
    return llm_rows


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    count = 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    return count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--read-db", type=Path, default=DEFAULT_READ_DB)
    parser.add_argument("--snomed-db", type=Path, default=DEFAULT_SNOMED_DB)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--out-with-ambiguity", type=Path, default=DEFAULT_OUT_WITH_AMBIGUITY
    )
    parser.add_argument(
        "--out-api-resolved", type=Path, default=DEFAULT_OUT_API_RESOLVED
    )
    parser.add_argument(
        "--out-llm-resolved", type=Path, default=DEFAULT_OUT_LLM_RESOLVED
    )
    parser.add_argument(
        "--api-url",
        default="https://leo-clinical-dev.healthcarecopilot.ai/api/snomed/search",
    )
    parser.add_argument("--api-key-env", default="SNOMED_API_KEY")
    parser.add_argument("--concept-type", default="all")
    parser.add_argument("--api-limit", type=int, default=5)
    parser.add_argument("--similarity-threshold", type=float, default=0.85)
    parser.add_argument("--api-max-terms", type=int, default=None)
    parser.add_argument("--aws-model-env", default="AWS_BIG_MODEL")
    parser.add_argument("--llm-max-rows", type=int, default=None)
    parser.add_argument("--log-every", type=int, default=1000)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    log("Starting export_read_to_snomed_jsonl pipeline")
    load_dotenv(ROOT / "secrets" / ".env")
    log("Loading Access databases and building local term index")
    with open_access_connection(args.read_db) as read_conn:
        with open_access_connection(args.snomed_db) as snomed_conn:
            snomed_term_index = load_term_to_snomed(snomed_conn)
            read_code_to_candidates, read_code_to_term = collect_candidate_map(
                read_conn, snomed_term_index
            )
    log(
        f"Local candidate map built: read_codes={len(read_code_to_candidates)} "
        f"terms={len(read_code_to_term)}"
    )

    clean_rows = build_clean_mapping(read_code_to_candidates, read_code_to_term)
    written_clean = write_jsonl(args.out, clean_rows)
    log(f"Wrote {written_clean} rows to {args.out}")

    all_rows = build_mapping_with_ambiguity(read_code_to_candidates, read_code_to_term)
    written_all = write_jsonl(args.out_with_ambiguity, all_rows)
    log(f"Wrote {written_all} rows to {args.out_with_ambiguity}")

    api_key = os.getenv(args.api_key_env, "").strip()
    if not api_key:
        log(f"Skipping API resolution: missing env var {args.api_key_env}")
        return

    api_rows = resolve_with_api(
        rows=all_rows,
        api_url=args.api_url,
        api_key=api_key,
        concept_type=args.concept_type,
        api_limit=args.api_limit,
        similarity_threshold=args.similarity_threshold,
        api_max_terms=args.api_max_terms,
        log_every=args.log_every,
    )
    written_api = write_jsonl(args.out_api_resolved, api_rows)
    log(f"Wrote {written_api} rows to {args.out_api_resolved}")

    aws_model = os.getenv(args.aws_model_env, "").strip()
    aws_region = os.getenv("AWS_DEFAULT_REGION", "eu-west-2").strip()
    if not aws_model:
        log(f"Skipping LLM disambiguation: missing env var {args.aws_model_env}")
        return

    llm_rows = resolve_with_llm(
        rows=api_rows,
        model_id=aws_model,
        aws_region=aws_region,
        llm_max_rows=args.llm_max_rows,
        log_every=args.log_every,
    )
    written_llm = write_jsonl(args.out_llm_resolved, llm_rows)
    log(f"Wrote {written_llm} rows to {args.out_llm_resolved}")
    log("Pipeline complete")


if __name__ == "__main__":
    main()
