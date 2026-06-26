import json
import redis
import hashlib

def generate_key(term: str, expected_tag: str | None, enrich_lab_domain: bool) -> str:
    text_hash = hashlib.md5(term.strip().lower().encode("utf-8")).hexdigest()
    tag_str = (expected_tag or "").strip().lower()
    return f"term_resolve:v1:{text_hash}:{tag_str}:{enrich_lab_domain}"

r = redis.from_url("redis://localhost:6379", decode_responses=True)
k = generate_key("Ferritin", None, True)
val = r.get(k)
if val:
    data = json.loads(val)
    print("Found! Num candidates:", len(data))
    if data:
        print("First candidate:", data[0])
else:
    print("Not found")

