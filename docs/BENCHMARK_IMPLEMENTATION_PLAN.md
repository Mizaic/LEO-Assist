# Benchmark Implementation Plan

This plan covers the full benchmark feature set: upload wizard, rule creation, measure integration, chart recommendations, and APIs. It builds on the existing patient graph `Benchmark` nodes (per-episode indicators) and introduces **reference benchmarks** (NCDA, PHE, computed) stored in the Knowledge Graph.

---

## Current State

| Component | Status |
|----------|--------|
| Patient graph `Benchmark` nodes | 12k+ nodes (episode_id, metric_id, scope_type, scope_id, value) |
| NCDA JSON | `external_content/ncda_2018_benchmarks.json` – nested structure |
| Measure evaluation | Returns MeasureReport with `query-result` extension only |
| Measure creator | QueryBuilder for aggregation; no benchmark association |
| Report editor | ReportEditor from visual-report-builder; MeasureElement supports BenchmarkPoint |
| Benchmark comparison | VRB has `_get_benchmarks_for_measure`; Primary-care-audit does not |

---

## Target Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Benchmark Sources                                     │
├──────────────────────────────────┬──────────────────────────────────────────┤
│  External (NCDA, PHE)            │  Internal (derived from patient graph)    │
│  → Upload wizard + mapping       │  → Benchmark rule UX (no-code)             │
│  → POST /api/benchmarks/upload   │  → POST /api/benchmarks/rules/{id}/run    │
└──────────────────────────────────┴──────────────────────────────────────────┘
                                         │
                                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Canonical Benchmark Store (Knowledge Graph)                                  │
│  BenchmarkSet (audit_id, name, source, effective_from, effective_to)          │
│  BenchmarkValue (audit_id, metric_id, scope_type, scope_id, value, unit) or     │
│  BenchmarkSet -[:HAS_VALUE]-> BenchmarkValue                                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Measure creation: "Compare with benchmark" step                              │
│  → Pick benchmark set (NCDA 2018, PHE 2023, Our practice avg)                │
│  → Map measure output to metric_id                                            │
└─────────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Measure evaluation: fetch benchmarks + merge into MeasureReport extension    │
│  Report rendering: chart recommendations + axis mapping                      │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Canonical Schema & Backend APIs

### 1.1 Schema Design

**BenchmarkSet** (new node type in Knowledge Graph):

| Property | Type | Description |
|----------|------|-------------|
| id | string | Unique ID (e.g. `ncda-2018`, `phe-2023`, `computed-{rule_id}`) |
| name | string | Display name |
| source | string | `uploaded` \| `computed` |
| audit_year | int? | Optional year (NCDA 2018) |
| effective_from | date? | Optional validity start |
| effective_to | date? | Optional validity end |
| created_at | datetime | |
| updated_at | datetime | |
| metadata | json | Source-specific (e.g. report_version, data_cutoff) |

**BenchmarkValue** (or extend existing Benchmark for reference data):

| Property | Type | Description |
|----------|------|-------------|
| id | string | Unique (e.g. `{audit_id}_{metric_id}_{scope_id}`) |
| audit_id | string | FK to BenchmarkSet |
| metric_id | string | e.g. `demographics.sex.male`, `consultations.fewer_than_3` |
| scope_type | string | `practice` \| `cancer_alliance` \| `national` |
| scope_id | string | Entity ID (e.g. `woodbrook`, `east_midlands`, `england`) |
| value | double | Numeric value |
| unit | string | `pct`, `days`, `count`, `years` |
| label | string | Display label |
| sub_metric | string? | For breakdowns (e.g. `male`, `female`) |

**BenchmarkRule** (for computed benchmarks):

| Property | Type | Description |
|----------|------|-------------|
| id | string | Unique ID |
| name | string | Display name |
| query_definition | json | Same shape as QueryBuilder output |
| scope | string | `practice` \| `alliance` \| `all` |
| output_metric_id | string | Canonical metric ID for output |
| created_at | datetime | |
| updated_at | datetime | |
| last_run_at | datetime? | |
| last_run_status | string? | |

