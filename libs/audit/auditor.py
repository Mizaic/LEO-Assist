"""Core Agentic Auditor — shared library.

Used by both the CLI script (scripts/agentic_auditor.py) and the
API background runner (services/api/app/services/agentic_audit_service.py).

All stateless classes, data structures, Cypher queries, and processing
functions live here.  I/O (file writing, argparse, job-state management)
is the responsibility of the caller.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

from libs.llm_client.factory import create_llm, LLMClient, LLMResponse  # noqa: F401
from libs.llm_client.prompt_safety import INJECTION_GUARD, sanitise_for_prompt
from libs.prompts.registry import get_prompt  # noqa: F401

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

MAX_WORKERS = int(os.getenv("AUDIT_WORKERS", "5"))

SAFE_FIX_FIELDS = frozenset({
    "text",
    "assertion",
    "value", "unit", "reference_range",
    "label",
    "normalized",
})

# Additional fields unlocked only in pass 2 when the Terminology API
# and a second-opinion model both agree on the corrected SNOMED concept.
AGENTIC_FIX_FIELDS = SAFE_FIX_FIELDS | frozenset({
    "snomed_concept_id",
    "snomed_term",
    "read_code",
    "snomed_score",
})

SAFE_FIX_CONFIDENCE = 0.95
AUTOFIX_CAP_WINDOW = 100
AUTOFIX_CAP_RATIO = 0.30

READONLY_FIELDS = frozenset({
    "start", "end",
    "snomed_concept_id", "snomed_term", "read_code", "snomed_score",
    "decision_tier", "tier_decision", "tier_reason",
    "__sentence_id",
})

_SNOMED_KEYWORDS = frozenset({
    "snomed", "concept", "coding", "hierarchy", "terminology",
    "snomed_term", "snomed_concept_id",
})

MAX_TOOL_ITERATIONS = 5
TERMINOLOGY_API_URL = os.getenv("TERMINOLOGY_API_URL", "http://localhost:8001")
TOOL_HTTP_TIMEOUT = 10  # seconds

# Cost rates read from env vars so they stay in sync with secrets/.env.
# AUDIT_PROVIDER env var switches between AWS and Azure rate tables.
_AUDIT_PROVIDER = os.getenv("AUDIT_COST_PROVIDER", "aws")
if _AUDIT_PROVIDER == "azure":
    _AUDIT_IN_RATE  = float(os.getenv("AZURE_OPENAI_BIG_MODEL_COST_PER_1M_INPUT_TOKEN",  "1.25")) / 1_000_000
    _AUDIT_OUT_RATE = float(os.getenv("AZURE_OPENAI_BIG_MODEL_COST_PER_1M_OUTPUT_TOKEN", "10.0")) / 1_000_000
else:
    _AUDIT_IN_RATE  = float(os.getenv("AWS_BEDROCK_MODEL_BIG_MODEL_COST_PER_1M_INPUT_TOKEN",  "3.0"))  / 1_000_000
    _AUDIT_OUT_RATE = float(os.getenv("AWS_BEDROCK_MODEL_BIG_MODEL_COST_PER_1M_OUTPUT_TOKEN", "15.0")) / 1_000_000
_HAIKU_IN_RATE  = float(os.getenv("AWS_BEDROCK_MODEL_SMALL_MODEL_COST_PER_1M_INPUT_TOKEN",  "1.0")) / 1_000_000
_HAIKU_OUT_RATE = float(os.getenv("AWS_BEDROCK_MODEL_SMALL_MODEL_COST_PER_1M_OUTPUT_TOKEN", "5.0")) / 1_000_000

# ── Cypher ────────────────────────────────────────────────────────────────────

FETCH_AUDIT_LABELS = """
MATCH (t:TrainingLabel)
WHERE t.include = true
  AND t.text IS NOT NULL
  AND t.entities_json IS NOT NULL
  {skip_audited_clause}
  {hitl_ids_clause}
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

FETCH_HITL_PENDING_LABEL_IDS = """
MATCH (r:LabelVerificationReview)-[:REVIEWS_LABEL]->(t:TrainingLabel)
WHERE coalesce(r.resolved, false) = false
  AND t.include = true
RETURN DISTINCT t.label_id AS label_id
"""

SET_AUDITED_AT = """
MATCH (t:TrainingLabel {label_id: $label_id})
SET t.audited_at = datetime()
RETURN t.label_id AS label_id
"""

