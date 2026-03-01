# Software Development Plan

| Field            | Value                                               |
| ---------------- | --------------------------------------------------- |
| Document ID      | DC-SDP-001                                          |
| Version          | 2.0.0                                               |
| Status           | Draft                                               |
| Date             | 2026-02-25                                          |
| Standard         | IEC 62304:2006+A1:2015, Clause 4.4                  |
| Classification   | QMS - Design Controls                               |

---

## 1. Purpose

This document describes the software development plan for the Primary Care Clinical Pathway Audit Platform, in accordance with IEC 62304 Clause 4.4.

---

## 2. Scope

This plan covers the NLP Training and Inference Pipeline subsystem, comprising:
- FastAPI backend service (Python)
- Next.js frontend (TypeScript/React)
- Neo4j graph databases (Patient and Coding graphs)
- MedSpaCy training and inference pipeline
- AWS Bedrock LLM integration

---

## 3. Software Safety Classification

**Class B** per DC-SC-001. Non-serious injury is possible through an indirect harm pathway: systematic errors in clinical audit data could misdirect quality improvement efforts at population level.

Class B requires all lifecycle activities from Class A **plus**:
- Software architectural design (Clause 5.3)
- Software unit implementation and verification (Clause 5.5)
- Software integration and integration testing (Clause 5.6)

---

## 4. Development Lifecycle Model

The project follows an **iterative incremental** development model with the following phases:

1. **Requirements analysis** - User needs and software requirements captured and traced
2. **Design** - Architecture and detailed design documented
3. **Implementation** - Code developed with unit tests
4. **Verification** - Unit tests, integration tests, system tests
5. **Validation** - User acceptance testing, clinical review
6. **Release** - Version tagged, release notes, deployment

Each iteration delivers a working increment. Requirements, design, and tests are updated with each iteration.

---

## 5. Development Standards and Conventions

### 5.1 Coding Standards

| Area | Standard |
|------|----------|
| Python | PEP 8, type hints (PEP 484), f-strings preferred |
| TypeScript | Strict mode, ESLint, no implicit any |
| SQL/Cypher | Parameterised queries only (no string interpolation) |
| Comments | Non-obvious intent only; no narration of code behaviour |

### 5.2 Version Control

| Item | Value |
|------|-------|
| VCS | Git |
| Repository | GitHub (Primary-care-audit) |
| Branching | Feature branches from main |
| Merge | Pull request with review |
| Tagging | Semantic versioning (vMAJOR.MINOR.PATCH) |

### 5.3 Environment

| Item | Value |
|------|-------|
| Python | 3.12 |
| Node.js | 18+ LTS |
| Neo4j | 5.x Community Edition |
| OS | Windows (development), Linux (deployment target) |
| Package manager (Python) | pip with requirements.txt |
| Package manager (JS) | npm with package-lock.json |

---

## 6. Documentation Deliverables

### 6.1 Required (IEC 62304 Class B)

| Document | ID | Location | Status |
|----------|-----|----------|--------|
| Software Development Plan | DC-SDP-001 | design-controls/ | This document |
| Safety Classification | DC-SC-001 | design-controls/ | Complete |
| Software Requirements Specification | DC-SRS-001 | design-controls/ | Complete |
| Software Architecture Design | -- | docs/nlp-pipeline/02-*.md | Complete |
| Unit Test Summary | -- | DC-STP-001 Section 5 | Complete |
| Integration Test Plan | DC-ITP-001 | design-controls/ | Complete |
| Software System Test Plan | DC-STP-001 | design-controls/ | Complete |
| Software Maintenance Plan | DC-SMP-001 | design-controls/ | Complete |
| Risk Management | DC-RM-001 | design-controls/ | Complete |
| Configuration Management Plan | DC-CM-001 | design-controls/ | Complete |
| Problem Resolution Process | DC-PR-001 | design-controls/ | Complete |

### 6.2 Voluntary (beyond Class B minimum)

| Document | ID | Location | Status |
|----------|-----|----------|--------|
| Intended Use Statement | DC-IU-001 | design-controls/ | Complete |
| Software Detailed Design | -- | docs/nlp-pipeline/03-*.md | Complete |
| Verification Report | -- | docs/nlp-pipeline/VERIFICATION-REPORT.md | Complete |
| SOUP List | DC-SOUP-001 | design-controls/ | Complete |
| Traceability Matrix | DC-TM-001 | design-controls/ | Complete |

---

## 7. Tools

| Tool | Purpose | Version |
|------|---------|---------|
| Python | Backend runtime | 3.12 |
| pytest | Unit testing | Latest |
| FastAPI | API framework | >= 0.115.0 |
| Next.js | Frontend framework | ^14.2.20 |
| Neo4j | Graph database | 5.x Community |
| Git | Version control | Latest |
| GitHub | Repository hosting | N/A |
| AWS Bedrock | LLM inference | N/A |
| Docker Compose | Local Neo4j | Latest |

---

## 8. Risk Management Activities

Risk management is performed per DC-RM-001, linked to ISO 14971.

Key risk activities:
- Hazard identification during requirements analysis
- Risk estimation for each identified hazard (including indirect harm pathways per Class B)
- Risk control measures documented and verified
- Residual risk assessment at each release
- Automation bias monitoring (periodic sampling audits of reviewer behaviour)

---

## 9. Verification and Validation

### 9.1 Unit Verification (Clause 5.5 - Required for Class B)

- Python unit tests using pytest (58+ tests)
- Tests located in `services/api/tests/`
- Run via `python -m pytest services/api/tests/`
- Coverage includes all major service components (extractor, resolver, disambiguator, sync, writeback, review)

### 9.2 Integration Testing (Clause 5.6 - Required for Class B)

- Per DC-ITP-001
- Verifies correct interaction between software units and between the software and its external interfaces (Neo4j, AWS Bedrock, frontend)
- Covers cross-graph data flow (patient graph / coding graph separation)

### 9.3 System Testing (Clause 5.7)

- Per DC-STP-001
- Covers end-to-end user journeys
- Includes data governance verification (no patient data in Coding graph)

### 9.4 Validation

- User acceptance testing per docs/nlp-pipeline/05-verification-and-validation-procedures.md
- MedSpaCy validation: F1 >= 0.90 against gold before deployment
- Clinical review of SNOMED coding accuracy

---

## 10. Configuration Management

Per DC-CM-001:
- Source code versioned in Git
- Dependencies pinned in requirements.txt and package.json
- SOUP components tracked in DC-SOUP-001
- Releases tagged with semantic versions

---

## 11. Software Release Process

1. All unit tests pass (58+)
2. Integration tests pass (DC-ITP-001)
3. System test plan executed (DC-STP-001)
4. V&V checklist completed (docs/nlp-pipeline/05-*.md Section 10)
5. Residual risk acceptable (DC-RM-001 Section 6)
6. Release notes drafted
7. Version tagged in Git
8. Release artefacts archived

---

## 12. Approval

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Author | | | |
| Quality Manager | | | |
