"""Opus-in-the-Loop TrainingLabel auditor.

Uses Claude Opus 4.6 (AWS_MAX_MODEL) to review every included
TrainingLabel record, validating entities, assertions, values, SNOMED
codes, and span boundaries.  Applies safe auto-fixes and escalates
ambiguous issues for human review.

For entities flagged "needs_review" with SNOMED coding concerns a
second pass invokes Opus with Bedrock tool-use, delegating terminology
lookups to Haiku (AWS_SMALL_MODEL) via the internal Terminology API.
Cost guardrails (token budget + dollar cap) and a hard iteration cap
prevent runaway spending.  SNOMED fields are never auto-fixed.

Usage
-----
    # Dry-run (default) — audit only, no writes:
    python -m scripts.opus_training_auditor --limit 50

    # Apply safe auto-fixes:
    python -m scripts.opus_training_auditor --apply

    # Skip already-audited records on re-run:
    python -m scripts.opus_training_auditor --skip-audited --apply

    # Full options:
    python -m scripts.opus_training_auditor \\
        --limit 500 --offset 0 --apply --skip-audited

Environment variables
---------------------
    OPUS_AUDIT_WORKERS         Thread pool size (default: 5).
    OPUS_AUDIT_TOKEN_BUDGET    Max cumulative tokens for the run (default: 2_000_000).
    OPUS_AUDIT_COST_CAP        Max USD cost for the run (default: 50.0).
    TERMINOLOGY_API_URL        Terminology service base URL (default: http://localhost:8001).
    NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD
    AWS_DEFAULT_REGION         Bedrock region.
    AWS_MAX_MODEL              Override Opus model ID.
    AWS_SMALL_MODEL            Override Haiku model ID.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

_SECRETS = _REPO_ROOT / "secrets"
load_dotenv(_SECRETS / ".env.config", override=True)
load_dotenv(_SECRETS / ".env", override=False)

from libs.llm_client.factory import create_llm, LLMClient, LLMResponse
from libs.llm_client.prompt_safety import INJECTION_GUARD, sanitise_for_prompt
from libs.neo4j_client.client import PatientGraphClient
from libs.prompts.registry import get_prompt
from services.coding_worker.app.pipeline.sentence_splitter import SentenceSplitter, SentenceChunk

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("opus_training_auditor")

# ── Configuration ─────────────────────────────────────────────────────────────
MAX_WORKERS = int(os.getenv("OPUS_AUDIT_WORKERS", "5"))

# Fields the auditor may auto-fix when confidence >= SAFE_FIX_CONFIDENCE
SAFE_FIX_FIELDS = frozenset({
    "text",
    "assertion",
    "value", "unit", "reference_range",
    "label",
    "normalized",
})

SAFE_FIX_CONFIDENCE = 0.95

AUTOFIX_CAP_WINDOW = 100
AUTOFIX_CAP_RATIO = 0.30

# Fields that Opus must never suggest auto-fixes for; issues become proposals
READONLY_FIELDS = frozenset({
    "start", "end",
    "snomed_concept_id", "snomed_term", "read_code", "snomed_score",
    "decision_tier", "tier_decision", "tier_reason",
    "__sentence_id",
})

# Keywords in needs_review rationale that indicate a SNOMED coding concern
_SNOMED_KEYWORDS = frozenset({
    "snomed", "concept", "coding", "hierarchy", "terminology",
    "snomed_term", "snomed_concept_id",
})

# Agentic loop settings (DI-LEO-AI-054, R-LEO-AI-036)
MAX_TOOL_ITERATIONS = 5
TERMINOLOGY_API_URL = os.getenv("TERMINOLOGY_API_URL", "http://localhost:8001")
TOOL_HTTP_TIMEOUT = 10  # seconds

# Cost guardrail defaults (R-LEO-AI-036)
# Opus 4.6: ~$15/$75 per 1M tokens input/output (estimate)
# Haiku 4.5: ~$0.80/$4 per 1M tokens input/output (estimate)
_OPUS_IN_RATE = 15.0 / 1_000_000
_OPUS_OUT_RATE = 75.0 / 1_000_000
_HAIKU_IN_RATE = 0.80 / 1_000_000
_HAIKU_OUT_RATE = 4.0 / 1_000_000

# ── Cypher ────────────────────────────────────────────────────────────────────
FETCH_AUDIT_LABELS = """
MATCH (t:TrainingLabel)
WHERE t.include = true
  AND t.text IS NOT NULL
  AND t.entities_json IS NOT NULL
  {skip_audited_clause}
RETURN
    t.label_id       AS label_id,
    t.encounter_id   AS encounter_id,
    t.text           AS text,
    t.entities_json  AS entities_json,
    t.source         AS source,
    coalesce(t.quality_score, 0.0) AS quality_score
ORDER BY t.created_at ASC
{limit_clause}
{offset_clause}
"""

SET_AUDITED_AT = """
MATCH (t:TrainingLabel {label_id: $label_id})
SET t.audited_at = datetime()
RETURN t.label_id AS label_id
"""

UPDATE_ENTITIES = """
MATCH (t:TrainingLabel {label_id: $label_id})
SET t.entities_json = $entities_json,
    t.audited_at    = datetime(),
    t.updated_at    = datetime()
