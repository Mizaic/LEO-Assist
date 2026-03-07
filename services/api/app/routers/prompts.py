"""Prompt Config CRUD router.

Manages PromptConfig nodes in Neo4j — the single source of truth for
all LLM system prompts, output schemas, and few-shot examples.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.db.neo4j_client import PatientGraphClient
from libs.auth.org_scope import CallerScope, get_caller_scope
from libs.cypher.prompt_config_queries import (
    CREATE_PROMPT,
    DELETE_PROMPT,
    GET_PROMPT,
    LIST_PROMPTS,
    UPDATE_PROMPT,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/prompts", tags=["prompts"])


class FewShotExample(BaseModel):
    id: str
    input: str
    output: str
    deidentified: bool = False


class PromptCreateRequest(BaseModel):
    name: str
    systemPrompt: str
    outputSchema: str = "{}"
    verification: bool = False
    fewShotExamples: list[FewShotExample] = []


class PromptUpdateRequest(BaseModel):
    name: str
    systemPrompt: str
    outputSchema: str = "{}"
    verification: bool = False
    fewShotExamples: list[FewShotExample] = []


class ImproveRequest(BaseModel):
    currentPrompt: str
    outputSchema: str = "{}"


def _count_few_shot(raw: str | None) -> int:
    if not raw:
        return 0
    try:
        return len(json.loads(raw))
    except (json.JSONDecodeError, TypeError):
        return 0


@router.get("")
def list_prompts(scope: CallerScope = Depends(get_caller_scope)):
    client = PatientGraphClient()
    try:
        with client.session() as session:
            rows = [dict(r) for r in session.run(LIST_PROMPTS)]
        prompts = []
        for row in rows:
            prompts.append({
                "id": row["id"],
                "name": row["name"],
                "version": row.get("version", 1),
                "verification": bool(row.get("verification")),
                "fewShotCount": 1 if row.get("hasFewShot") else 0,
                "updatedAt": str(row.get("updatedAt") or row.get("createdAt") or ""),
            })
        return {"prompts": prompts}
    finally:
        client.close()


@router.get("/{prompt_id}")
def get_prompt(prompt_id: str, scope: CallerScope = Depends(get_caller_scope)):
    client = PatientGraphClient()
    try:
        with client.session() as session:
            row = session.run(GET_PROMPT, id=prompt_id).single()
        if not row:
            raise HTTPException(404, f"PromptConfig {prompt_id} not found")
        few_shot_raw = row.get("fewShotExamples") or "[]"
        try:
            few_shot = json.loads(few_shot_raw) if isinstance(few_shot_raw, str) else few_shot_raw
        except (json.JSONDecodeError, TypeError):
            few_shot = []
        return {
            "id": row["id"],
            "name": row["name"],
            "version": row.get("version", 1),
            "systemPrompt": row["systemPrompt"],
            "outputSchema": row.get("outputSchema") or "{}",
            "verification": bool(row.get("verification")),
            "fewShotExamples": few_shot,
        }
    finally:
        client.close()


@router.post("")
def create_prompt(body: PromptCreateRequest, scope: CallerScope = Depends(get_caller_scope)):
    prompt_id = str(uuid.uuid4())
    few_shot_json = json.dumps([e.model_dump() for e in body.fewShotExamples])
    client = PatientGraphClient()
    try:
        with client.session() as session:
            session.run(
                CREATE_PROMPT,
                id=prompt_id,
                name=body.name,
                version=1,
                system_prompt=body.systemPrompt,
                output_schema=body.outputSchema,
                verification=body.verification,
                few_shot_examples=few_shot_json,
                source="user",
            )
        return {"id": prompt_id}
    finally:
        client.close()


@router.put("/{prompt_id}")
def update_prompt(
    prompt_id: str,
    body: PromptUpdateRequest,
    scope: CallerScope = Depends(get_caller_scope),
):
    few_shot_json = json.dumps([e.model_dump() for e in body.fewShotExamples])
    client = PatientGraphClient()
    try:
        with client.session() as session:
            row = session.run(
                UPDATE_PROMPT,
                id=prompt_id,
                name=body.name,
                system_prompt=body.systemPrompt,
                output_schema=body.outputSchema,
                verification=body.verification,
                few_shot_examples=few_shot_json,
            ).single()
        if not row:
            raise HTTPException(404, f"PromptConfig {prompt_id} not found")
        return {"id": prompt_id, "status": "updated"}
    finally:
        client.close()


@router.delete("/{prompt_id}")
def delete_prompt(prompt_id: str, scope: CallerScope = Depends(get_caller_scope)):
    client = PatientGraphClient()
    try:
        with client.session() as session:
            row = session.run(DELETE_PROMPT, id=prompt_id).single()
        deleted = row["deleted"] if row else 0
        if deleted == 0:
            raise HTTPException(400, "Cannot delete seed prompts or prompt not found")
        return {"status": "deleted"}
    finally:
        client.close()


@router.post("/improve")
async def improve_prompt(
    body: ImproveRequest,
    scope: CallerScope = Depends(get_caller_scope),
):
    """Use the MAX model to suggest improvements to a system prompt."""
    try:
        from libs.llm_client.factory import create_llm

        llm = create_llm(provider="aws", tier="max")
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "You are an expert prompt engineer for clinical NLP systems. "
                    "The user will give you a system prompt and an output schema. "
                    "Improve the prompt for clarity, precision, and safety. "
                    "Return ONLY the improved prompt text, no explanation."
                ),
            },
            {
                "role": "user",
                "content": f"System prompt:\n{body.currentPrompt}\n\nOutput schema:\n{body.outputSchema}",
            },
        ]
        result = await llm.chat(messages=messages, max_tokens=4096)
        return {"improvedPrompt": result.content}
    except Exception as exc:
        logger.warning("Prompt improvement failed: %s", exc)
        raise HTTPException(500, f"AI improvement failed: {exc}")
