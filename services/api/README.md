# Core API

FastAPI microservice that forms the central backend for the LEO AI platform.
It manages the full human-in-the-loop (HITL) medical coding workflow for UK
NHS primary care cancer audits.

## What it does

1. Runs NLP/LLM pipelines over GP encounter records to extract and SNOMED
   CT-code clinical entities.
2. Surfaces candidate codings to human reviewers via a structured review queue.
3. Captures review decisions as training data and feeds that data back into an
   NER model lifecycle (train, validate, canary, promote).
4. Provides org-scoped multi-tenant access for GP practices, Integrated Care
   Boards (ICBs), and Cancer Alliances.

## Quick start (local)

Prerequisites: Python 3.12, a running Neo4j instance, Redis, and
`secrets/.env` populated (see `.env.example`).

```bash
# From the repo root
.venv/Scripts/Activate.ps1          # Windows
source .venv/bin/activate           # Linux / macOS

uvicorn services.api.app.main:app \
    --host 0.0.0.0 --port 8000 --reload
```

Startup scripts `scripts/start_leo-ai-core.sh` (macOS/Linux) and
`scripts/start_leo-ai-core.ps1` (Windows) handle venv creation and service
orchestration for local development.

## Docker

```bash
docker build -f infra/dockerfiles/Dockerfile.core-api -t core-api .
docker run --env-file secrets/.env -p 8000:8000 core-api
```

Python base image: `python:3.12-slim-bookworm`.

## Dependencies

Key packages (full list in `requirements.txt`):

| Package | Role |
|---|---|
| `fastapi` + `uvicorn` | Web framework and ASGI server |
| `neo4j>=5.20` | Patient graph and coding graph (Neo4j 5.x) |
| `pydantic>=2.7` | Request/response validation |
| `spacy>=3.8,<4.0` + `medspacy==1.3.1` | Clinical NLP inference |
| `azure-identity`, `azure-keyvault-secrets` | Azure credential chain |
| `azure-servicebus` | Async coding job dispatch |
| `redis` | Server-side session store and pipeline pub/sub |
| `boto3` | AWS Bedrock LLM client (Claude) |

## Architecture

### Dual Neo4j graphs

Every router distinguishes between two graph instances:

- **Patient graph** -- demographics, encounters, review queue, training labels.
- **Coding graph** -- SNOMED terminology, surface forms, coding relationships.

### Auth

Azure AD OAuth 2.0. Tokens are stored server-side in Redis; the browser holds
only an `HttpOnly`, `SameSite=lax`, `Secure` session cookie. All identity
resolves from the session -- `X-User-Email` headers and `?email=` params are
explicitly blocked (GAP-001/GAP-009/GAP-010).

### Org-scoped RBAC

`CallerScope` is resolved from the Neo4j practitioner graph on every request.
Platform admins bypass all filters; GP/ICB/Alliance users see only patients
registered to their org hierarchy. Scope failures return 404 (not 403) to
avoid leaking patient existence.

### Entra-group-driven roles (Option A)

LEO does not provision Entra security groups. The tenant administrator
creates the security groups in their Entra tenant and the LEO Neo4j graph
holds the binding catalogue mapping each group's object ID to a canonical
LEO role:

```cypher
(:Group {entra_object_id})-[:GRANTS_ROLE {org_id}]->(:Role {name})
```

On every successful OIDC callback, `core-api`:

1. Reads the verified `groups` claim from the ID token.
2. Resolves each group object ID against the catalogue.
3. Synchronises the practitioner's `[:HAS_ROLE]` edges to the resolved
   role-name set (drops stale, adds new).
4. Persists the resolved roles on the Redis session for fast read.
5. Audits any unknown group IDs via `auth.entra_groups.unknown_group`,
   missing claims via `auth.entra_groups.missing`, and overage via
   `auth.entra_groups.overage` (overage explicitly does NOT call
   Microsoft Graph -- the LEO app registration holds zero `Group.*`,
   `GroupMember.*`, or `Directory.*` permissions).

#### Required app registration manifest setting

The runtime Entra app registration MUST set:

```json
{
  "groupMembershipClaims": "SecurityGroup"
}
```

This emits each user's security-group object IDs in the OIDC `groups`
claim with no Graph permission. See Atlas DI-3610585D for the security
constraints on the app registration.

#### Seeding the Neo4j catalogue

