# NCDA Audit Module -- Clinical Safety Audit & Test Prompt

> **Classification**: Class B (IEC 62304) -- safety-relevant clinical dashboard.
> Incorrect data may mislead clinical audit teams reviewing cancer diagnosis
> pathways, potentially delaying systemic improvements in cancer care.

---

## Objective

Systematically verify that every Cypher query, API endpoint, data
transformation, and UI chart in the `/care/audit` module returns
**clinically correct, NCDA-aligned data**.  This is a safety-critical audit.

---

## Scope -- files under test

### Backend (Python / FastAPI / Cypher)

| File | Role |
|------|------|
| `services/analytics_api/app/routers/audit.py` | Router + inline summary query |
| `services/analytics_api/app/routers/_audit_sections.py` | Core section queries (`_q_cancer_type`, `_q_cancer_stage`, `_q_demographics`, `_q_place`, `_q_consultations`, `_q_investigations`, `_q_referrals`, `_q_safety_netting`, `_q_avoidable_delays`) |
| `services/analytics_api/app/routers/_audit_intervals.py` | Interval queries (`_q_intervals`, `INFERRED_CANCER_DIAG_CASE`, `FP_DATE_EXPR`) |
| `services/analytics_api/app/routers/_audit_comorbidities.py` | Comorbidity queries (`_q_comorbidities`, `_ensure_registry`) |
| `services/analytics_api/app/routers/_audit_helpers.py` | Shared helpers (`_episode_base`, `_add_date_filters`, `_run_multi_scope`, `_fetch_benchmark_metrics`, `_resolve_alliance_id`) |

### Frontend (TypeScript / React / Recharts)

| File | Role |
|------|------|
| `services/ui/src/app/care/audit/page.tsx` | Re-export (thin shell) |
| `services/ui/src/app/audit/page.tsx` | Main audit page -- state, fetch orchestration, section rendering |
| `services/ui/src/lib/analyticsApi.ts` | API client functions + TypeScript interfaces |
| `services/ui/src/components/audit/AuditSummarySection.tsx` | Summary stats |
| `services/ui/src/components/audit/CancerTypeSection.tsx` | Cancer type distribution |
| `services/ui/src/components/audit/CancerStageSection.tsx` | Stage at diagnosis |
| `services/ui/src/components/audit/DemographicsSection.tsx` | Sex, age, ethnicity, comorbidities |
| `services/ui/src/components/audit/PlaceOfPresentationSection.tsx` | Where patients first presented |
| `services/ui/src/components/audit/ConsultationsSection.tsx` | GP consultations before referral |
| `services/ui/src/components/audit/InvestigationsSection.tsx` | Primary care investigations |
| `services/ui/src/components/audit/ReferralsSection.tsx` | Referral routes |
| `services/ui/src/components/audit/PrimaryCareIntervalSection.tsx` | PCI strip plot + stats |
| `services/ui/src/components/audit/DiagnosticIntervalSection.tsx` | DI strip plot + stats |
| `services/ui/src/components/audit/SafetyNettingSection.tsx` | Safety netting documentation |
| `services/ui/src/components/audit/AvoidableDelaysSection.tsx` | GP-assessed avoidable delays |
| `services/ui/src/components/audit/AuditSnapshotView.tsx` | Insight Snapshot tab |
| `services/ui/src/components/audit/BenchmarkLegend.tsx` | `resolveBenchmarkValue` + colours |
| `services/ui/src/components/audit/ComparisonBarChart.tsx` | Recharts bar chart component |
| `services/ui/src/components/audit/IntervalStripPlot.tsx` | Recharts scatter chart for intervals |
| `services/ui/src/components/audit/CancerTypeBenchmarkGrid.tsx` | Mini bar grid for cancer types |
| `services/ui/src/components/audit/SummaryStatsRow.tsx` | Reusable stats table |

---

## Test methodology

For every section below, perform **all four layers** of verification:

### Layer 1 -- Cypher correctness (run against real or seeded Neo4j)

1. Run the Cypher query in isolation against the Patient Graph.
2. Verify the WHERE clause logic matches the NCDA clinical definition.
3. Hand-check 5 randomly selected patient episodes for correctness.
4. Confirm `count(DISTINCT ...)` is used wherever episodes or patients
   could appear via multiple graph paths.
5. Confirm date filtering uses `ep.referral_date` (not encounter date).
6. Confirm excluded statuses: `merged`, `closed_phantom`, `closed_related`
   are filtered by `_episode_base`.
