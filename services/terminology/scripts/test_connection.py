"""Quick connectivity test for the coding graph Neo4j instance."""

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from neo4j import AsyncGraphDatabase


async def main():
    load_dotenv(Path("secrets") / ".env")
    uri = os.environ["CODING_GRAPH_NEO4J_URI"]
    user = os.environ["CODING_GRAPH_NEO4J_USERNAME"]
    pw = os.environ["CODING_GRAPH_NEO4J_PASSWORD"]

    driver = AsyncGraphDatabase.driver(uri, auth=(user, pw))
    try:
        info = await driver.get_server_info()
        print(f"Connected: {info.agent} @ {info.address}")
        async with driver.session() as session:
            result = await session.run("RETURN 1 AS n")
            rec = await result.single()
            print(f"Query OK: n={rec['n']}")

            result = await session.run(
                "MATCH (n) RETURN labels(n) AS lbl, count(*) AS cnt "
                "ORDER BY cnt DESC LIMIT 10"
            )
            records = await result.data()
            if records:
                print("Existing node counts:")
                for r in records:
                    print(f"  {r['lbl']}: {r['cnt']}")
            else:
                print("Database is empty — ready for loading")
    finally:
        await driver.close()


if __name__ == "__main__":
    asyncio.run(main())
