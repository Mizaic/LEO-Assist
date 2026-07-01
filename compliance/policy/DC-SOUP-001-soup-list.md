# SOUP List (Software of Unknown Provenance)

| Field            | Value                                               |
| ---------------- | --------------------------------------------------- |
| Document ID      | DC-SOUP-001                                         |
| Version          | 1.2.0                                               |
| Status           | Draft - 3 of 4 open anomalies resolved for release v2026.3 ("Val Gardena"); pending Quality Manager sign-off on the remaining neo4j item |
| Date             | 2026-07-01                                          |
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

Consolidated from the root `requirements.txt` and every `services/*/requirements.txt`
in the repository as of 2026-07-01. "Used in" lists the services that pin the
package directly (transitive-only packages are not repeated here).

| # | Package | Version floor | Source | Used in | Functional Significance | Risk |
|---|---------|---------|--------|---------|------------------------|------|
| 1 | **fastapi** | >= 0.115.0 | PyPI | api, terminology_api, analytics_api, fhir_api, pipeline_worker, model_inference, training_worker, ods_sync | API framework; routes all requests | Medium |
| 2 | **uvicorn** | >= 0.34.0 | PyPI | api, terminology_api, analytics_api, fhir_api, pipeline_worker, model_inference, training_worker, ods_sync | ASGI server; serves all Python APIs | Low |
| 3 | **neo4j** | >= 5.28.0 | PyPI | api, terminology_api, analytics_api, fhir_api, pipeline_worker, training_worker, ods_sync | Neo4j driver; Patient Graph + Knowledge Graph access | Medium |
| 4 | **pydantic** | >= 2.10.0 | PyPI | api, terminology_api, analytics_api, fhir_api, pipeline_worker | Request/response validation | Medium |
| 5 | **python-dotenv** | >= 1.1.0 | PyPI | api, terminology_api, analytics_api, fhir_api, pipeline_worker, model_inference, training_worker | Environment variable loading | Low |
| 6 | **spacy** | >= 3.8, < 4.0 | PyPI | api, pipeline_worker, terminology (loader) | NLP pipeline framework; sentence splitting, NER | High |
| 6a | **spacy-transformers** | >= 1.3, < 1.4 | PyPI | model_inference, training_worker | Loads transformer-backbone NER models (Bio_ClinicalBERT) | High |
| 7 | **medspacy** | == 1.3.1 | PyPI | api, pipeline_worker, terminology (loader) | Clinical NLP; sentence boundary detection | High |
| 7a | **PyRuSH** | >= 1.0.8 | PyPI | terminology (loader) | Sentence-splitting backend used by medspacy | Medium |
| 8 | **boto3** | >= 1.42.64 | PyPI | api, analytics_api, pipeline_worker | AWS SDK; Bedrock LLM calls (primary provider) | Medium |
| 8a | **botocore** | >= 1.42.64 | PyPI | api, analytics_api, pipeline_worker | AWS SDK core; version-locked with boto3 | Medium |
| 9 | **sentence-transformers** | >= 3.0.0, < 4 | PyPI | terminology_api, pipeline_worker | Bio_ClinicalBERT embedding model | High |
| 10 | **torch** | >= 2.0.0 (CPU-pinned 2.10.0+cpu in Linux containers) | PyPI | model_inference, training_worker, pipeline_worker | Deep learning framework; embedding computation | Medium |
| 10a | **cupy-cuda12x** | >= 14 (Windows dev only) | PyPI | training_worker | CUDA acceleration for local GPU training runs | Low |
| 11 | **pysbd** | (installed) | PyPI | api | Backup sentence boundary detection | Medium |
| 12 | **loguru** | >= 0.7 | PyPI | api | Logging framework | Low |
| 13 | **httpx** | >= 0.28.0 | PyPI | api, terminology_api, analytics_api, fhir_api, pipeline_worker, model_inference, ods_sync | Async HTTP client; inter-service calls | Medium |
| 13a | **aiohttp** | >= 3.9.0 | PyPI | pipeline_worker | Async HTTP transport for Azure Service Bus / Key Vault clients | Medium |
| 13b | **requests** | >= 2.32 | PyPI | api, fhir_api, pipeline_worker, terminology (loader) | Sync HTTP client | Medium |
| 14 | **redis** | >= 5.2.0 | PyPI | api, terminology_api, analytics_api, pipeline_worker, training_worker | Redis client; pipeline progress, LLM cache | Medium |
| 15 | **azure-servicebus** | >= 7.13.0 | PyPI | api, pipeline_worker | Azure Service Bus SDK; batch job messaging | Medium |
| 15a | **azure-identity** | >= 1.19.0 (1.16.0 floor in terminology loader -- see 7.4) | PyPI | api, terminology_api, analytics_api, fhir_api, pipeline_worker, model_inference, training_worker, ods_sync, terminology (loader) | Azure AD credential chain for Key Vault / Blob / Service Bus auth | Medium |
| 15b | **azure-keyvault-secrets** | >= 4.8.0 | PyPI | api, terminology_api, analytics_api, fhir_api, pipeline_worker, model_inference, training_worker, ods_sync, terminology (loader) | Secret retrieval at startup | Medium |
| 15c | **azure-storage-blob** | >= 12.20.0 | PyPI | api (root), model_inference, training_worker | NER model artifact store | Medium |
| 16 | **openai** | >= 1.30.0 | PyPI | (via langchain-openai) | Azure OpenAI SDK; LLM fallback provider | Medium |
| 17 | **langchain-core** | >= 0.2.0 | PyPI | (transitive) | LLM provider abstraction layer | Medium |
| 18 | **langchain-aws** | >= 0.3.0 | PyPI | api, analytics_api, pipeline_worker | LangChain Bedrock integration | Medium |
| 19 | **langchain-openai** | >= 0.3.0 | PyPI | api, analytics_api, pipeline_worker | LangChain Azure OpenAI integration | Medium |
| 20 | **PyJWT** | >= 2.8.0 | PyPI | (auth libs) | JWT decoding; Azure AD token validation | Medium |
| 20a | **python-jose[cryptography]** | >= 3.4.0 (all services, aligned 2026-07-01) | PyPI | api, fhir_api, pipeline_worker | JWT/JWK verification at the OAuth callback auth boundary | High |
| 21 | **langgraph** | >= 0.4.0 | PyPI | api, pipeline_worker | Pipeline orchestration | Medium |
| 21a | **graphdatascience** | >= 1.10 | PyPI | analytics_api, ods_sync | Neo4j Graph Data Science library for analytics queries | Medium |
| 21b | **slowapi** | >= 0.1.9 | PyPI | api | API rate limiting | Low |
| 21c | **beautifulsoup4** | >= 4.12 | PyPI | api, pipeline_worker | HTML parsing for source-document ingestion | Medium |
| 21d | **jsonschema** | (unpinned floor) | PyPI | terminology_api, terminology (loader) | Schema validation for terminology config seeds | Medium |
| 21e | **numpy** | >= 1.26.0, < 2.4 | PyPI | terminology_api, pipeline_worker | Numerical arrays for embeddings and bitmap ops | Medium |
| 21f | **pyroaring** | >= 1.0.0 | PyPI | terminology_api | Roaring-bitmap compression for guideline bitmaps | Medium |
| 21g | **scikit-learn** | >= 1.3.0 (>= 1.4 in terminology loader) | PyPI | model_inference, training_worker, terminology (loader) | Classical ML utilities for model scoring/training | High |
| 21h | **scipy** | >= 1.12 | PyPI | terminology (loader) | Scientific computing support for terminology loaders | Medium |
| 21i | **joblib** | (unpinned floor) | PyPI | terminology (loader) | Model/artifact (de)serialisation | Medium |
| 21j | **nmslib** | >= 2.1.2 | PyPI | terminology (loader) | Approximate nearest-neighbour search for terminology matching | High |
| 22 | **opentelemetry-api** | >= 1.20.0 | PyPI | api, pipeline_worker | Observability | Low |
| 23 | **opentelemetry-sdk** | >= 1.20.0 | PyPI | api, pipeline_worker | Observability | Low |
| 24 | **opentelemetry-exporter-otlp** | >= 1.20.0 | PyPI | api, pipeline_worker | Observability | Low |