7. Record the raw row-count and totals returned.

### Layer 2 -- API response shape & values

1. Call the REST endpoint with a known `org_id` and date range.
2. Verify the response matches the `_make_response` envelope:
   `{ scopes: { practice, alliance_live, england_live }, benchmark }`.
3. Confirm `alliance_live` resolves to the correct CancerAlliance parent.
4. Confirm `england_live` uses no org filter (all episodes).
5. Confirm benchmark metrics come from the Knowledge Graph, not the
   Patient Graph.
6. Confirm percentages sum correctly (within rounding tolerance of 0.5%).
7. Confirm `null` is returned (not `0` or a stale value) when data is absent.

### Layer 3 -- Frontend data mapping

1. Read the section component and trace every field from the API response
   to the chart data structure.
2. Verify that practice data maps to the "Your Practice" bar/column.
3. Verify that `alliance_live` maps to the "Cancer Alliance (today)" column.
4. Verify that `england_live` maps to the "All Patients (today)" column.
5. Verify that benchmark data maps to the "NCDA 2018" column/bar only.
6. Confirm NO fallback from live columns to benchmark data -- if live data
   is null, the column should show nothing, not a 2018 benchmark value.
7. Verify `resolveBenchmarkValue` is only used for the national/2018 column.

### Layer 4 -- Visual chart review (browser)

1. Load the audit page in the browser with a known org and date range.
2. Verify each chart renders.
3. Spot-check 3 data points per chart against the raw API response.
4. Confirm the legend labels match the data source (live vs benchmark).
5. Confirm tooltips show the correct value and label.
6. Confirm empty/null states display gracefully (no "NaN%", no "0.0%"
   when data is absent).

---

## Section-by-section audit checklist

### 0. Summary (`/audit/summary`)

**NCDA purpose**: High-level overview metrics across all sections.

**Query location**: Inline in `audit.py` lines 82-103.

**Clinical checks**:
- [ ] `total_episodes` counts episodes excluding merged/phantom/related.
- [ ] `active_episodes` correctly identifies non-closed statuses.
- [ ] `confirmed_cancers` counts episodes with a diagnosis encounter
      (`milestone_type IN ['diagnosis', 'diagnosis_confirmed']`) or
      an inferred cancer outcome.
- [ ] `consultation_count` uses `count(DISTINCT enc2)` where `enc2` is
      matched via `IS_PART_OF`. **ISSUE TO VERIFY**: this counts ALL
      milestone-linked encounters, not pre-referral clinical consultations.
      Should this match the consultations section definition?
- [ ] `median_pci_days` = days from first presentation to referral.
      `FP_DATE_EXPR` falls back to referral date when no presenting
      complaint is recorded (avoiding artificial inflation).
- [ ] `median_di_days` = days from first presentation to diagnosis.
      `INFERRED_CANCER_DIAG_CASE` correctly cascades: coded diagnosis
      date -> inferred outcome date -> episode end date -> null.
- [ ] `safety_netting_pct` = episodes with `safety_netting_recorded = true`
      as percentage of total.
- [ ] Date filters (`date_from`, `date_to`) apply to `ep.referral_date`.

**Data integrity checks**:
- [ ] No division by zero when total_episodes = 0.
- [ ] Median calculation is correct for both odd and even counts.
- [ ] `_safe_days` returns None (not negative) for impossible dates.

---

### 1. Cancer type (`/audit/cancer-type`)

**NCDA purpose**: Distribution of cancer types across episodes.

**Query**: `_q_cancer_type` in `_audit_sections.py`.

**Clinical checks**:
- [ ] Excluded cancer types match NCDA exclusions: `unknown`,
      `non_site_specific`, `skin`, `upper_gi`, `head_and_neck`,
      `urological`, `gynaecological`, `haematological`, `childrens_tumour`.
      Verify this list against the current NCDA specification.
- [ ] Only `ep.status = 'completed'` episodes are included (confirmed
      cancer pathways only).
- [ ] `count(DISTINCT ep)` prevents overcounting.
- [ ] Percentages are of the included total (after exclusions), not of
      all episodes.
- [ ] Benchmark category = `"condition_type"` -- verify this matches the
      Knowledge Graph BenchmarkValue.category values.

