# NLP Training and Inference Pipeline — Documentation Index

| # | Document | Purpose |
|---|----------|---------|
| 1 | [01-intended-purpose.md](./01-intended-purpose.md) | Intended purpose, scope, success criteria |
| 2 | [02-software-architecture-design.md](./02-software-architecture-design.md) | Two-pipeline, dual-Neo4j architecture |
| 3 | [03-software-detailed-design.md](./03-software-detailed-design.md) | Data models, APIs, services, Neo4j queries |
| 4 | [04-step-by-step-implementation.md](./04-step-by-step-implementation.md) | Phased implementation plan with checklist |
| 5 | [05-verification-and-validation-procedures.md](./05-verification-and-validation-procedures.md) | Unit tests, integration tests, dry run, UAT |

---

## Quick Reference

**Training pipeline**: LLM → Coding graph (EncounterCandidate, ReviewTask)  
**Runtime pipeline**: MedSpaCy → Patient graph (DOCUMENTS)  
**Sync**: Coding gold → Patient DOCUMENTS  
**Reset**: Clear Patient DOCUMENTS, keep text