### 3.1 ML Models (not packaged, downloaded at runtime)

| # | Model | Source | Version | Purpose | Risk |
|---|-------|--------|---------|---------|------|
| 1 | **emilyalsentzer/Bio_ClinicalBERT** | Hugging Face | Latest | Clinical text embeddings for vector search | High |
| 2 | **Claude Haiku 4.5** | AWS Bedrock (Anthropic) | `eu.anthropic.claude-haiku-4-5-20251001-v1:0` | Small-tier: term extraction and disambiguation | High |
| 3 | **Claude Sonnet 4.6** | AWS Bedrock (Anthropic) | `eu.anthropic.claude-sonnet-4-6` | Big-tier: complex reasoning, escalation, SBAR generation | High |

Model IDs are defined in `libs/llm_client/factory.py`. This replaces the
previous "Claude 3.5 Haiku" entry, which was superseded and no longer
matches the model actually configured.

### 3.2 Open anomalies found during the 2026-07-01 refresh

These were found by diffing this list against the actual `requirements.txt`
files. Items 2-4 must be resolved (or formally risk-accepted) before this
document can be signed off (Section 10):

1. **RESOLVED 2026-07-01.** ~~python-jose version floor below the documented
   CVE mitigation.~~ Row 20a documented `>= 3.4.0` as the control for
   CVE-2024-33663 and CVE-2024-33664, but `services/api/requirements.txt`,
   `services/fhir_api/requirements.txt`, and `services/pipeline_worker/requirements.txt`
   each pinned only `>= 3.3`, so the Dockerfiles that build directly from
   those per-service files (`infra/dockerfiles/Dockerfile.core-api`,
   `Dockerfile.fhir-api`, `Dockerfile.pipeline-worker`) were not guaranteed
   to exclude the vulnerable range. Classified Class A per precedent set by
   the sibling authentication Design Inputs under `UN-LEO-035` (the human
   clinician-review gate covers downstream impact); tracked as `DI-A30F58D6`
   / `DO-FA6A62FC` in Atlas. Fixed by bumping all three floors to `>= 3.4.0`
   and adding `tests/test_soup_python_jose_floor.py` as a regression guard.
