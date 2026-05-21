import asyncio
from neo4j import AsyncGraphDatabase
import os

async def main():
    uri = os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI", "bolt://127.0.0.1:7688")
    user = os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "neo4j")
    password = os.getenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "knowledge-dev")
    
    driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
    async with driver.session() as session:
        result = await session.run(
            "MATCH (c:Concept) WHERE c.fsn CONTAINS 'Ferritin' AND c.active = true RETURN c.id, c.fsn, c.semantic_tag LIMIT 10"
        )
        records = await result.data()
        for r in records:
            print(r)
            
    await driver.close()

asyncio.run(main())
