#!/usr/bin/env python3
"""
UMLS CUI to SNOMED/ICD-10 code lookup via UMLS REST API.

Uses UMLS_API_KEY from secrets/.env. Maps a UMLS CUI to preferred terms
and codes in SNOMED CT and ICD-10.

API docs: https://documentation.uts.nlm.nih.gov/rest/atoms/
"""

from __future__ import annotations

import argparse
import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path

UMLS_BASE = "https://uts-ws.nlm.nih.gov/rest"
UMLS_ATOMS_BASE = f"{UMLS_BASE}/content/current/CUI"
UMLS_SEARCH_BASE = f"{UMLS_BASE}/search/current"
SNOMED_SABS = ("SNOMEDCT_US", "SNOMEDCT_UK")
ICD10_SABS = ("ICD10", "ICD10CM", "ICD10PCS")


def load_api_key() -> str:
    """Load UMLS_API_KEY from secrets/.env or environment."""
    key = os.environ.get("UMLS_API_KEY")
    if key:
        return key
    env_path = Path(__file__).resolve().parent.parent / "secrets" / ".env"
    if env_path.exists():
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("UMLS_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise ValueError(
        "UMLS_API_KEY not found. Set it in secrets/.env or as environment variable."
    )


def extract_code_from_url(url: str) -> str:
    """Extract source code from UMLS API code URL."""
    if not url or url == "NONE":
        return ""
    parts = url.rstrip("/").split("/")
    return parts[-1] if parts else ""


def fetch_atoms(cui: str, api_key: str) -> list[dict]:
    """Fetch atoms for CUI from UMLS API, filtered to SNOMED and ICD-10."""
    sabs = ",".join(SNOMED_SABS + ICD10_SABS)
    params = urllib.parse.urlencode({"apiKey": api_key, "sabs": sabs})
    url = f"{UMLS_ATOMS_BASE}/{cui}/atoms?{params}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    return data.get("result", [])


def lookup(cui: str, api_key: str | None = None) -> dict:
    """
    Look up SNOMED and ICD-10 codes for a UMLS CUI.

    Returns dict with:
      - cui: the CUI
      - snomed: list of {code, term, tty, sab}
      - icd10: list of {code, term, tty, sab}
    """
    key = api_key or load_api_key()
    atoms = fetch_atoms(cui, key)

    snomed: list[dict] = []
    icd10: list[dict] = []

    for a in atoms:
        root = a.get("rootSource", "")
        code_url = a.get("code", "")
        code = extract_code_from_url(code_url)
        name = a.get("name", "")
        tty = a.get("termType", "")

        entry = {"code": code, "term": name, "tty": tty, "sab": root}
        if root in SNOMED_SABS:
            snomed.append(entry)
        elif root in ICD10_SABS:
            icd10.append(entry)

    return {"cui": cui, "snomed": snomed, "icd10": icd10}


def search_umls(term: str, api_key: str | None = None, max_results: int = 10) -> list[dict]:
    """
    Search UMLS by term string. Returns list of {cui, name, semantic_types}.
    Uses: https://documentation.uts.nlm.nih.gov/rest/search/
    """
    key = api_key or load_api_key()
    params = urllib.parse.urlencode({
        "apiKey": key,
        "string": term,
        "searchType": "words",
        "pageSize": max_results,
    })
    url = f"{UMLS_SEARCH_BASE}?{params}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    results = data.get("result", {}).get("results", [])
    return [
        {"cui": r["ui"], "name": r["name"]}
        for r in results
        if r.get("ui", "NONE") != "NONE"
    ]


def search_and_lookup(
    term: str,
    api_key: str | None = None,
    max_results: int = 5,
) -> list[dict]:
    """
    Search UMLS by term, then look up SNOMED/ICD-10 for each CUI found.
    Returns list of {cui, name, snomed, icd10}.
    """
    key = api_key or load_api_key()
    hits = search_umls(term, key, max_results)
    results = []
    for hit in hits:
        codes = lookup(hit["cui"], key)
        codes["name"] = hit["name"]
        results.append(codes)
    return results


def print_result(result: dict, as_json: bool = False) -> None:
    """Print a single CUI result (from lookup or search_and_lookup)."""
    if as_json:
        print(json.dumps(result, indent=2))
        return
    name = result.get("name", "")
    header = f"CUI: {result['cui']}"
    if name:
        header += f"  |  {name}"
    print(header)
    print()
    if result["snomed"]:
        print("SNOMED CT:")
        for s in result["snomed"]:
            pt = " [PT]" if s["tty"] == "PT" else ""
            print(f"  {s['code']:15} {s['term'][:55]}{pt} ({s['sab']})")
    else:
        print("SNOMED CT: (none)")
    print()
    if result["icd10"]:
        print("ICD-10:")
        for s in result["icd10"]:
            pt = " [PT]" if s["tty"] == "PT" else ""
            print(f"  {s['code']:15} {s['term'][:55]}{pt} ({s['sab']})")
    else:
        print("ICD-10: (none)")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Look up SNOMED and ICD-10 codes via UMLS API.",
    )
    parser.add_argument(
        "input",
        help="UMLS CUI (e.g. C0011849) or search term (e.g. 'diabetes mellitus')",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=5,
        help="Max search results when searching by term (default: 5)",
    )
    args = parser.parse_args()

    is_cui = bool(re.match(r"^C\d{7}$", args.input.upper()))

    try:
        if is_cui:
            result = lookup(args.input.upper())
            result["name"] = ""
            print_result(result, args.json)
        else:
            results = search_and_lookup(
                args.input, max_results=args.max_results,
            )
            if not results:
                print(f"No UMLS concepts found for '{args.input}'")
                return
            for r in results:
                print_result(r, args.json)
                if not args.json:
                    print("-" * 70)
    except ValueError as e:
        print(f"ERROR: {e}")
    except urllib.error.HTTPError as e:
        print(f"API ERROR: {e.code} {e.reason}")
        if e.code == 401:
            print("Check that UMLS_API_KEY in secrets/.env is valid.")


if __name__ == "__main__":
    main()
