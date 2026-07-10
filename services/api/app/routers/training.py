"""Training data management router -- thin aggregator.

Atlas trace:
  DO: DO-236545C8
  Also implements: DO-2D2CE052, DO-54397CCD, DO-6CD07544, DO-94D87FA7, DO-A35D2D57, DO-B88D4941, DO-BA2B7A99
  DI: DI-2D9F5064, DI-37B3DC71, DI-3EA60D5A, DI-54D00E21, DI-6EFD68D0, DI-A0579B64, DI-AF5A1668, DI-D2D0117E
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-236545C8")

Historically this single file held every /training/* endpoint (7200+ LOC,
88 handlers) -- flagged in the 2026-07 CTO peer review as god-service
pressure on core-api. It has been decomposed into one sub-router module per
feature area; this file only creates the parent APIRouter (with the
"/training" prefix all sub-routers share) and composes the sub-routers onto
it. No route paths, response shapes, or behaviour changed as part of the
split -- see the sub-router modules for route documentation.

Sub-routers (see each module's docstring for its routes):
  - training_jobs.py               -- training worker job proxy
  - training_labels.py             -- TrainingLabel store
  - coding_review.py               -- HITL coding review queue + Ask LEO
  - context_and_ignore_rules.py    -- post-processor/context/ignore rules,
                                       surface-form admin
  - training_synthetic_data.py     -- synthetic gold-standard generation
  - training_candidates.py         -- TrainingCandidate dedupe/prune/
                                       active-learning + AI-first-pass jobs
  - training_gold_labels.py        -- GoldLabel store
  - training_corpus.py             -- corpus statistics + schema sample-node

Shared helpers used by more than one sub-router live in
app/routers/_training_common.py.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.routers.coding_review import router as _coding_review_router
from app.routers.context_and_ignore_rules import router as _rules_router
from app.routers.training_candidates import router as _candidates_router
from app.routers.training_corpus import router as _corpus_router
from app.routers.training_gold_labels import router as _gold_labels_router
from app.routers.training_jobs import router as _jobs_router
from app.routers.training_labels import router as _labels_router
from app.routers.training_synthetic_data import router as _synthetic_router

router = APIRouter(prefix="/training", tags=["training"])

router.include_router(_jobs_router)
router.include_router(_labels_router)
router.include_router(_coding_review_router)
router.include_router(_rules_router)
router.include_router(_synthetic_router)
router.include_router(_candidates_router)
router.include_router(_gold_labels_router)
router.include_router(_corpus_router)
