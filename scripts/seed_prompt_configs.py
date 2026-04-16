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
    SEED_PROMPTS.append(
        {
            "name": name,
            "version": version,
            "description": description,
            "system_prompt": text,
            "output_schema": output_schema,
            "verification": False,
            "few_shot_examples": few_shot_examples or [],
            "max_few_shot": max_few_shot,
        }
    )


# ── Extraction — structured output schema + example library ─────────────────
from libs.prompts.extraction_output_schema import EXTRACTION_OUTPUT_SCHEMA
from libs.prompts.extraction_examples import EXTRACTION_EXAMPLES
from libs.prompts.extraction_check_v1 import EXTRACTION_CHECK_EXAMPLES_V2
from libs.prompts.coding_check_v1 import CODING_CHECK_EXAMPLES_V1
from libs.prompts.relation_linking_v1 import RELATION_LINKING_EXAMPLES_V1

_add(
    "extraction",
    1,
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

_EXTRACTION_CHECK_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "drop": {"type": "array", "items": {"type": "integer"}},
        "correct_assertion": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "assertion": {"type": "string"},
                },
                "required": ["index", "assertion"],
            },
        },
        "correct_label": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "label": {"type": "string"},
                },
                "required": ["index", "label"],
            },
        },
        "add": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "label": {"type": "string"},
                    "assertion": {"type": "string"},
                    "lookup_term": {"type": "string"},
                },
                "required": ["text", "label", "assertion", "lookup_term"],
            },
        },
    },
    "required": ["drop", "correct_assertion", "correct_label", "add"],
}

_EXTRACTION_CHECK_OUTPUT_SCHEMA_V2 = {
    "type": "object",
    "properties": {
        "drop": {"type": "array", "items": {"type": "integer"}},
        "correct_assertion": _EXTRACTION_CHECK_OUTPUT_SCHEMA["properties"][
            "correct_assertion"
        ],
        "correct_label": _EXTRACTION_CHECK_OUTPUT_SCHEMA["properties"]["correct_label"],
        "add": _EXTRACTION_CHECK_OUTPUT_SCHEMA["properties"]["add"],
        "correct_relation": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "relations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {"type": "string"},
                                "target_idx": {"type": "integer"},
                                "target_text": {"type": "string"},
                                "confidence": {"type": "number"},
                            },
                            "required": ["type", "target_idx"],
                        },
                    },
                },
                "required": ["index", "relations"],
            },
        },
        "add_relation": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "type": {"type": "string"},
                    "target_idx": {"type": "integer"},
                    "target_text": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["index", "type", "target_idx"],
            },
        },
    },
    "required": [
        "drop",
        "correct_assertion",
        "correct_label",
        "add",
        "correct_relation",
        "add_relation",
    ],
}

_add(
    "extraction_check",
    2,
    "libs.prompts.extraction_check_v1.EXTRACTION_CHECK_SYSTEM_V2",
    output_schema=json.dumps(_EXTRACTION_CHECK_OUTPUT_SCHEMA_V2),
    few_shot_examples=[
        {
            "id": f"seed_excheck_{i:03d}",
            "input": ex["input"],
            "output": ex["output"],
            "deidentified": True,
            "category": ex.get("category", ""),
            "model_scope": ex.get("model_scope", "any"),
            "description": ex.get("description", ""),
            "core": bool(ex.get("core", False)),
        }
        for i, ex in enumerate(EXTRACTION_CHECK_EXAMPLES_V2)
    ],
    max_few_shot=12,
    description="Single-turn extraction quality check for entity and relation corrections.",
)

_RELATION_LINKING_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "relations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "head_idx": {"type": "integer"},
                    "tail_idx": {"type": "integer"},
                    "type": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["head_idx", "tail_idx", "type"],
            },
        },
        "suppress": {"type": "array", "items": {"type": "integer"}},
    },
    "required": ["relations", "suppress"],
}

_add(
    "relation_linking",
    1,
    "libs.prompts.relation_linking_v1.RELATION_LINKING_SYSTEM_V1",
    output_schema=json.dumps(_RELATION_LINKING_OUTPUT_SCHEMA),
    few_shot_examples=[
        {
            "id": f"seed_rellink_{i:03d}",
            "input": ex["input"],
            "output": ex["output"],
            "deidentified": True,
            "category": ex.get("category", ""),
            "model_scope": ex.get("model_scope", "any"),
            "description": ex.get("description", ""),
            "core": bool(ex.get("core", False)),
        }
        for i, ex in enumerate(RELATION_LINKING_EXAMPLES_V1)
    ],
    max_few_shot=8,
    description="Links extracted entities with typed relations such as finding_site.",
)

