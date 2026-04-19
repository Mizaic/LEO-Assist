"""Unified encounter coding/audit agent subgraph.

One LangGraph StateGraph for both SNOMED coding and audit:
  load_encounter -> coder (tool loop) -> post_process

Mode is derived from coded_entities: empty = code mode, populated = audit mode.
Tier selects the Bedrock model: big (Sonnet) for audit, small (Haiku) for runtime.
"""

from __future__ import annotations

import json
import logging
import os
from copy import deepcopy
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from libs.llm_client.prompt_safety import sanitise_for_prompt
from libs.terminology.client import TerminologyClient

logger = logging.getLogger(__name__)

_MAX_TOOL_ITERATIONS = max(1, int(os.getenv("CODING_AGENT_MAX_ITERATIONS", "6")))
_MAX_TOKENS = {"big": 200_000, "small": 50_000}

# Semantic tags that indicate the terminology server has returned a wrong/
# unexpected concept for what is expected to be a clinical concept.
_ORGANISM_TAGS = frozenset(
    {
        "organism",
        "virus",
        "bacterium",
        "fungus",
        "parasite",
        "prion",
        "archaea",
        "viroid",
    }
)
# Minimum confidence for auto-accepting a no-findings verdict without human review.
# Override with env var CODING_AGENT_CONF_THRESHOLD (float 0-1).
_CONF_AUTO_ACCEPT = float(os.getenv("CODING_AGENT_CONF_THRESHOLD", "0.75"))

# -- State -------------------------------------------------------------------


class CodingAgentState(TypedDict, total=False):
    encounter_id: str
    patient_id: str
    encounter_text: str
    coded_entities: list[dict]
    mode: str  # "audit" | "code"
    tier: str  # "big" | "small"
    apply: bool
    messages: list[dict]
    verdict: dict | None
    tool_iterations: int
    input_tokens: int
    output_tokens: int
    max_input_tokens: int
    model_id: str
    prompt_version: str
    errors: list[str]
    _pending_tool_uses: list[dict]


# -- Tools -------------------------------------------------------------------


def _tool_search_snomed(inp: dict) -> dict:
    query = str(inp.get("query") or "").strip()
    if not query:
        return {"ok": False, "error": "empty_query", "candidates": []}
    tag = str(inp.get("semantic_tag") or "").strip() or None
    try:
        client = TerminologyClient(timeout=5.0, max_retries=0)
        hits = client.resolve(
            [query],
            expected_tags={query: tag} if tag else None,
        ).get(query, [])
        return {
            "ok": True,
            "query": query,
            "candidates": [
                {
                    "concept_id": c.concept_id,
                    "term": c.term,
                    "semantic_tag": c.semantic_tag,
                    "score": round(float(c.score), 4),
                }
                for c in hits[:10]
            ],
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc), "candidates": []}