**Chart checks**:
- [ ] Dumbbell chart correctly pairs practice vs national.
- [ ] Grid of mini bar charts shows per-cancer-type breakdown.
- [ ] Table rows show practice, alliance (today), england (today), 2018.
- [ ] No benchmark fallback in the live columns.

---

### 2. Cancer stage (`/audit/cancer-stage`)

**NCDA purpose**: Stage at diagnosis (early vs late).

**Query**: `_q_cancer_stage` in `_audit_sections.py`.

**Clinical checks**:
- [ ] Only episodes with at least one diagnosis encounter
      (`milestone_type IN ['diagnosis', 'diagnosis_confirmed']`) are included.
- [ ] `ep.cancer_stage` is used for stage grouping. Verify values match
      NCDA groups (I, II, III, IV, unknown).
- [ ] Coverage percentage = episodes with known stage / episodes with
      diagnosis. Unknown stages are counted in the denominator.
- [ ] `by_cancer_type` breakdown uses `count(DISTINCT ep)`.
- [ ] `by_system` (TNM, FIGO, etc.) and `by_source` are informational.
- [ ] Benchmark category = `"cancer_stage"`.

**Chart checks**:
- [ ] Stacked/grouped bar chart shows stage distribution.
- [ ] Coverage metric is displayed and correct.
- [ ] Per-cancer-type stage grid renders correctly.

---

### 3. Demographics (`/audit/demographics`)

**NCDA purpose**: Sex, age, and ethnicity of audited patients.

**Query**: `_q_demographics` in `_audit_sections.py`.

**Clinical checks**:
- [ ] Sex: `p.gender` distribution. `count(DISTINCT p)` for patients,
      not episodes (a patient may have multiple episodes).
- [ ] Age: calculated as
      `duration.inDays(date(p.birthDate), date(ep.referral_date)).days / 365`.
      This is integer division -- verify rounding is acceptable.
- [ ] Age bands: 0-24, 25-49, 50-64, 65-74, 75-84, 85+.
      Verify boundary handling (e.g. exactly 25 -> "25-49" not "0-24").
- [ ] Median age: calculated client-side from sorted age values.
      Verify the median formula handles even/odd correctly.
- [ ] Ethnicity: `p.ethnicity` distribution. Verify categories match
      NHS ethnic group codes or NCDA groupings.
- [ ] Benchmark category = `"demographics"`.

**Chart checks**:
- [ ] Sex bar chart shows male/female with correct percentages.
- [ ] Age histogram shows correct band widths.
- [ ] Ethnicity bar chart is sorted by frequency.
- [ ] Summary stats table shows correct values for all scopes.

---

### 4. Comorbidities (`/audit/comorbidities`)

**NCDA purpose**: Prevalence of common comorbid conditions.

**Query**: `_q_comorbidities` in `_audit_comorbidities.py`.

**Clinical checks**:
- [ ] Concept groups are loaded from the DomainRegistry
      (`cancer_audit/comorbidities` subdomain), not hardcoded.
- [ ] Each top-level concept is expanded via IS_A hierarchy (depth=3)
      to capture clinical variants.
- [ ] Both `HAS_DISEASE` relationships AND `DOCUMENTS` relationships
      (with `domain = 'comorbidities'`) are checked.
- [ ] Patient deduplication: `collect(DISTINCT d1.conceptId) +
      collect(DISTINCT d2.conceptId)` -- verify this correctly dedupes
      across the two paths.
- [ ] Denominator is `count(DISTINCT p)` (patients, not episodes).
- [ ] Percentage = patients with comorbidity / total patients in scope.
- [ ] `_COMORBIDITY_CODE_META` fallback labels and benchmark keys are
      clinically accurate.
- [ ] Benchmark category = `"comorbidities"`.

**Chart checks**:
- [ ] Bar chart shows all comorbidity groups sorted by prevalence.
- [ ] Practice, alliance (today), england (today), and 2018 benchmark
      bars all render when data is available.
- [ ] Alliance and England live data come from `scopes.alliance_live`
      and `scopes.england_live`, not from benchmark fallback.

---

### 5. Place of presentation (`/audit/place-of-presentation`)

**NCDA purpose**: Where patients first presented (GP surgery, A&E, etc.).

**Query**: `_q_place` in `_audit_sections.py`.

**Clinical checks**:
- [ ] Uses `ep.place_of_presentation`, defaulting to "Not recorded".
- [ ] `count(DISTINCT ep)` prevents overcounting.
- [ ] Categories should align with NCDA presentation places:
      GP Surgery, A&E, Outpatient, Inpatient, Screening, Other.