### 1.2 Benchmark CRUD API

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/benchmarks/sets` | List benchmark sets (filter by source, year) |
| GET | `/api/benchmarks/sets/{id}` | Get set + metadata |
| GET | `/api/benchmarks/sets/{id}/values` | Get values (filter by metric_id, scope_type) |
| GET | `/api/benchmarks/sets/{id}/values/{metric_id}` | Get comparison for one metric (practice/alliance/national) |
| DELETE | `/api/benchmarks/sets/{id}` | Delete set and values |

### 1.3 Benchmark Rule CRUD API

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/benchmarks/rules` | List rules |
| POST | `/api/benchmarks/rules` | Create rule |
| GET | `/api/benchmarks/rules/{id}` | Get rule |
| PUT | `/api/benchmarks/rules/{id}` | Update rule |
| DELETE | `/api/benchmarks/rules/{id}` | Delete rule |
| POST | `/api/benchmarks/rules/{id}/run` | **Run benchmark** (async or sync) |
| GET | `/api/benchmarks/rules/{id}/run/{job_id}` | Job status (if async) |

### 1.4 Run Benchmark API (for Azure Functions)

- `POST /api/benchmarks/rules/{id}/run`
  - Query params: `?scope=practice|alliance|all` `&org_id=...` (optional)
  - Auth: API key or service principal for Azure Functions
  - Response: `202 Accepted` with `job_id` or `200 OK` with result summary
  - Implementation: Execute Cypher (reuse QueryBuilder → Cypher generator), write results to BenchmarkSet/BenchmarkValue

---

## Phase 2: Benchmark Upload Wizard

### 2.1 Wizard Steps

| Step | Component | Description |
|------|-----------|--------------|
| 1 | UploadStep | Paste JSON, upload file, or provide URL |
| 2 | InspectStep | Show structure (keys, nesting, sample values); infer schema |
| 3 | MapStep | Map source paths → target schema (audit_id, metric_id, scope_type, scope_id, value, unit, label) |
| 4 | PreviewStep | Run mapping on sample rows; show transformed output |
| 5 | SaveStep | Name set, save; optionally save mapping as template |

### 2.2 Mapping Model

- **Path-based**: JSONPath or dot notation (e.g. `entities.practice.benchmarks.demographics.sex.male`)
- **Scope detection**: User marks which part = practice, alliance, national
- **Entity extraction**: Map `entities[].id` to scope_id, `entities[].type` to scope_type
- **Metric extraction**: Flatten nested metrics (e.g. `demographics.sex` → `demographics.sex.male`, `demographics.sex.female`)

### 2.3 Mapping Templates

- Save templates (e.g. "NCDA format", "PHE format") for reuse
- Store in `BenchmarkMappingTemplate` or config file

### 2.4 Implementation Notes

- **NCDA structure**: `audit`, `entities`, `benchmarks` (nested by category → metric → values by entity)
- **Flattening**: Walk `benchmarks`; for each leaf value, create (audit_id, metric_id, scope_id, value, unit)
- **Backend**: `POST /api/benchmarks/upload` with `{ rawJson, mappingTemplate }` or `{ rawJson, mapping }`

---

## Phase 3: Benchmark Rule Creation UX

### 3.1 Scope

- Reuse **QueryBuilder** (node label, filters, groupBy, scope)
- Add: **Output destination** = "Save as benchmark rule"
- Add: **Scope** = practice / alliance / all (where to run aggregation)
- Add: **Output metric ID** = user-defined or auto-generated

### 3.2 Flow

1. User selects "Create benchmark rule" (or from Measure tab: "Create from aggregation")
2. QueryBuilder steps (same as measure): template, node, filters, groupBy
3. **Scope step**: Run for this practice / this alliance / all data
4. **Output step**: Name metric, set metric_id
5. Save → BenchmarkRule created

### 3.3 Execution

- Run API invokes Cypher generator (same as measure `$generate`)
- Executes against Patient Graph
- Writes results to BenchmarkSet (source=computed) + BenchmarkValue

---

## Phase 4: Measure Creator Integration

### 4.1 Add Benchmark to Measure

- **Measure model**: Add `benchmarkConfig` (or FHIR extension):
  - `benchmarkSetId`: string
  - `metricId`: string (map measure output to benchmark metric)
  - `scopeAlignment`: optional (practice vs practice, etc.)

