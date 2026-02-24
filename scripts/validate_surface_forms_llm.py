"""LLM + deterministic validator for surface-form JSONL datasets.

Correctness is defined explicitly by RULES below, and each row is validated with:
1) deterministic structural/semantic checks
2) Bedrock LLM adjudication against the same explicit rules

Usage example:
python scripts/validate_surface_forms_llm.py ^
  --input services/terminology/data/training/surface_forms_4202301609.jsonl ^
  --input services/terminology/data/training/surface_forms_4203796334.jsonl
"""

from __future__ import annotations

import argparse
import json
import random
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv
import os
import requests


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "services" / "terminology" / "data" / "training"

TYPE_TO_TAG = {
    "symptom": "finding",
    "diagnosis": "disorder",
    "vital_sign": "observable entity",
    "lab_result": "observable entity",
    "exposure": "situation",
    "social_history": "situation",
    "medication": "substance",
    "intervention": "procedure",
    "advice_event": "situation",
    "referral": "procedure",
    "administrative_event": "record artifact",
    "document_event": "record artifact",
}
ALLOWED_STATUS = {"current", "historic", "planned"}
ALLOWED_TYPES = set(TYPE_TO_TAG.keys())
CLINICAL_TYPES = {
    "symptom",
    "diagnosis",
    "vital_sign",
    "lab_result",
    "exposure",
    "social_history",
    "medication",
    "intervention",
    "advice_event",
    "referral",
}

RULES = [
    "R1 schema: row has exactly date,sentence,entities",
    "R2 date_format: date is YYYY-MM",
    "R3 date_range: date in [2024-01..2025-12]",
    "R4 sentence_non_empty: sentence is non-empty, plain text",
    "R5 entity_schema: each entity has text,type,snomed_semantic_tag,clinical_status,attributes,temporal,negation,uncertainty",
    "R6 type_allowed: entity.type is one of allowed categories",
    "R7 semantic_alignment: snomed_semantic_tag exactly matches type mapping",
    "R8 status_allowed: clinical_status in current|historic|planned",
    "R9 negation_logic: planned entity cannot be negated",
    "R10 uncertainty_scope: uncertainty true only for diagnosis/symptom",
    (
        "R11 negation_scope: if sentence has a negation cue (no/not/denies/nil/nad) applied to "
        "a clinical concept, then the corresponding entity(ies) must be negated. "
        "Common GP pattern: 'denies X. Y. Z' or 'no X, Y, Z' means ALL listed items are negated. "
        "Ignore safety-netting/conditional phrases (if no better, if no improvement, unless urgent). "
        "If at least one clinical entity IS already negated, the rule passes."
    ),
    "R12 deid: no direct email/phone/NHS-number/full-name patterns",
    "R13 admin_typing: admin/document phrases must not be symptom/diagnosis",
    "R14 procedure_vs_disorder: repair/vaccination/referral/advice must not be diagnosis",
    "R15 span_quality: entity text is concise and not obvious fragment (e.g. pins, needles, no sa)",
]

NEGATION_CUE_RE = re.compile(r"\bno\b|\bnot\b|\bdenies\b|\bnil\b|\bnad\b", re.IGNORECASE)
SAFETY_NET_RE = re.compile(
    r"\bto\s+return\s+if\s+no\s+(?:better|improvement|change|response)\b"
    r"|\bif\s+no\s+(?:better|improvement|change|response)\b"
    r"|\bno\s+(?:better|improvement|change|response)\b"
    r"|\bdiscussed\s+no\s+\w+"
    r"|\bunless\s+(?:urgent|otherwise)\b"
    r"|\bto\s+return\b",
    re.IGNORECASE,
)
EMAIL_RE = re.compile(r"\b[\w.\-+]+@[\w.\-]+\.\w+\b", re.IGNORECASE)
PHONE_RE = re.compile(r"\b(?:\+44|0)\d[\d\s\-]{8,}\d\b")
NHS_RE = re.compile(r"\b\d{3}\s?\d{3}\s?\d{4}\b")
FULLNAME_RE = re.compile(r"\b[A-Z][A-Z\-']+,\s*[A-Z][a-zA-Z\-']+")
YM_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
ADMIN_PHRASE_RE = re.compile(
    r"past medical history|occupation|employed|letter|administration|notes summary|unknown staff",
    re.IGNORECASE,
)


