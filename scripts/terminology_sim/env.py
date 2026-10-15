"""Load the local developer env files the dry-run tools use (values never printed)."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parents[2]
_ENV_FILES = ("secrets/.env", "secrets/.env.secrets", ".env")


def load_local_env() -> None:
    for name in _ENV_FILES:
        load_dotenv(_ROOT / name, override=False)
