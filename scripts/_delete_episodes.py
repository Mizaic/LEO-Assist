"""Delete all EpisodeOfCare nodes and IS_PART_OF edges for a clean rebuild."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env.config", override=True)
load_dotenv(ROOT / "secrets" / ".env.secrets", override=True)

from libs.neo4j_client.client import PatientGraphClient  # noqa: E402


def main() -> None:
    c = PatientGraphClient()
    try:
        rows = c.run(
            "MATCH ()-[r:IS_PART_OF]->(:EpisodeOfCare) "
            "WITH r LIMIT 200000 DELETE r RETURN count(*) AS n"
        )
        print(f"Deleted IS_PART_OF edges: {rows[0]['n']}")
        rows = c.run(
            "MATCH (ep:EpisodeOfCare) "
            "WITH ep LIMIT 200000 DETACH DELETE ep RETURN count(*) AS n"
        )
        print(f"Deleted EpisodeOfCare nodes: {rows[0]['n']}")
    finally:
        c.close()


if __name__ == "__main__":
    main()