RETURN t.label_id AS label_id
"""


# ── Data structures ───────────────────────────────────────────────────────────
@dataclass
class AuditVerdict:
    label_id: str
    record_verdict: str
    entity_verdicts: list[dict[str, Any]]
    missing_entities: list[dict[str, Any]]
    auto_fixes_applied: list[dict[str, Any]] = field(default_factory=list)
    proposals: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0


# ── Cost Guardrail (R-LEO-AI-036) ────────────────────────────────────────────
class CostGuardrail:
    """Tracks cumulative token usage and estimated cost across a run.

    Halts further agentic processing when either budget is exceeded.
    Configurable via environment variables; uses conservative per-call
    estimates that treat all pass-1 tokens as Opus and pass-2 as mixed.
    """

    def __init__(
        self,
        token_budget: int | None = None,
        cost_cap: float | None = None,
    ) -> None:
        self._token_budget = token_budget if token_budget is not None else int(
            os.getenv("OPUS_AUDIT_TOKEN_BUDGET", "2000000")
        )
        self._cost_cap = cost_cap if cost_cap is not None else float(
            os.getenv("OPUS_AUDIT_COST_CAP", "50.0")
        )
        self._total_tokens: int = 0
        self._estimated_cost: float = 0.0
        self._halted = False

    def record(
        self,
        input_tokens: int,
        output_tokens: int,
        is_haiku: bool = False,
    ) -> None:
        """Register token usage from a single LLM call."""
        self._total_tokens += input_tokens + output_tokens
        in_rate = _HAIKU_IN_RATE if is_haiku else _OPUS_IN_RATE
        out_rate = _HAIKU_OUT_RATE if is_haiku else _OPUS_OUT_RATE
        self._estimated_cost += input_tokens * in_rate + output_tokens * out_rate

    def over_budget(self) -> bool:
        """Return True if either budget has been exceeded."""
        if self._halted:
            return True
        if self._total_tokens > self._token_budget:
            logger.warning(
                "COST GUARDRAIL: token budget exceeded (%d > %d). "
                "Halting agentic pass for remaining records.",
                self._total_tokens,
                self._token_budget,
            )
            self._halted = True
        if self._estimated_cost > self._cost_cap:
            logger.warning(
                "COST GUARDRAIL: dollar cap exceeded ($%.2f > $%.2f). "
                "Halting agentic pass for remaining records.",
                self._estimated_cost,
                self._cost_cap,
            )
            self._halted = True
        return self._halted

    @property
    def total_tokens(self) -> int:
        return self._total_tokens

    @property
    def estimated_cost(self) -> float:
        return self._estimated_cost


# ── Terminology API Tool Executor ─────────────────────────────────────────────
class ToolExecutor:
    """Wraps Terminology API endpoints as callable tools for the agentic loop.

    All HTTP errors are caught and returned as error dicts so the agentic
    loop can continue gracefully.  Responses are not sanitised here — the
    caller must pass them through sanitise_for_prompt() before LLM submission.
    """

    def __init__(self, base_url: str = TERMINOLOGY_API_URL, timeout: float = TOOL_HTTP_TIMEOUT) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def resolve_term(self, text: str, label: str) -> dict[str, Any]:
        """POST /terminology/resolve — find SNOMED candidates for a term."""
        import httpx
        body = {"text": text, "label": label, "limit": 5}
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.post(f"{self._base_url}/terminology/resolve", json=body)
                resp.raise_for_status()
                return {"candidates": resp.json()}
        except Exception as exc:
            logger.warning("ToolExecutor.resolve_term failed: %s", exc)
            return {"error": str(exc), "candidates": []}

    def get_related_concepts(self, concept_id: str) -> dict[str, Any]:
        """GET /concepts/{id}/related — retrieve related SNOMED concepts."""
        import httpx
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.get(f"{self._base_url}/concepts/{concept_id}/related")
                resp.raise_for_status()
                return {"related": resp.json()}
        except Exception as exc:
            logger.warning("ToolExecutor.get_related_concepts failed: %s", exc)
            return {"error": str(exc), "related": []}

    def get_descendants(self, concept_id: str, depth: int = 2) -> dict[str, Any]:
        """GET /concepts/{id}/descendants — retrieve descendant SNOMED concepts."""
        import httpx
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.get(
                    f"{self._base_url}/concepts/{concept_id}/descendants",
                    params={"depth": depth},
                )
                resp.raise_for_status()
                return {"descendants": resp.json()}
        except Exception as exc:
            logger.warning("ToolExecutor.get_descendants failed: %s", exc)
            return {"error": str(exc), "descendants": []}

    def execute(self, tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
        """Dispatch a tool call by name."""
        if tool_name == "resolve_term":
            return self.resolve_term(
                text=tool_input.get("text", ""),
                label=tool_input.get("label", ""),
            )
        if tool_name == "get_related_concepts":
            return self.get_related_concepts(
                concept_id=tool_input.get("concept_id", ""),
            )
        if tool_name == "get_descendants":
            return self.get_descendants(
                concept_id=tool_input.get("concept_id", ""),
                depth=int(tool_input.get("depth", 2)),
            )
        return {"error": f"Unknown tool: {tool_name}"}


# ── Bedrock toolConfig builder ────────────────────────────────────────────────
def _build_tool_config() -> dict[str, Any]:
    """Return the Bedrock toolConfig dict describing the three terminology tools."""
    return {
        "tools": [
            {
                "toolSpec": {
                    "name": "resolve_term",
                    "description": (
                        "Look up SNOMED CT candidates for a clinical term. "
                        "Use when the entity text does not match the coded snomed_term "
                        "and you need to find better matching concepts."
                    ),
                    "inputSchema": {
                        "json": {
                            "type": "object",
                            "properties": {
                                "text": {
                                    "type": "string",
                                    "description": "The clinical text to look up (e.g. 'Colposcopy biopsy')",
                                },
                                "label": {
                                    "type": "string",
                                    "description": "SNOMED semantic tag (e.g. 'procedure', 'disorder', 'finding')",
                                },
                            },
                            "required": ["text", "label"],
                        }
                    },
                }
            },
            {
                "toolSpec": {
                    "name": "get_related_concepts",
                    "description": (
                        "Retrieve SNOMED concepts related to a given concept ID. "
                        "Use to explore the neighbourhood of an existing code and "
                        "find semantically related (broader or narrower) concepts."
                    ),
                    "inputSchema": {
                        "json": {
                            "type": "object",
                            "properties": {
                                "concept_id": {
                                    "type": "string",
                                    "description": "SNOMED concept ID to look up (e.g. '392003006')",
                                },
                            },
                            "required": ["concept_id"],
                        }
                    },
                }
            },
            {
                "toolSpec": {
                    "name": "get_descendants",
                    "description": (
                        "Retrieve descendant (more specific) SNOMED concepts. "
                        "Use when the current code is too broad and you want to "
                        "identify more specific child concepts."
                    ),
                    "inputSchema": {
                        "json": {
                            "type": "object",
                            "properties": {
                                "concept_id": {
                                    "type": "string",
                                    "description": "SNOMED concept ID (e.g. '392003006')",
                                },
                                "depth": {
                                    "type": "integer",
                                    "description": "Hierarchy depth to retrieve (default 2)",
                                },
                            },
                            "required": ["concept_id"],
                        }
                    },
                }
            },
        ]
    }


# ── Entity format normalisation ───────────────────────────────────────────────
def _normalise_entity(ent: dict[str, Any]) -> dict[str, Any]:
    """Flatten nested 'coding' sub-object to top-level fields."""
    coding = ent.pop("coding", None)
    if isinstance(coding, dict):
        ent.setdefault("snomed_concept_id", coding.get("snomed_concept_id"))
        ent.setdefault("snomed_term", coding.get("snomed_term") or coding.get("term"))
        ent.setdefault("read_code", coding.get("read_code"))
        if "score" in coding and "snomed_score" not in ent:
            ent["snomed_score"] = coding["score"]
        if "semantic_tag" in coding and "label" not in ent:
            ent["label"] = coding["semantic_tag"]
    return ent


def _parse_entities(raw: str) -> list[dict[str, Any]]:
    """Parse entities_json string, normalising to flat format."""
    entities = json.loads(raw) if isinstance(raw, str) else raw
    return [_normalise_entity(e) for e in entities]


# ── JSON extraction from LLM response ────────────────────────────────────────
_JSON_KEYS = {"record_verdict", "entity_verdicts"}


def _extract_json(text: str) -> dict[str, Any]:
    """Extract JSON object from LLM response, tolerating markdown fences."""
    text = text.strip()
    if text.startswith("{"):
        return json.loads(text)
    import re
    m = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if m:
        return json.loads(m.group(1).strip())
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        return json.loads(text[start : end + 1])
    raise json.JSONDecodeError("No JSON object found in response", text, 0)


def _validate_verdict(data: dict[str, Any]) -> dict[str, Any]:
    """Validate the Opus verdict against expected schema."""
    if not isinstance(data, dict):
        raise ValueError("Verdict must be a JSON object")
    if "record_verdict" not in data:
        raise ValueError("Missing 'record_verdict'")
    if data["record_verdict"] not in ("pass", "has_issues"):
        raise ValueError(f"Invalid record_verdict: {data['record_verdict']}")
    if "entity_verdicts" not in data or not isinstance(data["entity_verdicts"], list):
        raise ValueError("Missing or invalid 'entity_verdicts'")
    for ev in data["entity_verdicts"]:
        if "entity_index" not in ev:
            raise ValueError("entity_verdict missing 'entity_index'")
        if ev.get("verdict") not in ("correct", "fixable", "needs_review", "remove"):
            raise ValueError(f"Invalid verdict: {ev.get('verdict')}")
    data.setdefault("missing_entities", [])
    return data


# ── Sentence-aware context builder ───────────────────────────────────────────
_splitter: SentenceSplitter | None = None


def _get_splitter() -> SentenceSplitter:
    global _splitter
    if _splitter is None:
        _splitter = SentenceSplitter()
    return _splitter


def _assign_sentence_ids(
    entities: list[dict[str, Any]],
    sentences: list[SentenceChunk],
) -> list[dict[str, Any]]:
    """Return entities with '__sentence_id' based on character offset overlap."""
    enriched = []
    for ent in entities:
        ent_start = int(ent.get("start") or 0)
        ent_end = int(ent.get("end") or 0)
        matched_id = None
        for sent in sentences:
            if ent_start < sent.end and ent_end > sent.start:
                matched_id = sent.sentence_id
                break
        enriched.append({**ent, "__sentence_id": matched_id})
    return enriched


# ── Core audit logic — Pass 1 (no tools) ─────────────────────────────────────
def _build_user_message(
    text: str,
    entities: list[dict[str, Any]],
    label_id: str,
    source: str,
    quality_score: float,
) -> str:
    splitter = _get_splitter()
    sentences = splitter.split(text)
    sentence_list = [
        {"sentence_id": s.sentence_id, "start": s.start, "end": s.end, "text": s.text}
        for s in sentences
    ]
    enriched_entities = _assign_sentence_ids(entities, sentences)

    return json.dumps({
        "label_id": label_id,
        "source": source,
        "quality_score": quality_score,
        "encounter_text": sanitise_for_prompt(text),
        "sentences": sentence_list,
        "entities_json": enriched_entities,
    }, indent=2)


def audit_record(
    client: LLMClient,
    system_prompt: str,
    row: dict[str, Any],
    max_retries: int = 3,
) -> AuditVerdict:
    """Pass 1: Send one TrainingLabel to Opus and parse the verdict (no tools)."""
    label_id = row["label_id"]
    try:
        entities = _parse_entities(row["entities_json"])
    except (json.JSONDecodeError, TypeError) as exc:
        return AuditVerdict(
            label_id=label_id,
            record_verdict="error",
            entity_verdicts=[],
            missing_entities=[],
            error=f"entities_json parse error: {exc}",
        )

    user_msg = _build_user_message(
        text=row["text"],
        entities=entities,
        label_id=label_id,
        source=row.get("source", ""),
        quality_score=row.get("quality_score", 0.0),
    )

    last_error = ""
    for attempt in range(max_retries):
        try:
            resp: LLMResponse = client.converse(
                system=system_prompt,
                messages=[{"role": "user", "content": user_msg}],
                max_tokens=4096,
                temperature=0.0,
            )
            parsed = _extract_json(resp.text)
            verdict_data = _validate_verdict(parsed)

            return AuditVerdict(
                label_id=label_id,
                record_verdict=verdict_data["record_verdict"],
                entity_verdicts=verdict_data["entity_verdicts"],
                missing_entities=verdict_data.get("missing_entities", []),
                input_tokens=resp.input_tokens,
                output_tokens=resp.output_tokens,
                cached_tokens=resp.cached_input_tokens,
            )
        except (json.JSONDecodeError, ValueError) as exc:
            last_error = f"Parse error (attempt {attempt + 1}): {exc}"
            logger.warning("%s for %s", last_error, label_id)
        except Exception as exc:
            last_error = f"LLM error (attempt {attempt + 1}): {exc}"
            logger.warning("%s for %s", last_error, label_id)
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)

    return AuditVerdict(
        label_id=label_id,
        record_verdict="error",
        entity_verdicts=[],
        missing_entities=[],
        error=last_error,
    )


# ── Pass 2: Agentic terminology tool-use loop ─────────────────────────────────
def _is_snomed_needs_review(entity_verdict: dict[str, Any]) -> bool:
    """Return True if this entity_verdict warrants a SNOMED terminology lookup."""
    if entity_verdict.get("verdict") != "needs_review":
        return False
    for issue in entity_verdict.get("issues", []):
        rationale = (issue.get("rationale") or "").lower()
        field_name = (issue.get("field") or "").lower()
        if field_name in ("snomed_term", "snomed_concept_id", "snomed_score", "read_code"):
            return True
        if any(kw in rationale for kw in _SNOMED_KEYWORDS):
            return True
    return False


def _agentic_audit_record(
    opus_client: LLMClient,
    system_prompt: str,
    row: dict[str, Any],
    entity_verdict: dict[str, Any],
    entities: list[dict[str, Any]],
    tool_executor: ToolExecutor,
    guardrail: CostGuardrail,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Run a tool-use loop for a single entity flagged as SNOMED needs_review.

    Returns:
        (updated_entity_verdict, tool_calls_log)
        tool_calls_log entries have keys: tool_name, tool_input, tool_result.
    """
    entity_idx = entity_verdict.get("entity_index", -1)
    entity = entities[entity_idx] if 0 <= entity_idx < len(entities) else {}

    # Build the focused re-audit message for this entity
    user_msg = json.dumps({
        "label_id": row["label_id"],
        "encounter_text": sanitise_for_prompt(row["text"]),
        "entity_index": entity_idx,
        "entity": entity,
        "pass_1_issues": entity_verdict.get("issues", []),
        "instruction": (
            "Use the available tools to look up SNOMED terminology and "
            "provide an informed recommendation for this entity. "
            "Return only the updated entity_verdict JSON object for this entity."
        ),
    }, indent=2)

    tool_config = _build_tool_config()
    messages: list[dict[str, Any]] = [{"role": "user", "content": user_msg}]
    tool_calls_log: list[dict[str, Any]] = []

    # Hard iteration cap (DI-LEO-AI-054, R-LEO-AI-036)
    for iteration in range(MAX_TOOL_ITERATIONS):
        resp = opus_client.converse(
            system=system_prompt,
            messages=messages,
            max_tokens=2048,
            temperature=0.0,
            tool_config=tool_config,
        )
        guardrail.record(resp.input_tokens, resp.output_tokens, is_haiku=False)

        # Append assistant turn (text + tool_use blocks)
        assistant_content: list[dict[str, Any]] = []
        if resp.text:
            assistant_content.append({"text": resp.text})
        for tu in resp.tool_uses:
            assistant_content.append({"toolUse": tu})
        if assistant_content:
            messages.append({"role": "assistant", "content": assistant_content})

        if resp.stop_reason != "tool_use" or not resp.tool_uses:
            # Model returned a final answer — extract verdict from resp.text
            break

        # Execute each requested tool (DI-LEO-AI-054 §sanitisation)
        tool_result_blocks: list[dict[str, Any]] = []
        for tu in resp.tool_uses:
            tool_name = tu.get("name", "")
            tool_input = tu.get("input", {})
            tool_use_id = tu.get("toolUseId", "")

            raw_result = tool_executor.execute(tool_name, tool_input)
            # Sanitise before re-submission to Opus (DI-LEO-AI-054, R-LEO-AI-037)
            result_text = sanitise_for_prompt(json.dumps(raw_result, default=str))

            tool_calls_log.append({
                "tool_name": tool_name,
                "tool_input": tool_input,
                "tool_result": result_text,
            })

            tool_result_blocks.append({
                "toolResult": {
                    "toolUseId": tool_use_id,
                    "content": [{"text": result_text}],
                }
            })

        # Append tool results as user turn
        messages.append({"role": "user", "content": tool_result_blocks})

    # Parse the final verdict from the last text response
    final_verdict = dict(entity_verdict)  # fallback: return pass-1 verdict unchanged
    if resp.text:
        try:
            parsed = _extract_json(resp.text)
            # If Opus returned a full entity_verdict object, use it
            if "verdict" in parsed and "entity_index" in parsed:
                final_verdict = parsed
            elif "entity_verdicts" in parsed:
                # Full record verdict — extract the matching entity
                for ev in parsed["entity_verdicts"]:
                    if ev.get("entity_index") == entity_idx:
                        final_verdict = ev
                        break
        except (json.JSONDecodeError, ValueError):
            logger.warning(
                "Agentic pass: could not parse Opus response for entity[%d] in %s",
                entity_idx,
                row["label_id"],
            )

    return final_verdict, tool_calls_log