2. **OPEN -- neo4j major-version pin needs a compatibility decision, not a
   blind edit.** `services/terminology/requirements.txt` pins `neo4j==6.1.0`
   (exact) while every other service floors at `>= 5.20.0`/`>= 5.28`
   (root). This is a **major-version** divergence (5.x vs 6.x), and the
   Neo4j Python driver has breaking changes across that boundary, so this
   was deliberately **not** auto-aligned in the 2026-07-01 pass -- doing so
   without running the terminology loader's test suite against the older
   driver risks breaking it. Needs an owner to either (a) verify the
   terminology loader against `neo4j>=5.20.0` and drop to the shared floor,
   or (b) confirm 6.1.0 is intentional and document why, then update this
   row instead of flagging it as drift.
3. **RESOLVED 2026-07-01.** ~~python-dotenv version pin inconsistency.~~
   `services/terminology/requirements.txt` pinned `python-dotenv==1.2.1`
   (exact) against the `>= 1.0.1` floor used elsewhere. `python-dotenv`'s
   `load_dotenv()` API is stable across 1.0-1.2, so this was a safe,
   non-breaking alignment -- changed to `>= 1.0.1`.
4. **RESOLVED 2026-07-01 (corrected attribution).** ~~azure-identity floor
   inconsistency in services/terminology.~~ The actual drift was in
   `services/ods_sync/requirements.txt` (`>= 1.16.0` vs `>= 1.19.0`
   everywhere else) -- `services/terminology` does not depend on
   `azure-identity` at all; this was a misattribution in the initial
   2026-07-01 draft of this section, corrected here. Fixed by bumping
   `services/ods_sync/requirements.txt` to `>= 1.19.0`.

---

## 4. Node.js Frontend Dependencies

Consolidated from `services/ui/package.json`, `services/widget-sdk/package.json`,
and `services/design-system/package.json` as of 2026-07-01. `@leo/design-system`
and `@mizaic/leo-widget` are in-house workspace packages, not third-party SOUP,
and are listed only to show where the UI depends on internal packages.