The catalogue is checked in at
`data/identity/entra-group-bindings.example.yaml`. Copy it to
`entra-group-bindings.yaml`, fill in the real Entra group object IDs,
and run:

```bash
python -m scripts.seed_roles_and_groups \
    --bindings data/identity/entra-group-bindings.yaml
```

The script is idempotent and never creates or modifies anything in
Entra -- only the Neo4j `:Group` nodes and `[:GRANTS_ROLE]` edges.

Atlas chain: UN-A449F651 -> DI-D9D4BA02 / DI-3610585D ->
DO-11B1CC4D -> R-A4473229 -> VT-67FB9C97.

### Dual-model voting

Classification, label verification, and anchor domain review all run two
independent models (Claude Haiku via Bedrock + GPT-4o-mini via Azure OpenAI).
Disagreements are surfaced to human reviewers. Every vote records per-model
accuracy and feeds few-shot example caches.

### Closed training feedback loop

Every human action -- review decision, manual code addition, HITL task
resolution, verification resolution -- writes a `TrainingLabel` node. Human
corrections become training data for the next model version automatically.

### NER model lifecycle

```
registered -> offline_validated -> canary -> promoted
                                          -> deprecated / rollback
```

Gate checks enforce minimum precision/recall thresholds at each transition.
Promotion triggers an HTTP call to the inference service to hot-reload without
restart.

## API surface (summary)

| Prefix | Description |
|---|---|
| `/auth` | Azure AD OAuth 2.0 login, callback, logout, session |
| `/pipeline` | NLP/LLM pipeline runs (sync, SSE stream, async via Service Bus) |
| `/patients` | Patient list, encounter detail, manual coded links, hybrid search |
| `/review` | Paginated HITL review queue and decision capture |
| `/training` | Training label corpus, label verification, coding review queue |
| `/terminology` | SNOMED search, surface form management, writeback |
| `/model-registry` | NER model lifecycle (register, validate, canary, promote) |
| `/operations` | Cross-cutting HITL task queue for all review stages |
| `/anchor-review` | Anchor event domain disagreement review |
| `/exports` | Gold dataset and MedSpaCy training format export |
| `/api/proxy` | Authenticating proxy to FHIR, Analytics, and Pipeline APIs |
| `/audit` | Full audit timeline for an EncounterCandidate |
| `/agent` | LLM report interpretation and executive summary stubs |
| `/health` | `GET /health` returns `{"status": "ok"}` |

Full interactive docs at `http://localhost:8000/docs` when running locally.

## Shared libraries

Shared code lives in `libs/` at the repo root and is available on
`PYTHONPATH=/app` inside Docker:

| Library | Role |
|---|---|
| `libs/auth/` | `CallerScope`, org hierarchy resolution, `require_patient_in_scope` |
| `libs/llm_client/` | Unified sync client for AWS Bedrock and Azure OpenAI |
| `libs/neo4j_client/` | `PatientGraphClient` wrapper |
| `libs/redis_client/` | Session storage and pipeline checkpoint cache |
| `libs/cypher/` | All Cypher query strings, organised by domain |
| `libs/prompts/` | Versioned prompt registry and few-shot builder |
| `libs/ner/` | Training label writer, post-processor rules, precision gates |
| `libs/model_registry/` | Model lifecycle state machine |
| `libs/message_bus/` | Azure Service Bus and in-memory (dev) adapters |

## Configuration

Settings are loaded from `secrets/.env` via `python-dotenv` at import time
(`app/config.py`). See `.env.example` in the repo root for required keys.

## Regulatory

This service is classified as a **Class IIa medical device** software component
under UK MDR 2002. Changes must be traced to design controls in the
Atlas MCP server (`user-atlas-design-controls`, product
`PROD-LEO-CORE-AI-20260415-6AE8A23B`) and must not reduce precision /
recall below the baselines recorded against the relevant Atlas VTs.
Use `get_traceability_matrix` for the live trace.

## CI/CD and ACA deployment

- Docker image: `leoaicr.azurecr.io/core-api`
- Container App name: `core-api`
- Dockerfile: `infra/dockerfiles/Dockerfile.core-api`

GitHub Actions build this image in `CI - Build and Push Images` and deploy it in
`CD - Deploy`.

To trigger the full pipeline for this service, commit a small change in this
folder (for example `services/api/README.md`) and push to `main`, or run the
workflows with `workflow_dispatch`.
