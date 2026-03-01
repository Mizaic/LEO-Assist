#!/usr/bin/env python3
"""Expand SNOMED config surface forms with LLM-suggested shorthand terms.

For each concept in `configs/snomed/snomed_ncda_*.json`, this script:
1) asks one or more configured LLMs for additional surface forms
2) adjudicates each response with deterministic safety rules
3) optionally backfills accepted terms into config JSONs

Outputs a full decision report so every term can be audited.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import random
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

try:  # pragma: no cover
    import boto3
    from botocore.exceptions import ClientError
except Exception:  # pragma: no cover
    boto3 = None
    ClientError = Exception  # type: ignore[assignment]


ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "configs" / "snomed"
EXPORTS = ROOT / "exports"
MAPPING_GLOB = "snomed_ncda_*.json"

DEFAULT_REPORT = ROOT / "exports" / "ner" / "llm_surface_form_expand_report.json"

STOP_PHRASES = {
    "screening",
    "result",
    "procedure",
    "finding",
    "review",
    "clinic",
    "referral",
    "advice",
    "home visit",
}

NOISY_SUBSTRINGS = {
    "added from questionnaire",
    "new episode",
    "problem:",
    "date of first outpatient appointment",
    "seen in ",
    "reasons for request",
    "triaged ",
}

MONTH_TOKENS = {
    "jan",
    "feb",
    "mar",
    "apr",
    "may",
    "jun",
    "jul",
    "aug",
    "sep",
    "oct",
    "nov",
    "dec",
}

EXPORT_GLOBS = (
    "training/old/*.jsonl",
    "ner/all_domains/archive_pre_refactor/domain_entities_*.jsonl",
    "ner/all_domains/domain_*.jsonl",
    "ner/runs/20260228_161535/domain_*.jsonl",
    "ner/training/exclusion_domain_v1.jsonl",
)


@dataclass(frozen=True)
class MappingRef:
    file_path: Path
    mapping_key: str


@dataclass
class ConceptContext:
    concept_id: str
    preferred_term: str
    semantic_tag: str
    existing_forms: set[str]
    refs: list[MappingRef]
    evidence_counter: Counter
    evidence_snippets: list[str]


def _norm(text: str) -> str:
    t = text.strip()
    t = re.sub(r"\s+", " ", t)
    return t.replace("–", "-").replace("—", "-")


def _clean_candidate(text: str) -> str:
    t = _norm(text)
    t = re.sub(r"\[[A-Z_]+\]", "", t)
    t = re.sub(r"\s+", " ", t).strip(" -,:;.")
    t = re.sub(r"\s*\([A-Za-z0-9.]{3,8}\)\s*$", "", t)
    t = re.sub(r"^(Known|known|Probable|probable|Likely|likely)\s+", "", t)
    return t


def _is_valid_form(text: str) -> tuple[bool, str]:
    t = text.strip()
    low = t.lower()
    if len(t) < 3 or len(t) > 96:
        return False, "length_out_of_bounds"
    if low in STOP_PHRASES:
        return False, "too_generic"
    if "[" in t or "]" in t:
        return False, "contains_placeholder"
    if ":" in t:
        return False, "contains_colon"
    if any(s in low for s in NOISY_SUBSTRINGS):
        return False, "contains_noisy_substring"
    if not re.search(r"[A-Za-z]", t):
        return False, "no_letters"
    if len(t.split()) > 7:
        return False, "too_many_tokens"
    if any(tok in MONTH_TOKENS for tok in re.findall(r"[a-z]+", low)):
        return False, "contains_month_token"
    if len(re.findall(r"\d", t)) > 4:
        return False, "too_many_digits"
    if re.search(r"(canc|tumou|clin|haema|gynae|childrens t)$", low):
        return False, "likely_truncated"
    if re.fullmatch(r"[A-Z0-9.\-/ ]+", t) and len(t) <= 12:
        return False, "code_like_token"
    if re.fullmatch(r"[0-9.\-/ ]+", t):
        return False, "numeric_only"
    return True, "ok"


def _extract_json_block(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    start = cleaned.find("{")
    if start < 0:
        raise json.JSONDecodeError("No JSON object start found", cleaned, 0)
    obj, _ = json.JSONDecoder().raw_decode(cleaned[start:])
    if not isinstance(obj, dict):
        raise json.JSONDecodeError("Top-level JSON is not an object", cleaned, 0)
    return obj


def _extract_pairs_from_obj(obj: dict[str, Any]) -> list[tuple[str, str, str]]:
    """Return (concept_id, entity_text, sentence_or_text)."""
    out: list[tuple[str, str, str]] = []
    sentence = str(obj.get("sentence_text") or obj.get("sentence") or obj.get("text") or "").strip()

    top_cid = str(obj.get("concept_id", "")).strip()
    top_txt = str(obj.get("text", "")).strip()
    if top_cid and top_txt:
        out.append((top_cid, top_txt, sentence or top_txt))

    ents = obj.get("entities")
    if isinstance(ents, list):
        for e in ents:
            if not isinstance(e, dict):
                continue
            txt = str(e.get("text", "")).strip()
            if not txt:
                continue
            cid = ""
            if isinstance(e.get("normalised_code"), dict):
                cid = str(e["normalised_code"].get("code", "")).strip()
            if not cid:
                cid = str(e.get("snomed_id", "")).strip()
            if cid:
                out.append((cid, txt, sentence or txt))
    return out


def iter_export_files() -> list[Path]:
    files: list[Path] = []
    for rel_glob in EXPORT_GLOBS:
        files.extend((EXPORTS / rel_glob.split("/")[0]).glob("/".join(rel_glob.split("/")[1:])))
    # safer explicit for the single file path
    explicit = EXPORTS / "ner" / "training" / "exclusion_domain_v1.jsonl"
    if explicit.exists():
        files.append(explicit)
    deduped = []
    seen: set[str] = set()
    for fp in files:
        key = str(fp.resolve())
        if fp.exists() and fp.is_file() and key not in seen:
            deduped.append(fp)
            seen.add(key)
    return deduped


def collect_evidence() -> tuple[dict[str, Counter], dict[str, list[str]]]:
    by_concept: dict[str, Counter] = defaultdict(Counter)
    snippets: dict[str, list[str]] = defaultdict(list)
    for fp in iter_export_files():
        with fp.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                for cid, txt, sent in _extract_pairs_from_obj(obj):
                    form = _clean_candidate(txt)
                    ok, _reason = _is_valid_form(form)
                    if not ok:
                        continue
                    by_concept[cid][form] += 1
                    if len(snippets[cid]) < 12 and sent:
                        snippets[cid].append(sent[:220])
    return by_concept, snippets


def build_concepts() -> dict[str, ConceptContext]:
    concept_to_refs: dict[str, list[MappingRef]] = defaultdict(list)
    concept_forms: dict[str, set[str]] = defaultdict(set)
    preferred: dict[str, str] = {}
    semantic: dict[str, str] = {}

    for fp in sorted(CONFIG_DIR.glob(MAPPING_GLOB)):
        payload = json.loads(fp.read_text(encoding="utf-8"))
        mappings = payload.get("mappings", {})
        if not isinstance(mappings, dict):
            continue
        for key, obj in mappings.items():
            if not isinstance(obj, dict):
                continue
            cid = str(obj.get("concept_id", "")).strip()
            if not cid:
                continue
            concept_to_refs[cid].append(MappingRef(fp, str(key)))
            forms = [str(key), str(obj.get("preferred_term", ""))]
            forms.extend(str(s) for s in (obj.get("guideline_synonyms") or []))
            concept_forms[cid].update(_clean_candidate(f).lower() for f in forms if _clean_candidate(f))
            preferred.setdefault(cid, str(obj.get("preferred_term", "")).strip() or str(key))
            semantic.setdefault(cid, str(obj.get("semantic_tag", "")).strip())

    evidence, snippets = collect_evidence()
    concepts: dict[str, ConceptContext] = {}
    for cid, refs in concept_to_refs.items():
        concepts[cid] = ConceptContext(
            concept_id=cid,
            preferred_term=preferred.get(cid, ""),
            semantic_tag=semantic.get(cid, ""),
            existing_forms=concept_forms.get(cid, set()),
            refs=refs,
            evidence_counter=evidence.get(cid, Counter()),
            evidence_snippets=snippets.get(cid, []),
        )
    return concepts


def bedrock_call_with_backoff(
    client: Any,
    model_id: str,
    system_prompt: str,
    user_prompt: str,
    max_retries: int = 8,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
) -> dict[str, Any]:
    for attempt in range(max_retries):
        try:
            resp = client.converse(
                modelId=model_id,
                system=[{"text": system_prompt}],
                messages=[{"role": "user", "content": [{"text": user_prompt}]}],
                inferenceConfig={"temperature": 0.1, "maxTokens": 2000},
            )
            content = resp.get("output", {}).get("message", {}).get("content", [])
            text = "\n".join(str(part.get("text", "")) for part in content if isinstance(part, dict)).strip()
            return _extract_json_block(text)
        except (ClientError, json.JSONDecodeError):
            if attempt == max_retries - 1:
                raise
            sleep_s = min(max_delay, base_delay * (2**attempt)) + random.uniform(0, 0.35)
            time.sleep(sleep_s)
    raise RuntimeError("Bedrock request failed after retries")


def azure_chat_json_with_backoff(
    endpoint: str,
    api_key: str,
    api_version: str,
    deployment: str,
    system_prompt: str,
    user_prompt: str,
    max_retries: int = 8,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
) -> dict[str, Any]:
    chat_url = (
        endpoint.rstrip("/")
        + f"/openai/deployments/{deployment}/chat/completions"
        + f"?api-version={api_version}"
    )
    payload = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "reasoning_effort": "minimal",
        "max_completion_tokens": 2500,
        "response_format": {"type": "json_object"},
    }
    headers = {"api-key": api_key, "Content-Type": "application/json"}
    for attempt in range(max_retries):
        try:
            resp = requests.post(chat_url, headers=headers, json=payload, timeout=90)
            if resp.status_code in {429, 500, 502, 503, 504}:
                if attempt == max_retries - 1:
                    resp.raise_for_status()
                sleep_s = min(max_delay, base_delay * (2**attempt)) + random.uniform(0, 0.35)
                time.sleep(sleep_s)
                continue
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            return _extract_json_block(content)
        except (requests.RequestException, KeyError, ValueError, json.JSONDecodeError):
            if attempt == max_retries - 1:
                raise
            sleep_s = min(max_delay, base_delay * (2**attempt)) + random.uniform(0, 0.35)
            time.sleep(sleep_s)
    raise RuntimeError("Azure request failed after retries")


def llm_expand_concept(
    *,
    model_env_var: str,
    model_id: str,
    bedrock_client: Any,
    azure_cfg: dict[str, str],
    concept: ConceptContext,
    max_per_model: int,
    max_retries: int,
) -> dict[str, Any]:
    evidence_top = [f"{k} ({v})" for k, v in concept.evidence_counter.most_common(8)]
    evidence_examples = concept.evidence_snippets[:5]
    system_prompt = (
        "You are a clinical terminology assistant for UK GP free-text normalization. "
        "Generate plausible shorthand/surface forms for ONE SNOMED concept only. "
        "Do not output unrelated concepts."
    )
    user_prompt = (
        "Return strict JSON with this schema:\n"
        "{\n"
        '  "candidates": [\n'
        '    {"term": "...", "style": "abbrev|shorthand|colloquial|variant", "confidence": 0.0, "reason": "..."}\n'
        "  ]\n"
        "}\n\n"
        f"Concept ID: {concept.concept_id}\n"
        f"Preferred term: {concept.preferred_term}\n"
        f"Semantic tag: {concept.semantic_tag}\n"
        f"Existing forms (do not repeat): {json.dumps(sorted(list(concept.existing_forms))[:40], ensure_ascii=False)}\n"
        f"Observed mentions from data: {json.dumps(evidence_top, ensure_ascii=False)}\n"
        f"Observed sentence snippets: {json.dumps(evidence_examples, ensure_ascii=False)}\n\n"
        f"Constraints:\n"
        f"- Return at most {max_per_model} candidates.\n"
        "- Keep terms short (2-7 words).\n"
        "- No placeholders, no dates, no coding artifacts.\n"
        "- Keep UK clinical shorthand if plausible.\n"
        "- Do NOT include the preferred term unchanged.\n"
    )
    if model_env_var.startswith("AZURE_OPENAI_"):
        data = azure_chat_json_with_backoff(
            endpoint=azure_cfg["endpoint"],
            api_key=azure_cfg["api_key"],
            api_version=azure_cfg["api_version"],
            deployment=model_id,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_retries=max_retries,
        )
    else:
        if bedrock_client is None:
            raise RuntimeError("Bedrock client not available")
        data = bedrock_call_with_backoff(
            client=bedrock_client,
            model_id=model_id,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_retries=max_retries,
        )
    cands = data.get("candidates", [])
    if not isinstance(cands, list):
        raise ValueError("LLM response missing candidates[]")
    return {"candidates": cands}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--model-env-var",
        action="append",
        default=[],
        help="Repeatable model env vars (e.g. AWS_BIG_MODEL, AZURE_OPENAI_BIG_MODEL)",
    )
    p.add_argument("--max-per-model", type=int, default=10)
    p.add_argument("--workers", type=int, default=1, help="Concepts processed concurrently")
    p.add_argument("--max-retries", type=int, default=8)
    p.add_argument("--limit-concepts", type=int, default=0)
    p.add_argument("--concept-ids", default="", help="Comma-separated concept IDs filter")
    p.add_argument(
        "--config-file-contains",
        action="append",
        default=[],
        help="Only concepts from config file paths containing this text (repeatable)",
    )
    p.add_argument("--min-confidence", type=float, default=0.70)
    p.add_argument("--min-consensus", type=int, default=2)
    p.add_argument("--allow-single-model-with-evidence", action="store_true")
    p.add_argument("--evidence-threshold", type=int, default=2)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    p.add_argument("--sleep-ms", type=int, default=0, help="Delay between concept calls")
    return p.parse_args()


def _select_concepts(all_concepts: dict[str, ConceptContext], args: argparse.Namespace) -> list[ConceptContext]:
    ordered = [all_concepts[k] for k in sorted(all_concepts.keys())]
    if args.config_file_contains:
        needles = [n.lower().strip() for n in args.config_file_contains if n.strip()]
        if needles:
            ordered = [
                c for c in ordered
                if any(any(n in str(ref.file_path).lower() for n in needles) for ref in c.refs)
            ]
    if args.concept_ids.strip():
        wanted = {x.strip() for x in args.concept_ids.split(",") if x.strip()}
        ordered = [c for c in ordered if c.concept_id in wanted]
    if args.limit_concepts > 0:
        ordered = ordered[: args.limit_concepts]
    return ordered


def _dedupe_append_synonyms(mapping_obj: dict[str, Any], new_forms: list[str]) -> int:
    syns = list(mapping_obj.get("guideline_synonyms") or [])
    low = {_clean_candidate(s).lower() for s in syns if _clean_candidate(str(s))}
    added = 0
    for form in new_forms:
        cl = _clean_candidate(form)
        if cl and cl.lower() not in low:
            syns.append(cl)
            low.add(cl.lower())
            added += 1
    mapping_obj["guideline_synonyms"] = syns
    mapping_obj["guideline_synonym_count"] = len(syns)
    return added


def _process_concept(
    *,
    concept: ConceptContext,
    active_models: dict[str, str],
    bedrock_client: Any,
    azure_cfg: dict[str, str],
    args: argparse.Namespace,
) -> tuple[dict[str, Any], list[str]]:
    model_outputs: dict[str, list[dict[str, Any]]] = {}
    concept_report: dict[str, Any] = {
        "concept_id": concept.concept_id,
        "preferred_term": concept.preferred_term,
        "semantic_tag": concept.semantic_tag,
        "existing_form_count": len(concept.existing_forms),
        "evidence_top": concept.evidence_counter.most_common(10),
        "model_outputs": {},
        "decisions": [],
        "accepted": [],
        "rejected_count": 0,
    }

    for model_var, model_id in active_models.items():
        try:
            out = llm_expand_concept(
                model_env_var=model_var,
                model_id=model_id,
                bedrock_client=bedrock_client,
                azure_cfg=azure_cfg,
                concept=concept,
                max_per_model=args.max_per_model,
                max_retries=args.max_retries,
            )
            candidates = out.get("candidates", [])
            if not isinstance(candidates, list):
                candidates = []
        except Exception as exc:  # pragma: no cover - network/runtime branch
            candidates = []
            concept_report["model_outputs"][model_var] = {"error": str(exc), "candidates": []}
            continue

        parsed: list[dict[str, Any]] = []
        for c in candidates:
            if not isinstance(c, dict):
                continue
            term = _clean_candidate(str(c.get("term", "")).strip())
            style = str(c.get("style", "")).strip().lower() or "unknown"
            conf_raw = c.get("confidence", 0.0)
            conf = float(conf_raw) if isinstance(conf_raw, (int, float)) else 0.0
            reason = str(c.get("reason", "")).strip()
            if term:
                parsed.append({"term": term, "style": style, "confidence": conf, "reason": reason})
        model_outputs[model_var] = parsed[: args.max_per_model]
        concept_report["model_outputs"][model_var] = {"candidates": model_outputs[model_var]}

    grouped: dict[str, dict[str, Any]] = {}
    for model_var, cands in model_outputs.items():
        for c in cands:
            key = c["term"].lower()
            g = grouped.setdefault(
                key,
                {
                    "term": c["term"],
                    "models": set(),
                    "max_conf": 0.0,
                    "styles": set(),
                    "reasons": [],
                    "evidence_count": concept.evidence_counter.get(c["term"], 0),
                },
            )
            g["models"].add(model_var)
            g["max_conf"] = max(float(g["max_conf"]), float(c["confidence"]))
            if c["style"]:
                g["styles"].add(c["style"])
            if c["reason"]:
                g["reasons"].append(c["reason"])

    accepted: list[str] = []
    for key, g in sorted(grouped.items(), key=lambda kv: (-len(kv[1]["models"]), -kv[1]["max_conf"], kv[1]["term"])):
        term = g["term"]
        ok, invalid_reason = _is_valid_form(term)
        decision_reasons: list[str] = []
        if not ok:
            decision_reasons.append(f"reject:{invalid_reason}")
        if key in concept.existing_forms:
            decision_reasons.append("reject:already_exists")
        model_count = len(g["models"])
        enough_conf = float(g["max_conf"]) >= args.min_confidence
        enough_consensus = model_count >= args.min_consensus
        evidence_ok = int(g["evidence_count"]) >= args.evidence_threshold
        accepted_flag = False
        if ok and key not in concept.existing_forms and enough_conf:
            if enough_consensus:
                accepted_flag = True
                decision_reasons.append("accept:consensus")
            elif args.allow_single_model_with_evidence and model_count >= 1 and evidence_ok:
                accepted_flag = True
                decision_reasons.append("accept:single_model_plus_evidence")
            else:
                decision_reasons.append("reject:insufficient_consensus")
        elif ok and key not in concept.existing_forms:
            decision_reasons.append("reject:low_confidence")

        concept_report["decisions"].append(
            {
                "term": term,
                "models": sorted(list(g["models"])),
                "max_confidence": round(float(g["max_conf"]), 4),
                "styles": sorted(list(g["styles"])),
                "evidence_count": int(g["evidence_count"]),
                "decision": "accept" if accepted_flag else "reject",
                "reasons": decision_reasons,
            }
        )
        if accepted_flag:
            accepted.append(term)

    concept_report["accepted"] = accepted
    concept_report["rejected_count"] = len([d for d in concept_report["decisions"] if d["decision"] == "reject"])
    return concept_report, accepted


def main() -> None:
    args = parse_args()
    load_dotenv(ROOT / "secrets" / ".env")

    model_vars = list(dict.fromkeys(args.model_env_var or ["AWS_BIG_MODEL", "AZURE_OPENAI_BIG_MODEL"]))
    azure_cfg = {
        "endpoint": os.getenv("AZURE_OPENAI_ENDPOINT", ""),
        "api_key": os.getenv("AZURE_OPENAI_API_KEY", ""),
        "api_version": os.getenv("AZURE_OPENAI_API_VERSION", ""),
    }
    bedrock_region = os.getenv("AWS_DEFAULT_REGION", "")
    bedrock_client = boto3.client("bedrock-runtime", region_name=bedrock_region) if (boto3 and bedrock_region) else None

    active_models: dict[str, str] = {}
    for mv in model_vars:
        mid = os.getenv(mv, "").strip()
        if not mid:
            continue
        if mv.startswith("AZURE_OPENAI_") and not all(azure_cfg.values()):
            continue
        if not mv.startswith("AZURE_OPENAI_") and bedrock_client is None:
            continue
        active_models[mv] = mid
    if not active_models:
        raise RuntimeError("No usable model env vars found. Set at least one model and credentials in secrets/.env")

    concepts_map = build_concepts()
    concepts = _select_concepts(concepts_map, args)
    file_cache: dict[Path, dict[str, Any]] = {}

    report: dict[str, Any] = {
        "models": list(active_models.keys()),
        "concepts_total": len(concepts),
        "concepts_processed": 0,
        "concepts_with_accepts": 0,
        "accepted_terms_total": 0,
        "files_updated": 0,
        "dry_run": args.dry_run,
        "concept_reports": [],
    }

    touched_files: set[Path] = set()
    concept_by_id = {c.concept_id: c for c in concepts}
    workers = max(1, int(args.workers))
    concept_results: dict[str, tuple[dict[str, Any], list[str]]] = {}

    if workers == 1:
        for idx, concept in enumerate(concepts, start=1):
            concept_report, accepted = _process_concept(
                concept=concept,
                active_models=active_models,
                bedrock_client=bedrock_client,
                azure_cfg=azure_cfg,
                args=args,
            )
            concept_results[concept.concept_id] = (concept_report, accepted)
            print(f"[{idx}/{len(concepts)}] concept={concept.concept_id} accepted={len(accepted)}", flush=True)
            if args.sleep_ms > 0:
                time.sleep(args.sleep_ms / 1000.0)
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(
                    _process_concept,
                    concept=concept,
                    active_models=active_models,
                    bedrock_client=bedrock_client,
                    azure_cfg=azure_cfg,
                    args=args,
                ): concept
                for concept in concepts
            }
            completed = 0
            for fut in as_completed(futures):
                concept = futures[fut]
                completed += 1
                try:
                    concept_report, accepted = fut.result()
                except Exception as exc:  # pragma: no cover - defensive
                    concept_report = {
                        "concept_id": concept.concept_id,
                        "preferred_term": concept.preferred_term,
                        "semantic_tag": concept.semantic_tag,
                        "existing_form_count": len(concept.existing_forms),
                        "evidence_top": concept.evidence_counter.most_common(10),
                        "model_outputs": {},
                        "decisions": [],
                        "accepted": [],
                        "rejected_count": 0,
                        "error": str(exc),
                    }
                    accepted = []
                concept_results[concept.concept_id] = (concept_report, accepted)
                print(f"[{completed}/{len(concepts)}] concept={concept.concept_id} accepted={len(accepted)}", flush=True)
                if args.sleep_ms > 0:
                    time.sleep(args.sleep_ms / 1000.0)

    for concept in concepts:
        concept_report, accepted = concept_results.get(concept.concept_id, ({}, []))
        if not concept_report:
            continue
        report["concepts_processed"] += 1
        report["concept_reports"].append(concept_report)
        if accepted:
            report["concepts_with_accepts"] += 1
            report["accepted_terms_total"] += len(accepted)
            for ref in concept.refs:
                if ref.file_path not in file_cache:
                    file_cache[ref.file_path] = json.loads(ref.file_path.read_text(encoding="utf-8"))
                obj = file_cache[ref.file_path]["mappings"][ref.mapping_key]
                _dedupe_append_synonyms(obj, accepted)
                touched_files.add(ref.file_path)

    if not args.dry_run:
        for fp, payload in file_cache.items():
            fp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report["files_updated"] = len(touched_files)

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "concepts_processed": report["concepts_processed"],
                "concepts_with_accepts": report["concepts_with_accepts"],
                "accepted_terms_total": report["accepted_terms_total"],
                "files_updated": report["files_updated"],
                "report": str(args.report),
                "dry_run": args.dry_run,
            },
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
