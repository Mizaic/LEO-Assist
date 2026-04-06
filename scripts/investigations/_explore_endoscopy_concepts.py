"""Explore GI endoscopy SNOMED hierarchy to find the best procedure codes
for direct-access upper and lower GI endoscopy actions in NG12.

Uses:
  GET /concepts/{id}/descendants   -- IS_A hierarchy traversal
  GET /search?q=...                -- fulltext search for comparison
"""
from __future__ import annotations

import requests

BASE = "http://localhost:8001/terminology"


def descendants(concept_id: str, depth: int = 4, tag: str | None = None) -> list[dict]:
    params: dict = {"depth": depth, "limit": 200}
    if tag:
        params["semantic_tag"] = tag
    r = requests.get(f"{BASE}/concepts/{concept_id}/descendants", params=params, timeout=60)
    r.raise_for_status()
    return r.json()


def search(q: str, tag: str | None = None, limit: int = 20) -> list[dict]:
    params: dict = {"q": q, "limit": limit}
    if tag:
        params["semantic_tag"] = tag
    r = requests.get(f"{BASE}/search", params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def resolve(term: str) -> list[dict]:
    r = requests.post(f"{BASE}/resolve",
                      json={"terms": [term], "top_k": 8}, timeout=30)
    r.raise_for_status()
    data = r.json()
    return data.get("results", {}).get(term, [])


def _print(items: list[dict], label: str) -> None:
    print(f"\n{label} ({len(items)} results):")
    for item in items:
        cid = item.get("snomed_concept_id") or item.get("id") or ""
        term = item.get("term") or item.get("snomed_term") or item.get("fsn") or ""
        score = item.get("score")
        suffix = f" | score={score:.3f}" if score is not None else ""
        print(f"  {cid} | {term[:70]}{suffix}")


# ------------------------------------------------------------------ #
# 1. Search to find the right parent concept for GI endoscopy         #
# ------------------------------------------------------------------ #
print("=" * 70)
print("SEARCH: gastrointestinal endoscopy (finding the right parent)")
print("=" * 70)
gi_parents = search("gastrointestinal tract endoscopy", tag="procedure")
_print(gi_parents, "GI endoscopy procedure parents")

# Try to traverse from any found parent
if gi_parents:
    parent_id = gi_parents[0].get("snomed_concept_id") or gi_parents[0].get("id", "")
    if parent_id:
        print(f"\nDescendants of {parent_id}:")
        try:
            desc = descendants(parent_id, depth=4, tag="procedure")
            upper = [d for d in desc if any(w in (d.get("term") or "").lower()
                                            for w in ["upper", "oesophag", "esophag",
                                                      "gastro", "gastric", "duoden", "stomach"])]
            lower = [d for d in desc if any(w in (d.get("term") or "").lower()
                                             for w in ["lower", "colon", "colono", "sigmoid",
                                                       "rectal", "rectum", "bowel"])]
            _print(upper, "Upper GI candidates")
            _print(lower, "Lower GI candidates")
        except Exception as e:
            print(f"  Could not traverse: {e}")

# ------------------------------------------------------------------ #
# 2. Fulltext search for specific procedure concepts                   #
# ------------------------------------------------------------------ #
print("\n" + "=" * 70)
print("SEARCH: upper gastrointestinal endoscopy")
print("=" * 70)
_print(search("upper gastrointestinal endoscopy", tag="procedure"), "Search results")

print("\n" + "=" * 70)
print("SEARCH: oesophagogastroduodenoscopy")
print("=" * 70)
_print(search("oesophagogastroduodenoscopy"), "Search results")

print("\n" + "=" * 70)
print("SEARCH: gastroscopy")
print("=" * 70)
_print(search("gastroscopy", tag="procedure"), "Search results")

print("\n" + "=" * 70)
print("SEARCH: colonoscopy")
print("=" * 70)
_print(search("colonoscopy", tag="procedure"), "Search results")

print("\n" + "=" * 70)
print("SEARCH: flexible sigmoidoscopy")
print("=" * 70)
_print(search("flexible sigmoidoscopy", tag="procedure"), "Search results")

# ------------------------------------------------------------------ #
# 3. Resolve via the live resolver to see what candidates come back   #
# ------------------------------------------------------------------ #
print("\n" + "=" * 70)
print("RESOLVER: direct access upper gastrointestinal endoscopy")
print("=" * 70)
_print(resolve("direct access upper gastrointestinal endoscopy"), "Resolver candidates")

print("\n" + "=" * 70)
print("RESOLVER: direct access colonoscopy")
print("=" * 70)
_print(resolve("direct access colonoscopy"), "Resolver candidates")

print("\n" + "=" * 70)
print("RESOLVER: CT colonography")
print("=" * 70)
_print(resolve("CT colonography"), "Resolver candidates")
