"""Cypher queries for ModelPreset nodes stored in the Knowledge Graph.

A ModelPreset is a named, reusable pipeline configuration that pathway
designers select when building workflow steps.  Each preset encapsulates
the full routing config (consensus mode, tier, provider, extractor backend)
and an optional prompt config reference.

Only one preset can be the system default at a time — SET_DEFAULT enforces
this as an atomic operation.
"""

UPSERT_PRESET = """
MERGE (p:ModelPreset {preset_id: $preset_id})
ON CREATE SET
    p.name                  = $name,
    p.description           = $description,
    p.consensus_mode        = $consensus_mode,
    p.primary_model         = coalesce($primary_model, 'aws:small'),
    p.secondary_model       = coalesce($secondary_model, 'azure:small'),
    p.tiebreaker_model      = coalesce($tiebreaker_model, 'aws:big'),
    p.extractor             = coalesce($extractor, 'llm'),
    p.strict                = $strict,
    p.prompt_config_id      = coalesce($prompt_config_id, ''),
    p.color                 = coalesce($color, 'primary'),
    p.supports_temperature  = coalesce($supports_temperature, true),
    p.is_default            = coalesce($is_default, false),
    p.is_system             = coalesce($is_system, false),
    p.created_at            = datetime(),
    p.updated_at            = datetime()
ON MATCH SET
    p.name                  = $name,
    p.description           = $description,
    p.consensus_mode        = $consensus_mode,
    p.primary_model         = coalesce($primary_model, p.primary_model),
    p.secondary_model       = coalesce($secondary_model, p.secondary_model),
    p.tiebreaker_model      = coalesce($tiebreaker_model, p.tiebreaker_model),
    p.extractor             = coalesce($extractor, p.extractor),
    p.strict                = $strict,
    p.prompt_config_id      = coalesce($prompt_config_id, ''),
    p.color                 = coalesce($color, p.color),
    p.supports_temperature  = $supports_temperature,
    p.is_system             = coalesce($is_system, p.is_system),
    p.updated_at            = datetime()
RETURN p.preset_id AS preset_id
"""

LIST_PRESETS = """
MATCH (p:ModelPreset)
RETURN
    p.preset_id                AS preset_id,
    p.name                     AS name,
    p.description              AS description,
    p.consensus_mode           AS consensus_mode,
    p.primary_model            AS primary_model,
    p.secondary_model          AS secondary_model,
    p.tiebreaker_model         AS tiebreaker_model,
    p.extractor                AS extractor,
    p.strict                   AS strict,
    p.prompt_config_id         AS prompt_config_id,
    p.color                    AS color,
    coalesce(p.supports_temperature, true) AS supports_temperature,
    p.is_default               AS is_default,
    p.is_system                AS is_system,
    toString(p.created_at)     AS created_at,
    toString(p.updated_at)     AS updated_at
ORDER BY p.is_default DESC, p.is_system DESC, p.created_at ASC
"""

GET_PRESET = """
MATCH (p:ModelPreset {preset_id: $preset_id})
RETURN
    p.preset_id                AS preset_id,
    p.name                     AS name,
    p.description              AS description,
    p.consensus_mode           AS consensus_mode,
    p.primary_model            AS primary_model,
    p.secondary_model          AS secondary_model,
    p.tiebreaker_model         AS tiebreaker_model,
    p.extractor                AS extractor,
    p.strict                   AS strict,
    p.prompt_config_id         AS prompt_config_id,
    p.color                    AS color,
    coalesce(p.supports_temperature, true) AS supports_temperature,
    p.is_default               AS is_default,
    p.is_system                AS is_system,
    toString(p.created_at)     AS created_at,
    toString(p.updated_at)     AS updated_at
"""

# Atomically clear all is_default flags then set the target.
SET_DEFAULT_PRESET = """
MATCH (p:ModelPreset)
SET p.is_default = false
WITH p
MATCH (target:ModelPreset {preset_id: $preset_id})
SET target.is_default = true
RETURN target.preset_id AS preset_id
"""

DELETE_PRESET = """
MATCH (p:ModelPreset {preset_id: $preset_id})
WHERE p.is_system = false
DETACH DELETE p
RETURN count(p) AS deleted
"""