@dataclass
class DeterministicIssue:
    rule_id: str
    severity: str
    message: str


def deterministic_validate(row: dict[str, Any]) -> list[DeterministicIssue]:
    issues: list[DeterministicIssue] = []

    if set(row.keys()) != {"date", "sentence", "entities"}:
        issues.append(DeterministicIssue("R1", "error", "row keys mismatch"))

    date = row.get("date")
    sentence = row.get("sentence")
    entities = row.get("entities")

    if not isinstance(date, str) or not YM_RE.match(date):
        issues.append(DeterministicIssue("R2", "error", "date not YYYY-MM"))
    elif not ("2024-01" <= date <= "2025-12"):
        issues.append(DeterministicIssue("R3", "error", "date outside 2024-2025"))

    if not isinstance(sentence, str) or not sentence.strip():
        issues.append(DeterministicIssue("R4", "error", "empty sentence"))
        sentence = ""

    if (
        EMAIL_RE.search(sentence)
        or PHONE_RE.search(sentence)
        or NHS_RE.search(sentence)
        or FULLNAME_RE.search(sentence)
    ):
        issues.append(DeterministicIssue("R12", "error", "possible PHI pattern in sentence"))

    if not isinstance(entities, list) or len(entities) == 0:
        issues.append(DeterministicIssue("R5", "error", "entities missing/empty"))
        return issues

    has_negated_clinical = False
    has_clinical = False
    for idx, e in enumerate(entities):
        if not isinstance(e, dict):
            issues.append(DeterministicIssue("R5", "error", f"entity[{idx}] not object"))
            continue

        required = {
            "text",
            "type",
            "snomed_semantic_tag",
            "clinical_status",
            "attributes",
            "temporal",
            "negation",
            "uncertainty",
        }
        if not required.issubset(e.keys()):
            issues.append(DeterministicIssue("R5", "error", f"entity[{idx}] missing required fields"))
            continue

        etype = e["type"]
        text = str(e["text"]).strip()
        status = e["clinical_status"]
        neg = e["negation"]
        unc = e["uncertainty"]
        tag = e["snomed_semantic_tag"]

        if etype not in ALLOWED_TYPES:
            issues.append(DeterministicIssue("R6", "error", f"entity[{idx}] invalid type: {etype}"))
            continue
        if tag != TYPE_TO_TAG[etype]:
            issues.append(DeterministicIssue("R7", "error", f"entity[{idx}] type/tag mismatch"))
        if status not in ALLOWED_STATUS:
            issues.append(DeterministicIssue("R8", "error", f"entity[{idx}] invalid clinical_status"))
        if status == "planned" and bool(neg):
            issues.append(DeterministicIssue("R9", "error", f"entity[{idx}] planned+negated"))
        if bool(unc) and etype not in {"diagnosis", "symptom"}:
            issues.append(DeterministicIssue("R10", "error", f"entity[{idx}] uncertainty not allowed for type"))

        if etype in CLINICAL_TYPES:
            has_clinical = True
            has_negated_clinical = has_negated_clinical or bool(neg)

        low_text = text.lower()
        if ADMIN_PHRASE_RE.search(sentence) and etype in {"symptom", "diagnosis"}:
            issues.append(DeterministicIssue("R13", "warning", f"entity[{idx}] admin phrase typed clinical"))
        if any(t in low_text for t in ("repair", "vaccination", "immunisation", "referral", "advice")) and etype == "diagnosis":
            issues.append(DeterministicIssue("R14", "error", f"entity[{idx}] procedure-like mention typed diagnosis"))
        if low_text in {"pins", "needles", "no sa", "sa"} or len(low_text) < 3:
            issues.append(DeterministicIssue("R15", "warning", f"entity[{idx}] low-quality span"))

    if NEGATION_CUE_RE.search(sentence) and has_clinical and not has_negated_clinical:
        stripped = SAFETY_NET_RE.sub("", sentence)
        if NEGATION_CUE_RE.search(stripped):
            issues.append(DeterministicIssue("R11", "error", "negation cue present without negated clinical entity"))
    return issues