UPDATE_ENTITIES = """
MATCH (t:TrainingLabel {label_id: $label_id})
SET t.entities_json  = $entities_json,
    t.audited_at     = datetime(),
    t.updated_at     = datetime(),
    t.audit_actions  = $audit_actions,
    t.audit_model    = $audit_model
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
    Configurable via environment variables.
    """

    def __init__(
        self,
        token_budget: int | None = None,
        cost_cap: float | None = None,
    ) -> None:
        self._token_budget = token_budget if token_budget is not None else int(
            os.getenv("AUDIT_TOKEN_BUDGET", "2000000")
        )
        self._cost_cap = cost_cap if cost_cap is not None else float(
            os.getenv("AUDIT_COST_CAP", "50.0")
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
        self._total_tokens += input_tokens + output_tokens
        in_rate  = _HAIKU_IN_RATE  if is_haiku else _AUDIT_IN_RATE
        out_rate = _HAIKU_OUT_RATE if is_haiku else _AUDIT_OUT_RATE
        self._estimated_cost += input_tokens * in_rate + output_tokens * out_rate

    def over_budget(self) -> bool:
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


# ── Blind Second-Opinion Provider ─────────────────────────────────────────────

_SECOND_OPINION_SYSTEM = (
    "You are an independent clinical NLP entity reviewer. "
    "You will be shown a clinical encounter text passage and a single extracted "
    "clinical entity. Your task is to answer the question about this entity based "
    "solely on the clinical text and entity data shown to you. "
    "Do not speculate beyond the evidence in the text. Be concise and factual. "
    "Do not reference any prior analysis or audit — this is your own independent assessment."
)


class SecondOpinionProvider:
    """Solicits a blind second opinion from the small model without any primary-model reasoning context.

    The secondary model receives ONLY the original clinical text, the entity data,
    and the neutral question.  The primary model's current verdict, reasoning, prior tool call
    history, and pass-1 issues are NEVER included, preventing anchoring bias
    (DI-LEO-AI-054 §second-opinion, R-LEO-AI-037).

    Safety constraints:
    - All inputs sanitised with sanitise_for_prompt() before transmission.
    - Internal audit fields (__ prefix) stripped from entity data.
    - INJECTION_GUARD prepended to the Haiku system prompt.
    - CostGuardrail checked before every call.
    """

    def __init__(self, guardrail: CostGuardrail) -> None:
        self._guardrail = guardrail
        self._haiku: LLMClient | None = None

    def _get_haiku(self) -> LLMClient:
        if self._haiku is None:
            self._haiku = create_llm(provider="aws", tier="small")
        return self._haiku

    def get_opinion(
        self,
        clinical_text: str,
        entity: dict[str, Any],
        question: str,
    ) -> dict[str, Any]:
        """Ask Haiku for an independent entity assessment.

        Returns dict with 'opinion' on success, 'error' on failure or budget halt.
        The question is sanitised to strip any potential primary-model verdict leakage.
        """
        if self._guardrail.over_budget():
            return {"error": "Cost guardrail halted — second opinion skipped"}

        # Strip internal audit fields so the secondary model sees only original data
        clean_entity = {k: v for k, v in entity.items() if not k.startswith("__")}

        safe_text     = sanitise_for_prompt(clinical_text)
        safe_entity   = sanitise_for_prompt(json.dumps(clean_entity, default=str))
        safe_question = sanitise_for_prompt(question)

        user_msg = json.dumps(
            {
                "clinical_text": safe_text,
                "entity": safe_entity,
                "question": safe_question,
            },
            indent=2,
        )

        try:
            haiku = self._get_haiku()
            resp = haiku.converse(
                system=INJECTION_GUARD + _SECOND_OPINION_SYSTEM,
                messages=[{"role": "user", "content": user_msg}],
                max_tokens=512,
                temperature=0.0,
            )
            self._guardrail.record(resp.input_tokens, resp.output_tokens, is_haiku=True)
            return {"opinion": resp.text, "model": "haiku_independent"}
        except Exception as exc:
            logger.warning("SecondOpinionProvider failed: %s", exc)
            return {"error": str(exc)}


# ── Terminology API Tool Executor ─────────────────────────────────────────────

class ToolExecutor:
    """Wraps Terminology API endpoints and the second-opinion provider as callable tools.

    All HTTP errors are caught and returned as error dicts so the agentic
    loop can continue gracefully.  Responses are not sanitised here — the
    caller must pass them through sanitise_for_prompt() before LLM submission.
    """

    def __init__(
        self,
        base_url: str = TERMINOLOGY_API_URL,
        timeout: float = TOOL_HTTP_TIMEOUT,
        second_opinion: SecondOpinionProvider | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._second_opinion = second_opinion

    def resolve_term(self, text: str, label: str) -> dict[str, Any]:
        """POST /terminology/resolve — find SNOMED candidates for a term."""
        import httpx
        body: dict[str, Any] = {"terms": [text]}
        if label:
            body["expected_tags"] = {text: label}
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.post(f"{self._base_url}/terminology/resolve", json=body)
                resp.raise_for_status()
                data = resp.json()
                candidates = data.get("results", {}).get(text, [])
                return {"candidates": candidates[:5]}
        except Exception as exc:
            logger.warning("ToolExecutor.resolve_term failed: %s", exc)
            return {"error": str(exc), "candidates": []}

    def get_related_concepts(self, concept_id: str) -> dict[str, Any]:
        """GET /terminology/concepts/{id}/related — retrieve related SNOMED concepts."""
        import httpx
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.get(
                    f"{self._base_url}/terminology/concepts/{concept_id}/related"
                )
                resp.raise_for_status()
                return {"related": resp.json()}
        except Exception as exc:
            logger.warning("ToolExecutor.get_related_concepts failed: %s", exc)
            return {"error": str(exc), "related": []}

    def get_descendants(self, concept_id: str, depth: int = 2) -> dict[str, Any]:
        """GET /terminology/concepts/{id}/descendants — retrieve descendant SNOMED concepts."""
        import httpx
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.get(
                    f"{self._base_url}/terminology/concepts/{concept_id}/descendants",
                    params={"depth": depth},
                )
                resp.raise_for_status()
                return {"descendants": resp.json()}
        except Exception as exc:
            logger.warning("ToolExecutor.get_descendants failed: %s", exc)
            return {"error": str(exc), "descendants": []}

    def execute(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Dispatch a tool call by name.

        context may supply {'row': dict, 'entities': list} for get_second_opinion.
        """
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
        if tool_name == "get_second_opinion":
            if self._second_opinion is None:
                return {"error": "Second opinion provider not configured"}
            entity_idx = int(tool_input.get("entity_index", -1))
            question   = str(tool_input.get("question", ""))
            entities   = (context or {}).get("entities", [])
            row        = (context or {}).get("row", {})
            entity     = entities[entity_idx] if 0 <= entity_idx < len(entities) else {}
            return self._second_opinion.get_opinion(
                clinical_text=row.get("text", ""),
                entity=entity,
                question=question,
            )
        return {"error": f"Unknown tool: {tool_name}"}


# ── Bedrock toolConfig builder ────────────────────────────────────────────────

def _build_tool_config() -> dict[str, Any]:
    """Return the Bedrock toolConfig dict describing all four audit tools."""
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
            {
                "toolSpec": {
                    "name": "get_second_opinion",
                    "description": (
                        "Ask an independent model (which has NO access to your analysis, "
                        "reasoning, or current verdict) to assess an entity. "
                        "Use when you are genuinely uncertain and want an unbiased view. "
                        "CRITICAL: your question MUST be factual and neutral — "
                        "do NOT reveal your verdict, suspicions, or reasoning in the question. "
                        "Example good question: 'Is the assertion on this entity consistent "
                        "with the surrounding sentence?' "
                        "Example bad question: 'Don't you think this should be absent?' "
                        "(reveals your verdict)."
                    ),
                    "inputSchema": {
                        "json": {
                            "type": "object",
                            "properties": {
                                "entity_index": {
                                    "type": "integer",
                                    "description": "0-based index of the entity to review",
                                },
                                "question": {
                                    "type": "string",
                                    "description": (
                                        "A neutral factual question about the entity. "
                                        "Must not contain your verdict or reasoning."
                                    ),
                                },
                            },
                            "required": ["entity_index", "question"],
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
    import re
    text = text.strip()
    if text.startswith("{"):
        return json.loads(text)
    m = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if m:
        return json.loads(m.group(1).strip())
    start = text.find("{")
    end   = text.rfind("}")
    if start != -1 and end > start:
        return json.loads(text[start : end + 1])
    raise json.JSONDecodeError("No JSON object found in response", text, 0)


def _validate_verdict(data: dict[str, Any]) -> dict[str, Any]:
    """Validate the auditor verdict against expected schema."""
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

_splitter = None


def _get_splitter():
    global _splitter
    if _splitter is None:
        from services.coding_worker.app.pipeline.sentence_splitter import SentenceSplitter
        _splitter = SentenceSplitter()
    return _splitter


def _assign_sentence_ids(
    entities: list[dict[str, Any]],
    sentences: list,
) -> list[dict[str, Any]]:
    """Return entities with '__sentence_id' based on character offset overlap."""
    enriched = []
    for ent in entities:
        ent_start = int(ent.get("start") or 0)
        ent_end   = int(ent.get("end")   or 0)
        matched_id = None
        for sent in sentences:
            if ent_start < sent.end and ent_end > sent.start:
                matched_id = sent.sentence_id
                break
        enriched.append({**ent, "__sentence_id": matched_id})
    return enriched


def _sentences_from_entities(
    text: str,
    entities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Reconstruct sentence list from entity offsets when __sentence_id is already set.

    Groups entities by their existing __sentence_id and uses the min/max character
    offsets to slice sentence text from the encounter text directly, avoiding the
    sentence-splitter entirely.
    """
    from collections import defaultdict
    buckets: dict[int, list[dict]] = defaultdict(list)
    for ent in entities:
        sid = ent.get("__sentence_id")
        if sid is not None:
            buckets[int(sid)].append(ent)

    sentences = []
    for sid in sorted(buckets):
        group = buckets[sid]
        s_start = min(int(e.get("start") or 0) for e in group)
        s_end   = max(int(e.get("end")   or 0) for e in group)
        sentences.append({
            "sentence_id": sid,
            "start": s_start,
            "end":   s_end,
            "text":  text[s_start:s_end],
        })
    return sentences


def _build_user_message(
    text: str,
    entities: list[dict[str, Any]],
    label_id: str,
    source: str,
    quality_score: float,
) -> str:
    # Skip the sentence splitter if entities already carry __sentence_id from
    # the original pipeline run — reconstruct sentence boundaries from offsets.
    all_have_sid = entities and all(e.get("__sentence_id") is not None for e in entities)
    if all_have_sid:
        sentence_list    = _sentences_from_entities(text, entities)
        enriched_entities = entities
    else:
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


# ── Core audit logic — Pass 1 (no tools) ─────────────────────────────────────

def audit_record(
    client: LLMClient,
    system_prompt: str,
    row: dict[str, Any],
    max_retries: int = 3,
) -> AuditVerdict:
    """Pass 1: Send one TrainingLabel to the audit model and parse the verdict (no tools)."""
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
            parsed       = _extract_json(resp.text)
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
        rationale  = (issue.get("rationale") or "").lower()
        field_name = (issue.get("field") or "").lower()
        if field_name in ("snomed_term", "snomed_concept_id", "snomed_score", "read_code"):
            return True
        if any(kw in rationale for kw in _SNOMED_KEYWORDS):
            return True
    return False


def _agentic_audit_record(
    audit_client: LLMClient,
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

    user_msg = json.dumps({
        "label_id": row["label_id"],
        "encounter_text": sanitise_for_prompt(row["text"]),
        "entity_index": entity_idx,
        "entity": entity,
        "pass_1_issues": entity_verdict.get("issues", []),
        "instruction": (
            "Use the available tools to look up SNOMED terminology or request "
            "an independent second opinion, then provide an informed recommendation "
            "for this entity. "
            "Return only the updated entity_verdict JSON object for this entity."
        ),
    }, indent=2)

    tool_config = _build_tool_config()
    messages: list[dict[str, Any]] = [{"role": "user", "content": user_msg}]
    tool_calls_log: list[dict[str, Any]] = []
    resp = None

    context = {"row": row, "entities": entities}

    for _iteration in range(MAX_TOOL_ITERATIONS):
        resp = audit_client.converse(
            system=system_prompt,
            messages=messages,
            max_tokens=2048,
            temperature=0.0,
            tool_config=tool_config,
        )
        guardrail.record(resp.input_tokens, resp.output_tokens, is_haiku=False)

        assistant_content: list[dict[str, Any]] = []
        if resp.text:
            assistant_content.append({"text": resp.text})
        for tu in resp.tool_uses:
            assistant_content.append({"toolUse": tu})
        if assistant_content:
            messages.append({"role": "assistant", "content": assistant_content})

        if resp.stop_reason != "tool_use" or not resp.tool_uses:
            break

        tool_result_blocks: list[dict[str, Any]] = []
        for tu in resp.tool_uses:
            tool_name    = tu.get("name", "")
            tool_input   = tu.get("input", {})
            tool_use_id  = tu.get("toolUseId", "")

            raw_result  = tool_executor.execute(tool_name, tool_input, context=context)
            result_text = sanitise_for_prompt(json.dumps(raw_result, default=str))

            tool_calls_log.append({
                "tool_name":   tool_name,
                "tool_input":  tool_input,
                "tool_result": result_text,
            })

            tool_result_blocks.append({
                "toolResult": {
                    "toolUseId": tool_use_id,
                    "content": [{"text": result_text}],
                }
            })

        messages.append({"role": "user", "content": tool_result_blocks})

    final_verdict = dict(entity_verdict)
    if resp and resp.text:
        try:
            parsed = _extract_json(resp.text)
            if "verdict" in parsed and "entity_index" in parsed:
                final_verdict = parsed
            elif "entity_verdicts" in parsed:
                for ev in parsed["entity_verdicts"]:
                    if ev.get("entity_index") == entity_idx:
                        final_verdict = ev
                        break
        except (json.JSONDecodeError, ValueError):
            logger.warning(
                "Agentic pass: could not parse model response for entity[%d] in %s",
                entity_idx,
                row["label_id"],
            )

    return final_verdict, tool_calls_log


def _pass_two(
    pass_one_verdict: AuditVerdict,
    row: dict[str, Any],
    entities: list[dict[str, Any]],
    audit_client: LLMClient,
    system_prompt: str,
    tool_executor: ToolExecutor,
    guardrail: CostGuardrail,
) -> AuditVerdict:
    """Run agentic tool-use for SNOMED needs_review entities from pass 1."""
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
                audit_client=audit_client,
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

def _classify_fixes(verdict: AuditVerdict, agentic: bool = False) -> None:
    """Classify issues into auto_fixes_applied vs proposals.

    Processes ALL entity verdicts including 'needs_review', allowing partial
    fixes: safe-field issues on a 'needs_review' entity are still applied
    automatically; the entity remains in the review queue for its blocking
    issues (readonly fields, low-confidence problems, etc.).

    Args:
        agentic: When True (pass 2), SNOMED fields are eligible for auto-fix
                 provided confidence >= SAFE_FIX_CONFIDENCE and the fix was
                 informed by Terminology API tool calls.
    """
    allowed_fix_fields = AGENTIC_FIX_FIELDS if agentic else SAFE_FIX_FIELDS
    # In agentic mode, SNOMED fields are no longer readonly if confidence is met
    effective_readonly = (
        READONLY_FIELDS - {"snomed_concept_id", "snomed_term", "read_code", "snomed_score"}
        if agentic else READONLY_FIELDS
    )
    # Fields where clearing to None/null is a valid auto-fix (model knows the
    # field should not have been set — e.g. a unit that isn't in the text).
    nullable_fix_fields = frozenset({"unit", "value", "reference_range", "normalized"})

    for ev in verdict.entity_verdicts:
        # Process fixable, remove, AND needs_review (partial-fix support).
        if ev["verdict"] not in ("fixable", "remove", "needs_review"):
            continue
        for issue in ev.get("issues", []):
            fld = issue.get("field", "")
            if fld in effective_readonly or fld.startswith("__"):
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
            suggested = issue.get("suggested")
            # Allow null/None suggested for nullable fields (clearing spurious metadata).
            suggested_ok = (suggested is not None) or (fld in nullable_fix_fields)
            is_safe = (
                fld in allowed_fix_fields
                and issue.get("confidence", 0) >= SAFE_FIX_CONFIDENCE
                and suggested_ok
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


def _heal_spans(
    entities: list[dict[str, Any]],
    encounter_text: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Recompute start/end for any entity whose text span is inconsistent.

    For every entity where encounter_text[start:end] != entity.text, searches
    for the entity text as a substring and updates offsets if found.  Returns
    (healed_entities, list_of_span_repairs) so the caller can record what changed.
    """
    healed   = [dict(e) for e in entities]
    repairs: list[dict[str, Any]] = []
    for i, ent in enumerate(healed):
        text = ent.get("text") or ""
        if not text:
            continue
        start = int(ent.get("start") or 0)
        end   = int(ent.get("end")   or 0)
        if encounter_text[start:end] == text:
            continue  # already consistent
        # Search near current position first, then globally
        new_start = encounter_text.find(text, max(0, start - 50))
        if new_start < 0:
            new_start = encounter_text.find(text)
        if new_start >= 0 and new_start != start:
            healed[i]["start"] = new_start
            healed[i]["end"]   = new_start + len(text)
            repairs.append({
                "entity_index": i,
                "field": "start/end",
                "old_start": start,
                "old_end": end,
                "new_start": new_start,
                "new_end": new_start + len(text),
                "rationale": "Span recomputed from entity text substring search",
            })
    return healed, repairs


def _clamp_snomed_scores(
    entities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Clamp snomed_score > 1.0 to exactly 1.0 on every entity.

    A score above 1.0 is a data invariant violation in the embedding pipeline,
    not a clinical judgement call.  Safe to apply unconditionally.
    Returns a list of repair descriptors (may be empty).
    """
    repairs: list[dict[str, Any]] = []
    for i, ent in enumerate(entities):
        score = ent.get("snomed_score")
        try:
            score = float(score)
        except (TypeError, ValueError):
            continue
        if score > 1.0:
            entities[i]["snomed_score"] = 1.0
            repairs.append({
                "entity_index": i,
                "field": "snomed_score",
                "old_value": score,
                "new_value": 1.0,
                "rationale": "snomed_score > 1.0 is a pipeline invariant violation; clamped to 1.0",
            })
    return repairs


def _apply_fixes(
    entities: list[dict[str, Any]],
    fixes: list[dict[str, Any]],
    encounter_text: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Apply safe auto-fixes to entities (returns a new copy + programmatic repairs).

    Sequence:
      1. Apply LLM-suggested field fixes from *fixes*.
      2. If 'text' changed, recompute start/end via str.find().
      3. Clamp any snomed_score > 1.0 to 1.0 (pipeline invariant).
      4. Heal any remaining start/end span inconsistencies via substring search.
    Strips audit-only __ prefixed keys before returning.
    """
    entities = [dict(e) for e in entities]
    for fix in fixes:
        idx       = fix.get("entity_index", -1)
        fld       = fix.get("field")
        suggested = fix.get("suggested")    # may be None (clearing a field)
        if 0 <= idx < len(entities) and fld:
            entities[idx][fld] = suggested
            if fld == "text" and isinstance(suggested, str):
                old_start = int(entities[idx].get("start") or 0)
                new_start = encounter_text.find(suggested, max(0, old_start - 20))
                if new_start < 0:
                    new_start = encounter_text.find(suggested)
                if new_start >= 0:
                    entities[idx]["start"] = new_start
                    entities[idx]["end"]   = new_start + len(suggested)
    # Clamp snomed_score > 1.0 (pipeline invariant, always safe)
    score_repairs = _clamp_snomed_scores(entities)
    # Heal any remaining span inconsistencies across ALL entities
    entities, span_repairs = _heal_spans(entities, encounter_text)
    all_repairs = score_repairs + span_repairs
    cleaned = [{k: v for k, v in e.items() if not k.startswith("__")} for e in entities]
    return cleaned, all_repairs


# ── Auto-fix cap monitor ───────────────────────────────────────────────────────

class AutoFixCapMonitor:
    """Sliding-window monitor for auto-fix rate."""

    def __init__(self, window: int = AUTOFIX_CAP_WINDOW, ratio: float = AUTOFIX_CAP_RATIO):
        self._window  = window
        self._ratio   = ratio
        self._history: list[tuple[int, int]] = []
        self.triggered = False

    def record(self, entity_count: int, fix_count: int) -> bool:
        self._history.append((entity_count, fix_count))
        if len(self._history) > self._window:
            self._history = self._history[-self._window:]
        total_entities = sum(e for e, _ in self._history)
        total_fixes    = sum(f for _, f in self._history)
        if total_entities > 0 and total_fixes / total_entities > self._ratio:
            self.triggered = True
            return True
        return False