def _pass_two(
    pass_one_verdict: AuditVerdict,
    row: dict[str, Any],
    entities: list[dict[str, Any]],
    opus_client: LLMClient,
    system_prompt: str,
    tool_executor: ToolExecutor,
    guardrail: CostGuardrail,
) -> AuditVerdict:
    """Run agentic tool-use for SNOMED needs_review entities from pass 1.

    Filters entity_verdicts to those flagged as SNOMED-related needs_review,
    runs _agentic_audit_record for each (if guardrail allows), merges results
    back into the verdict.
    """
    if guardrail.over_budget():
        return pass_one_verdict

    updated_verdicts = list(pass_one_verdict.entity_verdicts)
    all_tool_calls: list[dict[str, Any]] = list(pass_one_verdict.tool_calls)

    for i, ev in enumerate(pass_one_verdict.entity_verdicts):
        if not _is_snomed_needs_review(ev):
            continue
        if guardrail.over_budget():
            logger.warning(
                "Cost guardrail halted pass 2 mid-record for %s at entity[%d]",
                pass_one_verdict.label_id,
                ev.get("entity_index", -1),
            )
            break

        try:
            updated_ev, tool_calls = _agentic_audit_record(
                opus_client=opus_client,
                system_prompt=system_prompt,
                row=row,
                entity_verdict=ev,
                entities=entities,
                tool_executor=tool_executor,
                guardrail=guardrail,
            )
            updated_verdicts[i] = updated_ev
            all_tool_calls.extend(tool_calls)
        except Exception as exc:
            logger.warning(
                "Agentic pass failed for entity[%d] in %s: %s",
                ev.get("entity_index", -1),
                pass_one_verdict.label_id,
                exc,
            )

    return AuditVerdict(
        label_id=pass_one_verdict.label_id,
        record_verdict=pass_one_verdict.record_verdict,
        entity_verdicts=updated_verdicts,
        missing_entities=pass_one_verdict.missing_entities,
        auto_fixes_applied=pass_one_verdict.auto_fixes_applied,
        proposals=pass_one_verdict.proposals,
        tool_calls=all_tool_calls,
        error=pass_one_verdict.error,
        input_tokens=pass_one_verdict.input_tokens,
        output_tokens=pass_one_verdict.output_tokens,
        cached_tokens=pass_one_verdict.cached_tokens,
    )


