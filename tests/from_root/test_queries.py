import asyncio
from neo4j import AsyncGraphDatabase
import os
from services.terminology_api.app.queries.terminology import BATCH_FULLTEXT_QUERY, FULLTEXT_QUERY

async def main():
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "password")
    
    driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
    async with driver.session() as session:
        try:
            print("Testing BATCH_FULLTEXT_QUERY")
            await session.run(BATCH_FULLTEXT_QUERY, ft_query="blood", k=10)
            print("BATCH_FULLTEXT_QUERY OK")
        except Exception as e:
            print(f"BATCH_FULLTEXT_QUERY ERROR: {e}")
            
        try:
            print("Testing FULLTEXT_QUERY")
            await session.run(FULLTEXT_QUERY, ft_query="blood", k=10)
            print("FULLTEXT_QUERY OK")
        except Exception as e:
            print(f"FULLTEXT_QUERY ERROR: {e}")
            
    await driver.close()

asyncio.run(main())
