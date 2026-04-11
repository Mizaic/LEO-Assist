"""Seed ModelPreset nodes into the Knowledge Graph.

Run once (or re-run safely — queries are idempotent):
    python scripts/seed_presets.py

Presets are named, reusable pipeline configurations that pathway designers
pick when building workflow steps.  System presets (is_system=True) cannot
be deleted via the UI.

Only seeds when no ModelPreset nodes exist; skips if any are already present
to avoid overwriting user-modified presets.
"""

from __future__ import annotations

import os
import sys

# Load secrets before any lib imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
try:
    from dotenv import load_dotenv

    load_dotenv("secrets/.env.config", override=False)
    load_dotenv("secrets/.env", override=False)
except ImportError:
    pass
try:
    from libs.keyvault.loader import load_keyvault_secrets

    load_keyvault_secrets()
except Exception:
    pass

from libs.cypher.preset_queries import UPSERT_PRESET, SET_DEFAULT_PRESET
from libs.neo4j_client.client import KnowledgeGraphClient

# ---------------------------------------------------------------------------
# Preset definitions
# ---------------------------------------------------------------------------

PRESETS = [
    {
        "preset_id": "preset-training",
        "name": "Training",
        "description": (
            "Used when running the gold training pipeline. "
            "Two AI assistants check each other's work — more reliable for building accurate training data."
        ),
        "consensus_mode": True,
        "primary_model": "device-aws-small",  # Amazon Claude Haiku
        "secondary_model": "device-azure-small",  # Microsoft GPT-5 mini
        "tiebreaker_model": "device-aws-big",  # Amazon Claude Sonnet arbitrates
        "extractor": "llm",  # AI finds terms (NER not yet trained on gold data)
        "strict": False,
        "prompt_config_id": "",
        "color": "success",
        "is_system": True,
        "is_default": False,
    },
    {
        "preset_id": "preset-inference",
        "name": "Inference",
        "description": (
            "Used for live patient processing. "
            "Single fast AI with the trained medical coder as primary extractor — quick and accurate."
        ),
        "consensus_mode": False,
        "primary_model": "device-aws-small",  # Amazon Claude Haiku
        "secondary_model": "device-azure-small",  # not used in single mode
        "tiebreaker_model": "device-aws-big",  # not used in single mode
        "extractor": "ner+llm",  # medical coder first, AI as backup
        "strict": False,
        "prompt_config_id": "",
        "color": "primary",
        "is_system": True,
        "is_default": True,
    },
    {
        "preset_id": "preset-quality-check",
        "name": "Quality check",
        "description": (
            "Used for verification and auditing runs. "
            "Two AIs check each other; the most careful model steps in if they disagree."
        ),
        "consensus_mode": True,
        "primary_model": "device-aws-small",  # Amazon Claude Haiku
        "secondary_model": "device-azure-small",  # Microsoft GPT-5 mini
        "tiebreaker_model": "device-aws-max",  # Amazon Claude Opus — most careful
        "extractor": "llm",
        "strict": True,
        "prompt_config_id": "",
        "color": "warning",
        "is_system": True,
        "is_default": False,
    },
]

# ---------------------------------------------------------------------------
# Seed
# ---------------------------------------------------------------------------


def main() -> None:
    client = KnowledgeGraphClient()
    default_preset_id = None

    try:
        with client.session() as session:
            result = session.run(
                "MATCH (p:ModelPreset) RETURN count(p) AS cnt"
            ).single()
            existing = result["cnt"] if result else 0
            if existing > 0:
                print(f"Skipped — {existing} ModelPreset(s) already present.")
                return

            for p in PRESETS:
                session.run(
                    UPSERT_PRESET,
                    preset_id=p["preset_id"],
                    name=p["name"],
                    description=p["description"],
                    consensus_mode=p["consensus_mode"],
                    primary_model=p["primary_model"],
                    secondary_model=p["secondary_model"],
                    tiebreaker_model=p["tiebreaker_model"],
                    extractor=p["extractor"],
                    strict=p["strict"],
                    prompt_config_id=p["prompt_config_id"] or None,
                    color=p["color"],
                    is_default=p.get("is_default", False),
                    is_system=p.get("is_system", False),
                )
                if p.get("is_default"):
                    default_preset_id = p["preset_id"]
                print(f"  [ok] {p['preset_id']} - {p['name']}")

            if default_preset_id:
                session.run(SET_DEFAULT_PRESET, preset_id=default_preset_id)
                print(f"  [default] {default_preset_id}")

    finally:
        client.close()

    print(f"Done. {len(PRESETS)} presets seeded.")


if __name__ == "__main__":
    main()