- **MeasureEditor**: New step or section "Compare with benchmark"
  - Benchmark set picker (dropdown of BenchmarkSet)
  - Metric picker (from set's metrics) or auto-map by name
  - Optional: scope alignment

### 4.2 Evaluate-Measure Integration

- In `evaluate_measure` (or `$evaluate-measure` handler):
  1. Fetch measure's benchmarkConfig
  2. If present: fetch benchmark values for metric_id + scope (from org context)
  3. Add extension to MeasureReport: `benchmark-comparison` (valueString = JSON of BenchmarkPoint[])

### 4.3 BenchmarkPoint Shape (from report)

```ts
interface BenchmarkPoint {
  metric_id: string;
  label: string;
  scope_type: string;
  scope_name: string;
  value: number | null;
  unit: string | null;
  source?: string | null;
}
```

---

## Phase 5: Chart Recommendations & Axis Mapping

### 5.1 Chart Recommendation

- **Input**: Measure report shape (rows, series, single value) + benchmark presence
- **Output**: Suggested chart types (bar, gauge, line, table, comparison bars)
- **Logic**:
  - Single value + benchmark → gauge or comparison bar
  - Rows (grouped) + benchmark → bar chart with benchmark line
  - Series (time) + benchmark → line chart with benchmark line

### 5.2 Axis Mapping

- **X-axis**: Category (from groupBy or default)
- **Y-axis**: Value (measure result)
- **Benchmark**: Second series or horizontal line

### 5.3 Implementation

- **ReportEditor**: When adding measure element, suggest chart type based on data shape
- **Element config**: Add `chartRecommendation` and `axisMapping` to element schema
- **MeasureElement**: Already supports `BenchmarkPoint`; ensure chart recommendations flow through

---

## Phase 6: Report Rendering & Benchmark Display

### 6.1 Existing Support

- MeasureElement (VRB): `BenchmarkPoint`, `ComparisonBarsElement`, `benchmarksToMetrics`
- useMeasureData: fetches benchmark-comparison extension

### 6.2 Gaps

- Ensure FHIR API returns benchmark-comparison when measure has benchmarkConfig
- Ensure measure-to-benchmark mapping exists in measure_service

---

## Phase 7: Ops & Auth

### 7.1 Run API Auth

- API key for Azure Functions: `X-API-Key` header
- Or: Azure AD client credentials for service-to-service

### 7.2 Permissions

- Upload benchmarks: admin or org admin
- Create rules: org admin
- Run rules: API key (Azure Functions) or org admin

### 7.3 Azure Functions

- Timer trigger: `0 0 1 * *` (monthly) → call `POST /api/benchmarks/rules/{id}/run` for each rule
- Or: HTTP trigger for manual invocation

---

## Implementation Order

| Phase | Priority | Dependencies |
|-------|----------|--------------|
| 1.1 Schema | P0 | None |
| 1.2 Benchmark CRUD API | P0 | 1.1 |
| 1.3 Benchmark Rule CRUD | P0 | 1.1 |
| 1.4 Run API | P0 | 1.3 |
| 2 Upload wizard | P1 | 1.2 |
| 3 Rule creation UX | P1 | 1.3, QueryBuilder |
| 4 Measure integration | P1 | 1.2, 4.2 |
| 4.2 Evaluate-measure benchmark fetch | P1 | 1.2 |
| 5 Chart recommendations | P2 | 4 |
| 6 Report rendering | P2 | 4.2 |
| 7 Ops & Auth | P2 | 1.4 |

---

## File / Component Touchpoints

| Area | Files |
|------|-------|
| Schema | `patient_graph_schema.json`, Neo4j migrations |
| Benchmark API | `services/api` or `services/fhir_api` – new routes |
| Upload wizard | `services/ui/src/components/benchmarks/` (new) |
| Rule creation | `services/ui/src/components/benchmarks/BenchmarkRuleEditor.tsx` (new), reuse QueryBuilder |
| Measure editor | `services/ui/src/components/measures/MeasureEditor.tsx` |
| Measure API | `services/ui/src/lib/api/measures.ts` |
| Evaluate measure | `services/fhir_api/app/services/measure_service.py` |
| Report editor | `services/ui/src/components/editor/` (from VRB) |
| measureData | `services/ui/src/lib/measureData.ts` (BenchmarkPoint, extractBenchmarkComparison) |

---

## Migration / Initial Load

- **Script**: One-off load of `ncda_2018_benchmarks.json` into BenchmarkSet + BenchmarkValue
- **Location**: `scripts/seed_ncda_benchmarks.py` or similar
- **Use**: Run after schema deployment; can be replaced by upload wizard once stable

---

## Summary Checklist

- [ ] Canonical schema (BenchmarkSet, BenchmarkValue, BenchmarkRule)
- [ ] Benchmark CRUD API
- [ ] Benchmark rule CRUD + Run API
- [ ] Upload wizard with mapping
- [ ] Benchmark rule creation UX (reuse QueryBuilder)
- [ ] Measure creator: add benchmark step
- [ ] Evaluate-measure: fetch benchmark, add extension
- [ ] Chart recommendations & axis mapping
- [ ] Report rendering (verify benchmark display)
- [ ] Run API auth for Azure Functions
- [ ] Initial NCDA seed script
