import asyncio
from neo4j import AsyncGraphDatabase
import os
from services.terminology_api.app.queries.terminology import TERMINOLOGY_SEARCH

async def main():
    uri = os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI", "bolt://localhost:7688")
    user = os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "neo4j")
    password = os.getenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "knowledge-dev")
    
    driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
    async with driver.session() as session:
        result = await session.run(
            "CALL db.index.fulltext.queryNodes('term_fulltext', 'Ferritin') YIELD node, score "
            "MATCH (node)-[:DESCRIBES]->(c:Concept) WHERE c.active = true RETURN c.id, c.fsn, c.semantic_tag, score LIMIT 10"
        )
        records = await result.data()
        for r in records:
            print(r["c.id"], r["c.fsn"], r["c.semantic_tag"], r["score"])
            
    await driver.close()

asyncio.run(main())