- [ ] Benchmark category = `"place_of_presentation"`.

**Chart checks**:
- [ ] Bar chart shows all presentation locations.
- [ ] "Not recorded" is displayed if present.
- [ ] Percentages sum to 100% (within rounding).

---

### 6. Consultations (`/audit/consultations`)

**NCDA purpose**: Number of GP consultations before referral.

**Query**: `_q_consultations` in `_audit_sections.py`.

**CRITICAL clinical checks**:
- [ ] **Direction**: encounters are counted BEFORE referral, not after.
      Window: `enc.date >= first_presentation_date` (or `referral_date -
      365 days`) AND `enc.date <= referral_date`.
- [ ] **Encounter filtering**: only `classification_content_type = 'clinical'`
      encounters are counted. Admin-only and document_transfer encounters
      are excluded via
      `coalesce(enc.classification_content_type, 'clinical') = 'clinical'`.
- [ ] **Traversal path**: uses `(p)-[:HAS_ENCOUNTER]->(enc:Encounter)`,
      NOT `IS_PART_OF`. This is correct because pre-referral GP
      consultations are not episode milestones.
- [ ] **Date null safety**: `enc.date IS NOT NULL AND ep.referral_date IS
      NOT NULL` are checked.
- [ ] NCDA split: "Fewer than 3" vs "3 or more" consultations.
- [ ] Median and IQR are calculated from per-episode consultation counts.
- [ ] Benchmark category = `"consultations"`.

**Validation test (5 patients)**:
For each of 5 randomly selected episodes:
1. Query all encounters for the patient in the pre-referral window.
2. Manually classify each as clinical / admin / document_transfer.
3. Count only the clinical ones.
4. Confirm the query returns the same count.

**Chart checks**:
- [ ] Summary shows "<3 consultations" and "Median consultations" rows.
- [ ] Values match the API response.

---

### 7. Investigations (`/audit/investigations`)

**NCDA purpose**: Primary care investigations ordered prior to referral.

**Query**: `_q_investigations` in `_audit_sections.py`.

**Clinical checks**:
- [ ] Uses `IS_PART_OF` (encounter linked to episode), not `HAS_ENCOUNTER`.
- [ ] `encounter_type` filter:
      `['investigation', 'blood_test', 'imaging', 'urinalysis',
       'biopsy', 'endoscopy', 'symptomatic_fit', 'other_investigation']`.
      Verify these types are complete against the episode builder's
      encounter type vocabulary.
- [ ] Casing: verify `With` vs `WITH` does not cause Cypher parse issues.
- [ ] Summary: "Has investigation" vs "No investigation" split.
- [ ] Types breakdown uses `count(DISTINCT ep.episode_id)`.
- [ ] Benchmark category = `"investigations"`.

**Chart checks**:
- [ ] Bar chart shows investigation type distribution.
- [ ] Has/no investigation percentage is displayed.

---

### 8. Referrals (`/audit/referrals`)

**NCDA purpose**: How patients were referred (TWW, Urgent, Emergency, etc.).

**Query**: `_q_referrals` in `_audit_sections.py`.

**Clinical checks**:
- [ ] Uses `ep.referral_route`, defaulting to "Not recorded".
- [ ] `count(DISTINCT ep)` prevents overcounting.
- [ ] Categories should include: TWW (Two Week Wait), Urgent, Routine,
      Emergency, Screening, Other, Not recorded.
- [ ] Benchmark category = `"referrals"`.

**Chart checks**:
- [ ] Bar chart shows referral routes sorted by frequency.
- [ ] Table shows practice, alliance (today), england (today), 2018.
- [ ] No benchmark fallback in live columns.

---

### 9. Primary care interval (`/audit/intervals`)

**NCDA purpose**: Time from first presentation to referral (PCI) and to
diagnosis (DI).

**Query**: `_q_intervals` in `_audit_intervals.py`.

**CRITICAL clinical checks**:
- [ ] **PCI** = `date(referral_date) - date(fp_date)` in days.
- [ ] **DI** = `date(effective_diag_date) - date(fp_date)` in days.
- [ ] **`FP_DATE_EXPR`**: uses `first_presentation_date` ONLY when
      `presenting_complaint` is non-empty. Falls back to `referral_date`
      otherwise. This prevents artificial PCI inflation when the
      presentation date was set by admin coding with no clinical complaint.