# ── Auto-fix logic ───────────────────────────────────────────────────────────
def _classify_fixes(verdict: AuditVerdict) -> None:
    """Classify issues into auto_fixes_applied vs proposals."""
    for ev in verdict.entity_verdicts:
        if ev["verdict"] not in ("fixable", "remove"):
            continue
        for issue in ev.get("issues", []):
            fld = issue.get("field", "")
            if fld in READONLY_FIELDS or fld.startswith("__"):
                verdict.proposals.append({
                    "entity_index": ev["entity_index"],
                    "verdict": "needs_review",
                    **issue,
                })
                continue
            entry = {
                "entity_index": ev["entity_index"],
                "verdict": ev["verdict"],
                **issue,
            }
            is_safe = (
                ev["verdict"] == "fixable"
                and fld in SAFE_FIX_FIELDS
                and issue.get("confidence", 0) >= SAFE_FIX_CONFIDENCE
                and issue.get("suggested") is not None
            )
            if is_safe:
                verdict.auto_fixes_applied.append(entry)
            else:
                verdict.proposals.append(entry)

    for me in verdict.missing_entities:
        verdict.proposals.append({
            "entity_index": -1,
            "verdict": "missing",
            **me,
        })


def _apply_fixes(
    entities: list[dict[str, Any]],
    fixes: list[dict[str, Any]],
    encounter_text: str,
) -> list[dict[str, Any]]:
    """Apply safe auto-fixes to entities (returns a new copy).

    When 'text' is changed, recomputes start/end via str.find().
    Strips audit-only __ prefixed keys before returning.
    """
    entities = [dict(e) for e in entities]
    for fix in fixes:
        idx = fix.get("entity_index", -1)
        fld = fix.get("field")
        suggested = fix.get("suggested")
        if 0 <= idx < len(entities) and fld and suggested is not None:
            entities[idx][fld] = suggested
            if fld == "text" and isinstance(suggested, str):
                old_start = int(entities[idx].get("start") or 0)
                new_start = encounter_text.find(suggested, max(0, old_start - 20))
                if new_start < 0:
                    new_start = encounter_text.find(suggested)
                if new_start >= 0:
                    entities[idx]["start"] = new_start
                    entities[idx]["end"] = new_start + len(suggested)
    return [{k: v for k, v in e.items() if not k.startswith("__")} for e in entities]