def _extract_json_block(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    # Tolerate model responses with extra trailing text by decoding first JSON object.
    start = cleaned.find("{")
    if start < 0:
        raise json.JSONDecodeError("No JSON object start found", cleaned, 0)
    decoder = json.JSONDecoder()
    obj, _ = decoder.raw_decode(cleaned[start:])
    return obj


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
                inferenceConfig={"temperature": 0.0, "maxTokens": 2048},
            )
            text = resp["output"]["message"]["content"][0]["text"]
            return _extract_json_block(text)
        except json.JSONDecodeError:
            if attempt == max_retries - 1:
                raise
            sleep_s = min(max_delay, base_delay * (2**attempt)) + random.uniform(0, 0.35)
            time.sleep(sleep_s)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            throttled = code in {
                "ThrottlingException",
                "TooManyRequestsException",
                "RequestLimitExceeded",
                "ServiceUnavailableException",
                "InternalServerException",
            }
            if not throttled or attempt == max_retries - 1:
                raise
            sleep_s = min(max_delay, base_delay * (2**attempt)) + random.uniform(0, 0.35)
            time.sleep(sleep_s)

        except json.JSONDecodeError:
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
        "max_completion_tokens": 3000,
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
            if "choices" in data:
                content = data["choices"][0]["message"]["content"]
                if not isinstance(content, str) or not content.strip():
                    raise ValueError("Azure returned empty content")
            else:
                raise ValueError("Unknown Azure response schema")
            return _extract_json_block(content)
        except requests.RequestException:
            if attempt == max_retries - 1:
                raise
            sleep_s = min(max_delay, base_delay * (2**attempt)) + random.uniform(0, 0.35)
            time.sleep(sleep_s)
        except (KeyError, ValueError, json.JSONDecodeError):
            if attempt == max_retries - 1:
                raise
            sleep_s = min(max_delay, base_delay * (2**attempt)) + random.uniform(0, 0.35)
            time.sleep(sleep_s)
    raise RuntimeError("Azure OpenAI request failed after retries")


