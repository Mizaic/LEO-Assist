"""Import curated few-shot examples back into PromptConfig nodes.

Input JSON format:
{
  "prompts": [
    {
      "name": "extraction",
      "version": 1,
      "max_few_shot": 20,
      "few_shot_examples": [ ... ]
    }
  ]
}
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

BACKUP_DIR = ROOT / "scripts" / "investigations" / "prompt_few_shot_backups"
CONFIRM_TOKEN = "IMPORT_FEW_SHOT"

_GET_PROMPT = """
MATCH (p:PromptConfig {name: $name, version: $version})
RETURN p.id AS id, p.name AS name, p.version AS version,
       p.few_shot_examples AS few_shot_examples, p.max_few_shot AS max_few_shot
"""

_UPDATE_PROMPT = """
MATCH (p:PromptConfig {name: $name, version: $version})
SET p.few_shot_examples = $few_shot_examples,
    p.max_few_shot = $max_few_shot,
    p.updated_at = datetime(),
    p.source = 'user'
RETURN p.id AS id, p.name AS name, p.version AS version
"""


def _load_env() -> None:
    load_dotenv(ROOT / "secrets" / ".env.config", override=False)
    load_dotenv(ROOT / "secrets" / ".env.secrets", override=False)
    load_dotenv(ROOT / "secrets" / ".env", override=False)
    try:
        from libs.keyvault.loader import load_keyvault_secrets

        load_keyvault_secrets()
    except ModuleNotFoundError:
        print("Key Vault dependencies missing; using local environment only.")


def _validate_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    prompts = payload.get("prompts")
    if not isinstance(prompts, list) or not prompts:
        raise ValueError("Input JSON must include non-empty 'prompts' list.")

    validated: list[dict[str, Any]] = []
    for index, entry in enumerate(prompts):
        if not isinstance(entry, dict):
            raise ValueError(f"prompts[{index}] must be an object.")
        name = str(entry.get("name") or "").strip()
        version = int(entry.get("version") or 0)
        max_few_shot = int(entry.get("max_few_shot") or 0)
        examples = entry.get("few_shot_examples")
        if not name:
            raise ValueError(f"prompts[{index}].name is required.")
        if version <= 0:
            raise ValueError(f"prompts[{index}].version must be > 0.")
        if max_few_shot <= 0:
            raise ValueError(f"prompts[{index}].max_few_shot must be > 0.")
        if not isinstance(examples, list):
            raise ValueError(f"prompts[{index}].few_shot_examples must be a list.")
        validated.append(
            {
                "name": name,
                "version": version,
                "max_few_shot": max_few_shot,
                "few_shot_examples": examples,
            }
        )
    return validated


def _backup_existing(entries: list[dict[str, Any]], backup_path: Path) -> None:
    from libs.neo4j_client.client import KnowledgeGraphClient

    client = KnowledgeGraphClient()
    backup_rows: list[dict[str, Any]] = []
    try:
        with client.session() as session:
            for entry in entries:
                row = session.run(
                    _GET_PROMPT, name=entry["name"], version=entry["version"]
                ).single()
                if row:
                    backup_rows.append(dict(row))
    finally:
        client.close()

    backup_path.parent.mkdir(parents=True, exist_ok=True)
    backup_path.write_text(
        json.dumps(
            {
                "created_at_utc": datetime.now(tz=timezone.utc).isoformat(),
                "prompt_count": len(backup_rows),
                "prompts": backup_rows,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _apply_import(entries: list[dict[str, Any]]) -> int:
    from libs.neo4j_client.client import KnowledgeGraphClient

    client = KnowledgeGraphClient()
    updated = 0
    try:
        with client.session() as session:
            for entry in entries:
                row = session.run(
                    _UPDATE_PROMPT,
                    name=entry["name"],
                    version=entry["version"],
                    max_few_shot=entry["max_few_shot"],
                    few_shot_examples=json.dumps(entry["few_shot_examples"]),
                ).single()
                if row:
                    updated += 1
    finally:
        client.close()
    return updated


def _build_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import curated few-shot examples into PromptConfig."
    )
    parser.add_argument(
        "--input-json",
        required=True,
        help="Path to curated prompt payload JSON.",
    )
    parser.add_argument(
        "--backup-path",
        default="",
        help="Optional explicit backup path for existing prompt states.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply updates. Without this flag command is dry-run only.",
    )
    parser.add_argument(
        "--confirm",
        default="",
        help=f"Must equal {CONFIRM_TOKEN} when --apply is set.",
    )
    return parser.parse_args()


def main() -> None:
    args = _build_args()
    _load_env()

    payload = json.loads(Path(args.input_json).read_text(encoding="utf-8"))
    entries = _validate_payload(payload)

    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = (
        Path(args.backup_path)
        if args.backup_path
        else BACKUP_DIR / f"prompt_few_shot_import_backup_{ts}.json"
    )
    print(
        json.dumps(
            {
                "mode": "apply" if args.apply else "dry-run",
                "input_json": args.input_json,
                "backup_path": str(backup_path),
                "target_prompts": [
                    f"{entry['name']}@{entry['version']}" for entry in entries
                ],
                "total_examples": sum(
                    len(entry["few_shot_examples"]) for entry in entries
                ),
            },
            indent=2,
        )
    )

    if not args.apply:
        return
    if args.confirm.strip() != CONFIRM_TOKEN:
        raise SystemExit(f"--confirm must equal {CONFIRM_TOKEN} when --apply is used.")

    _backup_existing(entries, backup_path)
    updated = _apply_import(entries)
    print(
        json.dumps(
            {"backup_written": str(backup_path), "updated_prompts": updated}, indent=2
        )
    )


if __name__ == "__main__":
    main()
