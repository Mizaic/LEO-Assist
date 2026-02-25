# Software Configuration Management Plan

| Field            | Value                                               |
| ---------------- | --------------------------------------------------- |
| Document ID      | DC-CM-001                                           |
| Version          | 1.0.0                                               |
| Status           | Draft                                               |
| Date             | 2026-02-25                                          |
| Standard         | IEC 62304:2006+A1:2015, Clause 8                    |
| Classification   | QMS - Design Controls                               |

---

## 1. Purpose

This document defines the software configuration management (SCM) practices for the Primary Care Clinical Pathway Audit Platform.

---

## 2. Configuration Items

### 2.1 Source Code

| Item | Location | Identification |
|------|----------|---------------|
| Backend (Python) | services/api/ | Git commit hash |
| Frontend (TypeScript) | services/ui/ | Git commit hash |
| Scripts | scripts/ | Git commit hash |
| Terminology service | services/terminology/ | Git commit hash |

### 2.2 Documentation

| Item | Location | Identification |
|------|----------|---------------|
| Design controls | design-controls/ | Git commit hash + document version |
| NLP pipeline docs | docs/nlp-pipeline/ | Git commit hash + document version |

### 2.3 Dependencies

| Item | Location | Identification |
|------|----------|---------------|
| Python backend | services/api/requirements.txt | Package name + version |
| Python terminology | services/terminology/requirements.txt | Package name + version |
| Node.js frontend | services/ui/package.json + package-lock.json | Package name + version |
| Infrastructure | docker-compose.yml | Image tag |
| ML models | DC-SOUP-001 Section 3.1 | Model name + version |

### 2.4 Configuration

| Item | Location | Identification |
|------|----------|---------------|
| Environment variables | secrets/.env (not in VCS) | Key names documented in 03-detail Section 8 |
| Neo4j schema | services/api/app/models/neo4j_schema.py | Git commit hash |

### 2.5 Terminology Data

| Item | Location | Identification |
|------|----------|---------------|
| SNOMED UK Clinical Edition | external_content/trud-snomed-uk-clinical-edition/ | Release date (2026-02-11) |
| UMLS Metathesaurus | external_content/umls/ | Release version (2025AB) |
| SNOMED Drug Extension | external_content/trud-snomed-ct-drug-extension/ | Release date |

---

## 3. Version Control

### 3.1 Repository

| Item | Value |
|------|-------|
| System | Git |
| Host | GitHub |
| Repository | Primary-care-audit |
| Default branch | main |

### 3.2 Branching Strategy

| Branch | Purpose | Merge To |
|--------|---------|----------|
| main | Production-ready code | -- |
| feature/* | New features | main (via PR) |
| fix/* | Bug fixes | main (via PR) |
| docs/* | Documentation updates | main (via PR) |

### 3.3 Commit Standards

- Commit messages describe the "why" not the "what"
- Each commit should be atomic (one logical change)
- Do not commit secrets, credentials, or .env files

### 3.4 Release Tagging

Releases are tagged using semantic versioning: `vMAJOR.MINOR.PATCH`

| Change Type | Version Bump |
|-------------|-------------|
| Breaking API change | MAJOR |
| New feature, backward compatible | MINOR |
| Bug fix | PATCH |

---

## 4. Change Control

### 4.1 Code Changes

1. Developer creates feature/fix branch
2. Changes implemented with tests
3. Pull request created with description
4. Code review by at least one other developer
5. All tests pass
6. Merge to main

### 4.2 SOUP Updates

1. Review release notes and changelogs
2. Check for security advisories
3. Update version in requirements.txt or package.json
4. Run full test suite
5. Update DC-SOUP-001 if version changes
6. Review risk impact (DC-RM-001)

### 4.3 Terminology Data Updates

1. Download new release from TRUD / UMLS
2. Run terminology loaders
3. Re-run embedding backfill if needed
4. Validate resolver behaviour against gold set
5. Update version in DC-SOUP-001 Section 6

---

## 5. Items Under Version Control

### 5.1 Tracked (in Git)

- All source code (services/api/, services/ui/, scripts/)
- All documentation (design-controls/, docs/)
- Configuration files (docker-compose.yml, requirements.txt, package.json)
- Test files (services/api/tests/)
- .gitignore

### 5.2 Not Tracked (excluded via .gitignore)

- secrets/.env (credentials)
- external_content/ (large terminology data files)
- models/ (trained model artefacts)
- node_modules/, .venv/, __pycache__/
- .python-version

---

## 6. Backup and Recovery

| Item | Backup Method |
|------|--------------|
| Source code | GitHub (remote repository) |
| Terminology data | TRUD / UMLS download archives retained |
| Neo4j databases | Neo4j dump or export procedures |
| Trained models | Re-trainable from exported gold + training script |

---

## 7. Approval

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Author | | | |
| Quality Manager | | | |