def llm_validate_batch(
    client: Any,
    model_id: str,
    model_env_var: str,
    azure_cfg: dict[str, str],
    batch_rows: list[dict[str, Any]],
    max_retries: int,
) -> dict[str, Any]:
    system_prompt = (
        "You are a strict clinical data QA validator for GP surface-form rows. "
        "Validate ONLY against the provided explicit rules and allowed type/tag map. "
        "Return JSON only, no prose."
    )
    allowed_map = {
        "symptom": "finding",
        "diagnosis": "disorder",
        "vital_sign": "observable entity",
        "lab_result": "observable entity",
        "exposure": "situation",
        "social_history": "situation",
        "medication": "substance",
        "intervention": "procedure",
        "advice_event": "situation",
        "referral": "procedure",
        "administrative_event": "record artifact",
        "document_event": "record artifact",
    }
    user_prompt = (
        "Correctness Rules (enforce exactly, no extra rules):\n"
        + "\n".join(f"- {r}" for r in RULES)
        + "\n\nAllowed type->tag map:\n"
        + json.dumps(allowed_map, ensure_ascii=False)
        + "\n\nImportant clarifications:\n"
        "- Placeholders like [CARE_SITE], [PERSON], [DATE] are allowed and not PHI leaks.\n"
        "- Read/SNOMED style clinical codes in parentheses are allowed.\n"
        "- 'referral', 'document_event', and 'administrative_event' are valid types.\n"
        "- GP misspellings/typos faithful to the original note are acceptable surface forms for R15.\n"
        "- Safety-netting phrases ('if no better', 'if no improvement', 'unless urgent') "
        "are NOT clinical negations — ignore them for R11.\n"
        "- 'patient denies X. Y. Z' means ALL listed entities are negated, not just the first.\n"
        "- Vague but real GP examination phrases ('obvious local trigger') are acceptable when negated.\n"
        "- advice_event (situation) = advice WAS given/declined/not indicated (state). "
        "intervention (procedure) = the ACT of advising (education/recommendation). "
        "E.g. 'advice about treatment given' = advice_event; 'smoking cessation advice' = intervention.\n"
        + "\n\nReturn strict JSON with schema:\n"
        '{\n'
        '  "results": [\n'
        '    {"line_number": 1, "pass": true, "what_is_wrong": []}\n'
        "  ]\n"
        "}\n\n"
        "Rows:\n"
        + json.dumps(batch_rows, ensure_ascii=False)
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
        data = bedrock_call_with_backoff(
            client=client,
            model_id=model_id,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_retries=max_retries,
        )
    if "results" not in data or not isinstance(data["results"], list):
        raise ValueError("LLM response invalid schema: missing results[]")
    return data


def llm_fix_batch(
    client: Any,
    model_id: str,
    model_env_var: str,
    azure_cfg: dict[str, str],
    failed_rows: list[dict[str, Any]],
    max_retries: int,
    metadata_only: bool,
    allow_drop: bool,
) -> dict[str, Any]:
    """Send failed rows to LLM and get corrected entities back."""
    system_prompt = (
        "You are a clinical data QA fixer for GP surface-form training rows. "
        "You receive rows that failed validation together with the issues found. "
        "Return corrected rows as JSON. Do NOT invent new entities. "
        "Fix only the identified issues. Return JSON only, no prose."
    )
    allowed_map = {k: v for k, v in TYPE_TO_TAG.items()}
    entity_schema_desc = (
        "Each entity MUST have exactly these fields:\n"
        "  text (str): the clinical surface form\n"
        "  type (str): one of the allowed types\n"
        "  snomed_semantic_tag (str): must match type->tag map exactly\n"
        "  clinical_status (str): current|historic|planned\n"
        "  attributes (object): {} if none, or {key: value} pairs\n"
        "  temporal (object): {onset, duration, offset, pattern, recurrence, context}\n"
        "  negation (bool)\n"
        "  uncertainty (bool)\n"
    )
    drop_action_line = (
        '- "drop": row should be removed entirely (not clinical, pure admin/safety-netting)\n'
        if allow_drop
        else ""
    )
    drop_schema_line = '  {"line_number": N, "action": "drop"}\n' if allow_drop else ""
    metadata_line = (
        "- METADATA-ONLY MODE: preserve entity text/attributes/temporal exactly. "
        "Only edit: type, snomed_semantic_tag, clinical_status, negation, uncertainty.\n"
        if metadata_only
        else ""
    )
    user_prompt = (
        "Allowed type->tag map:\n"
        + json.dumps(allowed_map, ensure_ascii=False)
        + "\n\n"
        + entity_schema_desc
        + "\nFor each failed row below, return a corrected version.\n"
        + "Actions:\n"
        + '- "fix": provide corrected entities array (keep date and sentence unchanged)\n'
        + drop_action_line
        + "\nRules for fixing:\n"
        + "- type/tag must match the allowed map exactly\n"
        + "- advice_event (situation) = advice WAS given/declined/not indicated. "
        + "intervention (procedure) = ACT of advising.\n"
        + "- vital_sign: pulse rate, BP, sats, temperature, BMI, weight, height.\n"
        + "- lab_result: HbA1c, cholesterol, liver/renal function, electrolytes, "
        + "blood chemistry, urine tests, SARS-CoV-2 test results.\n"
        + "- Safety-netting phrases (if no better, symptoms worsen to return, "
        + "when to seek medical help) are NOT clinical entities — drop them.\n"
        + "- Admin phrases (additional SCR dataset, COPI regulations, gov.uk, "
        + "contact patient, prescription issue) should be administrative_event/record artifact.\n"
        + "- Preserve clinical concept specificity. Do NOT rewrite to broader terms "
        + "(e.g. 'rabies vaccination' must not become 'rabies').\n"
        + "- Do not change the text field to something not in the original sentence.\n"
        + "- Keep temporal object structure even if all null.\n"
        + "- negation/uncertainty must be bool (true/false).\n"
        + metadata_line
        + "\nReturn strict JSON:\n"
        + '{"fixes": [\n'
        + '  {"line_number": N, "action": "fix", "entities": [...]},\n'
        + drop_schema_line
        + "]}\n\n"
        + "Failed rows with issues:\n"
        + json.dumps(failed_rows, ensure_ascii=False)
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
        data = bedrock_call_with_backoff(
            client=client,
            model_id=model_id,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_retries=max_retries,
        )
    if "fixes" not in data or not isinstance(data["fixes"], list):
        raise ValueError("LLM fix response invalid: missing fixes[]")
    return data


def _validate_fixed_entity(e: dict[str, Any]) -> list[str]:
    """Check that a LLM-corrected entity has valid structure."""
    errors: list[str] = []
    required = {"text", "type", "snomed_semantic_tag", "clinical_status",
                "attributes", "temporal", "negation", "uncertainty"}
    if not required.issubset(set(e.keys())):
        errors.append(f"missing fields: {required - set(e.keys())}")
        return errors
    if e["type"] not in TYPE_TO_TAG:
        errors.append(f"invalid type: {e['type']}")
        return errors
    if e["snomed_semantic_tag"] != TYPE_TO_TAG[e["type"]]:
        errors.append(f"tag mismatch: {e['type']}->{e['snomed_semantic_tag']}")
    if e["clinical_status"] not in ALLOWED_STATUS:
        errors.append(f"invalid status: {e['clinical_status']}")
    if not isinstance(e["negation"], bool):
        errors.append("negation not bool")
    if not isinstance(e["uncertainty"], bool):
        errors.append("uncertainty not bool")
    return errors


def validate_file(path: Path, client: Any, model_id: str, max_retries: int) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))

    return {
        "rows": rows,
    }


