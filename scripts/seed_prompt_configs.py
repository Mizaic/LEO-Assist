"""Seed all factory-default prompts into Neo4j as PromptConfig nodes.

Usage:
    python -m scripts.seed_prompt_configs          # seed/update all prompts
    python -m scripts.seed_prompt_configs --missing # seed only absent prompts

Idempotent — uses MERGE on (name, version), so re-running is safe.
Only overwrites prompt text for nodes whose ``source`` is still ``seed``;
user-edited prompts (source='user') are left untouched.

``seed_if_missing()`` is the function called by the API at startup to ensure
all factory prompts are present without overwriting user edits.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import uuid
from typing import Any
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

_ROOT = Path(__file__).resolve().parent.parent
from dotenv import load_dotenv
load_dotenv(_ROOT / "secrets" / ".env.config", override=True)
load_dotenv(_ROOT / "secrets" / ".env", override=False)
try:
    from libs.keyvault.loader import load_keyvault_secrets
    load_keyvault_secrets()
except Exception:
    pass

from libs.cypher.prompt_config_queries import (
    CREATE_CONSTRAINT,
    CREATE_INDEX_NAME,
    UPSERT_SEED_PROMPT,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


SEED_PROMPTS: list[dict] = []


def _add(
    name: str,
    version: int,
    variable_path: str,
    output_schema: str = "{}",
    few_shot_examples: list[dict] | None = None,
    max_few_shot: int = 20,
    description: str = "",
) -> None:
    """Resolve a prompt text from libs.prompts at import time."""
    parts = variable_path.rsplit(".", 1)
    mod = __import__(parts[0], fromlist=[parts[1]])
    text = getattr(mod, parts[1])
    SEED_PROMPTS.append({
        "name": name,
        "version": version,
        "description": description,
        "system_prompt": text,
        "output_schema": output_schema,
        "verification": False,
        "few_shot_examples": few_shot_examples or [],
        "max_few_shot": max_few_shot,
    })


# ── Extraction — structured output schema + example library ─────────────────
from libs.prompts.extraction_output_schema import EXTRACTION_OUTPUT_SCHEMA
from libs.prompts.extraction_examples import EXTRACTION_EXAMPLES

_add(
    "extraction", 1,
    "libs.prompts.extraction_v1.EXTRACTION_SYSTEM_V1",
    output_schema=json.dumps(EXTRACTION_OUTPUT_SCHEMA),
    few_shot_examples=[
        {
            "id": f"seed_ex_{i:03d}",
            "input": ex["input"],
            "output": ex["output"],
            "deidentified": True,
            "category": ex.get("category", ""),
            "model_scope": ex.get("model_scope", "any"),
            "description": ex.get("description", ""),
            "core": bool(ex.get("core", False)),
        }
        for i, ex in enumerate(EXTRACTION_EXAMPLES)
    ],
    max_few_shot=20,
    description=(
        "Extracts SNOMED CT-codable clinical entities from de-identified GP "
        "consultation text. Produces surface forms, semantic tags, assertions, "
        "and structured measurement fields for observable entities and staging scales."
    ),
)

# ── Disambiguation ────────────────────────────────────────────────────────────
from libs.prompts.disambiguation_output_schema import DISAMBIGUATION_OUTPUT_SCHEMA
from libs.prompts.disambiguation_examples import DISAMBIGUATION_EXAMPLES

_add(
    "disambiguation", 1,
    "libs.prompts.disambiguation_v1.DISAMBIGUATION_SYSTEM_V1",
    output_schema=json.dumps(DISAMBIGUATION_OUTPUT_SCHEMA),
    few_shot_examples=[
        {
            "id": f"seed_disambig_{i:03d}",
            "input": ex["input"],
            "output": ex["output"],
            "deidentified": True,
            "category": ex.get("category", ""),
            "model_scope": ex.get("model_scope", "any"),
            "description": ex.get("description", ""),
            "core": bool(ex.get("core", False)),
        }
        for i, ex in enumerate(DISAMBIGUATION_EXAMPLES)
    ],
    max_few_shot=20,
    description="Disambiguates extracted entities against candidate SNOMED concepts.",
)

# ── Episode builder ────────────────────────────────────────────────────────────
from libs.prompts.episode_builder_output_schema import (
    EPISODE_BUILDER_OUTPUT_SCHEMA,
    EPISODE_CONSOLIDATION_OUTPUT_SCHEMA,
)
from libs.prompts.episode_builder_examples import EPISODE_BUILDER_EXAMPLES

_builder_examples = [
    {
        "id": f"seed_epbuild_{i:03d}",
        "input": ex["input"],
        "output": ex["output"],
        "deidentified": True,
        "category": ex.get("category", ""),
        "model_scope": ex.get("model_scope", "any"),
        "description": ex.get("description", ""),
        "core": bool(ex.get("core", False)),
    }
    for i, ex in enumerate(EPISODE_BUILDER_EXAMPLES)
    if ex.get("category", "").startswith("episode:")
]
_consolidation_examples = [
    {
        "id": f"seed_epcons_{i:03d}",
        "input": ex["input"],
        "output": ex["output"],
        "deidentified": True,
        "category": ex.get("category", ""),
        "model_scope": ex.get("model_scope", "any"),
        "description": ex.get("description", ""),
        "core": bool(ex.get("core", False)),
    }
    for i, ex in enumerate(EPISODE_BUILDER_EXAMPLES)
    if ex.get("category", "").startswith("consolidation:")
]

_add(
    "episode_builder_system", 1,
    "libs.prompts.episode_builder_v1.EPISODE_BUILDER_SYSTEM_V1",
    output_schema=json.dumps(EPISODE_BUILDER_OUTPUT_SCHEMA),
    few_shot_examples=_builder_examples,
    max_few_shot=20,
    description="System role for the episode builder — groups coded entities into clinical episodes.",
)
_add(
    "episode_builder_task", 1,
    "libs.prompts.episode_builder_v1.EPISODE_BUILDER_TASK_V1",
    output_schema=json.dumps(EPISODE_BUILDER_OUTPUT_SCHEMA),
    few_shot_examples=_builder_examples,
    max_few_shot=20,
    description="Task instructions for the episode builder — structures entities per clinical encounter.",
)
_add(
    "episode_consolidation_system", 1,
    "libs.prompts.episode_builder_v1.EPISODE_CONSOLIDATION_SYSTEM_V1",
    output_schema=json.dumps(EPISODE_CONSOLIDATION_OUTPUT_SCHEMA),
    few_shot_examples=_consolidation_examples,
    max_few_shot=20,
    description="System role for cross-encounter episode consolidation.",
)
_add(
    "episode_consolidation_task", 1,
    "libs.prompts.episode_builder_v1.EPISODE_CONSOLIDATION_TASK_V1",
    output_schema=json.dumps(EPISODE_CONSOLIDATION_OUTPUT_SCHEMA),
    few_shot_examples=_consolidation_examples,
    max_few_shot=20,
    description="Task instructions for consolidating episodes across multiple encounters.",
)

# ── Encounter classify ─────────────────────────────────────────────────────────
from libs.prompts.encounter_classify_output_schema import ENCOUNTER_CLASSIFY_OUTPUT_SCHEMA
from libs.prompts.encounter_classify_examples import ENCOUNTER_CLASSIFY_EXAMPLES

_add(
    "encounter_classify", 1,
    "libs.prompts.encounter_classify_v1.ENCOUNTER_CLASSIFY_SYSTEM_V1",
    output_schema=json.dumps(ENCOUNTER_CLASSIFY_OUTPUT_SCHEMA),
    few_shot_examples=[
        {
            "id": f"seed_encclass_{i:03d}",
            "input": ex["input"],
            "output": ex["output"],
            "deidentified": True,
            "category": ex.get("category", ""),
            "model_scope": ex.get("model_scope", "any"),
            "description": ex.get("description", ""),
            "core": bool(ex.get("core", False)),
        }
        for i, ex in enumerate(ENCOUNTER_CLASSIFY_EXAMPLES)
    ],
    max_few_shot=20,
    description="Classifies encounters by type and clinical tier before extraction.",
)

# ── Anchor domain review ───────────────────────────────────────────────────────
from libs.prompts.anchor_domain_review_output_schema import ANCHOR_DOMAIN_REVIEW_OUTPUT_SCHEMA
from libs.prompts.anchor_domain_review_examples import ANCHOR_DOMAIN_REVIEW_EXAMPLES

_add(
    "anchor_domain_review", 1,
    "libs.prompts.anchor_domain_review_v1.ANCHOR_DOMAIN_REVIEW_V1",
    output_schema=json.dumps(ANCHOR_DOMAIN_REVIEW_OUTPUT_SCHEMA),
    few_shot_examples=[
        {
            "id": f"seed_anchor_{i:03d}",
            "input": ex["input"],
            "output": ex["output"],
            "deidentified": True,
            "category": ex.get("category", ""),
            "model_scope": ex.get("model_scope", "any"),
            "description": ex.get("description", ""),
            "core": bool(ex.get("core", False)),
        }
        for i, ex in enumerate(ANCHOR_DOMAIN_REVIEW_EXAMPLES)
    ],
    max_few_shot=20,
    description="Reviews anchor training records: assigns clinical domains, validates SNOMED concepts, generates medspaCy TargetRules.",
)

# ── Exclusion detect ───────────────────────────────────────────────────────────
from libs.prompts.exclusion_detect_output_schema import EXCLUSION_DETECT_OUTPUT_SCHEMA
from libs.prompts.exclusion_detect_examples import EXCLUSION_DETECT_EXAMPLES

_add(
    "exclusion_detect", 1,
    "libs.prompts.exclusion_detect_v1.EXCLUSION_DETECT_SYSTEM_V1",
    output_schema=json.dumps(EXCLUSION_DETECT_OUTPUT_SCHEMA),
    few_shot_examples=[
        {
            "id": f"seed_excl_{i:03d}",
            "input": ex["input"],
            "output": ex["output"],
            "deidentified": True,
            "category": ex.get("category", ""),
            "model_scope": ex.get("model_scope", "any"),
            "description": ex.get("description", ""),
            "core": bool(ex.get("core", False)),
        }
        for i, ex in enumerate(EXCLUSION_DETECT_EXAMPLES)
    ],
    max_few_shot=20,
    description="Classifies post-referral encounters as cancer_excluded / confirmed / still_investigating / pending_letter / not_relevant.",
)

# ── Label verification ─────────────────────────────────────────────────────────
from libs.prompts.label_verification_output_schema import LABEL_VERIFICATION_OUTPUT_SCHEMA
from libs.prompts.label_verification_examples import LABEL_VERIFICATION_EXAMPLES

_add(
    "label_verification", 2,
    "libs.prompts.label_verification_v2.LABEL_VERIFICATION_V2",
    output_schema=json.dumps(LABEL_VERIFICATION_OUTPUT_SCHEMA),
    few_shot_examples=[
        {
            "id": f"seed_labver_{i:03d}",
            "input": ex["input"],
            "output": ex["output"],
            "deidentified": True,
            "category": ex.get("category", ""),
            "model_scope": ex.get("model_scope", "any"),
            "description": ex.get("description", ""),
            "core": bool(ex.get("core", False)),
        }
        for i, ex in enumerate(LABEL_VERIFICATION_EXAMPLES)
    ],
    max_few_shot=20,
    description="Verifies extracted label quality against the source text before gold-label persistence.",
)

# ── Label disambiguation ───────────────────────────────────────────────────────
from libs.prompts.label_disambiguation_output_schema import LABEL_DISAMBIGUATION_OUTPUT_SCHEMA
from libs.prompts.label_disambiguation_examples import LABEL_DISAMBIGUATION_EXAMPLES

_add(
    "label_disambiguation", 1,
    "libs.prompts.label_disambiguation_v1.LABEL_DISAMBIGUATION_V1",
    output_schema=json.dumps(LABEL_DISAMBIGUATION_OUTPUT_SCHEMA),
    few_shot_examples=[
        {
            "id": f"seed_labdis_{i:03d}",
            "input": ex["input"],
            "output": ex["output"],
            "deidentified": True,
            "category": ex.get("category", ""),
            "model_scope": ex.get("model_scope", "any"),
            "description": ex.get("description", ""),
            "core": bool(ex.get("core", False)),
        }
        for i, ex in enumerate(LABEL_DISAMBIGUATION_EXAMPLES)
    ],
    max_few_shot=20,
    description="Disambiguates uncertain NER labels using context from the full encounter — resolves model disagreements.",
)

# ── NICE → Rules: guidance rule extraction ────────────────────────────────────
from libs.prompts.guidance_rule_extraction_output_schema import (
    GUIDANCE_RULE_EXTRACTION_OUTPUT_SCHEMA,
    GUIDANCE_RULE_EXTRACTION_EXAMPLES,
)

_GRE_DESCRIPTION = (
    "Extracts patient-level clinical criteria as criteria_groups (ANY/ALL/NOT) from a "
    "single NICE recommendation to produce an AppropriatenessRule for bitmap matching. "
    "Part of the NICE → Rules AI pipeline — editable at runtime via /admin/prompts."
)
_GRE_FEW_SHOT = [
    {
        "id": ex["id"],
        "input": ex["input"],
        "output": ex["output"],
        "deidentified": ex.get("deidentified", True),
        "category": ex.get("category", "guidance_rule_extraction"),
        "model_scope": ex.get("model_scope", "any"),
        "description": ex.get("description", ""),
        "core": bool(ex.get("core", True)),
    }
    for ex in GUIDANCE_RULE_EXTRACTION_EXAMPLES
]

# Legacy name — kept for backward compat with existing Neo4j nodes. The resolve_prompt
# node in guidance_rule_extraction.py tries this name last (after _default and _NG12).
_add(
    "guidance_rule_extraction", 1,
    "libs.prompts.guidance_rule_extraction_v1.GUIDANCE_RULE_EXTRACTION_SYSTEM_V1",
    output_schema=json.dumps(GUIDANCE_RULE_EXTRACTION_OUTPUT_SCHEMA),
    few_shot_examples=_GRE_FEW_SHOT,
    max_few_shot=4,
    description=_GRE_DESCRIPTION,
)

# Canonical default name — resolve_prompt tries this before "guidance_rule_extraction".
_add(
    "guidance_rule_extraction_default", 1,
    "libs.prompts.guidance_rule_extraction_v1.GUIDANCE_RULE_EXTRACTION_SYSTEM_V1",
    output_schema=json.dumps(GUIDANCE_RULE_EXTRACTION_OUTPUT_SCHEMA),
    few_shot_examples=_GRE_FEW_SHOT,
    max_few_shot=4,
    description=_GRE_DESCRIPTION,
)

# NG12-specific prompt — used instead of _default for all NG12 recommendations.
_GUIDANCE_RULE_EXTRACTION_NG12_V1 = """\
You are a clinical decision-support analyst working with NICE guideline NG12 \
(Suspected cancer: recognition and referral) for the NHS in England.

