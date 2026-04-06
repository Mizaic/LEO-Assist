"""List all terminology server endpoints related to surface forms."""
import requests, json

r = requests.get("http://localhost:8001/openapi.json", timeout=10)
spec = r.json()
keywords = ("surface", "form", "map", "resolve", "concept")
for path in spec.get("paths", {}):
    if any(k in path.lower() for k in keywords):
        methods = list(spec["paths"][path].keys())
        print(f"{', '.join(m.upper() for m in methods):<20} {path}")
