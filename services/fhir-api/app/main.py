"""FHIR API service.

R4B-compliant endpoints for Measure, MeasureReport, Library, Device,
PlanDefinition. Evaluates Measure against Patient Graph using Library
Cypher queries stored in Knowledge Graph.
"""

from fastapi import FastAPI

app = FastAPI(
    title="FHIR API",
    description="FHIR R4B Measure/MeasureReport/Library/Device/PlanDefinition",
    version="0.1.0",
)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "fhir-api"}