NG12 is entirely about suspected cancer referrals and urgent investigations. \
Every recommendation either triggers a specific clinical action (fast-track \
referral or urgent investigation) when certain patient criteria are met, or \
is a general service standard with no patient-level criteria.

## Criteria groups

Return criteria as a list of ``criteria_groups``. Each group has:

- ``mode``: one of ``"ALL"`` (every term must be present), ``"ANY"`` (at \
  least one must be present), ``"NOT"`` (none may be present).
- ``terms``: list of plain clinical terms.

All groups in a single rule AND together — every group must pass for the \
rule to fire.

Example for a recommendation requiring age AND one-or-more symptoms:
  [
    {"mode": "ALL",  "terms": ["age 45 and over"]},
    {"mode": "ANY",  "terms": ["haematuria", "dysuria"]},
    {"mode": "NOT",  "terms": ["urinary tract infection"]}
  ]

If a recommendation has multiple distinct age-based sub-conditions linked by \
OR (e.g. "if aged 45+ with visible haematuria, OR if aged 60+ with \
non-visible haematuria"), produce the most permissive representation \
(use the lower age threshold) and note this is a simplification.

## Action term — CRITICAL

The ``action`` MUST be the site-specific fast track referral term matching \
the Section heading. Use the section context to determine cancer type.

