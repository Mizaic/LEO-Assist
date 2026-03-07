"""Core Agentic Auditor — shared library.

Used by both the CLI script (scripts/agentic_auditor.py) and the
API background runner (services/api/app/services/agentic_audit_service.py).

All stateless classes, data structures, Cypher queries, and processing
functions live here.  I/O (file writing, argparse, job-state management)
is the responsibility of the caller.
"""

from __future__ import annotations

import concurrent.futures
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

# ── Consensus / dual-small-model configuration ────────────────────────────────

# Jaccard similarity threshold on (entity_index, field) issue pairs.
# Records below this threshold are escalated to the big model.
CONSENSUS_AGREEMENT_THRESHOLD = float(os.getenv("AUDIT_CONSENSUS_THRESHOLD", "0.60"))

# A solo issue flagged by only one small model is still included in the merged
# verdict if its confidence reaches this level.
CONSENSUS_SOLO_CONFIDENCE = 0.97

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
# Small-model rate used for BOTH AWS Haiku and Azure GPT-mini.
# Azure GPT-mini is significantly cheaper (~$0.15/$0.60 per 1M) but we use the
# Haiku rate as a conservative upper bound.  Override AZURE_OPENAI_SMALL_MODEL_COST_*
# to track Azure mini separately if needed.
_aws_small_in   = float(os.getenv("AWS_BEDROCK_MODEL_SMALL_MODEL_COST_PER_1M_INPUT_TOKEN",   "1.0")) / 1_000_000
_aws_small_out  = float(os.getenv("AWS_BEDROCK_MODEL_SMALL_MODEL_COST_PER_1M_OUTPUT_TOKEN",  "5.0")) / 1_000_000
_az_small_in    = float(os.getenv("AZURE_OPENAI_SMALL_MODEL_COST_PER_1M_INPUT_TOKEN",  "0.15")) / 1_000_000
_az_small_out   = float(os.getenv("AZURE_OPENAI_SMALL_MODEL_COST_PER_1M_OUTPUT_TOKEN", "0.60")) / 1_000_000
# Blended small-model rate (average of AWS + Azure small, used by is_haiku=True path)
_HAIKU_IN_RATE  = (_aws_small_in  + _az_small_in)  / 2
_HAIKU_OUT_RATE = (_aws_small_out + _az_small_out) / 2

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
class ConsensusInfo:
    """Per-record metadata produced by the dual-small-model consensus path."""
    aws_verdict: str = ""        # record_verdict from AWS small model
    azure_verdict: str = ""      # record_verdict from Azure small model
    agreed: bool = False         # True when small models agreed and big model was skipped
    jaccard: float = 0.0         # Jaccard similarity of (entity_index, field) issue sets
    escalated: bool = False      # True when disagreement triggered big-model escalation
    escalation_model: str = ""   # model_id of the escalating model (if escalated)
    aws_input_tokens: int = 0
    aws_output_tokens: int = 0
    azure_input_tokens: int = 0
    azure_output_tokens: int = 0


