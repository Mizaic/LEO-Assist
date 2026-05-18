"""Upsert terminology SurfaceForm aliases for NCDA ethnicity SNOMED concepts.

Reads ``configs/snomed/snomed_ncda_ethnicity_mapping.json`` and POSTs each
benchmark label plus guideline synonyms to ``POST /terminology/surface-forms/upsert-mapping``.

Mappings share overlapping synonyms (for example census wording); each alias maps to the
concept listed under its parent NCDA category key only.

Run:
    python scripts/ncda/upsert_ncda_ethnicity_surface_forms.py
    python scripts/ncda/upsert_ncda_ethnicity_surface_forms.py --dry-run

Requires API reachable (default ``http://localhost:8001``) and admin-auth headers.
Concept ids must exist in the terminology coding graph before upsert succeeds (404 otherwise).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.auth.service_auth import get_service_auth_header  # noqa: E402
from libs.keyvault.loader import load_keyvault_secrets  # noqa: E402

load_keyvault_secrets()

MAPPING_PATH = ROOT / "configs" / "snomed" / "snomed_ncda_ethnicity_mapping.json"
BASE = os.getenv("LEO_API_BASE_URL", os.getenv("API_BASE_URL", "http://localhost:8001"))
PROVENANCE = "ncda_ethnicity_mapping_v2026_04"


def _normalize(form: str) -> str:
    return " ".join(form.strip().lower().split())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    mapping = json.loads(MAPPING_PATH.read_text(encoding="utf-8"))
    session = requests.Session()
    session.headers.update(get_service_auth_header())

    ok = 0
    failed: list[tuple[str, str]] = []

    for ncda_label, payload in (mapping.get("mappings") or {}).items():
        cid = str(payload.get("concept_id") or "").strip()
        if not cid:
            continue
        forms = {_normalize(ncda_label): ncda_label}
        for syn in payload.get("guideline_synonyms") or []:
            if syn:
                forms[_normalize(str(syn))] = str(syn).strip()

        for norm, surface in forms.items():
            if not norm:
                continue
            body = {
                "normalized": norm,
                "form": surface,
                "concept_id": cid,
                "confidence": 1.0,
                "source": "ncda_ethnicity_config",
                "provenance": PROVENANCE,
                "created_by": "ncda_ethnicity_surface_script",
            }
            if args.dry_run:
                print(f"[dry-run] {surface!r} -> {cid}")
                ok += 1
                continue
            r = session.post(
                f"{BASE}/terminology/surface-forms/upsert-mapping",
                json=body,
                timeout=60,
            )
            if r.status_code not in (200, 201):
                failed.append((surface, f"HTTP {r.status_code}: {r.text[:200]}"))
            else:
                ok += 1

    print(f"Upserts attempted OK={ok}, failed={len(failed)}")
    for surf, err in failed[:30]:
        print(f"  FAIL {surf!r}: {err}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