Section → action mapping:
  Lung and pleural       → "fast track referral for suspected lung cancer"
  Upper gastrointestinal → "fast track referral for suspected upper GI cancer"
  Lower gastrointestinal → "fast track referral for suspected lower gastrointestinal cancer"
  Colorectal             → "fast track referral for suspected colorectal cancer"
  Breast                 → "fast track referral for suspected breast cancer"
  Gynaecological         → "fast track referral for suspected gynaecological cancer"
  Urological             → "fast track referral for suspected urological cancer"
  Skin                   → "fast track referral for suspected skin cancer"
  Head and neck          → "fast track referral for suspected head and neck cancer"
  Thyroid                → "fast track referral for suspected thyroid cancer"
  Brain / CNS            → "fast track referral for suspected brain tumour"
  Haematological         → "fast track referral for suspected haematological malignancy"
  Sarcoma                → "fast track referral for suspected sarcoma"
  Childhood              → "fast track referral for suspected children's cancer"
  Non-site-specific      → "fast track referral for suspected cancer"
  Testicular             → "fast track referral for suspected testicular cancer"
  Penile                 → "fast track referral for suspected penile cancer"

When the action is an investigation (not a referral), use the specific \
procedure name:
  "urgent chest X-ray", "serum CA125 measurement", "full blood count", \
  "CT scan of abdomen and pelvis", "direct access upper gastrointestinal endoscopy"