_CODING_CHECK_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "drop": {"type": "array", "items": {"type": "integer"}},
        "force_review": {"type": "array", "items": {"type": "integer"}},
    },
    "required": ["drop", "force_review"],
}

_add(
    "coding_check",
    1,
    "libs.prompts.coding_check_v1.CODING_CHECK_SYSTEM_V1",
    output_schema=json.dumps(_CODING_CHECK_OUTPUT_SCHEMA),
    few_shot_examples=[
        {
            "id": f"seed_codecheck_{i:03d}",
            "input": ex["input"],
            "output": ex["output"],
            "deidentified": True,
            "category": ex.get("category", ""),
            "model_scope": ex.get("model_scope", "any"),
            "description": ex.get("description", ""),
            "core": bool(ex.get("core", False)),
        }
        for i, ex in enumerate(CODING_CHECK_EXAMPLES_V1)
    ],
    max_few_shot=8,
    description="Single-turn quality check that drops unsupported codes and forces review on ambiguous coding.",
)

# ── Disambiguation ────────────────────────────────────────────────────────────
from libs.prompts.disambiguation_output_schema import DISAMBIGUATION_OUTPUT_SCHEMA
from libs.prompts.disambiguation_examples import DISAMBIGUATION_EXAMPLES

_add(
    "disambiguation",
    1,
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
    "episode_builder_system",
    1,
    "libs.prompts.episode_builder_v1.EPISODE_BUILDER_SYSTEM_V1",
    output_schema=json.dumps(EPISODE_BUILDER_OUTPUT_SCHEMA),
    few_shot_examples=_builder_examples,
    max_few_shot=20,
    description="System role for the episode builder — groups coded entities into clinical episodes.",
)
_add(
    "episode_builder_task",
    1,
    "libs.prompts.episode_builder_v1.EPISODE_BUILDER_TASK_V1",
    output_schema=json.dumps(EPISODE_BUILDER_OUTPUT_SCHEMA),
    few_shot_examples=_builder_examples,
    max_few_shot=20,
    description="Task instructions for the episode builder — structures entities per clinical encounter.",
)
_add(
    "episode_consolidation_system",
    1,
    "libs.prompts.episode_builder_v1.EPISODE_CONSOLIDATION_SYSTEM_V1",
    output_schema=json.dumps(EPISODE_CONSOLIDATION_OUTPUT_SCHEMA),
    few_shot_examples=_consolidation_examples,
    max_few_shot=20,
    description="System role for cross-encounter episode consolidation.",
)
_add(
    "episode_consolidation_task",
    1,
    "libs.prompts.episode_builder_v1.EPISODE_CONSOLIDATION_TASK_V1",
    output_schema=json.dumps(EPISODE_CONSOLIDATION_OUTPUT_SCHEMA),
    few_shot_examples=_consolidation_examples,
    max_few_shot=20,
    description="Task instructions for consolidating episodes across multiple encounters.",
)

# ── Encounter classify ─────────────────────────────────────────────────────────
from libs.prompts.encounter_classify_output_schema import (
    ENCOUNTER_CLASSIFY_OUTPUT_SCHEMA,
)
from libs.prompts.encounter_classify_examples import ENCOUNTER_CLASSIFY_EXAMPLES

