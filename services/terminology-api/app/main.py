"""Terminology API service.

Owns: SNOMED search, hybrid coding resolution, terminology writeback,
ValueSet/ConceptMap CRUD against the Knowledge Graph, Redis-cached lookups.
"""

from fastapi import FastAPI

app = FastAPI(
    title="Terminology API",
    description="SNOMED terminology search, coding resolution, ValueSet/ConceptMap management",
    version="0.1.0",
)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "terminology-api"}
