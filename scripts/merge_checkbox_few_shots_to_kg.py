"""Merge form:checkbox few-shots into knowledge-graph PromptConfig nodes.

Merges with existing Neo4j examples (does not wipe the library), then updates
system_prompt text from libs for extraction + referral_extraction v1.

Usage:
  python -m scripts.merge_checkbox_few_shots_to_kg           # dry-run
  python -m scripts.merge_checkbox_few_shots_to_kg --apply --confirm IMPORT_FEW_SHOT
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

CONFIRM_TOKEN = "IMPORT_FEW_SHOT"
BACKUP_DIR = ROOT / "scripts" / "investigations" / "prompt_few_shot_backups"

_GET = """
MATCH (p:PromptConfig {name: $name, version: $version})
RETURN p.id AS id, p.name AS name, p.version AS version,
       p.few_shot_examples AS few_shot_examples,
       p.max_few_shot AS max_few_shot,
       p.system_prompt AS system_prompt,
       p.source AS source
"""

_SET = """
MATCH (p:PromptConfig {name: $name, version: $version})
SET p.few_shot_examples = $few_shot_examples,
    p.system_prompt = $system_prompt,
    p.max_few_shot = $max_few_shot,
    p.updated_at = datetime(),
    p.source = 'user'
RETURN p.id AS id, p.name AS name, p.version AS version
"""

TARGETS = (
    ("extraction", 1),
    ("referral_extraction", 1),
)


def _load_env() -> None:
    load_dotenv(ROOT / "secrets" / ".env.config", override=True)
    load_dotenv(ROOT / "secrets" / ".env.secrets", override=False)
    load_dotenv(ROOT / "secrets" / ".env", override=False)
    try:
        from libs.keyvault.loader import load_keyvault_secrets

        load_keyvault_secrets()
    except ModuleNotFoundError:
        print("Key Vault deps missing; using local env only.")


def _parse_examples(raw: Any) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if isinstance(raw, str):
        parsed = json.loads(raw)
        return _parse_examples(parsed)
    if isinstance(raw, list):
        out: list[dict[str, Any]] = []
        for item in raw:
            if isinstance(item, dict):
                out.append(dict(item))
            elif isinstance(item, str):
                out.append(json.loads(item))
            else:
                raise TypeError(f"Unexpected example type: {type(item)}")
        return out
    raise TypeError(f"Unexpected few_shot_examples type: {type(raw)}")


def _serialize_examples(examples: list[dict[str, Any]], like_raw: Any) -> Any:
    """Preserve existing Neo4j property shape (JSON string vs list of maps)."""
    if isinstance(like_raw, str):
        return json.dumps(examples)
    return examples


def _checkbox_examples() -> list[dict[str, Any]]:
    from libs.prompts.extraction_examples import EXTRACTION_EXAMPLES

    examples = [e for e in EXTRACTION_EXAMPLES if e.get("category") == "form:checkbox"]
    stamped: list[dict[str, Any]] = []
    for index, example in enumerate(examples, start=1):
        stamped.append(
            {
                "id": f"form_checkbox_{index:02d}",
                "input": example["input"],
                "output": example["output"],
                "deidentified": True,
                "category": example.get("category", "form:checkbox"),
                "model_scope": example.get("model_scope", "any"),
                "description": example.get("description", ""),
                "core": True,
            }
        )
    return stamped


def _merge(
    existing: list[dict[str, Any]], incoming: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], int, int]:
    by_id: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for ex in existing:
        eid = str(ex.get("id") or "")
        if not eid:
            eid = f"legacy_{len(order)}"
            ex = {**ex, "id": eid}
        if eid not in by_id:
            order.append(eid)
        by_id[eid] = ex

    replaced = 0
    added = 0
    for ex in incoming:
        eid = str(ex["id"])
        if eid in by_id:
            replaced += 1
        else:
            order.append(eid)
            added += 1
        by_id[eid] = ex
    return [by_id[i] for i in order], added, replaced


def _system_prompt(name: str) -> str:
    if name == "extraction":
        from libs.prompts.extraction_v1 import EXTRACTION_SYSTEM_V1

        return EXTRACTION_SYSTEM_V1
    if name == "referral_extraction":
        from libs.prompts.referral_extraction_v1 import REFERRAL_EXTRACTION_SYSTEM_V1

        return REFERRAL_EXTRACTION_SYSTEM_V1
    raise ValueError(name)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args()

    _load_env()
    incoming = _checkbox_examples()
    if not incoming:
        print("No form:checkbox examples found in EXTRACTION_EXAMPLES.")
        return 1
    print(f"Incoming checkbox examples: {len(incoming)}")

    from libs.neo4j_client.client import KnowledgeGraphClient

    client = KnowledgeGraphClient()
    backup_rows: list[dict[str, Any]] = []
    plans: list[dict[str, Any]] = []
    try:
        with client.session() as session:
            for name, version in TARGETS:
                row = session.run(_GET, name=name, version=version).single()
                if not row:
                    print(f"MISSING PromptConfig name={name} version={version}")
                    return 1
                raw = row["few_shot_examples"]
                existing = _parse_examples(raw)
                merged, added, replaced = _merge(existing, incoming)
                max_few = int(row["max_few_shot"] or 20)
                system_prompt = _system_prompt(name)
                plans.append(
                    {
                        "name": name,
                        "version": version,
                        "before": len(existing),
                        "after": len(merged),
                        "added": added,
                        "replaced": replaced,
                        "max_few_shot": max_few,
                        "merged": merged,
                        "serialized": _serialize_examples(merged, raw),
                        "system_prompt": system_prompt,
                        "system_prompt_changed": system_prompt
                        != (row["system_prompt"] or ""),
                        "storage": type(raw).__name__,
                    }
                )
                backup_rows.append(
                    {
                        "id": row["id"],
                        "name": name,
                        "version": version,
                        "source": row["source"],
                        "max_few_shot": max_few,
                        "few_shot_examples": existing,
                        "system_prompt": row["system_prompt"],
                    }
                )

        stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_path = BACKUP_DIR / f"checkbox_merge_backup_{stamp}.json"
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        backup_path.write_text(
            json.dumps(
                {
                    "created_at_utc": datetime.now(tz=timezone.utc).isoformat(),
                    "prompts": backup_rows,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"Backup written: {backup_path}")

        for plan in plans:
            print(
                f"{plan['name']} v{plan['version']}: "
                f"{plan['before']} -> {plan['after']} "
                f"(+{plan['added']} ~{plan['replaced']}) "
                f"storage={plan['storage']} "
                f"system_prompt_changed={plan['system_prompt_changed']}"
            )

        if not args.apply:
            print("Dry-run only. Re-run with --apply --confirm IMPORT_FEW_SHOT")
            return 0
        if args.confirm != CONFIRM_TOKEN:
            print(f"Refusing apply without --confirm {CONFIRM_TOKEN}")
            return 1

        with client.session() as session:
            for plan in plans:
                session.run(
                    _SET,
                    name=plan["name"],
                    version=plan["version"],
                    few_shot_examples=plan["serialized"],
                    system_prompt=plan["system_prompt"],
                    max_few_shot=plan["max_few_shot"],
                )
                print(f"Updated {plan['name']} v{plan['version']}")

            for name, version in TARGETS:
                row = session.run(_GET, name=name, version=version).single()
                examples = _parse_examples(row["few_shot_examples"])
                ids = {str(e.get("id")) for e in examples}
                cats = {str(e.get("category")) for e in examples}
                missing = [e["id"] for e in incoming if e["id"] not in ids]
                sp = row["system_prompt"] or ""
                print(
                    f"Verify {name}: total={len(examples)} "
                    f"has_form_checkbox={'form:checkbox' in cats} "
                    f"missing_ids={missing} "
                    f"checkbox_rule={'Checkbox / guideline criteria forms' in sp}"
                )
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
