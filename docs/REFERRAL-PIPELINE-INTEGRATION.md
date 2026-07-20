# LEO CDS -- Referral Pipeline Integration Guide

This guide is for developers at Mizaic-portfolio products that want to
submit referral documents to the LEO Clinical Decision Support pipeline
for automated extraction, coding, completeness checking, and SBAR
summary generation.

For retrieving the finished SBAR in the browser, see
`services/widget-sdk/README.md`.

---

## Contents

1. [How it works](#how-it-works)
2. [Prerequisites](#prerequisites)
3. [Submitting a job via the REST API](#submitting-a-job-via-the-rest-api)
4. [Submitting a job directly via Service Bus](#submitting-a-job-directly-via-service-bus)
5. [Message fields reference](#message-fields-reference)
6. [Monitoring progress](#monitoring-progress)
7. [Consuming the output](#consuming-the-output)
8. [Error handling](#error-handling)
9. [Environment variables](#environment-variables)
10. [End-to-end flow diagram](#end-to-end-flow-diagram)
11. [Atlas trace](#atlas-trace)

---

## How it works

A single trigger message starts a nine-step durable workflow that runs
in the LEO pipeline worker:

```
trigger: "referral-received"
          |
          v
 1. extraction             -- NLP entity extraction
 2. post_processing        -- assertion, scope, and value linking
 3. relation_linking       -- entity-relation graph construction
 4. extraction_check       -- LLM accuracy pass
 5. terminology            -- SNOMED CT resolution
 6. clinical_facts_persist -- write DOCUMENTS and CodingDecision nodes
 7. compliance             -- NICE guideline rule evaluation
 8. completeness           -- referral completeness and quality report
 9. sbar                   -- SBAR summary generation
          |
          v
 completion: "referral_assessment_completed" -> referral-assessments-output
```

Each step publishes the next step's message automatically. Your system
only needs to send the initial trigger and then poll or listen for the
completion event.

---

## Prerequisites

Before your first submission:

1. **Service Bus access** -- your backend needs a connection string (or
   managed identity) with `Send` rights on the `pipeline-jobs` queue and
   (optionally) `Listen` rights on the `referral-assessments-output` queue.
   Request these from the LEO ops team.

2. **Patient + referral document graph** -- the production contract is
   document-chunk handoff, not Encounter text. Before you submit a job the
   patient graph must already contain:

   ```text
   (:Patient)<-[:FOR_PATIENT]-(:ReferralRequest)
        -[:HAS_DOCUMENT]->(:DocumentReference)-[:HAS_CHUNK]->(:Chunk)
   ```

   The trigger message must include `referral_id`, `document_reference_id`,
   `chunk_ids`, and `text_segmentation_mode: "document_chunks"`.
   `encounter_id` is a correlation id only; extraction reads `:Chunk.text`.
   AI summarisation scenario runs materialise this shape via
   `libs/referral_simulator` from scenario markdown.

3. **Host onboarding** -- if you are also embedding the SBAR widget, your
   host product must complete the governance onboarding described in
   `services/widget-sdk/README.md` (Slice 6) before widget tokens are
   issued.

4. **Guideline and completeness identifiers** -- you need to know which
   NICE guideline to evaluate against (e.g. `NG12`) and which completeness
   domain and subdomain apply to the referral type (e.g.
   `completeness_domain: "cancer_referrals"`,
   `completeness_subdomain: "lower_gi"`). Ask the LEO clinical team for the
   correct values for your pathway.

---

## Submitting a job via the REST API

This is the recommended path for most host products. It avoids the need
for a direct Service Bus dependency and goes through the standard LEO
auth layer.

### Endpoint

```
POST /api/sbar/scenario-runs
Authorization: Bearer <admin-JWT>
Content-Type: application/json
```

This endpoint is admin-only. Use your platform service account JWT.

### Request body

```json
{
  "case_ids": ["case-001", "case-002"],
  "guideline_id": "NG12",
  "completeness_domain": "cancer_referrals",
  "completeness_subdomain": "lower_gi",
  "plan_definition_id": "pd-referral-assessment"
}
```

`case_ids` maps to pre-loaded extraction scenario records in the LEO
knowledge graph. If you are submitting live referrals rather than
scenarios, use the direct Service Bus path below.

### Response

```json
{
  "run_id": "a1b2c3d4-...",
  "status": "queued",
  "child_runs": {
    "case-001": "a1b2c3d4-...:case-001",
    "case-002": "a1b2c3d4-...:case-002"
  }
}
```

Each `child_runs` entry is the `run_id` to use when polling for
progress (see [Monitoring progress](#monitoring-progress)).

---

## Submitting a job directly via Service Bus

Use this path when you are sending live referral data that is not
pre-loaded as an extraction scenario.

### Queue

`pipeline-jobs` (value of env var `PIPELINE_QUEUE_NAME` on the pipeline
worker, default `pipeline-jobs`).

### Trigger message body

```json
{
  "event_type": "referral-received",
  "run_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "plan_definition_id": "pd-referral-assessment",
  "workflow_id": "pd-referral-assessment",
  "patient_id": "patient-9990000001",
  "encounter_id": "000049831707:referral-assessment",
  "referral_id": "000049831707",
  "document_reference_id": "000049831707:leo-referral-bundle",
  "chunk_ids": ["chunk-id-1", "chunk-id-2"],
  "text_segmentation_mode": "document_chunks",
  "guideline_id": "NG12",
  "completeness_domain": "cancer_referrals",
  "completeness_subdomain": "lower_gi",
  "source_node_type": "ReferralRequest",
  "source_node_id": "000049831707",
  "tenant_id": "your-org-id",
  "requested_by": "clinician-user-id",
  "context": {
    "source": "hccp_referral_prep",
    "referral_id": "000049831707",
    "parent_run_id": null
  }
}
```

Set the Service Bus message `Subject` property to `"referral-received"`.

### Python example (Azure SDK)

```python
import json, uuid
from azure.servicebus import ServiceBusClient, ServiceBusMessage

CONNECTION_STR = "Endpoint=sb://..."
QUEUE_NAME = "pipeline-jobs"

run_id = str(uuid.uuid4())
body = {
    "event_type": "referral-received",
    "run_id": run_id,
    "plan_definition_id": "pd-referral-assessment",
    "workflow_id": "pd-referral-assessment",
    "patient_id": "patient-9990000001",
    "encounter_id": "000049831707:referral-assessment",
    "referral_id": "000049831707",
    "document_reference_id": "000049831707:leo-referral-bundle",
    "chunk_ids": ["chunk-id-1", "chunk-id-2"],
    "text_segmentation_mode": "document_chunks",
    "guideline_id": "NG12",
    "completeness_domain": "cancer_referrals",
    "completeness_subdomain": "lower_gi",
    "source_node_type": "ReferralRequest",
    "source_node_id": "000049831707",
    "tenant_id": "your-org-id",
    "requested_by": "user@example.com",
    "context": {
        "source": "hccp_referral_prep",
        "referral_id": "000049831707",
    },
}

with ServiceBusClient.from_connection_string(CONNECTION_STR) as client:
    with client.get_queue_sender(QUEUE_NAME) as sender:
        msg = ServiceBusMessage(
            json.dumps(body),
            subject="referral-received",
            correlation_id=run_id,
        )
        sender.send_messages(msg)

print(f"Submitted run_id={run_id}")
```

---

## Message fields reference

| Field | Required | Description |
|---|---|---|
| `event_type` | Yes | Must be `"referral-received"` |
| `run_id` | Yes | UUID you generate. Used to correlate all progress events and the final completion message |
| `plan_definition_id` | Yes | Must be `"pd-referral-assessment"` |
| `workflow_id` | No | Defaults to `plan_definition_id` if omitted |
| `patient_id` | Yes | ID of the `(:Patient)` node in the LEO patient graph |
| `encounter_id` | Yes | Correlation encounter id (e.g. `{ubrn}:referral-assessment`). Not the text source in document_chunks mode |
| `referral_id` | Yes | ID of the `(:ReferralRequest)` node |
| `document_reference_id` | Yes | ID of the `(:DocumentReference)` bundle (e.g. `{ubrn}:leo-referral-bundle`) |
| `chunk_ids` | Yes | Non-empty list of `(:Chunk)` ids that hold the referral text |
| `text_segmentation_mode` | Yes | Must be `"document_chunks"` for the production handoff |
| `guideline_id` | Yes | NICE guideline to evaluate (e.g. `"NG12"`) |
| `completeness_domain` | Yes | Completeness domain key (e.g. `"cancer_referrals"`) |
| `completeness_subdomain` | No | Completeness subdomain key (e.g. `"lower_gi"`) |
| `source_node_type` | Yes | `"ReferralRequest"` for production referrals |
| `source_node_id` | Yes | Same as `referral_id` |
| `tenant_id` | No | Your organisation ID for telemetry attribution |
| `requested_by` | No | User or service identity for audit trail |
| `context` | No | Arbitrary key-value pairs forwarded to every pipeline step (include `referral_id`) |

Shared builders: `libs/referral_simulator.message.build_referral_received_message`
and graph materialisation via `libs/referral_simulator.scaffold.scaffold_referral`.

---

## Monitoring progress

### Option A -- Server-Sent Events (real-time)

Connect to the SSE stream while the job is running:

```
GET /api/pipeline/progress/{run_id}
Authorization: Bearer <JWT>
Accept: text/event-stream
```

The connection stays open and emits events as each of the nine steps
completes. The stream closes automatically when a terminal event arrives.

| Event type | Meaning |
|---|---|
| `run_started` | Pipeline worker has picked up the job |
| `durable_step_started` | A pipeline step has begun |
| `durable_step_completed` | A pipeline step finished successfully |
| `durable_step_failed` | A pipeline step failed (check `message`) |
| `run_completed` | All steps finished -- SBAR is ready |
| `pipeline_error` | Unrecoverable failure |
| `heartbeat` | Keep-alive tick every 2 s (no state change) |

```javascript
const source = new EventSource(`/api/pipeline/progress/${runId}`, {
  headers: { Authorization: `Bearer ${token}` },
});
source.addEventListener("run_completed", (e) => {
  const data = JSON.parse(e.data);
  console.log("Done:", data.assessment_id);
  source.close();
});
source.addEventListener("pipeline_error", (e) => {
  console.error("Pipeline failed:", e.data);
  source.close();
});
```

### Option B -- HTTP polling (fallback)

If SSE is not suitable (e.g. serverless backend):

```
GET /api/pipeline/progress-status/{run_id}
Authorization: Bearer <JWT>
```

Returns:

```json
{
  "run_id": "a1b2c3d4-...",
  "state": "running",
  "event_type": "durable_step_completed",
  "status": null
}
```

`state` values: `queued`, `running`, `completed`, `failed`.

Poll every 5-10 seconds. Stop when `state` is `completed` or `failed`.

---

## Consuming the output

### Via the referral-assessments-output queue

When the final SBAR step completes, the pipeline worker publishes a
completion message to the `referral-assessments-output` Service Bus
queue:

```json
{
  "event_type": "referral_assessment_completed",
  "run_id": "a1b2c3d4-...",
  "patient_id": "patient-9990000001",
  "encounter_id": "enc-20260605-001",
  "assessment_id": "abcdef1234567890",
  "status": "completed"
}
```

Subscribe to this queue to know when a run is done without polling.

### Via the SBAR REST API

Once the run is complete, retrieve the generated SBAR:

```
GET /api/sbar/{assessment_id}
Authorization: Bearer <JWT>
```

### Via the SBAR widget

Mount the `<leo-sbar>` web component or hardened iframe, passing the
`assessment_id` as the `assessment-id` attribute. The widget handles
rendering, disclosure engagement tracking, and telemetry. See
`services/widget-sdk/README.md` for the full embed contract.

---

## Error handling

The durable workflow stores each step's result in the Neo4j patient
graph. If a step fails:

- The step emits a `durable_step_failed` event on the SSE stream.
- The run is marked `failed` in the pipeline stage store.
- The pipeline does **not** auto-retry. Re-submit the original
  `referral-received` message with the same `run_id` to resume from
  the beginning, or a new `run_id` to start fresh.
- The previous partial results for the `run_id` are overwritten on
  re-submission.

Common failure causes:

| Symptom | Likely cause |
|---|---|
| Step 1 (extraction) fails immediately | `encounter_id` does not exist in Neo4j, or `.text` is empty |
| Completeness step returns poor score | `completeness_domain` / `completeness_subdomain` mismatch |
| SBAR step times out | LLM provider is degraded -- check AWS Bedrock / Azure OpenAI health |
| `403 host_not_onboarded` from widget token endpoint | Host governance artefacts incomplete (see widget-sdk README, Slice 6) |

---

## Environment variables

These are set on the **pipeline worker** service (not your product):

| Variable | Default | Description |
|---|---|---|
| `PIPELINE_QUEUE_NAME` | `pipeline-jobs` | Azure Service Bus queue for inbound jobs |
| `PIPELINE_WORKER_PORT` | `8006` | HTTP port for the pipeline worker |
| `REDIS_URL` | `redis://localhost:6379` | Redis connection for progress pub/sub |

Your product needs:

| Variable | Description |
|---|---|
| `AZURE_SERVICEBUS_CONNECTION_STRING` | Connection string with `Send` on `pipeline-jobs` |
| `LEO_API_BASE_URL` | Base URL of the LEO Core API (for progress polling and SBAR retrieval) |
| `LEO_SERVICE_TOKEN` | Service account JWT for authenticated API calls |

---

## End-to-end flow diagram

```
Host product backend
        |
        | POST /api/sbar/scenario-runs  (REST, admin JWT)
        |  -- OR --
        | Send to pipeline-jobs queue  (Service Bus, "referral-received")
        |
        v
  pipeline-jobs (Azure Service Bus queue)
        |
        v
  LEO Pipeline Worker
        |
        +-- Step 1: extraction           (NLP)
        +-- Step 2: post_processing      (rules + ConText)
        +-- Step 3: relation_linking     (entity graph)
        +-- Step 4: extraction_check     (LLM verification)
        +-- Step 5: terminology          (SNOMED CT)
        +-- Step 6: persist              (Neo4j write)
        +-- Step 7: compliance           (NICE guideline check)
        +-- Step 8: completeness         (quality report)
        +-- Step 9: sbar                 (SBAR generation)
        |
        | Progress events -> Redis pub/sub -> GET /api/pipeline/progress/{run_id} (SSE)
        |
        v
  referral-assessments-output (Azure Service Bus queue)
        |
        | "referral_assessment_completed" {assessment_id}
        v
  Host product backend
        |
        | GET /api/sbar/{assessment_id}   (fetch SBAR data)
        |  -- OR --
        | Mount <leo-sbar assessment-id="..." widget-token="...">
        v
  Clinician sees SBAR in the review UI
```

---

## Atlas trace

| Artefact | dcId | Notes |
|---|---|---|
| User Need | UN-64F0E9C3 | Embeddable AI surface across the Mizaic portfolio |
| Design Input | DI-06CB6881 | Pipeline worker message bus consumer |
| Design Output | DO-C2F6CA16 | Pipeline worker -- dual-mode HTTP + message bus |
| Risk | R-4965BCD2 | AI handover summary used without clinician review |

Look up any artefact via:

```
get_design_control(dc_type="design_input", dc_id="DI-06CB6881")
```

Product: `PROD-LEO-CLINICAL-DECISION-SUPPORT-20260515-118182E4`
