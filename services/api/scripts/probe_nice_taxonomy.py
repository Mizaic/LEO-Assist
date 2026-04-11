"""Diagnostic probe: walk the NICE taxonomy API step by step and print raw responses.

Run from the services/api directory:
    python scripts/probe_nice_taxonomy.py

Loads AZURE_KEYVAULT_URL from secrets/.env.config and pulls NICE_API_KEY from
Key Vault automatically (same bootstrap as the service).

Prints the raw JSON at every level so we can see the exact field names the
live API uses and fix the parser accordingly.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

# ── Bootstrap secrets ─────────────────────────────────────────────────────────
# scripts/probe_nice_taxonomy.py is at services/api/scripts/ -- 3 levels from repo root
_REPO_ROOT = Path(__file__).resolve().parents[3]
# libs/ lives at repo root; app/ lives under services/api
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "services" / "api"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_REPO_ROOT / "secrets" / ".env.config", override=False)

if os.environ.get("AZURE_KEYVAULT_URL"):
    try:
        from libs.keyvault.loader import load_keyvault_secrets

        load_keyvault_secrets()
        print("[bootstrap] Loaded secrets from Key Vault")
    except Exception as exc:
        print(f"[bootstrap] Key Vault load failed: {exc}")
else:
    print("[bootstrap] AZURE_KEYVAULT_URL not set -- using .env only")

api_key = os.environ.get("NICE_API_KEY", "")
if not api_key:
    print(
        "[ERROR] NICE_API_KEY not set. Run 'az login' and ensure AZURE_KEYVAULT_URL is configured."
    )
    sys.exit(1)

print(f"[bootstrap] NICE_API_KEY present (length={len(api_key)})\n")

# ── Probe ─────────────────────────────────────────────────────────────────────
import httpx  # noqa: E402

_NICE_ROOT = "https://api.nice.org.uk/services/guidance"
_HEADERS = {
    "API-Key": api_key,
    "Accept": "application/json",
}
_MAX_RETRIES = 3


def _pp(label: str, data: dict | list) -> None:
    """Pretty-print a JSON object with a label."""
    print(f"\n{'='*70}")
    print(f"  {label}")
    print("=" * 70)
    text = json.dumps(data, indent=2, default=str)
    # Truncate huge responses
    lines = text.splitlines()
    if len(lines) > 80:
        print("\n".join(lines[:80]))
        print(f"  ... ({len(lines) - 80} more lines truncated) ...")
    else:
        print(text)


async def get(client: httpx.AsyncClient, url: str) -> dict:
    """GET with retries, return parsed JSON."""
    url = url if url.endswith(".json") else f"{url}.json"
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            r = await client.get(url, headers=_HEADERS, timeout=30)
            r.raise_for_status()
            return r.json()
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            if attempt == _MAX_RETRIES:
                raise RuntimeError(
                    f"Failed after {_MAX_RETRIES} attempts: {exc}"
                ) from exc
            await asyncio.sleep(1)
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(f"HTTP {exc.response.status_code} for {url}") from exc


def _pick(*candidates: str | None) -> str:
    """Return first non-empty candidate."""
    return next((c for c in candidates if c), "")


async def probe() -> None:
    async with httpx.AsyncClient() as client:

        # ── Step 1: API root ─────────────────────────────────────────────────
        root_url = f"{_NICE_ROOT}.json"
        print(f"\n[STEP 1] Fetching API root: {root_url}")
        root = await get(client, root_url)
        _pp("STEP 1 — API root (Resources / links)", root)

        # Find taxonomy link
        taxonomy_uri = None
        for res in root.get("Resources", []):
            rel = res.get("Rel", "").lower()
            if "taxonomy" in rel:
                taxonomy_uri = res.get("Uri") or res.get("Href")
                rel_val = res.get("Rel")
                print(
                    f"\n[STEP 1] Found taxonomy link: rel={rel_val!r}  uri={taxonomy_uri}"
                )
                break

        if not taxonomy_uri:
            print(
                "\n[ERROR] No taxonomy link found in Resources. Available Rel values:"
            )
            for res in root.get("Resources", []):
                print(f"  Rel={res.get('Rel')}  Uri={res.get('Uri')}")
            return

        # ── Step 2: taxonomy root ────────────────────────────────────────────
        print(f"\n[STEP 2] Fetching taxonomy root: {taxonomy_uri}")
        tax_doc = await get(client, taxonomy_uri)
        _pp(
            "STEP 2 — Taxonomy root document (top-level keys + first category)",
            {
                "top_level_keys": list(tax_doc.keys()),
                "first_category_raw": (
                    tax_doc.get("categories")
                    or tax_doc.get("Categories")
                    or tax_doc.get("TaxonomyCategories")
                    or []
                )[
                    :1
                ],  # just the first one
            },
        )

        # Find categories
        categories = (
            tax_doc.get("categories")
            or tax_doc.get("TaxonomyCategories")
            or tax_doc.get("Categories")
            or tax_doc.get("Items")
            or []
        )
        print(
            f"\n[STEP 2] Found {len(categories)} categories. First category keys: {list(categories[0].keys()) if categories else 'NONE'}"
        )

        if not categories:
            print("[ERROR] No categories found -- stopping.")
            return

        # ── Step 3: first category ───────────────────────────────────────────
        first_cat = categories[0]
        cat_title = _pick(first_cat.get("title"), first_cat.get("Title"))
        cat_uri = _pick(
            first_cat.get("uri"), first_cat.get("Uri"), first_cat.get("Href")
        )
        print(f"\n[STEP 3] First category: title={cat_title!r}  uri={cat_uri!r}")
        _pp(f"STEP 3 — First category raw object ({cat_title!r})", first_cat)

        # Check for inline subcategories vs link
        inline_subs = (
            first_cat.get("subcategories")
            or first_cat.get("TaxonomySubcategories")
            or first_cat.get("Subcategories")
            or []
        )
        if inline_subs:
            print(
                f"[STEP 3] Category has {len(inline_subs)} INLINE subcategories. First sub keys: {list(inline_subs[0].keys())}"
            )
            subs = inline_subs
        elif cat_uri:
            print(f"[STEP 3] No inline subcategories -- following link: {cat_uri}")
            cat_doc = await get(client, cat_uri)
            _pp(
                f"STEP 3 — Category document for '{cat_title}'",
                {
                    "top_level_keys": list(cat_doc.keys()),
                    "first_3_items": (
                        cat_doc.get("subcategories")
                        or cat_doc.get("Subcategories")
                        or cat_doc.get("Items")
                        or []
                    )[:3],
                },
            )
            subs = (
                cat_doc.get("subcategories")
                or cat_doc.get("TaxonomySubcategories")
                or cat_doc.get("Subcategories")
                or cat_doc.get("Items")
                or []
            )
            print(
                f"[STEP 3] Got {len(subs)} subcategories from category link. First sub keys: {list(subs[0].keys()) if subs else 'NONE'}"
            )
        else:
            print(
                "[ERROR] No inline subcategories and no URI on category -- cannot proceed."
            )
            return

        if not subs:
            print("[ERROR] No subcategories found -- stopping.")
            return

        # ── Step 4: first subcategory ────────────────────────────────────────
        first_sub = subs[0]
        sub_title = _pick(first_sub.get("title"), first_sub.get("Title"))
        sub_uri = _pick(
            first_sub.get("uri"), first_sub.get("Uri"), first_sub.get("Href")
        )
        print(f"\n[STEP 4] First subcategory: title={sub_title!r}  uri={sub_uri!r}")
        _pp(f"STEP 4 — First subcategory raw object ({sub_title!r})", first_sub)

        if sub_uri:
            print(f"\n[STEP 4] Fetching subcategory guidelines: {sub_uri}")
            sub_doc = await get(client, sub_uri)
            _pp(
                f"STEP 4 — Subcategory document for '{sub_title}'",
                {
                    "top_level_keys": list(sub_doc.keys()),
                    "first_5_guidelines": (
                        sub_doc.get("guidance")
                        or sub_doc.get("Guidance")
                        or sub_doc.get("items")
                        or sub_doc.get("Items")
                        or sub_doc.get("IndexItems")
                        or []
                    )[:5],
                },
            )
        else:
            print(
                f"[STEP 4] No URI on subcategory '{sub_title}' -- checking for inline guidelines:"
            )
            _pp("STEP 4 — Full subcategory object", first_sub)

        # ── Summary ──────────────────────────────────────────────────────────
        print(f"\n{'='*70}")
        print("  SUMMARY")
        print(f"  Total categories in taxonomy root: {len(categories)}")
        print(
            f"  Subcategory sample from first category: {[_pick(s.get('title'), s.get('Title')) for s in subs[:5]]}"
        )
        print(f"{'='*70}\n")


if __name__ == "__main__":
    asyncio.run(probe())