# ── Audit trail (JSONL) ───────────────────────────────────────────────────────
def _write_trail_entry(
    trail_path: Path,
    verdict: AuditVerdict,
    applied: bool,
) -> None:
    entry = {
        "label_id": verdict.label_id,
        "record_verdict": verdict.record_verdict,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "applied": applied,
        "auto_fixes": verdict.auto_fixes_applied,
        "proposals": verdict.proposals,
        "missing_entities": verdict.missing_entities,
        "entity_verdicts": verdict.entity_verdicts,
        "tool_calls": verdict.tool_calls,
        "input_tokens": verdict.input_tokens,
        "output_tokens": verdict.output_tokens,
        "cached_tokens": verdict.cached_tokens,
        "error": verdict.error,
    }
    with open(trail_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, default=str) + "\n")


# ── Auto-fix cap check ────────────────────────────────────────────────────────
class AutoFixCapMonitor:
    """Sliding-window monitor for auto-fix rate."""

    def __init__(self, window: int = AUTOFIX_CAP_WINDOW, ratio: float = AUTOFIX_CAP_RATIO):
        self._window = window
        self._ratio = ratio
        self._history: list[tuple[int, int]] = []
        self.triggered = False

    def record(self, entity_count: int, fix_count: int) -> bool:
        self._history.append((entity_count, fix_count))
        if len(self._history) > self._window:
            self._history = self._history[-self._window:]
        total_entities = sum(e for e, _ in self._history)
        total_fixes = sum(f for _, f in self._history)
        if total_entities > 0 and total_fixes / total_entities > self._ratio:
            self.triggered = True
            return True
        return False


