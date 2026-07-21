import asyncio
from neo4j import AsyncGraphDatabase
import os
from services.terminology_api.app.queries.terminology import BATCH_FULLTEXT_QUERY, FULLTEXT_QUERY

async def main():
    uri = os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI", "bolt://localhost:7688")
    user = os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "neo4j")
    password = os.getenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "knowledge-dev")
    
    driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
    async with driver.session() as session:
        result = await session.run(BATCH_FULLTEXT_QUERY, ft_query="Ferritin", k=50)
        records = await result.data()
        for r in records:
            print(r["concept_id"], r["fsn"], r["semantic_tag"], r["score"])
            
    await driver.close()

asyncio.run(main())