def _tool_lookup_concept(inp: dict) -> dict:
    cid = str(inp.get("concept_id") or "").strip()
    if not cid:
        return {"ok": False, "error": "concept_id required"}
    try:
        client = TerminologyClient(timeout=5.0, max_retries=0)
        hits = client.resolve([cid]).get(cid, [])
        top = hits[0] if hits else None
        if top is None:
            return {"ok": False, "error": "concept_not_found", "concept_id": cid}
        result = {
            "ok": True,
            "concept_id": cid,
            "preferred_term": top.term,
            "semantic_tag": top.semantic_tag,
        }
        if top.semantic_tag in _ORGANISM_TAGS:
            result["unreliable"] = True
            result["unreliable_reason"] = (
                f"terminology server returned semantic_tag='{top.semantic_tag}'"
                " for what is expected to be a clinical concept; index may be"
                " corrupted for this concept ID"
            )
        elif "Extension Namespace" in top.term:
            result["unreliable"] = True
            result["unreliable_reason"] = (
                "terminology server returned an Extension Namespace placeholder"
                " term; preferred term cannot be confirmed from this server"
            )
        return result
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _tool_resolve_evidence(inp: dict) -> dict:
    phrase = str(inp.get("phrase") or "").strip()
    if not phrase:
        return {"ok": False, "error": "phrase required"}
    try:
        client = TerminologyClient(timeout=5.0, max_retries=0)
        hits = client.resolve([phrase]).get(phrase, [])
        top = hits[0] if hits else None
        return {
            "ok": True,
            "phrase": phrase,
            "resolved": top is not None,
            "concept_id": top.concept_id if top else None,
            "term": top.term if top else None,
            "score": round(float(top.score), 4) if top else None,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


_Q_DEMOGRAPHICS = (
    "MATCH (p:Patient) WHERE toString(p.id) = $pid "
    "RETURN p.age AS age, p.sex AS sex LIMIT 1"
)

_Q_PROBLEMS = """\
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[r:DOCUMENTS]->(s)
WHERE toString(p.id) = $pid
  AND s.semanticTag IN ['disorder', 'finding', 'situation']
RETURN DISTINCT s.conceptId AS concept_id, s.name AS term,
       s.semanticTag AS semantic_tag, r.context AS context
ORDER BY term LIMIT 50"""


def _tool_get_demographics(inp: dict) -> dict:
    pid = str(inp.get("patient_id") or "").strip()
    if not pid:
        return {"ok": False, "error": "patient_id required"}
    try:
        from libs.neo4j_client.client import PatientGraphClient

        client = PatientGraphClient()
        rows = client.run(_Q_DEMOGRAPHICS, pid=pid)
        client.close()
        if not rows:
            return {"ok": False, "error": "patient_not_found"}
        return {"ok": True, "age": rows[0].get("age"), "sex": rows[0].get("sex")}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _tool_get_problems(inp: dict) -> dict:
    pid = str(inp.get("patient_id") or "").strip()
    if not pid:
        return {"ok": False, "error": "patient_id required"}
    try:
        from libs.neo4j_client.client import PatientGraphClient

        client = PatientGraphClient()
        rows = client.run(_Q_PROBLEMS, pid=pid)
        client.close()
        return {
            "ok": True,
            "problems": [
                {
                    "concept_id": r.get("concept_id"),
                    "term": r.get("term"),
                    "semantic_tag": r.get("semantic_tag"),
                }
                for r in rows
            ],
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _tool_read_context(inp: dict) -> dict:
    phrase = str(inp.get("phrase") or "").strip()
    text = str(inp.get("_encounter_text") or "").strip()
    if not phrase or not text:
        return {"ok": False, "error": "phrase and encounter_text required"}
    idx = text.lower().find(phrase.lower())
    if idx == -1:
        return {"ok": False, "error": "phrase_not_found"}
    start = max(0, idx - 200)
    end = min(len(text), idx + len(phrase) + 200)
    return {"ok": True, "phrase": phrase, "context": text[start:end]}


def _tool_get_descendants(inp: dict) -> dict:
    cid = str(inp.get("concept_id") or "").strip()
    if not cid:
        return {"ok": False, "error": "concept_id required"}
    depth = max(1, min(5, int(inp.get("depth") or 3)))
    limit = max(1, min(100, int(inp.get("limit") or 30)))
    tag = str(inp.get("semantic_tag") or "").strip() or None
    try:
        client = TerminologyClient(timeout=8.0, max_retries=0)
        results = client.get_descendants(
            cid, depth=depth, limit=limit, semantic_tag=tag
        )
        return {
            "ok": True,
            "concept_id": cid,
            "count": len(results),
            "descendants": results,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _tool_get_related_concepts(inp: dict) -> dict:
    cid = str(inp.get("concept_id") or "").strip()
    if not cid:
        return {"ok": False, "error": "concept_id required"}
    try:
        client = TerminologyClient(timeout=8.0, max_retries=0)
        result = client.get_related(cid)
        if not result:
            return {"ok": False, "error": "concept_not_found"}
        return {"ok": True, **result}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


_TOOL_DISPATCH: dict[str, Any] = {
    "search_snomed": _tool_search_snomed,
    "lookup_concept": _tool_lookup_concept,
    "resolve_evidence": _tool_resolve_evidence,
    "get_patient_demographics": _tool_get_demographics,
    "get_patient_problems": _tool_get_problems,
    "read_context": _tool_read_context,
    "get_descendants": _tool_get_descendants,
    "get_related_concepts": _tool_get_related_concepts,
}

_TOOL_CONFIG: dict[str, Any] = {
    "tools": [
        {
            "toolSpec": {
                "name": "search_snomed",
                "description": "Search SNOMED CT for a clinical term. Returns up to 10 candidates.",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "2-5 word clinical term",
                            },
                            "semantic_tag": {
                                "type": "string",
                                "description": "Expected SNOMED semantic tag (optional)",
                            },
                        },
                        "required": ["query"],
                    }
                },
            }
        },
        {
            "toolSpec": {
                "name": "lookup_concept",
                "description": "Lookup the preferred term and semantic tag for a known SNOMED concept ID.",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "concept_id": {
                                "type": "string",
                                "description": "SNOMED concept ID",
                            },
                        },
                        "required": ["concept_id"],
                    }
                },
            }
        },
        {
            "toolSpec": {
                "name": "resolve_evidence",
                "description": "Resolve an evidence phrase via the terminology resolver. Detects surface form gaps.",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "phrase": {
                                "type": "string",
                                "description": "Evidence phrase to resolve",
                            },
                        },
                        "required": ["phrase"],
                    }
                },
            }
        },
        {
            "toolSpec": {
                "name": "get_patient_demographics",
                "description": "Get patient age and sex for clinical plausibility checking.",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "patient_id": {
                                "type": "string",
                                "description": "Patient ID",
                            },
                        },
                        "required": ["patient_id"],
                    }
                },
            }
        },
        {
            "toolSpec": {
                "name": "get_patient_problems",
                "description": "Get active problem list (disorders and findings) for this patient.",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "patient_id": {
                                "type": "string",
                                "description": "Patient ID",
                            },
                        },
                        "required": ["patient_id"],
                    }
                },
            }
        },
        {
            "toolSpec": {
                "name": "read_context",
                "description": "Read +/- 2 sentences around a phrase for disambiguation.",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "phrase": {
                                "type": "string",
                                "description": "Phrase to locate in the encounter text",
                            },
                        },
                        "required": ["phrase"],
                    }
                },
            }
        },
        {
            "toolSpec": {
                "name": "get_descendants",
                "description": (
                    "Return active SNOMED descendants of a concept via IS_A relationships. "
                    "Use to check specificity (e.g. are there more specific child codes than "
                    "what is already coded?) or to verify that a concept ID is in the expected "
                    "clinical hierarchy. Filter by semantic_tag to narrow results."
                ),
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "concept_id": {
                                "type": "string",
                                "description": "SNOMED concept ID to traverse from",
                            },
                            "depth": {
                                "type": "integer",
                                "description": "IS_A traversal depth (1-5, default 3)",
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Max results to return (1-100, default 30)",
                            },
                            "semantic_tag": {
                                "type": "string",
                                "description": "Filter by semantic tag e.g. 'disorder'",
                            },
                        },
                        "required": ["concept_id"],
                    }
                },
            }
        },
        {
            "toolSpec": {
                "name": "get_related_concepts",
                "description": (
                    "Return the SNOMED ontology family for a concept via INTERPRETS, "
                    "HAS_COMPONENT, and HAS_ASSOCIATED_FINDING relationships. Most useful "
                    "for observable entity / lab concepts -- returns which procedures measure "
                    "it and which findings are associated."
                ),
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "concept_id": {
                                "type": "string",
                                "description": "SNOMED concept ID",
                            },
                        },
                        "required": ["concept_id"],
                    }
                },
            }
        },
        {
            "toolSpec": {
                "name": "submit_verdict",
                "description": "Submit the final verdict JSON. This is the terminal action.",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "encounter_assessment": {"type": "string"},
                            "missing": {"type": "array"},
                            "overcoded": {"type": "array"},
                            "wrong_assertion": {"type": "array"},
                            "entities": {"type": "array"},
                            "confidence": {"type": "number"},
                            "notes": {"type": "string"},
                        },
                        "required": ["encounter_assessment", "confidence"],
                    }
                },
            }
        },
    ]
}

