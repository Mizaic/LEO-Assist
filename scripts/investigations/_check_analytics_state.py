"""Check current state of analytics pipeline artefacts in Neo4j."""

from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()
from libs.neo4j_client.client import PatientGraphClient

LABELS = [
    "AuditRun",
    "DriftMetric",
    "SafetyNetAlert",
    "EpisodeOfCare",
]

REL_CHECKS = [
    ("HAS_EPISODE_OF_CARE", "Patient -> EpisodeOfCare"),
    ("IS_PART_OF", "Encounter -> EpisodeOfCare"),
    ("HAS_SAFETY_NET_ALERT", "Patient -> SafetyNetAlert"),
]


def main() -> None:
    c = PatientGraphClient()
    try:
        with c.session() as s:
            print("=== Node counts ===")
            for label in LABELS:
                result = s.run(f"MATCH (n:{label}) RETURN count(n) AS cnt").single()
                cnt = result["cnt"] if result else 0
                if cnt > 0:
                    keys = s.run(
                        f"MATCH (n:{label}) RETURN keys(n) AS k LIMIT 1"
                    ).data()
                    k = keys[0]["k"] if keys else []
                    print(f"  {label:<30} {cnt:6d}  keys: {sorted(k)}")
                else:
                    print(f"  {label:<30} {cnt:6d}")

            print()
            print("=== Relationship counts ===")
            for rel, desc in REL_CHECKS:
                result = s.run(
                    f"MATCH ()-[r:{rel}]->() RETURN count(r) AS cnt"
                ).single()
                cnt = result["cnt"] if result else 0
                print(f"  {rel:<30} {cnt:6d}  ({desc})")

            print()
            print("=== AuditRun details (last 5) ===")
            runs = s.run(
                "MATCH (a:AuditRun) RETURN a.run_id AS run_id, a.status AS status, "
                "a.created_at AS created_at, a.patient_count AS patient_count "
                "ORDER BY a.created_at DESC LIMIT 5"
            ).data()
            for r in runs:
                print(
                    f"  {r.get('run_id','?'):40} status={r.get('status','?'):12} "
                    f"patients={r.get('patient_count','?')} created={r.get('created_at','?')}"
                )

            print()
            print("=== SafetyNetAlert types ===")
            alerts = s.run(
                "MATCH (a:SafetyNetAlert) RETURN a.alert_type AS t, count(*) AS n ORDER BY n DESC LIMIT 10"
            ).data()
            for r in alerts:
                print(f"  {r.get('t','?'):<40} {r.get('n',0)}")

    finally:
        c.close()


if __name__ == "__main__":
    main()
