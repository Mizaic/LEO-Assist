# Usability Engineering File (UEF)

| Field            | Value                          |
| ---------------- | ------------------------------ |
| Document ID      | UEF-INDEX                      |
| Version          | 0.1.0-draft                   |
| Status           | Draft                         |
| Date             | 2026-02-24                    |
| Classification   | QMS — Usability Engineering   |
| Standard         | IEC 62366-1:2015 + Amd 1:2020  |

---

## 1. Purpose

This directory contains the Usability Engineering File for the Primary Care Clinical Pathway Audit Platform. The UEF supports compliance with IEC 62366-1 (usability engineering for medical devices) and provides traceability from intended use through user needs, critical tasks, and use-related hazards.

---

## 2. Document Index

### Core UEF
| Document | ID | Description |
| -------- | -- | ----------- |
| [Use Specification](./use-specification.md) | USE-SPEC-001 | User groups, use environment, UI description, training assumptions |
| [Use Specification (NLP Pipeline)](./use-specification-nlp-pipeline.md) | USE-SPEC-002 | NLP pipeline UI: users, environment, critical tasks |
| [User Needs](./user-needs.md) | USER-NEEDS-001 | Traceable user needs with acceptance criteria |
| [Critical Task List](./critical-tasks.md) | CRITICAL-TASKS-001 | Tasks where use error could cause harm |
| [Use-Related Hazard Analysis](./use-related-hazards.md) | URHA-001 | Hazards, causes, effects, risk controls |
| [Use-Related Risk Table](./use-related-risk-table.md) | URRT-001 | Critical tasks, use errors, mitigations, summative criteria |

### UX Analysis (NLP Pipeline UI)
| Document | ID | Description |
| -------- | -- | ----------- |
| [UX Audit Report](./UX-AUDIT-REPORT.md) | UX-AUDIT-001 | 8 principles + gaps; file/line references |
| [Prioritised Improvement List](./prioritised-improvement-list.md) | PIL-001 | Ordered changes; effort; implementation phases |
| [Microcopy and Error Message Audit](./microcopy-error-audit.md) | MEA-001 | Labels, errors, empty states, confirmations |

### Process
| Document | ID | Description |
| -------- | -- | ----------- |
| [Usability Engineering Prompt](./USABILITY-ENGINEERING-PROMPT.md) | — | Process prompt for generating UEF deliverables |

---

## 3. Traceability Flow

```
DC-IU-001 (Intended Use)
        │
        ▼
USE-SPEC-001 (Use Specification)
        │
        ├──────────────────────────┐
        ▼                          ▼
USER-NEEDS-001              CRITICAL-TASKS-001
        │                          │
        │                          ▼
        │                  URHA-001 (Use-Related Hazards)
        │                          │
        ▼                          ▼
   Design inputs  ←──────  Risk control measures
   (UI components, API)
```

---

## 4. Usability Process Summary

1. **Use specification** — Define user groups, environment, UI, training (IEC 62366-1 Clause 5.1)
2. **User needs** — Derive needs from intended use and use specification
3. **Critical tasks** — Identify tasks with use-related risk
4. **Use-related hazard analysis** — Analyse hazards, implement risk controls
5. **Formative evaluation** — (Planned) Usability testing with representative users
6. **Summative evaluation** — (Planned) Validation that residual risk is acceptable

---

## 5. References

- `compliance/policy/intended-use.md` (DC-IU-001)
- `compliance/architecture-superseded/neo4j-nlp-terminology-schema.md`
  (historical; live architecture is in the Atlas SAD via
  `get_software_architecture_document`)
- `services/ui/` — HITL review UI implementation
- `services/api/` — REST API, review workflow
