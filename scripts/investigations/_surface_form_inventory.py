"""Inventory of surface forms: what we have in terminology vs what's missing.

Shows:
1. Surface form gaps logged by the re-audit (phrases that didn't resolve correctly)
2. Surface forms currently in the terminology service
3. How encounters get coded when a surface form is absent
"""
import json
import sqlite3
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

TERMINOLOGY_URL = "http://localhost:8001/terminology"

# -- 1. Surface form gaps from re-audit ---------------------------------
REAUDIT_DB = ROOT / "scripts" / "investigations" / "encounter_audit_reaudit" / "encounter_audit.db"
MAIN_DB = ROOT / "scripts" / "investigations" / "encounter_audit" / "encounter_audit.db"

for label, db_path in [("re-audit", REAUDIT_DB), ("main (30k)", MAIN_DB)]:
    if not db_path.exists():
        continue
    db = sqlite3.connect(str(db_path))
    total = db.execute("SELECT COUNT(*) FROM surface_form_gaps").fetchone()[0]
    try:
        types = db.execute(
            "SELECT gap_type, COUNT(*) n FROM surface_form_gaps GROUP BY gap_type ORDER BY n DESC"
        ).fetchall()
        top = db.execute(
            "SELECT evidence, expected_name, gap_type, COUNT(*) n"
            " FROM surface_form_gaps GROUP BY evidence ORDER BY n DESC LIMIT 25"
        ).fetchall()
    except sqlite3.OperationalError:
        types, top = [], []
    db.close()

    print(f"\n=== Surface form gaps [{label}] total={total} ===")
    for gt, n in types:
        print(f"  {gt}: {n}")
    print("\n  Top 25 phrases not resolving correctly:")
    for ev, name, gtype, n in top:
        print(f"    {n:>3}x  [{gtype:<12}]  '{ev}'  ->  {name}")

# -- 2. How many surface forms exist in terminology ---------------------
print("\n\n=== Terminology service surface forms ===")
try:
    resp = httpx.get(f"{TERMINOLOGY_URL}/surface-forms/stats", timeout=10)
    if resp.status_code == 200:
        stats = resp.json()
        print(json.dumps(stats, indent=2))
    else:
        print(f"  /surface-forms/stats returned {resp.status_code}")
        # Try a count via search
        resp2 = httpx.get(f"{TERMINOLOGY_URL}/surface-forms?limit=1", timeout=10)
        print(f"  /surface-forms status: {resp2.status_code}")
except Exception as exc:
    print(f"  Could not reach terminology API: {exc}")

# -- 3. Surface form gaps feed file ------------------------------------
gaps_file = ROOT / "scripts" / "investigations" / "encounter_audit" / "surface_form_gaps.json"
if gaps_file.exists():
    gaps = json.loads(gaps_file.read_text(encoding="utf-8"))
    print(f"\n=== surface_form_gaps.json (feed file) ===")
    print(f"  Entries: {len(gaps)}")
    print("  Sample (first 5):")
    for g in gaps[:5]:
        print(f"    {g}")