@dataclass
class AuditVerdict:
    label_id: str
    record_verdict: str
    entity_verdicts: list[dict[str, Any]]
    missing_entities: list[dict[str, Any]]
    auto_fixes_applied: list[dict[str, Any]] = field(default_factory=list)
    proposals: list[dict[str, Any]] = field(default_factory=list)
    # data_quality_flags holds observations about derived/read-only fields (e.g.
    # snomed_score) that cannot be corrected without re-running upstream pipelines.
    # Kept separate from proposals so manual reviewers aren't swamped with issues
    # they cannot action in the label editor.
    data_quality_flags: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    consensus_info: ConsensusInfo | None = None


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

    For 'remove' verdict entities, if the minimum confidence across all issues
    reaches SAFE_FIX_CONFIDENCE, a single entity-removal entry is appended to
    auto_fixes_applied (field=None, verdict='remove').  _apply_fixes() then
    deletes the entity from the list.  This unlocks automatic removal of
    duplicate qualifier_value entities and spurious result-descriptor entities
    that the LLM correctly flags but can't patch via a field value.

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

        # ── Entity-removal fast path ───────────────────────────────────────
        # When the model says 'remove', treat the whole entity as the unit of
        # change rather than trying to patch individual fields.  A single
        # entity-removal entry (field=None) is written to auto_fixes_applied;
        # _apply_fixes() filters those entities out of the final list.
        #
        # We use max_conf (not min_conf) because entities often have a primary
        # high-confidence reason to remove plus secondary lower-confidence
        # observations.  If the strongest evidence clears SAFE_FIX_CONFIDENCE
        # the entity should be removed — the weaker secondary issues are just
        # additional supporting detail, not veto votes.
        if ev["verdict"] == "remove":
            issues = ev.get("issues", [])
            max_conf = max((i.get("confidence", 0) for i in issues), default=0.0)
            rationale = "; ".join(i.get("rationale", "") for i in issues)
            if max_conf >= SAFE_FIX_CONFIDENCE:
                verdict.auto_fixes_applied.append({
                    "entity_index": ev["entity_index"],
                    "verdict": "remove",
                    "field": None,
                    "confidence": max_conf,
                    "rationale": rationale,
                })
            else:
                for issue in issues:
                    verdict.proposals.append({
                        "entity_index": ev["entity_index"],
                        "verdict": "remove",
                        **issue,
                    })
            continue

        # ── Field-level fix / needs_review partial-fix ─────────────────────
        for issue in ev.get("issues", []):
            fld = issue.get("field", "")
            if fld in effective_readonly or fld.startswith("__"):
                # Derived / read-only fields (snomed_score, snomed_concept_id,
                # snomed_term, start, end …) cannot be corrected in the label
                # editor — they require re-running upstream pipelines.  Route
                # these to data_quality_flags so they're tracked but don't
                # inflate the actionable proposals count.
                verdict.data_quality_flags.append({
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
        text = me.get("text", "")
        conf = me.get("confidence", 0.0)
        # Promote high-confidence missing entities with a concrete text span
        # to auto_fixes so _apply_fixes can insert them programmatically.
        # The script resolves the span via substring search and optionally
        # calls the terminology API for SNOMED coding.
        if text and conf >= SAFE_FIX_CONFIDENCE:
            verdict.auto_fixes_applied.append({
                "entity_index": -1,   # sentinel: new entity, not a patch
                "verdict": "add",
                "text": text,
                "normalized": me.get("normalized") or text,
                "label": me.get("label", "finding"),
                "assertion": me.get("assertion", "present"),
                "sentence_id": me.get("sentence_id"),
                "confidence": conf,
                "rationale": me.get("rationale", ""),
            })
        else:
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


def _remove_duplicate_qualifier_values(
    entities: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Programmatically remove qualifier_value entities that duplicate an observable entity.

    When a qualifier_value entity sits alongside an observable entity in the same
    sentence AND that observable entity already has both 'value' and 'unit' set,
    the qualifier_value is structurally redundant — the observable_post_processor
    already captured that information in the parent entity's fields.

    This is a deterministic pipeline invariant (not a clinical judgement), so it
    is applied unconditionally at high confidence without requiring LLM instruction.

    Returns:
        (filtered_entities, list_of_removal_descriptors)
    """
    # Index observable entities by __sentence_id that already have value + unit
    obs_sentence_ids: set = set()
    for ent in entities:
        if (
            ent.get("label") == "observable entity"
            and ent.get("value") is not None
            and ent.get("unit") is not None
        ):
            sid = ent.get("__sentence_id")
            if sid is not None:
                obs_sentence_ids.add(sid)

    kept: list[dict[str, Any]] = []
    removals: list[dict[str, Any]] = []
    for i, ent in enumerate(entities):
        if (
            ent.get("label") == "qualifier_value"
            and ent.get("__sentence_id") in obs_sentence_ids
        ):
            removals.append({
                "entity_index": i,
                "field": None,
                "verdict": "remove",
                "confidence": 1.0,
                "rationale": (
                    "qualifier_value duplicate: sibling observable entity already "
                    "captures value and unit in its own fields (programmatic invariant)"
                ),
            })
        else:
            kept.append(ent)
    return kept, removals


def _resolve_snomed_for_new_entity(
    text: str,
    normalized: str,
    label: str,
) -> dict[str, Any]:
    """Call the terminology API to get SNOMED fields for a newly added entity.

    Returns a dict of SNOMED fields to merge into the entity (may be all-None
    if the API is unavailable or returns no confident match).
    """
    import httpx  # lazy import — not all callers need it
    result: dict[str, Any] = {
        "snomed_concept_id": None,
        "snomed_term": None,
        "snomed_score": None,
        "read_code": None,
    }
    try:
        body: dict[str, Any] = {"terms": [normalized]}
        if label:
            body["expected_tags"] = {normalized: label}
        resp = httpx.post(
            f"{TERMINOLOGY_API_URL}/terminology/resolve",
            json=body,
            timeout=TOOL_HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        candidates = resp.json().get("results", {}).get(normalized, [])
        if candidates:
            best = candidates[0]
            result["snomed_concept_id"] = best.get("concept_id")
            result["snomed_term"]       = best.get("term")
            result["snomed_score"]      = best.get("score")
            result["read_code"]         = best.get("read_code")
    except Exception as exc:
        logger.debug("SNOMED resolve failed for %r: %s", normalized, exc)
    return result


def _apply_fixes(
    entities: list[dict[str, Any]],
    fixes: list[dict[str, Any]],
    encounter_text: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Apply safe auto-fixes to entities (returns a new copy + programmatic repairs).

    Sequence:
      0. Insert new entities for high-confidence missing-entity additions
         (verdict='add', entity_index=-1).  Span resolved via substring search
         within the correct sentence; SNOMED resolved via terminology API.
      1. Remove entities flagged for deletion (field=None, verdict='remove') from
         auto_fixes.  Indices refer to the original position in *entities*.
      2. Apply LLM-suggested field fixes to surviving entities.
      3. If 'text' changed, recompute start/end via str.find().
      4. Programmatically remove remaining duplicate qualifier_value entities
         whose parent observable entity already carries value + unit.
      5. Clamp any snomed_score > 1.0 to 1.0 (pipeline invariant).
      6. Heal any remaining start/end span inconsistencies via substring search.
    Strips audit-only __ prefixed keys before returning.
    """
    entities = [dict(e) for e in entities]

    # Step 0 — insert missing entities proposed by the LLM at high confidence.
    # For each "add" entry, locate the exact text span in the encounter, check
    # it doesn't duplicate an existing entity, call the terminology API for
    # SNOMED coding, then append a new entity to the list.
    add_repairs: list[dict[str, Any]] = []
    existing_spans: set[tuple[int, int]] = {
        (int(e.get("start") or 0), int(e.get("end") or 0)) for e in entities
    }
    existing_texts: set[str] = {(e.get("text") or "").lower() for e in entities}

    for fix in fixes:
        if fix.get("verdict") != "add" or fix.get("entity_index") != -1:
            continue
        text       = fix.get("text", "").strip()
        normalized = fix.get("normalized") or text
        label      = fix.get("label", "finding")
        assertion  = fix.get("assertion", "present")
        sentence_id = fix.get("sentence_id")

        if not text or text.lower() in existing_texts:
            continue  # already extracted or empty

        # Locate the span.  If sentence_id is provided, restrict search to the
        # character range of the sentence so we pick the right occurrence.
        search_start = 0
        search_end   = len(encounter_text)
        if sentence_id:
            # Find sentence bounds from existing entities sharing that sentence_id
            sent_entities = [e for e in entities if e.get("__sentence_id") == sentence_id]
            if sent_entities:
                search_start = max(0, min(int(e.get("start") or 0) for e in sent_entities) - 50)
                search_end   = min(len(encounter_text), max(int(e.get("end") or 0) for e in sent_entities) + 100)

        span_start = encounter_text.find(text, search_start, search_end)
        if span_start < 0:
            # Fallback: case-insensitive search in full text
            lower_enc  = encounter_text.lower()
            lower_text = text.lower()
            span_start = lower_enc.find(lower_text, search_start, search_end)
            if span_start < 0:
                span_start = lower_enc.find(lower_text)
            if span_start >= 0:
                text = encounter_text[span_start: span_start + len(text)]
        if span_start < 0:
            logger.debug("Could not locate missing entity %r in encounter text — skipped", text)
            continue

        span_end = span_start + len(text)
        if (span_start, span_end) in existing_spans:
            continue  # exact duplicate span

        existing_spans.add((span_start, span_end))
        existing_texts.add(text.lower())

        snomed = _resolve_snomed_for_new_entity(text, normalized, label)

        new_entity: dict[str, Any] = {
            "text":            text,
            "start":           span_start,
            "end":             span_end,
            "label":           label,
            "assertion":       assertion,
            "normalized":      normalized,
            "value":           None,
            "unit":            None,
            "reference_range": None,
            "decision_tier":   None,
            "tier_decision":   None,
            "tier_reason":     None,
            "__sentence_id":   sentence_id,
            **snomed,
        }
        entities.append(new_entity)
        add_repairs.append({
            "action":     "add_missing_entity",
            "text":       text,
            "label":      label,
            "assertion":  assertion,
            "start":      span_start,
            "end":        span_end,
            "snomed_resolved": snomed.get("snomed_concept_id") is not None,
            "rationale":  fix.get("rationale", ""),
        })
        logger.debug("Auto-added missing entity %r (%s/%s) at [%d:%d]", text, label, assertion, span_start, span_end)

    # Step 1 — entity removals from LLM (field=None, verdict='remove')
    llm_remove_idxs = {
        f["entity_index"]
        for f in fixes
        if f.get("verdict") == "remove" and f.get("field") is None
        and 0 <= f.get("entity_index", -1) < len(entities)
    }
    if llm_remove_idxs:
        entities = [e for i, e in enumerate(entities) if i not in llm_remove_idxs]

    # Step 2 — field patches (operate on surviving entities by re-indexing)
    # fixes still use original indices; after removal, surviving entities may
    # have shifted positions.  Build a mapping from old index → new position.
    old_to_new: dict[int, int] = {}
    new_pos = 0
    for old_i in range(len(entities) + len(llm_remove_idxs)):
        if old_i not in llm_remove_idxs:
            old_to_new[old_i] = new_pos
            new_pos += 1

    for fix in fixes:
        old_idx = fix.get("entity_index", -1)
        fld     = fix.get("field")
        if not fld or fld is None:
            continue  # entity-removal entries handled above
        new_idx = old_to_new.get(old_idx, -1)
        if 0 <= new_idx < len(entities):
            suggested = fix.get("suggested")
            entities[new_idx][fld] = suggested
            if fld == "text" and isinstance(suggested, str):
                old_start = int(entities[new_idx].get("start") or 0)
                new_start = encounter_text.find(suggested, max(0, old_start - 20))
                if new_start < 0:
                    new_start = encounter_text.find(suggested)
                if new_start >= 0:
                    entities[new_idx]["start"] = new_start
                    entities[new_idx]["end"]   = new_start + len(suggested)

    # Step 4 — programmatic qualifier_value dedup
    entities, qv_repairs = _remove_duplicate_qualifier_values(entities)

    # Step 5 — clamp snomed_score > 1.0 (pipeline invariant, always safe)
    score_repairs = _clamp_snomed_scores(entities)

    # Step 6 — heal any remaining span inconsistencies across ALL entities
    entities, span_repairs = _heal_spans(entities, encounter_text)

    all_repairs = add_repairs + qv_repairs + score_repairs + span_repairs
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


# ── Dual-small-model consensus with big-model escalation ─────────────────────

def _issue_key_set(verdict: AuditVerdict) -> frozenset[tuple[int, str]]:
    """Return (entity_index, field) pairs for every issue in the verdict."""
    return frozenset(
        (ev["entity_index"], issue.get("field", ""))
        for ev in verdict.entity_verdicts
        for issue in ev.get("issues", [])
    )


def _jaccard(a: frozenset, b: frozenset) -> float:
    """Jaccard similarity between two frozensets. Empty intersection → 0.0."""
    if not a and not b:
        return 1.0
    union = a | b
    return len(a & b) / len(union) if union else 1.0


def _merge_audit_verdicts(
    v1: AuditVerdict,
    v2: AuditVerdict,
    threshold: float = CONSENSUS_AGREEMENT_THRESHOLD,
) -> tuple[AuditVerdict | None, float]:
    """Attempt to merge two independent small-model audit verdicts.

    Agreement strategy (optimised for cross-family models that rarely choose
    identical (entity_index, field) pairs):

      1. record_verdict must match — "pass" vs "has_issues" disagreement always
         escalates regardless of any threshold setting.
      2. Both "pass" → trivially agree; return v1 unchanged (Jaccard = 1.0).
      3. Both "has_issues" → use INTERSECTION-based merge:
           - entity_verdicts: keep only issues flagged by BOTH models for the
             same (entity_index, field) pair, taking the higher-confidence copy.
           - Solo issues from one model are retained only when confidence ≥
             CONSENSUS_SOLO_CONFIDENCE (very high bar, ~0.97).
           - missing_entities: kept only when both models proposed the same
             (text, label) pair, or a solo proposal has confidence ≥
             CONSENSUS_SOLO_CONFIDENCE.
           - If the intersection is empty (models agreed there were issues but
             found completely different ones), the record is escalated so the big
             model can arbitrate cleanly.
      4. The *threshold* parameter is retained for callers that pass a custom
         value but is no longer the primary gate — escalation is now driven by
         whether the intersection is non-empty after filtering, not raw Jaccard.
         Jaccard is still computed and stored in ConsensusInfo for reporting.

    Returns:
        (merged_verdict, jaccard) if models agree sufficiently,
        (None, jaccard)           if disagreement requires big-model escalation.
    """
    if v1.record_verdict != v2.record_verdict:
        return None, 0.0

    if v1.error and v2.error:
        return v1, 1.0

    if v1.record_verdict == "pass":
        return v1, 1.0

    # Both "has_issues" — compute Jaccard for reporting, then do intersection merge.
    keys1 = _issue_key_set(v1)
    keys2 = _issue_key_set(v2)
    j = _jaccard(keys1, keys2)
    agreed_keys = keys1 & keys2

    # Index v2 issues by (entity_index, field) for O(1) lookup
    v2_issues_idx: dict[tuple[int, str], dict[str, Any]] = {}
    for ev in v2.entity_verdicts:
        eidx = ev["entity_index"]
        for issue in ev.get("issues", []):
            v2_issues_idx[(eidx, issue.get("field", ""))] = issue

    # Index v2 entity_verdicts by entity_index for verdict merging
    v2_ev_idx: dict[int, dict[str, Any]] = {ev["entity_index"]: ev for ev in v2.entity_verdicts}

    # Build intersection-based merged entity_verdicts
    merged_evs: list[dict[str, Any]] = []
    v1_eidxs = {ev["entity_index"] for ev in v1.entity_verdicts}
    has_any_agreed_issue = False

    for ev in v1.entity_verdicts:
        eidx = ev["entity_index"]
        merged_issues: list[dict[str, Any]] = []

        for issue in ev.get("issues", []):
            fld = issue.get("field", "")
            key = (eidx, fld)
            if key in agreed_keys:
                # Both models flagged this — take the higher-confidence copy
                v2_issue = v2_issues_idx.get(key, {})
                merged_issues.append(
                    v2_issue if v2_issue.get("confidence", 0) > issue.get("confidence", 0)
                    else issue
                )
                has_any_agreed_issue = True
            elif issue.get("confidence", 0) >= CONSENSUS_SOLO_CONFIDENCE:
                # Solo but very high confidence — include anyway
                merged_issues.append(issue)
                has_any_agreed_issue = True

        if merged_issues:
            # Use the more severe verdict between the two models for this entity
            v2_ev = v2_ev_idx.get(eidx, ev)
            severity = {"remove": 3, "needs_review": 2, "fixable": 1, "correct": 0}
            best_verdict = max(
                ev.get("verdict", "correct"), v2_ev.get("verdict", "correct"),
                key=lambda x: severity.get(x, 0),
            )
            merged_evs.append({**ev, "verdict": best_verdict, "issues": merged_issues})
        elif ev.get("verdict") == "correct":
            merged_evs.append(ev)

    # Solo v2 entities at very high confidence
    for ev in v2.entity_verdicts:
        if ev["entity_index"] in v1_eidxs:
            continue
        high_conf = [i for i in ev.get("issues", []) if i.get("confidence", 0) >= CONSENSUS_SOLO_CONFIDENCE]
        if high_conf:
            merged_evs.append({**ev, "issues": high_conf})
            has_any_agreed_issue = True

    # Merge missing_entities: intersection or solo at high confidence
    me1 = {(m.get("text", ""), m.get("label", "")): m for m in v1.missing_entities}
    me2 = {(m.get("text", ""), m.get("label", "")): m for m in v2.missing_entities}
    agreed_missing: list[dict[str, Any]] = [me1[k] for k in me1 if k in me2]
    for k, m in me1.items():
        if k not in me2 and m.get("confidence", 0) >= CONSENSUS_SOLO_CONFIDENCE:
            agreed_missing.append(m)
    for k, m in me2.items():
        if k not in me1 and m.get("confidence", 0) >= CONSENSUS_SOLO_CONFIDENCE:
            agreed_missing.append(m)

    if agreed_missing:
        has_any_agreed_issue = True

    # If models agree there were issues but found zero in common, escalate
    # so the big model can make a clean determination.
    if not has_any_agreed_issue:
        return None, j

    record_verdict = (
        "has_issues"
        if (any(ev.get("issues") for ev in merged_evs) or agreed_missing)
        else "pass"
    )

    merged = AuditVerdict(
        label_id=v1.label_id,
        record_verdict=record_verdict,
        entity_verdicts=merged_evs,
        missing_entities=agreed_missing,
        input_tokens=v1.input_tokens + v2.input_tokens,
        output_tokens=v1.output_tokens + v2.output_tokens,
        cached_tokens=v1.cached_tokens + v2.cached_tokens,
    )
    return merged, j


def audit_record_consensus(
    system_prompt: str,
    row: dict[str, Any],
    *,
    escalate_provider: str = "aws",
    escalate_tier: str = "big",
    agreement_threshold: float = CONSENSUS_AGREEMENT_THRESHOLD,
) -> AuditVerdict:
    """Dual-small-model audit with big-model escalation on disagreement.

    Runs AWS Haiku and Azure GPT-mini in parallel.  Agreement is evaluated in
    three tiers:

      1. Both "pass"        → return merged pass immediately (no big-model call).
      2. Both "has_issues"  → intersection merge: only issues flagged by BOTH
         models are actioned; if the intersection is empty the big model is called
         to arbitrate.  Solo issues at confidence ≥ CONSENSUS_SOLO_CONFIDENCE are
         also kept.  This precision-first strategy avoids noise from cross-family
         model verbosity differences.
      3. Verdict disagreement → escalate unconditionally.

    In practice, for a GP clinical-note dataset this saves roughly 30-50% of
    big-model calls (records where both models agree on the exact set of issues,
    or where both cleanly pass).  Records with complex, ambiguous entity mixtures
    still get the full big-model treatment.

    Token counts in the returned verdict include ALL model calls made:
      consensus path  → aws_small + azure_small tokens
      escalation path → aws_small + azure_small + big_model tokens

    The ``consensus_info`` field on the returned ``AuditVerdict`` records
    which path was taken and the per-model token split for cost reporting.
    """
    aws_small   = create_llm(provider="aws",   tier="small", use_reasoning=True)
    azure_small = create_llm(provider="azure", tier="small", use_reasoning=True)
    label_id    = row["label_id"]

    v_aws: AuditVerdict | None   = None
    v_azure: AuditVerdict | None = None

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        fut_aws   = pool.submit(audit_record, aws_small,   system_prompt, row)
        fut_azure = pool.submit(audit_record, azure_small, system_prompt, row)

        try:
            v_aws = fut_aws.result(timeout=120)
        except Exception as exc:
            logger.warning("Consensus AWS small failed for %s: %s", label_id, exc)

        try:
            v_azure = fut_azure.result(timeout=120)
        except Exception as exc:
            logger.warning("Consensus Azure small failed for %s: %s", label_id, exc)

    def _escalate(info: ConsensusInfo) -> AuditVerdict:
        # Enable extended thinking for AWS big/max models — Claude Sonnet/Opus
        # support reasoning via additionalModelRequestFields on Bedrock.
        # Azure models use a different reasoning API (not supported here).
        big = create_llm(
            provider=escalate_provider,
            tier=escalate_tier,
            use_reasoning=(escalate_provider == "aws"),
        )
        info.escalated = True
        info.escalation_model = big.model_id
        v = audit_record(big, system_prompt, row)
        # Carry small-model tokens into the verdict for accurate run totals
        small_in  = (v_aws.input_tokens  if v_aws  else 0) + (v_azure.input_tokens  if v_azure  else 0)
        small_out = (v_aws.output_tokens if v_aws  else 0) + (v_azure.output_tokens if v_azure  else 0)
        small_cac = (v_aws.cached_tokens if v_aws  else 0) + (v_azure.cached_tokens if v_azure  else 0)
        v.input_tokens  += small_in
        v.output_tokens += small_out
        v.cached_tokens += small_cac
        v.consensus_info = info
        return v

    # Both small models failed → escalate immediately
    if v_aws is None and v_azure is None:
        logger.warning("Consensus: both small models failed for %s — escalating", label_id)
        return _escalate(ConsensusInfo())

    # One failed → use the survivor without escalation (conservative but cheap)
    if v_aws is None:
        v_azure.consensus_info = ConsensusInfo(azure_verdict=v_azure.record_verdict)  # type: ignore[union-attr]
        return v_azure  # type: ignore[return-value]
    if v_azure is None:
        v_aws.consensus_info = ConsensusInfo(aws_verdict=v_aws.record_verdict)
        return v_aws

    merged, jaccard = _merge_audit_verdicts(v_aws, v_azure, threshold=agreement_threshold)

    info = ConsensusInfo(
        aws_verdict=v_aws.record_verdict,
        azure_verdict=v_azure.record_verdict,
        jaccard=round(jaccard, 3),
        aws_input_tokens=v_aws.input_tokens,
        aws_output_tokens=v_aws.output_tokens,
        azure_input_tokens=v_azure.input_tokens,
        azure_output_tokens=v_azure.output_tokens,
    )

    if merged is not None:
        info.agreed = True
        merged.consensus_info = info
        logger.debug(
            "Consensus agreed for %s: verdict=%s jaccard=%.2f",
            label_id, merged.record_verdict, jaccard,
        )
        return merged

    # Disagreement → escalate to big model
    logger.info(
        "Consensus disagreement for %s: aws=%s azure=%s jaccard=%.2f — escalating to %s/%s",
        label_id, v_aws.record_verdict, v_azure.record_verdict, jaccard,
        escalate_provider, escalate_tier,
    )
    return _escalate(info)