- [ ] **`INFERRED_CANCER_DIAG_CASE`**: cascades correctly:
      1. Coded diagnosis date (from IS_PART_OF milestone)
      2. Inferred cancer outcome date (`ep.inferred_outcome = 'cancer'`)
      3. Episode end date (`ep.status = 'completed'` and `ep.end_date`)
      4. null (no diagnosis available)
- [ ] **Negative intervals**: can PCI or DI be negative? (Referral before
      presentation -- should be filtered or flagged.)
- [ ] Aggregates use `percentileCont` for median and IQR.
- [ ] Patient-level data capped at 500 for rendering performance.
- [ ] Alliance/england scopes strip patient-level points (privacy).
- [ ] Benchmark fetches BOTH `"primary_care_interval"` AND
      `"diagnostic_interval"` categories and merges them.

**Chart checks**:
- [ ] Strip/dot plot renders individual PCI/DI data points.
- [ ] Median, Q1, Q3 reference lines are shown.
- [ ] Outliers (very long intervals) do not break the axis scale.
- [ ] Tooltip shows episode_id, cancer_type, and interval days.

---

### 10. Safety netting (`/audit/safety-netting`)

**NCDA purpose**: Was safety netting advice documented?

**Query**: `_q_safety_netting` in `_audit_sections.py`.

**Clinical checks**:
- [ ] Uses `ep.safety_netting_recorded = true` boolean check.
- [ ] Percentage = recorded / total_episodes.
- [ ] Does not require any encounter linkage (episode-level property).
- [ ] Benchmark category = `"safety_netting"`.

**Chart checks**:
- [ ] Shows "Safety netting recorded" percentage.
- [ ] No benchmark fallback in live columns.

---

### 11. Avoidable delays (`/audit/avoidable-delays`)

**NCDA purpose**: GP-assessed avoidable delay and phase breakdown.

**Query**: `_q_avoidable_delays` in `_audit_sections.py`.

**Clinical checks**:
- [ ] Uses `ep.avoidable_delay = true` boolean check.
- [ ] Phase breakdown uses `ep.avoidable_delay_phase` with values:
      `before_presentation`, `pres_to_referral`, `after_referral`.
- [ ] Phase percentages: denominator is episodes WITH delay (not all
      episodes). Verify this is clinically correct per NCDA.
- [ ] `delay_total` defaults to 1 to avoid division by zero -- but this
      means if there are 0 delays, the phase percentages will show 0%
      rather than null. **Verify this is acceptable**.
- [ ] Benchmark category = `"avoidable_delays"`.

**Chart checks**:
- [ ] Shows overall "GP-assessed avoidable delay" percentage.
- [ ] Phase breakdown bar chart shows three phases.
- [ ] No benchmark fallback in live columns.

---

## Cross-cutting checks (apply to ALL sections)

### A. Multi-scope logic (`_run_multi_scope`)

- [ ] Practice scope: uses `_episode_base` with org_id.
- [ ] Alliance scope: resolves `_resolve_alliance_id`, then re-runs the
      same query with the alliance org as scope.
- [ ] England scope: uses `_ENGLAND_BASE` (no org filter).
- [ ] Alliance/England queries swallow exceptions and return None (not
      crash the endpoint). Verify this is logged.
- [ ] Verify the alliance query uses `_ORG_PATIENT_MATCH` with
      `org = alliance_id` -- this means it matches GPs within the
      alliance, which is correct.

### B. Episode exclusion

- [ ] All queries exclude episodes with status:
      `merged`, `closed_phantom`, `closed_related`.
- [ ] Verify this is consistent: `_EPISODE_EXCLUDE` in `_audit_helpers.py`
      applies to all `_episode_base` outputs.

### C. Date filtering

- [ ] `_add_date_filters` appends `AND ep.referral_date >= $date_from`
      and `AND ep.referral_date <= $date_to`.
- [ ] Both date filters are optional -- omitting them returns all-time data.
- [ ] Date comparison uses `ep.referral_date` (date type in Neo4j),
      not string comparison. Verify date types are consistent.

### D. Benchmark integration

- [ ] `_fetch_benchmark_metrics` reads from the **Knowledge Graph**
      (separate from Patient Graph).
