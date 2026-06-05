# SOUP List (Software of Unknown Provenance)

| Field            | Value                                               |
| ---------------- | --------------------------------------------------- |
| Document ID      | DC-SOUP-001                                         |
| Version          | 1.0.0                                               |
| Status           | Draft                                               |
| Date             | 2026-02-25                                          |
| Standard         | IEC 62304:2006+A1:2015, Clause 8.1.2                |
| Classification   | QMS - Design Controls                               |

---

## 1. Purpose

This document lists all Software of Unknown Provenance (SOUP) used by the Primary Care Clinical Pathway Audit Platform, as required by IEC 62304 Clause 8.1.2.

SOUP is software that is already developed, is not developed as part of the device, and for which adequate records of the development processes are not available.

---

## 2. Classification

All SOUP items are assessed for:
- **Functional significance**: How critical is this component to the system's intended purpose?
- **Risk class**: Based on what happens if this component fails or produces incorrect output

| Risk Level | Definition |
|------------|-----------|
| High | Component directly affects clinical output (coding, entity extraction) |
| Medium | Component supports clinical output (data transport, validation) |
| Low | Component provides infrastructure or UI presentation |

---

## 3. Python Backend Dependencies

| # | Package | Version | Source | Functional Significance | Risk | Anomaly Procedures |
|---|---------|---------|--------|------------------------|------|-------------------|
| 1 | **fastapi** | >= 0.115.0 | PyPI | API framework; routes all requests (Core, Terminology, FHIR, Analytics) | Medium | Monitor CVEs; pin major version |
| 2 | **uvicorn** | >= 0.30.0 | PyPI | ASGI server; serves all Python APIs | Low | Standard HTTP server; well-tested |
| 3 | **neo4j** | >= 5.20.0 | PyPI | Neo4j Python driver; Patient Graph + Knowledge Graph access | Medium | Pin to 5.x; test on upgrade |
| 4 | **pydantic** | >= 2.7.0 | PyPI | Request/response validation | Medium | Type validation; failures caught by tests |
| 5 | **python-dotenv** | >= 1.0.1 | PyPI | Environment variable loading | Low | Configuration only |
| 6 | **spacy** | >= 3.8, < 4.0 | PyPI | NLP pipeline framework; sentence splitting, NER | High | Core NLP dependency; pin minor version |
| 7 | **medspacy** | >= 1.3.0 | PyPI | Clinical NLP; PyRuSH sentence splitting | High | Clinical sentence boundaries; validate on upgrade |
| 8 | **boto3** | >= 1.35.0 | PyPI | AWS SDK; Bedrock LLM calls (primary provider) | Medium | API client; failures trigger Azure fallback |
| 9 | **sentence-transformers** | (installed) | PyPI | Bio_ClinicalBERT embedding model | High | Vector search quality depends on model |
| 10 | **torch** | (installed) | PyPI | Deep learning framework; embedding computation | Medium | GPU/CPU inference; well-tested |
| 11 | **pysbd** | (installed) | PyPI | Sentence boundary detection | Medium | Backup sentence splitter |
| 12 | **loguru** | (transitive via PyRuSH) | PyPI | Logging framework | Low | Logging only; no clinical impact |
| 13 | **httpx** | >= 0.27.0 | PyPI | Async HTTP client; inter-service calls (Coding Worker -> Terminology API) | Medium | Network failures caught by retry logic |
| 14 | **redis** | >= 5.0.0 | PyPI | Redis client; pipeline progress, LLM cache | Medium | Used for caching/progress; clinical data unaffected |
| 15 | **azure-servicebus** | >= 7.12.0 | PyPI | Azure Service Bus SDK; batch job messaging | Medium | Queue-based processing; failures retry via dead-letter |
| 16 | **openai** | >= 1.30.0 | PyPI | Azure OpenAI SDK; LLM fallback provider | Medium | Fallback for Bedrock; failures surface as errors |
| 17 | **langchain-core** | >= 0.2.0 | PyPI | LLM provider abstraction layer | Medium | Abstraction only; delegates to boto3/openai |
| 18 | **langchain-aws** | >= 0.2.0 | PyPI | LangChain Bedrock integration | Medium | Wrapper for boto3 Bedrock calls |
| 19 | **langchain-openai** | >= 0.2.0 | PyPI | LangChain Azure OpenAI integration | Medium | Wrapper for openai Azure calls |
| 20 | **PyJWT** | >= 2.8.0 | PyPI | JWT decoding; Azure AD token validation | Medium | Auth boundary; invalid tokens rejected |
| 20a | **python-jose[cryptography]** | >= 3.4.0 | PyPI | JWT/JWK verification at the OAuth callback auth boundary | High | CVE-2024-33663 (algorithm confusion) and CVE-2024-33664 (JWE DoS) affect <3.4.0. Algorithm confusion partially mitigated by RS256-only decode; version floor is the primary control. |
| 21 | **langgraph** | >= 0.4.0 | PyPI | Pipeline orchestration | Medium | Pipeline orchestration; failures surface as errors |
| 22 | **opentelemetry-api** | >= 1.20.0 | PyPI | Observability | Low | Observability only; no clinical impact |
| 23 | **opentelemetry-sdk** | >= 1.20.0 | PyPI | Observability | Low | Observability only; no clinical impact |
| 24 | **opentelemetry-exporter-otlp** | >= 1.20.0 | PyPI | Observability | Low | Observability only; no clinical impact |

