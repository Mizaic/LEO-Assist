"""Upsert staging surface forms into terminology server mappings."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.auth.service_auth import get_service_auth_header
from libs.keyvault.loader import load_keyvault_secrets
from libs.terminology.surface_normalize import normalize_surface

load_keyvault_secrets()

BASE = "http://localhost:8001"
MAPPINGS_FILE = (
    ROOT
    / "scripts"
    / "investigations"
    / "output"
    / "staging_surface_form_upserts_compiled.json"
)
PROVENANCE = "staging-tnm-surface-form-backfill-2026-04-08"


def main() -> None:
    rows = json.loads(MAPPINGS_FILE.read_text(encoding="utf-8"))
    session = requests.Session()
    session.headers.update(get_service_auth_header())

    ok = 0
    failed = 0
    for row in rows:
        form = str(row["surface_form"]).strip()
        concept_id = str(row["concept_id"]).strip()
        if not form or not concept_id:
            continue
        payload = {
            "form": form,
            "normalized": normalize_surface(form),
            "concept_id": concept_id,
            "confidence": 1.0,
            "source": "manual",
            "provenance": PROVENANCE,
        }
        try:
            resp = session.post(
                f"{BASE}/terminology/surface-forms/upsert-mapping",
                json=payload,
                timeout=60,
            )
            if resp.status_code in (200, 201):
                ok += 1
            else:
                failed += 1
                print(f"FAIL {form!r} -> {concept_id}: HTTP {resp.status_code}")
        except Exception as exc:
            failed += 1
            print(f"FAIL {form!r} -> {concept_id}: {exc}")

    print(f"upserted_ok={ok}")
    print(f"upserted_failed={failed}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