# -- Helpers -----------------------------------------------------------------


def _format_coded(coded: list[dict]) -> str:
    if not coded:
        return "  (none)"
    lines = []
    for c in coded:
        if not c.get("concept_id"):
            continue
        lines.append(
            f"  [{c['concept_id']}] {c.get('term', '')} ({c.get('semantic_tag', '')}) "
            f"evidence={c.get('evidence', '')} assertion={c.get('assertion', 'present')}"
        )
    return "\n".join(lines) if lines else "  (none)"


def _build_user_message(text: str, coded: list[dict], mode: str) -> str:
    safe_text = sanitise_for_prompt(text, max_chars=16_000)
    if mode == "audit":
        coded_block = _format_coded(coded)
        n = len([c for c in coded if c.get("concept_id")])
        return (
            f"ENCOUNTER TEXT:\n{safe_text}\n\n"
            f"ALREADY CODED ({n} concepts):\n{coded_block}"
        )
    return f"ENCOUNTER TEXT:\n{safe_text}"


def _extract_verdict_from_messages(messages: list[dict]) -> dict | None:
    """Try to parse a JSON verdict from the last assistant text message."""
    import re

    _FENCE = re.compile(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", re.IGNORECASE)
    _OBJ = re.compile(r"\{[\s\S]*\}")
    for msg in reversed(messages):
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content") or []
        text = ""
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            text = " ".join(
                item.get("text", "") for item in content if isinstance(item, dict)
            )
        text = text.strip()
        if not text:
            continue
        for pat in [_FENCE, _OBJ]:
            m = pat.search(text)
            if m:
                try:
                    parsed = json.loads(m.group(1) if pat is _FENCE else m.group(0))
                    if isinstance(parsed, dict):
                        return parsed
                except Exception:
                    pass
    return None


def _tool_result_block(tool_id: str, payload: dict) -> dict:
    safe = sanitise_for_prompt(json.dumps(payload, ensure_ascii=True), max_chars=4000)
    return {"toolResult": {"toolUseId": tool_id, "content": [{"text": safe}]}}


# -- Nodes -------------------------------------------------------------------


def load_encounter(state: CodingAgentState) -> dict:
    """Format encounter and initialise per-run state fields."""
    coded = state.get("coded_entities") or []
    mode = "audit" if coded else "code"
    tier = state.get("tier") or "big"
    max_tokens = _MAX_TOKENS.get(tier, 50_000)
    from libs.prompts.coding_agent_v1 import PROMPT_VERSION

    user_msg = _build_user_message(state.get("encounter_text") or "", coded, mode)
    return {
        "mode": mode,
        "prompt_version": PROMPT_VERSION,
        "max_input_tokens": max_tokens,
        "tool_iterations": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "errors": [],
        "verdict": None,
        "_pending_tool_uses": [],
        "messages": [{"role": "user", "content": user_msg}],
    }


def coder(state: CodingAgentState) -> dict:
    """Make one LLM call, return tool_uses or text for routing."""
    from libs.llm_client.factory import create_llm
    from libs.prompts.coding_agent_v1 import build_system_prompt

    tier = state.get("tier") or "big"
    mode = state.get("mode") or "audit"
    messages = list(state.get("messages") or [])
    errors = list(state.get("errors") or [])

    patient_id = str(state.get("patient_id") or "")
    try:
        llm = create_llm(tier=tier)
        system = build_system_prompt(mode)
        resp = llm.converse(
            system=system,
            messages=deepcopy(messages),
            max_tokens=4096,
            tool_config=_TOOL_CONFIG,
            agent_task="encounter_coding_agent",
            patient_id=patient_id,
        )
        assistant_content: list[dict] = []
        if resp.text:
            assistant_content.append({"text": resp.text})
        for tu in resp.tool_uses:
            assistant_content.append({"toolUse": tu})
        messages.append({"role": "assistant", "content": assistant_content})
        return {
            "messages": messages,
            "model_id": resp.model_id,
            "input_tokens": (state.get("input_tokens") or 0) + resp.input_tokens,
            "output_tokens": (state.get("output_tokens") or 0) + resp.output_tokens,
            "_pending_tool_uses": resp.tool_uses,
            "errors": errors,
        }
    except Exception as exc:
        msg = f"coder_error: {exc}"
        logger.exception("coder node failed")
        errors.append(msg)
        return {"errors": errors, "_pending_tool_uses": [], "messages": messages}


def _dispatch_tool_uses(
    tool_uses: list[dict], encounter_text: str
) -> tuple[list[dict], dict | None]:
    """Dispatch tool calls; return (tool_result_blocks, verdict_or_None)."""
    results: list[dict] = []
    verdict: dict | None = None

    for tu in tool_uses:
        name = str(tu.get("name") or "")
        tool_id = str(tu.get("toolUseId") or "")
        inp = dict(tu.get("input") or {})

        if name == "submit_verdict":
            verdict = inp
            results.append(_tool_result_block(tool_id, {"ok": True, "received": True}))
            continue

        if name == "read_context":
            inp["_encounter_text"] = encounter_text

        fn = _TOOL_DISPATCH.get(name)
        try:
            payload = fn(inp) if fn else {"ok": False, "error": f"unknown_tool:{name}"}
        except Exception as exc:
            payload = {"ok": False, "error": str(exc)}

        results.append(_tool_result_block(tool_id, payload))

    return results, verdict


def execute_tools(state: CodingAgentState) -> dict:
    """Dispatch pending tool calls; set verdict if submit_verdict was called."""
    tool_uses = list(state.get("_pending_tool_uses") or [])
    messages = list(state.get("messages") or [])
    iters = (state.get("tool_iterations") or 0) + 1
    text = state.get("encounter_text") or ""

    results, verdict = _dispatch_tool_uses(tool_uses, text)

    if results:
        messages.append({"role": "user", "content": results})

    return {
        "messages": messages,
        "tool_iterations": iters,
        "_pending_tool_uses": [],
        "verdict": verdict,
    }


def _forced_verdict_call(state: CodingAgentState) -> dict | None:
    """One final LLM call asking the agent to submit a verdict now.

    Called when the agent exits the tool loop without calling submit_verdict.
    Returns the parsed verdict dict or None if the call fails.
    """
    from libs.llm_client.factory import create_llm
    from libs.prompts.coding_agent_v1 import build_system_prompt

    tier = state.get("tier") or "big"
    mode = state.get("mode") or "audit"
    messages = list(state.get("messages") or [])
    messages.append(
        {
            "role": "user",
            "content": [
                {
                    "text": (
                        "You have not yet called submit_verdict. "
                        "Based on your analysis so far, call submit_verdict NOW with "
                        "your best verdict. Use needs_review only if you cannot determine "
                        "correctness. For admin-only encounters use no_clinical_content."
                    ),
                }
            ],
        }
    )
    try:
        llm = create_llm(tier=tier)
        resp = llm.converse(
            system=build_system_prompt(mode),
            messages=deepcopy(messages),
            max_tokens=2048,
            tool_config=_TOOL_CONFIG,
            agent_task="encounter_coding_agent_forced_verdict",
            patient_id=str(state.get("patient_id") or ""),
        )
        for tu in resp.tool_uses:
            if tu.get("name") == "submit_verdict":
                verdict = dict(tu.get("input") or {})
                if isinstance(verdict, dict) and "encounter_assessment" in verdict:
                    logger.info("forced_verdict_call succeeded")
                    return verdict
        if resp.text:
            tmp = [{"role": "assistant", "content": [{"text": resp.text}]}]
            return _extract_verdict_from_messages(tmp)
    except Exception:
        logger.exception("forced_verdict_call failed")
    return None


def _apply_confidence_gate(verdict: dict) -> dict:
    """Auto-accept high-confidence no-findings verdicts; avoid unnecessary HITL.

    If the agent is confident (>= _CONF_AUTO_ACCEPT) and found no missing/
    overcoded/wrong_assertion items, promote needs_review -> coded/clean.
    Safety-critical findings always bypass this gate.
    """
    assessment = str(verdict.get("encounter_assessment") or "")
    if assessment != "needs_review":
        return verdict

    conf = float(verdict.get("confidence") or 0)
    if conf < _CONF_AUTO_ACCEPT:
        return verdict

    has_findings = any(
        [
            verdict.get("missing"),
            verdict.get("overcoded"),
            verdict.get("wrong_assertion"),
        ]
    )
    if has_findings:
        return verdict

    promoted = "coded" if not verdict.get("overcoded") else "clean"
    logger.info("conf_gate: promoted needs_review -> %s (conf=%.2f)", promoted, conf)
    verdict["encounter_assessment"] = promoted
    verdict.setdefault("notes", "")
    verdict["notes"] = (
        f"[auto-accepted conf={conf:.2f}] " + (verdict["notes"] or "")
    ).strip()
    return verdict


def post_process(state: CodingAgentState) -> dict:
    """Validate verdict, apply confidence gate, add metadata block."""
    from libs.prompts.coding_agent_v1 import PROMPT_VERSION

    verdict = state.get("verdict")
    if verdict is None:
        verdict = _extract_verdict_from_messages(state.get("messages") or [])

    # Lever 1: forced verdict call when agent exited without submitting.
    if verdict is None or not isinstance(verdict, dict):
        logger.warning("post_process: no verdict -- attempting forced_verdict_call")
        verdict = _forced_verdict_call(state)

    if verdict is None or not isinstance(verdict, dict):
        verdict = {
            "encounter_assessment": "needs_review",
            "missing": [],
            "overcoded": [],
            "wrong_assertion": [],
            "confidence": 0.0,
            "notes": "Agent did not produce a valid verdict.",
        }

    # Lever 3: confidence gate -- auto-accept high-confidence no-findings verdicts.
    verdict = _apply_confidence_gate(verdict)

    input_tok = state.get("input_tokens") or 0
    output_tok = state.get("output_tokens") or 0
    verdict["metadata"] = {
        "model_id": state.get("model_id") or "",
        "prompt_version": state.get("prompt_version") or PROMPT_VERSION,
        "tool_iterations": state.get("tool_iterations") or 0,
        "input_tokens": input_tok,
        "output_tokens": output_tok,
        "total_tokens": input_tok + output_tok,
        "schema_version": 1,
    }

    errors = state.get("errors") or []
    if errors:
        verdict.setdefault("_errors", errors)

    return {"verdict": verdict}


# -- Routing -----------------------------------------------------------------


def _route_after_coder(state: CodingAgentState) -> str:
    """Route to execute_tools or post_process after coder runs."""
    tool_uses = state.get("_pending_tool_uses") or []
    iters = state.get("tool_iterations") or 0
    usage = state.get("input_tokens") or 0
    max_tokens = state.get("max_input_tokens") or 50_000

    if iters >= _MAX_TOOL_ITERATIONS or usage >= max_tokens or not tool_uses:
        return "post_process"
    return "execute_tools"


def _route_after_tools(state: CodingAgentState) -> str:
    """Route back to coder or to post_process if verdict was submitted."""
    if state.get("verdict") is not None:
        return "post_process"
    iters = state.get("tool_iterations") or 0
    usage = state.get("input_tokens") or 0
    max_tokens = state.get("max_input_tokens") or 50_000
    if iters >= _MAX_TOOL_ITERATIONS or usage >= max_tokens:
        return "post_process"
    return "coder"


# -- Builder -----------------------------------------------------------------


def build_encounter_coding_agent_subgraph() -> CompiledStateGraph:
    """Build and compile the unified encounter coding/audit agent subgraph."""
    g = StateGraph(CodingAgentState)
    g.add_node("load_encounter", load_encounter)
    g.add_node("coder", coder)
    g.add_node("execute_tools", execute_tools)
    g.add_node("post_process", post_process)

    g.add_edge(START, "load_encounter")
    g.add_edge("load_encounter", "coder")
    g.add_conditional_edges(
        "coder",
        _route_after_coder,
        {"execute_tools": "execute_tools", "post_process": "post_process"},
    )
    g.add_conditional_edges(
        "execute_tools",
        _route_after_tools,
        {"coder": "coder", "post_process": "post_process"},
    )
    g.add_edge("post_process", END)
    return g.compile()