## Symptom term coding rules

1. **Strip ALL qualifiers** — do NOT write "unexplained", "persistent", \
   "recurrent", "significant". Write "weight loss" not "unexplained weight loss".
2. **Use the simplest SNOMED-codeable term** — what a GP would write in a \
   consultation note or select in clinical coding software.
3. **List each symptom separately** — NICE "one or more of" → each symptom is \
   its own entry in an ANY group.
4. **Simplify descriptive phrases** to their clinical concept:
   - "lump that is increasing in size" → "soft tissue mass"
   - "change in shape of testis" → "testicular swelling"
   - "post-menopausal bleeding" → "postmenopausal bleeding"
   - "lump on lip or in oral cavity" → "oral cavity mass"
   - "change in bowel habit" → "change in bowel habit"
   - "non-healing ulcer" → "skin ulcer"
   - "unexplained enlarged lymph node" → "lymphadenopathy"
   - "enlarged gallbladder" → "enlarged gallbladder"
5. **Age**: write exactly as "age N and over" or "age N and under". \
   Place age in its own ALL group.
6. **Sex**: write exactly as "female sex" or "male sex". \
   Include in an ALL group alongside age if both apply.
7. **Maximum 5 terms per group.**

## When to return empty criteria

If the recommendation is a general service standard (e.g. "services should \
ensure...", "patients should have access to...", "discuss with patients..."), \
return: {"criteria_groups": [], "action": null}