_add(
    "encounter_classify",
    1,
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
from libs.prompts.anchor_domain_review_output_schema import (
    ANCHOR_DOMAIN_REVIEW_OUTPUT_SCHEMA,
)
from libs.prompts.anchor_domain_review_examples import ANCHOR_DOMAIN_REVIEW_EXAMPLES

_add(
    "anchor_domain_review",
    1,
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
    "exclusion_detect",
    1,
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
_add(
    "annotation_guidelines",
    1,
    "libs.prompts.annotation_guidelines_v1.ANNOTATION_GUIDELINES_V1",
    output_schema="{}",
    few_shot_examples=[],
    max_few_shot=0,
    description=(
        "Canonical annotation rules shared across extraction, quality checks, "
        "relation linking, and human gold review."
    ),
)

# ── Label verification ─────────────────────────────────────────────────────────
from libs.prompts.label_verification_output_schema import (
    LABEL_VERIFICATION_OUTPUT_SCHEMA,
)
from libs.prompts.label_verification_examples import LABEL_VERIFICATION_EXAMPLES

_add(
    "label_verification",
    2,
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

# ── Pipeline verification ─────────────────────────────────────────────────────
from libs.prompts.verification_output_schema import VERIFICATION_OUTPUT_SCHEMA
from libs.prompts.verification_examples import VERIFICATION_EXAMPLES

_add(
    "verification",
    1,
    "libs.prompts.verification_v1.VERIFICATION_V1",
    output_schema=json.dumps(VERIFICATION_OUTPUT_SCHEMA),
    few_shot_examples=[
        {
            "id": f"seed_verify_{i:03d}",
            "input": ex["input"],
            "output": ex["output"],
            "deidentified": True,
            "category": ex.get("category", ""),
            "model_scope": ex.get("model_scope", "any"),
            "description": ex.get("description", ""),
            "core": bool(ex.get("core", False)),
        }
        for i, ex in enumerate(VERIFICATION_EXAMPLES)
    ],
    max_few_shot=12,
    description="Pipeline verification judge for material extraction errors with optional terminology lookups.",
)

# ── Label disambiguation ───────────────────────────────────────────────────────
from libs.prompts.label_disambiguation_output_schema import (
    LABEL_DISAMBIGUATION_OUTPUT_SCHEMA,
)
from libs.prompts.label_disambiguation_examples import LABEL_DISAMBIGUATION_EXAMPLES

_add(
    "label_disambiguation",
    1,
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

# ── NICE → Rules: guidance rule extraction + verifier ─────────────────────────
from libs.prompts.guidance_rule_extraction_output_schema import (
    GUIDANCE_RULE_EXTRACTION_OUTPUT_SCHEMA,
    GUIDANCE_RULE_EXTRACTION_EXAMPLES,
)
from libs.prompts.guidance_rule_code_verifier_output_schema import (
    GUIDANCE_RULE_CODE_VERIFIER_OUTPUT_SCHEMA,
    GUIDANCE_RULE_CODE_VERIFIER_EXAMPLES,
)

_GRE_DESCRIPTION = (
    "Extracts exact patient-level clinical logic trees from a single NICE "
    "recommendation, preserving OR branches, thresholds, exclusions, and "
    "branch-local demographics."
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

_add(
    "guidance_rule_extraction",
    1,
    "libs.prompts.guidance_rule_extraction_v1.GUIDANCE_RULE_EXTRACTION_SYSTEM_V1",
    output_schema=json.dumps(GUIDANCE_RULE_EXTRACTION_OUTPUT_SCHEMA),
    few_shot_examples=_GRE_FEW_SHOT,
    max_few_shot=4,
    description=_GRE_DESCRIPTION,
)
_add(
    "guidance_rule_extraction_default",
    1,
    "libs.prompts.guidance_rule_extraction_v1.GUIDANCE_RULE_EXTRACTION_SYSTEM_V1",
    output_schema=json.dumps(GUIDANCE_RULE_EXTRACTION_OUTPUT_SCHEMA),
    few_shot_examples=_GRE_FEW_SHOT,
    max_few_shot=4,
    description=_GRE_DESCRIPTION,
)
_add(
    "guidance_rule_extraction",
    2,
    "libs.prompts.guidance_rule_extraction_v1.GUIDANCE_RULE_EXTRACTION_SYSTEM_V2",
    output_schema=json.dumps(GUIDANCE_RULE_EXTRACTION_OUTPUT_SCHEMA),
    few_shot_examples=_GRE_FEW_SHOT,
    max_few_shot=4,
    description=_GRE_DESCRIPTION,
)
_add(
    "guidance_rule_extraction_default",
    2,
    "libs.prompts.guidance_rule_extraction_v1.GUIDANCE_RULE_EXTRACTION_SYSTEM_V2",
    output_schema=json.dumps(GUIDANCE_RULE_EXTRACTION_OUTPUT_SCHEMA),
    few_shot_examples=_GRE_FEW_SHOT,
    max_few_shot=4,
    description=_GRE_DESCRIPTION,
)
_add(
    "guidance_rule_leaf_expansion",
    1,
    "libs.prompts.guidance_rule_extraction_v1.GUIDANCE_RULE_LEAF_EXPANSION_SYSTEM_V1",
    output_schema=json.dumps(
        {
            "type": "object",
            "properties": {
                "category": {"type": "string"},
                "concrete_terms": {"type": "array", "items": {"type": "string"}},
                "search_terms": {"type": "array", "items": {"type": "string"}},
                "safety_note": {"type": "string"},
            },
            "required": ["category", "concrete_terms", "search_terms"],
        }
    ),
    few_shot_examples=[],
    max_few_shot=0,
    description="Expands abstract NICE criterion phrases into concrete codable findings/search terms.",
)

_GUIDANCE_RULE_EXTRACTION_NG12_V1 = """\
You are a clinical decision-support analyst working with NICE guideline NG12
(Suspected cancer: recognition and referral) for the NHS in England.

Return an EXACT patient-rule `logic_tree` that preserves:
- OR branches
- AND branches
- threshold logic such as "2 or more"
- branch-local demographics
- exclusions

Do NOT flatten multiple branches into one approximate list.

## NG12-specific action rules

The `action` must be the site-specific procedure/referral term.
Use explicit fast-track referral wording when the recommendation is a suspected
cancer pathway referral, for example:
- `fast track referral for suspected sarcoma`
- `fast track referral for suspected lung cancer`
- `fast track referral for suspected skin cancer`
- `fast track referral for suspected brain tumour`
- `fast track referral for suspected breast cancer`
- `fast track referral for suspected childrens tumour`
- `fast track referral for suspected urological cancer`
- `fast track referral for suspected colorectal cancer`
- `fast track referral for suspected head and neck cancer`
- `fast track referral for suspected gynaecological cancer`
- `fast track referral for suspected haematology malignancy`
- `fast track referral for suspected lower gastrointestinal cancer`
- `fast track referral for suspected upper gastrointestinal cancer`
- `fast track referral for suspected cancer due to non-site-specific symptoms`

Map site wording to these USC pathways:
- stomach/gastric/oesophageal -> upper gastrointestinal
- anal -> lower gastrointestinal
- thyroid/oral/laryngeal -> head and neck
- myeloma/lymphoma/hodgkin -> haematology malignancy
- neuroblastoma/retinoblastoma -> childrens tumour

When the recommendation is an investigation, use a specific procedure term such
as:
- `urgent chest X-ray`
- `serum CA125 measurement`
- `direct access upper gastrointestinal endoscopy`

## Clinical wording rules

1. Use broad, coder-realistic terms rather than narrow cancer-diagnosis terms.
2. Strip qualifiers like `unexplained`, `persistent`, and `recurrent` from the
   main coded term, but keep the original wording in `source_text` if helpful.
3. For vague NICE phrases, provide 1-5 broad `search_terms` that a terminology
   resolver can try.
4. For wording such as `suggestive of`, `suspicious of`, `raises suspicion of`,
   or `consistent with`, keep the leaf at finding/situation level unless the
   NICE text is explicitly diagnostic.
5. Use `demographic` nodes for age or sex.
6. If an exact site-specific referral term is unavailable, prefer the closest
   specialty umbrella referral that preserves site intent (`gynaecological`,
   `urological`, `upper gastrointestinal`) rather than a wrong-site referral.
7. Do not inflate urgency. Keep `non-urgent` or `routine` actions as such.
8. If the recommendation is a service standard with no patient trigger, return
   `logic_tree: null` and `action: null`.

## Output format

Return ONLY valid JSON:
{
  "schema_version": 2,
  "logic_tree": { ... } | null,
  "action": {"text":"...", "search_terms":["...", "..."]} | null
}\
"""

_NG12_FEW_SHOT = [
    {
        **ex,
        "category": "guidance_rule_extraction_NG12",
    }
    for ex in GUIDANCE_RULE_EXTRACTION_EXAMPLES
]

SEED_PROMPTS.append(
    {
        "name": "guidance_rule_extraction_NG12",
        "version": 1,
        "description": (
            "NG12-specific exact rule extraction prompt. Produces schema_version=2 "
            "logic trees with site-specific fast-track referral or investigation actions."
        ),
        "system_prompt": _GUIDANCE_RULE_EXTRACTION_NG12_V1,
        "output_schema": json.dumps(GUIDANCE_RULE_EXTRACTION_OUTPUT_SCHEMA),
        "verification": False,
        "few_shot_examples": _NG12_FEW_SHOT,
        "max_few_shot": 4,
    }
)
SEED_PROMPTS.append(
    {
        "name": "guidance_rule_extraction_NG12",
        "version": 2,
        "description": (
            "NG12-specific exact rule extraction prompt. Produces schema_version=2 "
            "logic trees with site-specific fast-track referral or investigation actions."
        ),
        "system_prompt": _GUIDANCE_RULE_EXTRACTION_NG12_V1,
        "output_schema": json.dumps(GUIDANCE_RULE_EXTRACTION_OUTPUT_SCHEMA),
        "verification": False,
        "few_shot_examples": _NG12_FEW_SHOT,
        "max_few_shot": 4,
    }
)

_GRCV_DESCRIPTION = (
    "Verifies terminology candidates for guidance-rule leaves/actions and either "
    "approves a concept or requests broader alternate search terms."
)
_GRCV_FEW_SHOT = [
    {
        "id": ex["id"],
        "input": ex["input"],
        "output": ex["output"],
        "deidentified": ex.get("deidentified", True),
        "category": ex.get("category", "guidance_rule_code_verifier"),
        "model_scope": ex.get("model_scope", "any"),
        "description": ex.get("description", ""),
        "core": bool(ex.get("core", True)),
    }
    for ex in GUIDANCE_RULE_CODE_VERIFIER_EXAMPLES
]

_add(
    "guidance_rule_code_verifier",
    1,
    "libs.prompts.guidance_rule_code_verifier_v1.GUIDANCE_RULE_CODE_VERIFIER_SYSTEM_V1",
    output_schema=json.dumps(GUIDANCE_RULE_CODE_VERIFIER_OUTPUT_SCHEMA),
    few_shot_examples=_GRCV_FEW_SHOT,
    max_few_shot=4,
    description=_GRCV_DESCRIPTION,
)
_add(
    "guidance_rule_code_verifier_default",
    1,
    "libs.prompts.guidance_rule_code_verifier_v1.GUIDANCE_RULE_CODE_VERIFIER_SYSTEM_V1",
    output_schema=json.dumps(GUIDANCE_RULE_CODE_VERIFIER_OUTPUT_SCHEMA),
    few_shot_examples=_GRCV_FEW_SHOT,
    max_few_shot=4,
    description=_GRCV_DESCRIPTION,
)
_add(
    "guidance_rule_code_verifier",
    2,
    "libs.prompts.guidance_rule_code_verifier_v1.GUIDANCE_RULE_CODE_VERIFIER_SYSTEM_V2",
    output_schema=json.dumps(GUIDANCE_RULE_CODE_VERIFIER_OUTPUT_SCHEMA),
    few_shot_examples=_GRCV_FEW_SHOT,
    max_few_shot=4,
    description=_GRCV_DESCRIPTION,
)
_add(
    "guidance_rule_code_verifier_default",
    2,
    "libs.prompts.guidance_rule_code_verifier_v1.GUIDANCE_RULE_CODE_VERIFIER_SYSTEM_V2",
    output_schema=json.dumps(GUIDANCE_RULE_CODE_VERIFIER_OUTPUT_SCHEMA),
    few_shot_examples=_GRCV_FEW_SHOT,
    max_few_shot=4,
    description=_GRCV_DESCRIPTION,
)


def _get_driver():
    """Return a Neo4j driver for the Knowledge Graph."""
    from neo4j import GraphDatabase

    uri = os.getenv(
        "KNOWLEDGE_GRAPH_NEO4J_URI", os.getenv("NEO4J_URI", "bolt://localhost:7687")
    )
    user = os.getenv(
        "KNOWLEDGE_GRAPH_NEO4J_USERNAME",
        os.getenv("NEO4J_USER", os.getenv("NEO4J_USERNAME", "neo4j")),
    )
    password = os.getenv(
        "KNOWLEDGE_GRAPH_NEO4J_PASSWORD", os.getenv("NEO4J_PASSWORD", "password")
    )
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
                logger.info(
                    "[PromptSeed] Seeded %s v%d", prompt["name"], prompt["version"]
                )

        if seeded:
            logger.info(
                "[PromptSeed] Done — %d seeded, %d already present.", seeded, skipped
            )
        else:
            logger.debug(
                "[PromptSeed] All %d prompts already present — nothing to seed.",
                skipped,
            )
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
            if missing_only and _prompt_exists(
                session, prompt["name"], prompt["version"]
            ):
                logger.info(
                    "  %s v%d — already present, skipped",
                    prompt["name"],
                    prompt["version"],
                )
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
                prompt["name"],
                prompt["version"],
                action,
                n_examples,
            )
            seeded += 1

    driver.close()
    logger.info("Done. %d prompts processed.", seeded)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Seed PromptConfig nodes into Neo4j")
    parser.add_argument(
        "--missing", action="store_true", help="Only seed prompts not yet in Neo4j"
    )
    args = parser.parse_args()
    main(missing_only=args.missing)
