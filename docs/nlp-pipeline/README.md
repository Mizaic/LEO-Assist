# NLP Training and Inference Pipeline — Documentation Index

| # | Document | Purpose |
|---|----------|---------|
| 1 | [01-intended-purpose.md](./01-intended-purpose.md) | Intended purpose, scope, success criteria |
| 2 | [02-software-architecture-design.md](./02-software-architecture-design.md) | Two-pipeline, dual-Neo4j architecture |
| 3 | [03-software-detailed-design.md](./03-software-detailed-design.md) | Data models, APIs, services, Neo4j queries |
| 4 | [04-step-by-step-implementation.md](./04-step-by-step-implementation.md) | Implementation history and current state |
| 5 | [05-verification-and-validation-procedures.md](./05-verification-and-validation-procedures.md) | Unit tests, integration tests, dry run, UAT |
| 6 | [06-phase5-6-implementation-plan.md](./06-phase5-6-implementation-plan.md) | MedSpaCy training, inference, and terminology writeback |

---

## Quick Reference

**Training pipeline**: LLM → Patient graph (EncounterCandidate, ReviewTask)
**Runtime pipeline**: MedSpaCy → Patient graph (DOCUMENTS)
**Sync gold**: Patient graph approved candidates → Patient graph DOCUMENTS
**Terminology writeback**: Patient graph approved terms → Coding graph SurfaceForm nodes
**Coding graph**: Read-only terminology (Term, Concept, SurfaceForm) — no patient data
**Reset**: Clear Patient graph DOCUMENTS, keep text