| # | Package | Version | Source | Functional Significance | Risk |
|---|---------|---------|--------|------------------------|------|
| 1 | **next** | ^16.2.9 | npm | React framework; SSR, routing, App Router | Low |
| 2 | **react** | ^18.3.1 | npm | UI component library | Low |
| 3 | **react-dom** | ^18.3.1 | npm | React DOM rendering | Low |
| 4 | **@mui/material** | ^7.3.8 | npm | Material UI component library | Low |
| 5 | **@mui/icons-material** | ^7.3.8 | npm | Material UI icons | Low |
| 5a | **@mui/lab** | ^7.0.1-beta.22 | npm | Material UI lab (pre-release) components | Low |
| 6 | **@emotion/react** | ^11.14.0 | npm | CSS-in-JS styling (MUI dependency) | Low |
| 7 | **@emotion/styled** | ^11.14.1 | npm | CSS-in-JS styled components | Low |
| 8 | **next-auth** | ^5.0.0-beta.30 | npm | Authentication; Azure AD / Entra ID SSO | Medium |
| 9 | **recharts** | ^3.7.0 | npm | Chart components for dashboard visualisations | Low |
| 10 | **zustand** | ^5.0.11 | npm | State management for report builder | Low |
| 11 | **dompurify** | ^3.4.11 | npm | Sanitises HTML rendered from AI/user-generated content (XSS control) | High |
| 12 | **@dnd-kit/core**, **@dnd-kit/sortable**, **@dnd-kit/utilities** | ^6.3.1 / ^10.0.0 / ^3.2.2 | npm | Drag-and-drop for guideline rule builder | Low |
| 13 | **@tiptap/*** (core, react, starter-kit, extension-link/placeholder/table/table-cell/table-header/table-row/task-item/task-list/underline) | ^3.20.1 | npm | Rich-text editor for guideline rule authoring and clinical notes | Medium |
| 14 | **tiptap-markdown** | ^0.9.0 | npm | Markdown serialisation for the Tiptap editor | Low |
| 15 | **@xyflow/react** | ^12.10.1 | npm | Node/edge graph rendering (pathway and logic-tree views) | Low |
| 16 | **d3-force**, **d3-sankey** | ^1.2.1 / ^0.12.3 | npm | Force-directed and sankey chart layouts | Low |
| 17 | **framer-motion** | ^11.18.2 | npm | UI animation (also a peer dependency of `@leo/design-system`) | Low |
| 18 | **html2canvas** | ^1.4.1 | npm | Client-side screenshot capture for report export | Low |
| 19 | **immer** | ^11.1.4 | npm | Immutable state updates | Low |
| 20 | **ioredis** | ^5.9.3 | npm | Redis client for UI-side real-time features | Medium |
| 21 | **jspdf**, **jspdf-autotable** | ^4.2.1 / ^5.0.7 | npm | Client-side PDF export | Low |
| 22 | **plotly.js-dist-min**, **react-plotly.js** | ^3.5.0 / ^2.6.0 | npm | Chart components for analytics dashboards | Low |
| 23 | **react-force-graph-2d** | ^1.29.1 | npm | Graph visualisation | Low |
| 24 | **react-grid-layout** | ^2.2.3 | npm | Dashboard widget layout | Low |
| 25 | **react-icons** | ^5.5.0 | npm | Icon set | Low |
| 26 | **react-virtuoso** | ^4.18.1 | npm | Virtualised list rendering for large tables | Low |
| 27 | **undici** | ^7.28.0 | npm | HTTP client used for server-side fetch calls | Medium |
| -- | **@leo/design-system** | workspace (`*`) | in-house | Internal design tokens, motion, primitives -- not third-party SOUP | n/a |
| -- | **@mizaic/leo-widget** | ^0.1.0-mvp.1 | in-house | Internal embeddable SBAR widget -- not third-party SOUP | n/a |

### 4.1 Development-Only Dependencies

| # | Package | Version | Purpose |
|---|---------|---------|---------|
| 1 | **typescript** | ^5.5.0 | Type checking |
| 2 | **@types/node** | ^20.14.0 | Node.js type definitions |
| 3 | **@types/react** | ^18.3.3 | React type definitions |
| 4 | **@types/react-dom** | ^18.3.0 | ReactDOM type definitions |
| 5 | **jest**, **jest-environment-jsdom** | 30.4.1 | Unit/static-source test runner (generates VT evidence) |
| 6 | **ts-jest** | ^29.4.6 | TypeScript support for Jest |
| 7 | **@testing-library/react**, **dom**, **jest-dom**, **user-event** | ^16.3.2 / ^10.4.1 / ^6.9.1 / ^14.6.1 | Component-level test rendering |
| 8 | **@playwright/test** | ^1.58.2 | End-to-end test runner (generates VAL evidence) |
| 9 | **@axe-core/playwright** | ^4.11.1 | Automated WCAG 2.1 AA accessibility checks |
| 10 | **vite** | ^6.4.3 | Build tool for `services/widget-sdk` |

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
| 7 | **AWS Bedrock** | Current | AWS | Primary LLM provider (Claude Haiku 4.5 / Sonnet 4.6, see 3.1) | High |
| 8 | **Azure OpenAI** | API version 2024-12-01-preview (default; overridable via `AZURE_OPENAI_API_VERSION`) | Azure | Fallback LLM provider; model set via `AZURE_OPENAI_SMALL_MODEL` / `AZURE_OPENAI_BIG_MODEL` env vars | High |
| 9 | **Python** | 3.12 | python.org | Backend runtime | Medium |
| 10 | **Node.js** | >= 20, < 23 (per `services/ui/package.json` engines) | nodejs.org | Frontend runtime | Low |
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

### 7.4 Open items from the 2026-07-01 refresh

See Section 3.2 for the full detail. Summary for release-gate tracking:

| Item | Risk if unresolved | Status |
|---|---|---|
| `python-jose` floor below documented CVE control in 3 production services | High -- auth-boundary package | **Resolved 2026-07-01** (DI-A30F58D6 / DO-FA6A62FC) |
| `neo4j` exact-pin (`==6.1.0`) vs `>=5.x` floor elsewhere, in terminology loader | Low-Medium -- untested major-version skew | Open -- needs compatibility verification, not a blind edit |
| `python-dotenv` exact-pin drift in terminology loader | Low | **Resolved 2026-07-01** |
| `azure-identity` floor drift (misattributed to terminology; actual owner is `services/ods_sync`) | Low | **Resolved 2026-07-01** |

This document cannot be signed off (Section 10) until the remaining Open
`neo4j` item is resolved (compatibility verified and aligned, or explicitly
risk-accepted with rationale); it is not High risk and does not block the
python-jose fix above.

---

## 9. Revision history

| Version | Date | Author | Summary |
| ------- | ---- | ------ | ------- |
| 1.0.0 | 2026-02-25 | Engineering | Initial SOUP list. |
| 1.1.0 | 2026-07-01 | Engineering | Refreshed against all 11 `requirements.txt` files and the 3 frontend `package.json` files ahead of release v2026.3 ("Val Gardena"). Corrected version drift (uvicorn, neo4j, pydantic, httpx, boto3, next, recharts, next-auth). Added ~30 previously undocumented packages (frontend editor/visualisation stack, ML tooling, Azure SDKs). Corrected the LLM model entries from "Claude 3.5 Haiku" / "GPT-4o" to the models actually configured in `libs/llm_client/factory.py`. Logged 4 open anomalies including one High-risk security floor gap (Section 3.2 / 7.4). |
| 1.2.0 | 2026-07-01 | Engineering | Resolved 3 of the 4 open anomalies. python-jose bumped to `>= 3.4.0` in `services/api`, `services/fhir_api`, `services/pipeline_worker` (Atlas `DI-A30F58D6` / `DO-FA6A62FC`), closing the CVE-2024-33663/33664 gap; added `tests/test_soup_python_jose_floor.py` as a regression guard. `python-dotenv` aligned to `>= 1.0.1` in `services/terminology`. Corrected a misattribution: the `azure-identity` floor drift belonged to `services/ods_sync` (not `services/terminology`), now bumped to `>= 1.19.0`. The `neo4j` major-version pin (`services/terminology` on `6.1.0` vs `5.x` elsewhere) is left open pending compatibility verification -- deliberately not auto-aligned given the driver's breaking changes across major versions. |

---

## 10. Approval

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Author | | | |
| Quality Manager | | | |