- [ ] Benchmark values are keyed by `(set_id, category, metric_id)`.
- [ ] Scope types: `national`, `cancer_alliance`, `gp_practice`.
- [ ] Practice benchmark: primary match on ODS code, fuzzy fallback on
      normalised name. Verify fuzzy match does not produce false positives.
- [ ] Alliance benchmark: matched by `alliance_id`.
- [ ] National benchmark: always `scope_type = 'national'`.
- [ ] **CRITICAL**: Benchmark data (2018) must NEVER appear in the
      "alliance (today)" or "all patients (today)" columns. It must
      only appear in the "NCDA 2018" column.

### E. Null safety

- [ ] Every percentage calculation guards against division by zero.
- [ ] `or 1` fallback denominators: verify these produce 0.0% rather than
      misleading small percentages.
- [ ] `None`/`null` is returned for absent data, not `0` or `0.0`.

### F. Patient privacy

- [ ] No patient identifiers (NHS number, name, DOB) are returned in
      API responses.
- [ ] `episode_id` is the only identifier in interval patient-level data.
- [ ] Alliance and England scope responses do not include patient-level
      data points.

---

## Known issues fixed in this session (verify regression)

These bugs were identified and fixed. Confirm each fix is in place and
working correctly:

1. **Consultations counted post-referral instead of pre-referral**.
   Verify `_PRE_REF` uses `enc.date <= ep.referral_date` (not `>=`).

2. **Consultations counted admin/document_transfer encounters**.
   Verify `_PRE_REF` includes
   `coalesce(enc.classification_content_type, 'clinical') = 'clinical'`.

3. **`_q_place` used `count(ep)` instead of `count(DISTINCT ep)`**.
   Verify DISTINCT is present.

4. **`_q_referrals` used `count(ep)` instead of `count(DISTINCT ep)`**.
   Verify DISTINCT is present.

5. **10+ sections fell back to 2018 Cancer Alliance benchmark when live
   England data was null**. Verify all `alliance:` fields in section
   components use `englandLive ? { value: ... } : null` (not a
   `bm?.[...]?.alliance` fallback).

6. **Demographics comorbidity chart ignored alliance/england live data**.
   Verify `DemographicsSection.tsx` maps `comorbidities?.scopes.alliance_live`
   and `england_live` to the chart's `similar` and `alliance` bars.

---

## Test data requirements

To run these tests you need:

1. **A seeded Neo4j Patient Graph** with at least:
   - 20+ episodes across 3+ GP practices
   - Episodes in multiple CancerAlliance regions
   - Mix of completed / in_progress / merged / closed statuses
   - Episodes with and without diagnosis encounters
   - Patients with classified encounters (admin_only, document_transfer,
     clinical)
   - Patients with comorbidity HAS_DISEASE relationships
   - Episodes with safety_netting_recorded = true and false
   - Episodes with avoidable_delay = true and phase values

2. **A seeded Neo4j Knowledge Graph** with:
   - At least one BenchmarkSet (e.g. `ncda_2018_benchmarks`)
   - BenchmarkValue nodes for all categories with national,
     cancer_alliance, and gp_practice scope types
   - NCDA comorbidity ValueSet nodes

3. **5 hand-verified patients** for ground truth comparison.
   For each patient, manually determine:
   - Cancer type and stage
   - Number of clinical consultations before referral
   - PCI and DI in days
   - Referral route
   - Place of presentation
   - Comorbidities
   - Safety netting status
   Compare these against query results.

---

## Execution order

1. Start with the **Summary** endpoint -- it touches most sections
   and gives a quick smell test.
2. Then the **Consultations** section -- highest-risk query (recently
   fixed, traverses Patient->Encounter, encounter type filtering).
3. Then **Intervals** -- second-highest complexity (date cascading,
   inferred diagnosis, FP_DATE_EXPR logic).
4. Then all remaining sections in order.
5. Finish with **cross-cutting checks** (multi-scope, benchmarks, nulls).
6. Run the **browser visual review** last, after all data checks pass.

---

## Reporting

For each section, record:

| Field | Value |
|-------|-------|
| Section name | |
| Query verified correct? | Yes / No / Issue found |
| API response shape correct? | Yes / No |
| Frontend mapping correct? | Yes / No |
| Chart renders correctly? | Yes / No |
| 5-patient spot check passed? | Yes / No / N/A |
| Issues found | (describe) |
| Severity | Critical / Major / Minor / Info |
| Fix applied? | Yes / Pending |