def run_validation(
    path: Path,
    rows: list[dict[str, Any]],
    client: Any,
    model_id: str,
    model_env_var: str,
    azure_cfg: dict[str, str],
    max_retries: int,
    batch_size: int,
) -> dict[str, Any]:
    line_count = len(rows)
    failures: list[dict[str, Any]] = []
    passed_rows = 0

    det_issues_by_line: dict[int, list[str]] = {}
    for i, row in enumerate(rows, start=1):
        issues = deterministic_validate(row)
        det_msgs = [f"{x.rule_id}: {x.message}" for x in issues if x.severity == "error"]
        det_issues_by_line[i] = det_msgs

    for start in range(0, line_count, batch_size):
        end = min(start + batch_size, line_count)
        batch_payload: list[dict[str, Any]] = []
        for i in range(start, end):
            row = rows[i]
            batch_payload.append(
                {
                    "line_number": i + 1,
                    "date": row.get("date"),
                    "sentence": row.get("sentence"),
                    "entities": row.get("entities"),
                }
            )

        llm_out = llm_validate_batch(
            client=client,
            model_id=model_id,
            model_env_var=model_env_var,
            azure_cfg=azure_cfg,
            batch_rows=batch_payload,
            max_retries=max_retries,
        )
        llm_results = llm_out.get("results", [])
        llm_by_line = {int(x["line_number"]): x for x in llm_results if "line_number" in x}

        for i in range(start, end):
            line_no = i + 1
            det_msgs = det_issues_by_line.get(line_no, [])
            llm_row = llm_by_line.get(line_no, {})
            llm_msgs = llm_row.get("what_is_wrong", []) if isinstance(llm_row, dict) else []
            llm_msgs = [str(m) for m in llm_msgs if str(m).strip()]

            combined = []
            seen: set[str] = set()
            for msg in det_msgs + llm_msgs:
                if msg not in seen:
                    seen.add(msg)
                    combined.append(msg)

            if combined:
                failures.append({"line_number": line_no, "what_is_wrong": combined})
            else:
                passed_rows += 1

        print(f"[{model_env_var}][{path.name}] validated {end}/{line_count} rows", flush=True)

    return {
        "input_file": str(path),
        "rows": line_count,
        "passed_rows": passed_rows,
        "failed_rows": len(failures),
        "overall_pass": len(failures) == 0,
        "failures": failures,
        "rules": RULES,
    }