# ── Report generation ─────────────────────────────────────────────────────────
def _generate_report(
    verdicts: list[AuditVerdict],
    report_path: Path,
    applied: bool,
    elapsed_s: float,
    guardrail: CostGuardrail,
) -> None:
    total = len(verdicts)
    errors = sum(1 for v in verdicts if v.error)
    passed = sum(1 for v in verdicts if v.record_verdict == "pass")
    has_issues = sum(1 for v in verdicts if v.record_verdict == "has_issues")

    verdict_counts: Counter[str] = Counter()
    for v in verdicts:
        for ev in v.entity_verdicts:
            verdict_counts[ev["verdict"]] += 1

    total_auto_fixes = sum(len(v.auto_fixes_applied) for v in verdicts)
    total_proposals = sum(len(v.proposals) for v in verdicts)
    total_tool_calls = sum(len(v.tool_calls) for v in verdicts)

    total_input = sum(v.input_tokens for v in verdicts)
    total_output = sum(v.output_tokens for v in verdicts)
    total_cached = sum(v.cached_tokens for v in verdicts)

    fix_field_counts: Counter[str] = Counter()
    for v in verdicts:
        for fix in v.auto_fixes_applied:
            fix_field_counts[fix.get("field", "unknown")] += 1

    proposal_type_counts: Counter[str] = Counter()
    for v in verdicts:
        for p in v.proposals:
            proposal_type_counts[p.get("verdict", "unknown")] += 1

    sample_fixes: list[dict] = []
    sample_proposals: list[dict] = []
    sample_reviews: list[dict] = []
    sample_tool_calls: list[dict] = []
    for v in verdicts:
        if len(sample_fixes) < 10:
            for fix in v.auto_fixes_applied:
                sample_fixes.append({"label_id": v.label_id, **fix})
                if len(sample_fixes) >= 10:
                    break
        if len(sample_proposals) < 10:
            for p in v.proposals:
                sample_proposals.append({"label_id": v.label_id, **p})
                if len(sample_proposals) >= 10:
                    break
        if len(sample_reviews) < 10:
            for ev in v.entity_verdicts:
                if ev["verdict"] == "needs_review":
                    sample_reviews.append({"label_id": v.label_id, **ev})
                    if len(sample_reviews) >= 10:
                        break
        if len(sample_tool_calls) < 5:
            for tc in v.tool_calls:
                sample_tool_calls.append({"label_id": v.label_id, **tc})
                if len(sample_tool_calls) >= 5:
                    break

    lines = [
        "# Opus Training Label Audit Report",
        "",
        f"**Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}  ",
        f"**Mode:** {'APPLY' if applied else 'DRY-RUN'}  ",
        f"**Records audited:** {total}  ",
        f"**Elapsed:** {elapsed_s:.0f}s ({elapsed_s / max(total, 1):.1f}s/record)  ",
        "",
        "## Summary",
        "",
        "| Metric | Count |",
        "|--------|-------|",
        f"| Records passed | {passed} |",
        f"| Records with issues | {has_issues} |",
        f"| Errors (parse/LLM) | {errors} |",
        f"| Total auto-fixes | {total_auto_fixes} |",
        f"| Total proposals (human review) | {total_proposals} |",
        f"| Total agentic tool calls | {total_tool_calls} |",
        "",
        "## Entity Verdict Breakdown",
        "",
        "| Verdict | Count |",
        "|---------|-------|",
    ]
    for verdict_type in ("correct", "fixable", "needs_review", "remove"):
        lines.append(f"| {verdict_type} | {verdict_counts.get(verdict_type, 0)} |")
    lines.append("")

    if fix_field_counts:
        lines.extend([
            "## Auto-Fix Field Breakdown",
            "",
            "| Field | Count |",
            "|-------|-------|",
        ])
        for fld, cnt in fix_field_counts.most_common():
            lines.append(f"| {fld} | {cnt} |")
        lines.append("")

    if proposal_type_counts:
        lines.extend([
            "## Proposal Type Breakdown",
            "",
            "| Type | Count |",
            "|------|-------|",
        ])
        for ptype, cnt in proposal_type_counts.most_common():
            lines.append(f"| {ptype} | {cnt} |")
        lines.append("")

    lines.extend([
        "## Token Usage & Cost",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total input tokens | {total_input:,} |",
        f"| Total output tokens | {total_output:,} |",
        f"| Cached input tokens | {total_cached:,} |",
        f"| Guardrail total tokens | {guardrail.total_tokens:,} |",
        f"| Estimated cost | ${guardrail.estimated_cost:.2f} |",
        "",
    ])

    if sample_fixes:
        lines.extend(["## Sample Auto-Fixes (up to 10)", ""])
        for sf in sample_fixes:
            lines.append(
                f"- **{sf['label_id'][:12]}...** entity[{sf.get('entity_index')}] "
                f"`{sf.get('field')}`: `{sf.get('current')}` -> `{sf.get('suggested')}` "
                f"(conf={sf.get('confidence', 0):.2f}) -- {sf.get('rationale', '')}"
            )
        lines.append("")

    if sample_proposals:
        lines.extend(["## Sample Proposals for Human Review (up to 10)", ""])
        for sp in sample_proposals:
            if sp.get("verdict") == "missing":
                lines.append(
                    f"- **{sp['label_id'][:12]}...** MISSING: `{sp.get('text')}` "
                    f"({sp.get('label')}, {sp.get('assertion')}) "
                    f"conf={sp.get('confidence', 0):.2f} -- {sp.get('rationale', '')}"
                )
            else:
                lines.append(
                    f"- **{sp['label_id'][:12]}...** entity[{sp.get('entity_index')}] "
                    f"`{sp.get('field')}`: `{sp.get('current')}` -> `{sp.get('suggested')}` "
                    f"(conf={sp.get('confidence', 0):.2f}) -- {sp.get('rationale', '')}"
                )
        lines.append("")

    if sample_reviews:
        lines.extend(["## Sample Needs-Review (up to 10)", ""])
        for sr in sample_reviews:
            issues_str = "; ".join(
                f"{i.get('field')}: {i.get('rationale', '')}"
                for i in sr.get("issues", [])
            )
            lines.append(
                f"- **{sr['label_id'][:12]}...** entity[{sr.get('entity_index')}] "
                f"-- {issues_str}"
            )
        lines.append("")

    if sample_tool_calls:
        lines.extend(["## Sample Agentic Tool Calls (up to 5)", ""])
        for tc in sample_tool_calls:
            lines.append(
                f"- **{tc['label_id'][:12]}...** `{tc.get('tool_name')}` "
                f"input={json.dumps(tc.get('tool_input', {}))}"
            )
        lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Report written to %s", report_path)


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Opus-in-the-Loop TrainingLabel auditor"
    )
    parser.add_argument("--limit", type=int, default=0, help="Max records (0=all)")
    parser.add_argument("--offset", type=int, default=0, help="Skip first N records")
    parser.add_argument("--apply", action="store_true", help="Write fixes to Neo4j")
    parser.add_argument("--skip-audited", action="store_true", help="Skip audited records")
    parser.add_argument("--workers", type=int, default=MAX_WORKERS, help="Thread pool size")
    parser.add_argument(
        "--no-agentic", action="store_true",
        help="Skip pass 2 (no tool-use); useful for cost-constrained runs",
    )
    args = parser.parse_args()

    mode_label = "APPLY" if args.apply else "DRY-RUN"
    logger.info("=== Opus Training Label Auditor [%s] ===", mode_label)

    skip_clause = "AND t.audited_at IS NULL" if args.skip_audited else ""
    limit_clause = f"LIMIT {args.limit}" if args.limit else ""
    offset_clause = f"SKIP {args.offset}" if args.offset else ""
    query = FETCH_AUDIT_LABELS.format(
        skip_audited_clause=skip_clause,
        limit_clause=limit_clause,
        offset_clause=offset_clause,
    )

    neo4j = PatientGraphClient()
    try:
        rows = neo4j.run(query)
    except Exception as exc:
        logger.error("Failed to fetch TrainingLabels: %s", exc)
        sys.exit(1)

    total = len(rows)
    logger.info("Fetched %d records to audit", total)
    if total == 0:
        logger.info("Nothing to audit -- exiting.")
        neo4j.close()
        return

    logger.info("Initialising sentence splitter...")
    _get_splitter()
    logger.info("Sentence splitter ready (mode: %s)", _get_splitter().mode)

    opus = create_llm(provider="aws", tier="max")
    system_prompt = INJECTION_GUARD + get_prompt("opus_audit", version=1)
    logger.info("Using Opus model: %s", opus.model_id)

    tool_executor = ToolExecutor()
    guardrail = CostGuardrail()
    logger.info(
        "Cost guardrail: token_budget=%d, cost_cap=$%.2f",
        guardrail._token_budget,
        guardrail._cost_cap,
    )

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    scripts_dir = Path(__file__).resolve().parent
    trail_path = scripts_dir / f"opus_audit_trail_{ts}.jsonl"
    report_path = scripts_dir / f"opus_audit_report_{ts}.md"

    verdicts: list[AuditVerdict] = []
    cap_monitor = AutoFixCapMonitor()
    cap_triggered_at: int | None = None
    t_start = time.monotonic()

    def _process_one(row: dict[str, Any]) -> AuditVerdict:
        return audit_record(opus, system_prompt, row)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        future_to_row = {pool.submit(_process_one, row): row for row in rows}
        for i, future in enumerate(as_completed(future_to_row), 1):
            row = future_to_row[future]
            label_id = row["label_id"]

            try:
                verdict = future.result()
            except Exception as exc:
                verdict = AuditVerdict(
                    label_id=label_id,
                    record_verdict="error",
                    entity_verdicts=[],
                    missing_entities=[],
                    error=str(exc),
                )

            # Update pass-1 guardrail tracking
            guardrail.record(verdict.input_tokens, verdict.output_tokens, is_haiku=False)

            # Pass 2: agentic tool-use for SNOMED needs_review
            if not args.no_agentic and not verdict.error:
                try:
                    entities = _parse_entities(row["entities_json"])
                except Exception:
                    entities = []
                verdict = _pass_two(
                    pass_one_verdict=verdict,
                    row=row,
                    entities=entities,
                    opus_client=opus,
                    system_prompt=system_prompt,
                    tool_executor=tool_executor,
                    guardrail=guardrail,
                )

            _classify_fixes(verdict)

            try:
                entities = _parse_entities(row["entities_json"])
                entity_count = len(entities)
            except Exception:
                entity_count = 0
            fix_count = len(verdict.auto_fixes_applied)

            if cap_monitor.record(entity_count, fix_count) and cap_triggered_at is None:
                cap_triggered_at = i
                logger.warning(
                    "AUTO-FIX CAP TRIGGERED at record %d/%d -- "
                    ">%.0f%% of entities in last %d records received auto-fixes. "
                    "Continuing audit but SUSPENDING auto-fix writes.",
                    i, total, cap_monitor._ratio * 100, cap_monitor._window,
                )

            applied_this_record = False
            if args.apply and verdict.auto_fixes_applied and cap_triggered_at is None:
                try:
                    fixed_entities = _apply_fixes(entities, verdict.auto_fixes_applied, row["text"])
                    neo4j.run(
                        UPDATE_ENTITIES,
                        label_id=label_id,
                        entities_json=json.dumps(fixed_entities),
                    )
                    applied_this_record = True
                except Exception as exc:
                    logger.error("Failed to write fixes for %s: %s", label_id, exc)
            else:
                try:
                    neo4j.run(SET_AUDITED_AT, label_id=label_id)
                except Exception as exc:
                    logger.warning("Failed to set audited_at for %s: %s", label_id, exc)

            _write_trail_entry(trail_path, verdict, applied=applied_this_record)
            verdicts.append(verdict)

            if i % 50 == 0 or i == total:
                elapsed = time.monotonic() - t_start
                rate = i / elapsed if elapsed > 0 else 0
                tool_total = sum(len(v.tool_calls) for v in verdicts)
                logger.info(
                    "Progress: %d/%d (%.1f rec/s) | pass=%d issues=%d errors=%d "
                    "fixes=%d proposals=%d tools=%d cost=$%.2f",
                    i, total, rate,
                    sum(1 for v in verdicts if v.record_verdict == "pass"),
                    sum(1 for v in verdicts if v.record_verdict == "has_issues"),
                    sum(1 for v in verdicts if v.error),
                    sum(len(v.auto_fixes_applied) for v in verdicts),
                    sum(len(v.proposals) for v in verdicts),
                    tool_total,
                    guardrail.estimated_cost,
                )

    elapsed_s = time.monotonic() - t_start
    logger.info("Audit complete in %.0fs", elapsed_s)

    _generate_report(verdicts, report_path, applied=args.apply, elapsed_s=elapsed_s, guardrail=guardrail)
    logger.info("Audit trail: %s", trail_path)

    if cap_triggered_at is not None:
        logger.warning(
            "AUTO-FIX CAP was triggered at record %d. Review the audit trail "
            "for systemic issues before re-running with --apply.",
            cap_triggered_at,
        )

    neo4j.close()


if __name__ == "__main__":
    main()
