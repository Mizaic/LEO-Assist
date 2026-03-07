"""Test the exact comorbidities query path end-to-end."""
import sys, json
sys.path.insert(0, ".")
from libs.neo4j_client.client import KnowledgeGraphClient, PatientGraphClient
from libs.domain_config.registry import DomainRegistry

kg = KnowledgeGraphClient()

# Step 1: Does _ensure_registry work?
print("=== Step 1: Load registry from KG ===")
rows = kg.run(
    "MATCH (v:ValueSet) WHERE v.id STARTS WITH 'ncda-' "
    "RETURN v.id AS id, v.rawJson AS raw_json"
)
print(f"  ValueSet rows found: {len(rows)}")
valuesets = {}
for r in (rows or []):
    raw = r.get("raw_json")
    if not raw:
        print(f"  WARN: {r['id']} has no rawJson")
        continue
    try:
        vs_dict = json.loads(raw) if isinstance(raw, str) else raw
        valuesets[r["id"]] = vs_dict
        print(f"  Loaded: {r['id']}")
    except Exception as e:
        print(f"  ERROR parsing {r['id']}: {e}")

registry = DomainRegistry.from_fhir(valuesets)

# Step 2: What concepts does the registry have for comorbidities?
print("\n=== Step 2: Registry concepts for comorbidities ===")
concepts = registry.get_domain_concepts("comorbidities")
print(f"  Count: {len(concepts)}")
for c in concepts:
    print(f"  concept_id={c.concept_id}  term={c.term!r}  benchmark_key={c.benchmark_key!r}")

# Step 3: concept_id_groups
print("\n=== Step 3: concept_id_groups ===")
groups = registry.get_concept_id_groups("comorbidities", kg, depth=2)
print(f"  Groups: {len(groups)}")
all_ids = []
for term, ids in groups.items():
    id_strs = [str(i) for i in ids]
    all_ids.extend(id_strs)
    print(f"  {term!r}: top={ids[0] if ids else None}  total_ids={len(ids)}")
all_ids = list(dict.fromkeys(all_ids))  # dedupe preserving order
print(f"\n  all_ids count: {len(all_ids)}")
print(f"  sample: {all_ids[:5]}")

kg.close()

# Step 4: Run the actual patient query for org C82070
print("\n=== Step 4: Patient graph match ===")
pg = PatientGraphClient()
base = (
    "MATCH (_scope:Organization {id: $org}) "
    "MATCH (p:Patient)-[:HAS_GENERAL_PRACTITIONER]->(gp) "
    "WHERE (gp.id = $org) OR (gp)-[:COMMISSIONED_BY]->(_scope) "
    "   OR (gp)-[:COMMISSIONED_BY]->(:ICB)-[:PART_OF_ALLIANCE]->(_scope) "
    "MATCH (p)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
)
params = {"org": "C82070"}

# Count total patients
total_rows = pg.run(f"{base}RETURN count(DISTINCT p) AS n", **params)
total = total_rows[0]["n"] if total_rows else 0
print(f"  Total patients in scope: {total}")

# Run the disease query
disease_rows = pg.run(
    f"{base}"
    "WITH p, ep "
    "OPTIONAL MATCH (p)-[r1:HAS_DISEASE]->(d1) "
    "  WHERE d1.conceptId IN $concept_ids AND r1.domain = 'comorbidities' "
    "    AND (r1.encounter_date IS NULL OR r1.encounter_date <= ep.referral_date) "
    "OPTIONAL MATCH (p)-[:HAS_ENCOUNTER]->(enc)-[r2:DOCUMENTS]->(d2) "
    "  WHERE d2.conceptId IN $concept_ids AND r2.domain = 'comorbidities' "
    "    AND (enc.date IS NULL OR enc.date <= ep.referral_date) "
    "WITH p, collect(DISTINCT d1.conceptId) + collect(DISTINCT d2.conceptId) AS cids "
    "UNWIND cids AS concept_id "
    "WITH p, concept_id WHERE concept_id IS NOT NULL "
    "RETURN concept_id, count(DISTINCT p) AS n",
    **{**params, "concept_ids": all_ids},
)
print(f"  Disease rows returned: {len(disease_rows)}")
for r in disease_rows:
    print(f"    concept_id={r['concept_id']!r}  patients={r['n']}")

pg.close()