### 3.1 ML Models (not packaged, downloaded at runtime)

| # | Model | Source | Version | Purpose | Risk |
|---|-------|--------|---------|---------|------|
| 1 | **emilyalsentzer/Bio_ClinicalBERT** | Hugging Face | Latest | Clinical text embeddings for vector search | High |
| 2 | **Claude 3.5 Haiku** | AWS Bedrock (Anthropic) | anthropic.claude-3-5-haiku | Term extraction and disambiguation | High |

---

## 4. Node.js Frontend Dependencies

| # | Package | Version | Source | Functional Significance | Risk |
|---|---------|---------|--------|------------------------|------|
| 1 | **next** | ^16.1.6 | npm | React framework; SSR, routing, App Router | Low |
| 2 | **react** | ^18.3.1 | npm | UI component library | Low |
| 3 | **react-dom** | ^18.3.1 | npm | React DOM rendering | Low |
| 4 | **@mui/material** | ^7.3.8 | npm | Material UI component library | Low |
| 5 | **@mui/icons-material** | ^7.3.8 | npm | Material UI icons | Low |
| 6 | **@emotion/react** | ^11.14.0 | npm | CSS-in-JS styling (MUI dependency) | Low |
| 7 | **@emotion/styled** | ^11.14.1 | npm | CSS-in-JS styled components | Low |
| 8 | **next-auth** | 5.x (beta) | npm | Authentication; Azure AD / Entra ID SSO | Medium |
| 9 | **recharts** | ^2.13.0 | npm | Chart components for dashboard visualisations | Low |
| 10 | **zustand** | ^5.0.0 | npm | State management for report builder | Low |

### 4.1 Development-Only Dependencies

| # | Package | Version | Purpose |
|---|---------|---------|---------|
| 1 | **typescript** | ^5.5.0 | Type checking |
| 2 | **@types/node** | ^20.14.0 | Node.js type definitions |
| 3 | **@types/react** | ^18.3.3 | React type definitions |
| 4 | **@types/react-dom** | ^18.3.0 | ReactDOM type definitions |

---

## 5. Infrastructure Dependencies

| # | Component | Version | Source | Purpose | Risk |
|---|-----------|---------|--------|---------|------|
| 1 | **Neo4j Aura** (Patient Graph) | 5.x | Neo4j cloud | Patient data, encounters, episodes, review tasks | Medium |
| 2 | **Neo4j Aura** (Knowledge Graph) | 5.x | Neo4j cloud | SNOMED terminology, FHIR resources, domain config | Medium |
| 3 | **Neo4j APOC** | (bundled) | Neo4j Labs | Graph algorithms and utility procedures | Low |
| 4 | **Azure Cache for Redis** | 7.x | Azure | Pipeline progress, LLM response cache | Medium |
| 5 | **Azure Service Bus** | Standard | Azure | Async job queue for coding and analysis workers | Medium |
| 6 | **Azure Active Directory** | v2.0 | Azure | Authentication, RBAC, multi-tenancy | Medium |
| 7 | **AWS Bedrock** | Current | AWS | Primary LLM provider (Claude 3.5 Haiku) | High |
| 8 | **Azure OpenAI** | 2024-06-01 | Azure | Fallback LLM provider (GPT-4o) | High |
| 9 | **Python** | 3.12 | python.org | Backend runtime | Medium |
| 10 | **Node.js** | 18+ LTS | nodejs.org | Frontend runtime | Low |
| 11 | **Docker** | 24+ | docker.com | Container runtime (local development) | Low |

---

## 6. Terminology Data Sources

| # | Source | Version | Purpose | Risk |
|---|--------|---------|---------|------|
| 1 | **SNOMED UK Clinical Edition** | 2026-02-11 | Primary terminology (Concept, Term, ReadCode) | High |
| 2 | **UMLS Metathesaurus** | 2025AB | Cross-terminology crosswalk (CUI -> SNOMED) | Medium |
| 3 | **SNOMED CT Drug Extension (dm+d)** | Current | Drug concept terminology | Medium |

---

## 7. SOUP Management Procedures

### 7.1 Selection

New SOUP items must be evaluated for:
1. Licence compatibility
2. Active maintenance and community support
3. Known vulnerabilities (CVE scan)
4. Functional suitability and test coverage
5. Impact on safety classification

### 7.2 Monitoring

- Subscribe to security advisories for High-risk SOUP items
- Review SOUP updates quarterly
- Test system behaviour after SOUP upgrades before release

### 7.3 Version Pinning

- All Python dependencies pinned in `requirements.txt`
- All Node.js dependencies pinned via `package-lock.json`
- Neo4j version pinned in `docker-compose.yml`
- ML model versions documented in this SOUP list

---

## 8. Approval

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Author | | | |
| Quality Manager | | | |