def run_fix(
    path: Path,
    rows: list[dict[str, Any]],
    report: dict[str, Any],
    client: Any,
    model_id: str,
    model_env_var: str,
    azure_cfg: dict[str, str],
    max_retries: int,
    batch_size: int,
    metadata_only: bool,
    allow_drop: bool,
) -> dict[str, Any]:
    """Send failed rows to LLM for correction. Returns fix summary."""
    failures = report.get("failures", [])
    if not failures:
        return {"fixed": 0, "dropped": 0, "rejected": 0, "unchanged_rows": len(rows)}

    failed_line_map: dict[int, list[str]] = {
        f["line_number"]: f["what_is_wrong"] for f in failures
    }
    failed_indices = sorted(failed_line_map.keys())

    fix_results: dict[int, dict[str, Any]] = {}
    for start in range(0, len(failed_indices), batch_size):
        batch_keys = failed_indices[start : start + batch_size]
        batch_payload: list[dict[str, Any]] = []
        for ln in batch_keys:
            row = rows[ln - 1]
            batch_payload.append({
                "line_number": ln,
                "date": row.get("date"),
                "sentence": row.get("sentence"),
                "entities": row.get("entities"),
                "issues": failed_line_map[ln],
            })

        try:
            llm_out = llm_fix_batch(
                client=client,
                model_id=model_id,
                model_env_var=model_env_var,
                azure_cfg=azure_cfg,
                failed_rows=batch_payload,
                max_retries=max_retries,
                metadata_only=metadata_only,
                allow_drop=allow_drop,
            )
            for fix in llm_out.get("fixes", []):
                ln = int(fix.get("line_number", 0))
                if ln in failed_line_map:
                    fix_results[ln] = fix
        except Exception as exc:
            print(f"[{model_env_var}] fix batch error (lines {batch_keys[0]}-{batch_keys[-1]}): {exc}", flush=True)

        done = min(start + batch_size, len(failed_indices))
        print(f"[{model_env_var}][{path.name}] fixed {done}/{len(failed_indices)} failed rows", flush=True)

    fixed_count = 0
    dropped_count = 0
    rejected_count = 0
    drop_lines: set[int] = set()
    changes: list[dict[str, Any]] = []

    for ln, fix in sorted(fix_results.items()):
        action = fix.get("action", "fix")
        old_row = rows[ln - 1]
        issues = failed_line_map.get(ln, [])
        old_sentence_low = str(old_row.get("sentence", "")).lower()

        # Protect clinically sensitive travel+rabies phrasing from over-correction.
        if "rabies" in old_sentence_low and "discussed no travel" in old_sentence_low:
            rejected_count += 1
            changes.append({
                "line_number": ln,
                "action": "rejected",
                "reason": "protected_row: keep deterministic extractor output for rabies/travel sentence",
                "sentence": old_row.get("sentence", ""),
                "issues": issues,
                "original_entities": old_row.get("entities", []),
            })
            continue

        if action == "drop":
            if not allow_drop:
                rejected_count += 1
                changes.append({
                    "line_number": ln,
                    "action": "rejected",
                    "reason": "drop_not_allowed",
                    "sentence": old_row.get("sentence", ""),
                    "issues": issues,
                    "original_entities": old_row.get("entities", []),
                })
                continue
            drop_lines.add(ln)
            dropped_count += 1
            changes.append({
                "line_number": ln,
                "action": "drop",
                "sentence": old_row.get("sentence", ""),
                "issues": issues,
                "original_entities": old_row.get("entities", []),
            })
            continue

        new_entities = fix.get("entities")
        if not isinstance(new_entities, list) or len(new_entities) == 0:
            rejected_count += 1
            changes.append({
                "line_number": ln,
                "action": "rejected",
                "reason": "empty entities from LLM",
                "sentence": old_row.get("sentence", ""),
                "issues": issues,
                "original_entities": old_row.get("entities", []),
            })
            continue

        validation_errors: list[str] = []
        for eidx, ent in enumerate(new_entities):
            errs = _validate_fixed_entity(ent)
            validation_errors.extend(f"entity[{eidx}]: {e}" for e in errs)

        if validation_errors:
            rejected_count += 1
            changes.append({
                "line_number": ln,
                "action": "rejected",
                "reason": "; ".join(validation_errors[:3]),
                "sentence": old_row.get("sentence", ""),
                "issues": issues,
                "original_entities": old_row.get("entities", []),
                "proposed_entities": new_entities,
            })
            continue

        applied_entities = new_entities
        if metadata_only:
            old_entities = old_row.get("entities", [])
            if len(new_entities) != len(old_entities):
                rejected_count += 1
                changes.append({
                    "line_number": ln,
                    "action": "rejected",
                    "reason": "metadata_only_entity_count_mismatch",
                    "sentence": old_row.get("sentence", ""),
                    "issues": issues,
                    "original_entities": old_entities,
                    "proposed_entities": new_entities,
                })
                continue

            proposed_by_text: dict[str, list[dict[str, Any]]] = {}
            for ent in new_entities:
                key = str(ent.get("text", "")).strip().lower()
                proposed_by_text.setdefault(key, []).append(ent)

            merged_entities: list[dict[str, Any]] = []
            merge_errors: list[str] = []
            for ent in old_entities:
                key = str(ent.get("text", "")).strip().lower()
                bucket = proposed_by_text.get(key, [])
                if not bucket:
                    merge_errors.append(f"missing_proposal_for_text:{key}")
                    continue
                proposal = bucket.pop(0)
                merged = dict(ent)
                for field in ("type", "snomed_semantic_tag", "clinical_status", "negation", "uncertainty"):
                    merged[field] = proposal[field]
                merged_entities.append(merged)

            if merge_errors:
                rejected_count += 1
                changes.append({
                    "line_number": ln,
                    "action": "rejected",
                    "reason": "; ".join(merge_errors[:3]),
                    "sentence": old_row.get("sentence", ""),
                    "issues": issues,
                    "original_entities": old_entities,
                    "proposed_entities": new_entities,
                })
                continue
            applied_entities = merged_entities

        rows[ln - 1] = {
            "date": old_row["date"],
            "sentence": old_row["sentence"],
            "entities": applied_entities,
        }
        fixed_count += 1
        changes.append({
            "line_number": ln,
            "action": "fixed",
            "sentence": old_row.get("sentence", ""),
            "issues": issues,
            "original_entities": old_row.get("entities", []),
            "fixed_entities": applied_entities,
        })

    output_rows = [row for i, row in enumerate(rows, 1) if i not in drop_lines]
    out_path = path
    with out_path.open("w", encoding="utf-8") as f:
        for row in output_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    return {
        "input_file": str(path),
        "total_failed": len(failures),
        "fixed": fixed_count,
        "dropped": dropped_count,
        "rejected": rejected_count,
        "output_rows": len(output_rows),
        "output_file": str(out_path),
        "changes": changes,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate surface-form JSONL with Bedrock LLM")
    parser.add_argument("--input", action="append", required=True, help="Input JSONL file path (repeatable)")
    parser.add_argument(
        "--model-env-var",
        action="append",
        default=[],
        help="Model env var to use (repeatable), e.g. AWS_BIG_MODEL, AZURE_OPENAI_BIG_MODEL",
    )
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory for validation reports")
    parser.add_argument("--max-retries", type=int, default=8, help="Max retries for 429/throttling")
    parser.add_argument("--batch-size", type=int, default=20, help="Rows per LLM validation batch")
    parser.add_argument("--max-rows", type=int, default=0, help="Optional cap per file (0 = all rows)")
    parser.add_argument("--fix", action="store_true", help="Fix failed rows: LLM corrects entities and JSONL is overwritten")
    parser.add_argument("--fix-batch-size", type=int, default=5, help="Rows per LLM fix batch (smaller = better quality)")
    parser.add_argument(
        "--allow-text-rewrite",
        action="store_true",
        help="Allow LLM to rewrite entity text/spans (default off; metadata-only fixes)",
    )
    parser.add_argument(
        "--allow-drop",
        action="store_true",
        help="Allow LLM to drop rows entirely (default off)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    load_dotenv(ROOT / "secrets" / ".env")
    region = os.getenv("AWS_DEFAULT_REGION")
    azure_cfg = {
        "endpoint": os.getenv("AZURE_OPENAI_ENDPOINT", ""),
        "api_key": os.getenv("AZURE_OPENAI_API_KEY", ""),
        "api_version": os.getenv("AZURE_OPENAI_API_VERSION", ""),
    }
    bedrock_client = boto3.client("bedrock-runtime", region_name=region) if region else None
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    model_vars = list(dict.fromkeys(args.model_env_var or ["AWS_BIG_MODEL"]))
    for model_env_var in model_vars:
        model_id = os.getenv(model_env_var, "")
        if not model_id:
            print(f"Skipping {model_env_var}: env var not set", flush=True)
            continue
        if model_env_var.startswith("AZURE_OPENAI_"):
            if not all(azure_cfg.values()):
                print(f"Skipping {model_env_var}: Azure OpenAI config missing", flush=True)
                continue
            client = None
        else:
            if bedrock_client is None:
                print(f"Skipping {model_env_var}: AWS region/client missing", flush=True)
                continue
            client = bedrock_client

        for input_str in args.input:
            input_path = Path(input_str)
            loaded = validate_file(input_path, client, model_id, max_retries=args.max_retries)
            rows = loaded["rows"]
            if args.max_rows > 0:
                rows = rows[: args.max_rows]
            report = run_validation(
                path=input_path,
                rows=rows,
                client=client,
                model_id=model_id,
                model_env_var=model_env_var,
                azure_cfg=azure_cfg,
                max_retries=args.max_retries,
                batch_size=max(1, args.batch_size),
            )
            report_name = (
                f"{input_path.stem}.{model_env_var.lower()}.llm_validation_report.json"
            )
            out_path = out_dir / report_name
            with out_path.open("w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            print(
                f"[{model_env_var}] Report written: {out_path} | pass={report['overall_pass']} "
                f"failed_rows={report['failed_rows']}",
                flush=True,
            )

            if args.fix and report["failed_rows"] > 0:
                print(f"[{model_env_var}] Fixing {report['failed_rows']} failed rows...", flush=True)
                fix_summary = run_fix(
                    path=input_path,
                    rows=rows,
                    report=report,
                    client=client,
                    model_id=model_id,
                    model_env_var=model_env_var,
                    azure_cfg=azure_cfg,
                    max_retries=args.max_retries,
                    batch_size=max(1, args.fix_batch_size),
                    metadata_only=not args.allow_text_rewrite,
                    allow_drop=args.allow_drop,
                )
                fix_report_name = (
                    f"{input_path.stem}.{model_env_var.lower()}.llm_fix_report.json"
                )
                fix_out = out_dir / fix_report_name
                with fix_out.open("w", encoding="utf-8") as f:
                    json.dump(fix_summary, f, indent=2, ensure_ascii=False)
                print(
                    f"[{model_env_var}] Fix complete: "
                    f"fixed={fix_summary['fixed']} dropped={fix_summary['dropped']} "
                    f"rejected={fix_summary['rejected']} output_rows={fix_summary['output_rows']}",
                    flush=True,
                )
                print(f"[{model_env_var}] Fixed JSONL: {fix_summary['output_file']}", flush=True)
                print(f"[{model_env_var}] Fix report: {fix_out}", flush=True)


if __name__ == "__main__":
    main()
