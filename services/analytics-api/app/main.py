"""Analytics API service.

Dashboard endpoints, pre-computed aggregation reads, IMD data retrieval,
CCI scoring, benchmark queries. All reads from Patient Graph with
optional Knowledge Graph joins.
"""

from fastapi import FastAPI

app = FastAPI(
    title="Analytics API",
    description="Dashboards, benchmarks, IMD, CCI scoring, pre-computed analytics",
    version="0.1.0",
)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "analytics-api"}