## Output format

Return ONLY valid JSON — no explanation, no markdown, no preamble:

{"criteria_groups": [{"mode": "ALL|ANY|NOT", "terms": ["term 1", ...]}], "action": "procedure term or null"}
"""

_NG12_FEW_SHOT = [
    {
        "id": "ng12-ex-001",
        "description": "Lung: age ALL + symptoms ANY (urgent chest X-ray)",
        "input": (
            "Chapter: Lung and pleural cancers\n"
            "Section: Lung cancer\n"
            "Recommendation 1.1.2: Offer an urgent chest X-ray (within 2 weeks) to people "
            "aged 40 and over if they have ever smoked and have one or more of the following "
            "unexplained symptoms: cough, fatigue, shortness of breath, chest pain, weight "
            "loss, appetite loss.\n"
            "Urgency: urgent_2w  Strength: offer"
        ),
        "output": json.dumps({
            "criteria_groups": [
                {"mode": "ALL", "terms": ["age 40 and over"]},
                {"mode": "ANY", "terms": ["cough", "dyspnoea", "weight loss", "chest pain", "haemoptysis"]},
            ],
            "action": "urgent chest X-ray",
        }),
        "category": "guidance_rule_extraction_NG12",
        "model_scope": "any",
        "core": True,
        "deidentified": True,
    },
    {
        "id": "ng12-ex-002",
        "description": "Urological: age ALL + symptom ANY + UTI exclusion NOT",
        "input": (
            "Chapter: Urological cancers\n"
            "Section: Bladder cancer\n"
            "Recommendation 1.6.1: Refer people using a suspected cancer pathway referral "
            "for bladder cancer if they are aged 45 years or over and have unexplained "
            "visible haematuria without urinary tract infection.\n"
            "Urgency: urgent_2w  Strength: refer"
        ),
        "output": json.dumps({
            "criteria_groups": [
                {"mode": "ALL", "terms": ["age 45 and over"]},
                {"mode": "ANY", "terms": ["haematuria"]},
                {"mode": "NOT", "terms": ["urinary tract infection"]},
            ],
            "action": "fast track referral for suspected urological cancer",
        }),
        "category": "guidance_rule_extraction_NG12",
        "model_scope": "any",
        "core": True,
        "deidentified": True,
    },
    {
        "id": "ng12-ex-003",
        "description": "Haematological: symptoms ANY only (no age constraint)",
        "input": (
            "Chapter: Haematological cancers\n"
            "Section: Non-Hodgkin's lymphoma\n"
            "Recommendation 1.10.6: Consider a suspected cancer pathway referral for "
            "non-Hodgkin's lymphoma in adults with unexplained lymphadenopathy or splenomegaly.\n"
            "Urgency: urgent_2w  Strength: consider"
        ),
        "output": json.dumps({
            "criteria_groups": [
                {"mode": "ANY", "terms": ["lymphadenopathy", "splenomegaly"]},
            ],
            "action": "fast track referral for suspected haematological malignancy",
        }),
        "category": "guidance_rule_extraction_NG12",
        "model_scope": "any",
        "core": True,
        "deidentified": True,
    },
    {
        "id": "ng12-ex-004",
        "description": "Organisational standard — no patient criteria",
        "input": (
            "Chapter: Patient information and support\n"
            "Section: Patient information\n"
            "Recommendation 1.14.1: Discuss with people with suspected cancer their "
            "preferences for being involved in decision-making about their care and "
            "treatment.\n"
            "Urgency: routine  Strength: discuss"
        ),
        "output": json.dumps({
            "criteria_groups": [],
            "action": None,
        }),
        "category": "guidance_rule_extraction_NG12",
        "model_scope": "any",
        "core": True,
        "deidentified": True,
    },
]

_NG12_OUTPUT_SCHEMA = {
    "description": "Return ONLY valid JSON — no explanation, no markdown, no preamble.",
    "type": "object",
    "required": ["criteria_groups", "action"],
    "properties": {
        "criteria_groups": {
            "type": "array",
            "description": (
                "List of criteria groups. Each group has 'mode' (ANY|ALL|NOT) and "
                "'terms' (list of plain clinical language strings). All groups AND "
                "together — every group must pass for the rule to fire."
            ),
            "items": {
                "type": "object",
                "required": ["mode", "terms"],
                "properties": {
                    "mode": {"type": "string", "enum": ["ANY", "ALL", "NOT"]},
                    "terms": {"type": "array", "maxItems": 5, "items": {"type": "string"}},
                },
            },
        },
        "action": {
            "type": ["string", "null"],
            "description": (
                "The site-specific fast track referral or investigation procedure term. "
                "Null if the recommendation is a service standard with no clinical action."
            ),
        },
    },
}

SEED_PROMPTS.append({
    "name": "guidance_rule_extraction_NG12",
    "version": 1,
    "description": (
        "NG12-specific guidance rule extraction prompt. Produces criteria_groups "
        "(ANY/ALL/NOT) with site-specific fast-track referral action terms. "
        "Used instead of guidance_rule_extraction_default for all NG12 recommendations."
    ),
    "system_prompt": _GUIDANCE_RULE_EXTRACTION_NG12_V1,
    "output_schema": json.dumps(_NG12_OUTPUT_SCHEMA),
    "verification": False,
    "few_shot_examples": _NG12_FEW_SHOT,
    "max_few_shot": 4,
})


def _get_driver():
    """Return a Neo4j driver for the Knowledge Graph."""
    from neo4j import GraphDatabase

    uri = os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI", os.getenv("NEO4J_URI", "bolt://localhost:7687"))
    user = os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", os.getenv("NEO4J_USER", os.getenv("NEO4J_USERNAME", "neo4j")))
    password = os.getenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", os.getenv("NEO4J_PASSWORD", "password"))
    return GraphDatabase.driver(uri, auth=(user, password))


def _prompt_exists(session, name: str, version: int) -> bool:
    """Return True if a PromptConfig with (name, version) is already in Neo4j."""
    from libs.cypher.prompt_config_queries import GET_PROMPT_BY_NAME
    row = session.run(GET_PROMPT_BY_NAME, name=name, version=version).single()
    return row is not None


def seed_if_missing() -> None:
    """Seed only prompts that are not yet present in Neo4j.

    This is the startup-safe variant: it skips prompts that already exist
    (regardless of source), so it never overwrites user-edited prompts and
    adds minimal overhead when all prompts are already seeded.

    Called from the API lifespan on startup via a background thread.
    """
    driver = _get_driver()
    try:
        with driver.session() as session:
            session.run(CREATE_CONSTRAINT)
            session.run(CREATE_INDEX_NAME)

        seeded = 0
        skipped = 0
        for prompt in SEED_PROMPTS:
            with driver.session() as session:
                if _prompt_exists(session, prompt["name"], prompt["version"]):
                    skipped += 1
                    continue
                session.run(
                    UPSERT_SEED_PROMPT,
                    id=str(uuid.uuid4()),
                    name=prompt["name"],
                    version=prompt["version"],
                    description=prompt.get("description", ""),
                    system_prompt=prompt["system_prompt"],
                    output_schema=prompt["output_schema"],
                    verification=prompt["verification"],
                    few_shot_examples=json.dumps(prompt.get("few_shot_examples", [])),
                    max_few_shot=int(prompt.get("max_few_shot", 20)),
                )
                seeded += 1
                logger.info("[PromptSeed] Seeded %s v%d", prompt["name"], prompt["version"])

        if seeded:
            logger.info("[PromptSeed] Done — %d seeded, %d already present.", seeded, skipped)
        else:
            logger.debug("[PromptSeed] All %d prompts already present — nothing to seed.", skipped)
    finally:
        driver.close()


def main(missing_only: bool = False) -> None:
    driver = _get_driver()

    with driver.session() as session:
        session.run(CREATE_CONSTRAINT)
        session.run(CREATE_INDEX_NAME)
        logger.info("Constraints & indexes ensured.")

    seeded = 0
    for prompt in SEED_PROMPTS:
        with driver.session() as session:
            if missing_only and _prompt_exists(session, prompt["name"], prompt["version"]):
                logger.info("  %s v%d — already present, skipped", prompt["name"], prompt["version"])
                continue
            result = session.run(
                UPSERT_SEED_PROMPT,
                id=str(uuid.uuid4()),
                name=prompt["name"],
                version=prompt["version"],
                description=prompt.get("description", ""),
                system_prompt=prompt["system_prompt"],
                output_schema=prompt["output_schema"],
                verification=prompt["verification"],
                few_shot_examples=json.dumps(prompt.get("few_shot_examples", [])),
                max_few_shot=int(prompt.get("max_few_shot", 20)),
            ).single()
            source = result["source"] if result else "unknown"
            action = "created" if source == "seed" else "skipped (user-edited)"
            n_examples = len(prompt.get("few_shot_examples", []))
            logger.info(
                "  %s v%d — %s (%d examples)",
                prompt["name"], prompt["version"], action, n_examples,
            )
            seeded += 1

    driver.close()
    logger.info("Done. %d prompts processed.", seeded)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Seed PromptConfig nodes into Neo4j")
    parser.add_argument("--missing", action="store_true", help="Only seed prompts not yet in Neo4j")
    args = parser.parse_args()
    main(missing_only=args.missing)
