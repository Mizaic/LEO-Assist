"""ModelPreset API — named, reusable pipeline configuration presets.

Presets are stored in the Knowledge Graph as ModelPreset nodes.
Pathway designers pick a preset name when building a pipeline step;
the preset provides the full routing config at runtime.

Routes
------
GET    /presets                    List all presets
GET    /presets/{preset_id}        Get a single preset
POST   /presets                    Create or update a preset
PUT    /presets/{preset_id}/default  Set as system default
DELETE /presets/{preset_id}        Delete a non-system preset
"""

from __future__ import annotations

import logging
import re
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db.neo4j_client import CodingGraphClient
from libs.cypher.preset_queries import (
    DELETE_PRESET,
    GET_PRESET,
    LIST_PRESETS,
    SET_DEFAULT_PRESET,
    UPSERT_PRESET,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/presets", tags=["presets"])

_VALID_EXTRACTORS = {"llm", "ner", "ner+llm"}
_VALID_COLORS = {"primary", "success", "warning", "error", "info", "secondary"}
_VALID_MODELS = {
    "aws:small",
    "aws:big",
    "aws:max",
    "azure:small",
    "azure:big",
    "azure:max",
    "ner",
}


def _slug(name: str) -> str:
    """Generate a stable preset_id from a name."""
    return "preset-" + re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _row(rec: dict[str, Any]) -> dict[str, Any]:
    return {
        "preset_id": rec.get("preset_id", ""),
        "name": rec.get("name", ""),
        "description": rec.get("description", ""),
        "consensus_mode": bool(rec.get("consensus_mode", False)),
        "primary_model": rec.get("primary_model") or "aws:small",
        "secondary_model": rec.get("secondary_model") or "azure:small",
        "tiebreaker_model": rec.get("tiebreaker_model") or "aws:big",
        "extractor": rec.get("extractor") or "llm",
        "strict": bool(rec.get("strict", False)),
        "prompt_config_id": rec.get("prompt_config_id") or "",
        "color": rec.get("color") or "primary",
        # GPT-5 and NER models do not honour temperature; explicitly stored on the preset
        # so the pathway builder can show/hide the temperature slider without heuristics.
        "supports_temperature": bool(rec.get("supports_temperature", True)),
        "is_default": bool(rec.get("is_default", False)),
        "is_system": bool(rec.get("is_system", False)),
        "created_at": rec.get("created_at"),
        "updated_at": rec.get("updated_at"),
    }


class PresetRequest(BaseModel):
    name: str
    description: str = ""
    consensus_mode: bool = True
    # Compound "provider:tier" strings e.g. "aws:small", "azure:big", "ner"
    primary_model: str = "aws:small"  # single mode: the model; dual: first model
    secondary_model: str = "azure:small"  # dual only: second model
    tiebreaker_model: str = "aws:big"  # dual only: arbitrator on disagreement
    extractor: str = "llm"  # "llm" | "ner" | "ner+llm"
    strict: bool = False
    prompt_config_id: str = ""
    color: str = "primary"
    preset_id: str = ""
    # GPT-5 and NER models ignore temperature; set explicitly so the pathway
    # builder can show or hide the temperature slider without provider heuristics.
    supports_temperature: bool = True


@router.get("")
def list_presets() -> dict[str, Any]:
    client = CodingGraphClient()
    try:
        with client.session() as session:
            rows = session.run(LIST_PRESETS).data()
        return {"presets": [_row(r) for r in rows]}
    finally:
        client.close()


@router.get("/{preset_id}")
def get_preset(preset_id: str) -> dict[str, Any]:
    client = CodingGraphClient()
    try:
        with client.session() as session:
            rows = session.run(GET_PRESET, preset_id=preset_id).data()
        if not rows:
            raise HTTPException(
                status_code=404, detail=f"Preset {preset_id!r} not found"
            )
        return _row(rows[0])
    finally:
        client.close()


@router.post("")
def upsert_preset(body: PresetRequest) -> dict[str, Any]:
    if body.extractor not in _VALID_EXTRACTORS:
        raise HTTPException(
            status_code=400,
            detail=f"extractor must be one of {sorted(_VALID_EXTRACTORS)}",
        )
    if body.color not in _VALID_COLORS:
        raise HTTPException(
            status_code=400, detail=f"color must be one of {sorted(_VALID_COLORS)}"
        )

    preset_id = body.preset_id.strip() or _slug(body.name)
    client = CodingGraphClient()
    try:
        with client.session() as session:
            session.run(
                UPSERT_PRESET,
                preset_id=preset_id,
                name=body.name,
                description=body.description,
                consensus_mode=body.consensus_mode,
                primary_model=body.primary_model,
                secondary_model=body.secondary_model,
                tiebreaker_model=body.tiebreaker_model,
                extractor=body.extractor,
                strict=body.strict,
                prompt_config_id=body.prompt_config_id or None,
                color=body.color,
                supports_temperature=body.supports_temperature,
                is_default=None,
                is_system=None,
            )
            rows = session.run(GET_PRESET, preset_id=preset_id).data()
        logger.info("Preset upserted: %s (%s)", preset_id, body.name)
        return _row(rows[0]) if rows else {"preset_id": preset_id}
    finally:
        client.close()


@router.put("/{preset_id}/default")
def set_default(preset_id: str) -> dict[str, Any]:
    client = CodingGraphClient()
    try:
        with client.session() as session:
            rows = session.run(GET_PRESET, preset_id=preset_id).data()
            if not rows:
                raise HTTPException(
                    status_code=404, detail=f"Preset {preset_id!r} not found"
                )
            session.run(SET_DEFAULT_PRESET, preset_id=preset_id)
        logger.info("System default preset set to: %s", preset_id)
        return {"updated": True, "preset_id": preset_id}
    finally:
        client.close()


@router.delete("/{preset_id}")
def delete_preset(preset_id: str) -> dict[str, Any]:
    client = CodingGraphClient()
    try:
        with client.session() as session:
            rows = session.run(GET_PRESET, preset_id=preset_id).data()
            if not rows:
                raise HTTPException(
                    status_code=404, detail=f"Preset {preset_id!r} not found"
                )
            if rows[0].get("is_system"):
                raise HTTPException(
                    status_code=400, detail="System presets cannot be deleted."
                )
            result = session.run(DELETE_PRESET, preset_id=preset_id).data()
            deleted = result[0].get("deleted", 0) if result else 0
        return {"deleted": deleted > 0, "preset_id": preset_id}
    finally:
        client.close()
