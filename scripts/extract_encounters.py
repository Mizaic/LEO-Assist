"""Extract all encounters for a patient from Neo4j and save locally as JSON."""

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv(Path("secrets/.env"))

uri = os.getenv("NEO4J_URI")
user = os.getenv("NEO4J_USER")
pwd = os.getenv("NEO4J_PASSWORD")
patient_ids = [
    "4203796334",
    "7321643565",
    "4802235577",
    "4622879921",
]

print(f"Connecting to {uri} ...")
driver = GraphDatabase.driver(uri, auth=(user, pwd))
driver.verify_connectivity()
print("Connected.")

with driver.session() as session:
    for patient_id in patient_ids:
        result = session.run(
            "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter) "
            "WHERE toString(p.id) = $pid "
            "RETURN e.id AS encounter_id, e.date AS date, e.text AS text "
            "ORDER BY e.date",
            pid=patient_id,
        )
        encounters = [dict(r) for r in result]
        print(f"Fetched {len(encounters)} encounters for patient {patient_id}")

        for enc in encounters:
            if enc.get("date") is not None:
                enc["date"] = str(enc["date"])

        output = {
            "patient_id": patient_id,
            "encounter_count": len(encounters),
            "encounters": encounters,
        }

        out_path = Path(
            f"services/terminology/data/training/raw_encounters_{patient_id}.json"
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        print(f"Written to {out_path}")
        text = encounters[0]["text"] if encounters else ""
        print(f"Sample (first 200 chars): {text[:200]}")

driver.close()
