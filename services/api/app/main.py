"""FastAPI app for HITL training creator MVP."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.audit import router as audit_router
from app.routers.exports import router as exports_router
from app.routers.patients import router as patients_router
from app.routers.pipeline import router as pipeline_router
from app.routers.review import router as review_router
from app.routers.terminology import router as terminology_router


app = FastAPI(
    title="Training Creator HITL API",
    version="0.2.0",
    description="Medical-grade candidate generation and review workflow API.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(patients_router)
app.include_router(pipeline_router)
app.include_router(review_router)
app.include_router(audit_router)
app.include_router(exports_router)
app.include_router(terminology_router)


@app.get("/health")
def healthcheck():
    return {"status": "ok"}
