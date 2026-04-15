"""One-off utility to back up and clear PromptConfig few-shot examples.

Safety defaults:
- Dry-run by default (no database mutation).
- Creates a JSON backup before any mutation.
- Requires --apply + --confirm CLEAR_FEW_SHOT to mutate.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

BACKUP_DIR = ROOT / "scripts" / "investigations" / "prompt_few_shot_backups"
CONFIRM_TOKEN = "CLEAR_FEW_SHOT"

_LIST_PROMPTS = """
MATCH (p:PromptConfig)
RETURN
  p.id AS id,
  p.name AS name,
  p.version AS version,
  p.source AS source,
  p.description AS description,
  p.few_shot_examples AS few_shot_examples,
  p.max_few_shot AS max_few_shot,
  toString(p.updated_at) AS updated_at
ORDER BY p.name, p.version
"""

_CLEAR_PROMPT = """
MATCH (p:PromptConfig {id: $id})
SET p.few_shot_examples = '[]',
    p.updated_at = datetime()
RETURN p.id AS id, p.name AS name, p.version AS version
"""


@dataclass(frozen=True)
class PromptSnapshot:
    id: str
    name: str
    version: int
    source: str
    description: str
    few_shot_examples_raw: str
    max_few_shot: int
    updated_at: str

    @property
    def few_shot_count(self) -> int:
        return count_few_shot_examples(self.few_shot_examples_raw)


def count_few_shot_examples(raw: Any) -> int:
    """Return parsed few-shot list length from Neo4j field."""
    if raw is None:
        return 0
    if isinstance(raw, list):
        return len(raw)
    if not isinstance(raw, str):
        return 0
    text = raw.strip()
    if not text:
        return 0
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return 0
    return len(parsed) if isinstance(parsed, list) else 0


def _load_prompts() -> list[PromptSnapshot]:
    from libs.neo4j_client.client import KnowledgeGraphClient

    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            rows = [dict(r) for r in session.run(_LIST_PROMPTS)]
    finally:
        client.close()

    snapshots: list[PromptSnapshot] = []
    for row in rows:
        snapshots.append(
            PromptSnapshot(
                id=str(row.get("id") or ""),
                name=str(row.get("name") or ""),
                version=int(row.get("version") or 0),
                source=str(row.get("source") or ""),
                description=str(row.get("description") or ""),
                few_shot_examples_raw=str(row.get("few_shot_examples") or "[]"),
                max_few_shot=int(row.get("max_few_shot") or 0),
                updated_at=str(row.get("updated_at") or ""),
            )
        )
    return snapshots


def _write_backup(path: Path, prompts: list[PromptSnapshot]) -> None:
    payload = {
        "created_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "prompt_count": len(prompts),
        "prompts": [
            {
                "id": prompt.id,
                "name": prompt.name,
                "version": prompt.version,
                "source": prompt.source,
                "description": prompt.description,
                "max_few_shot": prompt.max_few_shot,
                "few_shot_count": prompt.few_shot_count,
                "few_shot_examples_raw": prompt.few_shot_examples_raw,
                "updated_at": prompt.updated_at,
            }
            for prompt in prompts
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _clear_prompts(prompt_ids: list[str]) -> int:
    from libs.neo4j_client.client import KnowledgeGraphClient

    client = KnowledgeGraphClient()
    cleared = 0
    try:
        with client.session() as session:
            for prompt_id in prompt_ids:
                row = session.run(_CLEAR_PROMPT, id=prompt_id).single()
                if row:
                    cleared += 1
    finally:
        client.close()
    return cleared


def _load_env() -> None:
    load_dotenv(ROOT / "secrets" / ".env.config", override=False)
    load_dotenv(ROOT / "secrets" / ".env.secrets", override=False)
    load_dotenv(ROOT / "secrets" / ".env", override=False)
    try:
        from libs.keyvault.loader import load_keyvault_secrets

        load_keyvault_secrets()
    except ModuleNotFoundError:
        print("Key Vault dependencies missing; using local environment only.")


def _build_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Back up and clear PromptConfig few-shot examples."
    )
    parser.add_argument(
        "--backup-path",
        default="",
        help="Optional explicit backup JSON path.",
    )
    parser.add_argument(
        "--prompt-name",
        action="append",
        default=[],
        help="Optional prompt name filter; can be supplied multiple times.",
    )
    parser.add_argument(
        "--include-empty",
        action="store_true",
        help="Also clear prompts already at zero few-shot examples.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the clear operation. Without this flag, command is dry-run only.",
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

    prompts = _load_prompts()
    name_filters = {n.strip() for n in args.prompt_name if n.strip()}
    if name_filters:
        prompts = [p for p in prompts if p.name in name_filters]

    target_prompts = (
        prompts
        if args.include_empty
        else [p for p in prompts if p.few_shot_count > 0]
    )
    total_examples = sum(p.few_shot_count for p in target_prompts)

    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = (
        Path(args.backup_path)
        if args.backup_path
        else BACKUP_DIR / f"prompt_few_shot_backup_{ts}.json"
    )
    print(
        json.dumps(
            {
                "mode": "apply" if args.apply else "dry-run",
                "backup_path": str(backup_path),
                "prompt_count": len(target_prompts),
                "total_examples": total_examples,
                "prompt_names": sorted({p.name for p in target_prompts}),
            },
            indent=2,
        )
    )

    if not args.apply:
        return

    if args.confirm.strip() != CONFIRM_TOKEN:
        raise SystemExit(
            f"--confirm must equal {CONFIRM_TOKEN} when --apply is used."
        )

    _write_backup(backup_path, target_prompts)
    cleared = _clear_prompts([p.id for p in target_prompts])
    print(
        json.dumps(
            {"backup_written": str(backup_path), "cleared_prompts": cleared}, indent=2
        )
    )


if __name__ == "__main__":
    main()
