"""Test gallbladder terms specifically."""
import re, httpx

API = "http://localhost:8001"
TOKEN_RE = re.compile(r"[a-z0-9]+")

def norm(t): return " ".join(TOKEN_RE.findall(t.lower()))

terms = [
    "upper abdominal mass consistent with enlarged gall bladder",
    "palpable gallbladder",
    "enlarged gallbladder",
    "gallbladder enlarged",
    "upper abdominal mass gallbladder",
]

print("Normalized forms sent to API:")
for t in terms:
    print(f"  {norm(t)!r}")

print()
resp = httpx.post(
    f"{API}/terminology/resolve",
    json={"terms": terms, "k": 3},
    timeout=15.0,
)
data = resp.json()
GB = {"271683004", "300344005"}
for term, results in data.get("results", {}).items():
    top = results[0] if results else {}
    cid = top.get("snomed_concept_id", "?")
    flag = "OK " if cid in GB else "---"
    print(f"[{flag}] {term!r}")
    for r in results[:3]:
        m = " <-- PINNED" if r.get("snomed_concept_id") in GB else ""
        print(f"       {r.get('snomed_concept_id')} | {(r.get('snomed_term') or '?')[:55]} "
              f"score={r.get('score',0):.3f}{m}")
