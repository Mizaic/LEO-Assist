"""Re-upload the ncda_2018_benchmarks.json to the analytics API.

The /benchmarks/upload endpoint expects:
  POST application/json { rawJson: <dict>, name?: str, auditId?: str }
"""
import urllib.request
import json
import sys
import os

json_path = os.path.join(os.path.dirname(__file__), "..", "external_content", "ncda_2018_benchmarks.json")

with open(json_path, "r", encoding="utf-8") as f:
    raw = json.load(f)

payload = json.dumps({"rawJson": raw}).encode("utf-8")

req = urllib.request.Request(
    "http://localhost:8002/benchmarks/upload",
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST",
)
try:
    resp = urllib.request.urlopen(req)
    print("Status:", resp.status)
    print(resp.read().decode()[:800])
except urllib.error.HTTPError as e:
    print("HTTP Error:", e.code)
    print(e.read().decode()[:1000])
    sys.exit(1)
