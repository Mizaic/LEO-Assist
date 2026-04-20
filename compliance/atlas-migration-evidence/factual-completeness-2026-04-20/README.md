# Atlas Design-Control Factual Completeness Audit -- 2026-04-20

**Product:** `PROD-LEO-CORE-AI-20260415-6AE8A23B`
**Standards basis:** IEC 62304 (software lifecycle), ISO 13485 (design controls).
**Source of truth:** Atlas MCP server (`user-atlas-design-controls`).
**Audit cache:** `/tmp/atlas-test-runs/audit/` (matrix, ACs, change requests, CAPAs, sample fetches).
**Deliverables:**
- `findings.csv` -- one row per (dcId, finding code).
- `summary.json` -- aggregated stats by code, severity, dcType.
- This README -- narrative report and remediation plan.

---

## 1. Scope

Audit the factual completeness of every active User Need (UN), Design
Input (DI), and Design Output (DO) in Atlas, plus the related Risks,
Verification Tests (VT), and Validation Tests (VAL) that anchor the
traceability chain.

| Type | Active in Atlas | Retired (Obsolete/Inactive) |
| --- | --- | --- |
| User Need        | 103 | 2 |
| Design Input     | 342 | 2 |
| Design Output    | 253 | 0 |
| Risk             | 193 | 1 |
| Verification Test| 355 | 0 |
| Validation Test  |  21 | 0 |
| **Total**        |**1,267**|**5**|

---

## 2. Method

### 2.1 Bulk data collected

| Source | Records | Notes |
| --- | --- | --- |
| `get_traceability_matrix`     | 1 matrix, 1,272 nodes, 3,041 links | Full graph of UN/DI/DO/Risk/VT/VAL with summary fields and edges. |
| `list_acceptance_criteria`    | 500 AC records | Atlas hard cap is 500. Used to confirm AC<->VT linkage rate (zero across the sample). |
| `list_change_requests`        | 4 records | None blocking. |
| `list_capa`                   | 0 records | No CAPAs raised yet against this product. |
| `list_design_review_findings` | parse failure | Tool errored on this product. Tracked as gap; non-blocking. |

### 2.2 Spot-checks

Direct `get_design_control` calls for individual nodes are unstable
(QMS Graph API timeouts on ~70% of attempts). To establish whether the
matrix-level signals reflect real content gaps, three records were
fetched in full via the IDE MCP wrapper:

- `UN-66396DEA` (Cohort builder) -- has rationale, persona, intended_users,
  6 acceptance_criteria, safety_class B. **Content is rich.** Yet the matrix
  shows it as `nextAction="Complete details and acceptance criteria."` --
  the matrix's nextAction generator is stale.
- `DI-FE3FFE50` (Cohort builder requirement) -- has rationale,
  acceptance_criteria, safety_class B, input_type=functional. **Rich.**
- `DO-21BFEF36` (CodingDecision Audit Trail) -- has 6 acceptance_criteria,
  description with implementation file path, output_type=software,
  software_item set. **Rich.**
- `VT-AF6C96D0` -- has only `title`, `test_type`, `safety_class`. **No
  protocol_steps, no acceptance_criteria, no description distinct from
  the title.** Confirms VT-class findings are real.

This means the audit must distinguish two kinds of finding:

- **Content gaps** -- a required ISO 62304 / ISO 13485 field is genuinely
  empty or missing. Treated as `BLOCKER` or `MAJOR`.
- **Lifecycle gaps** -- the node exists with rich content but is still in
  Draft status with the auto-generated nextAction prompt and has not
  been promoted to Reviewed/Approved. Treated as `LIFECYCLE`.

### 2.3 Finding codes

| Code | Severity | Meaning |
| --- | --- | --- |
| `DESC_EMPTY`         | BLOCKER | Description field is empty. |
| `DESC_EQUALS_TITLE`  | MAJOR   | Description duplicates title (stub). |
| `DESC_TOO_SHORT`     | MAJOR   | Description shorter than 30 chars. |
| `STATUS_DRAFT_STUB`  | LIFECYCLE | Draft + boilerplate nextAction. Indicates lifecycle promotion lag, not content gap. |
| `REVIEW_CANDIDATE`   | MAJOR   | Atlas itself flagged `isReviewCandidate=true`. |
| `UN_AC_NONE`         | BLOCKER | UN has zero acceptance criteria. |
| `UN_AC_UNCOVERED`    | MAJOR   | UN ACs are 0% covered by VT/VAL. |
| `UN_NO_DI`           | BLOCKER | UN has no Design Inputs. |
| `UN_NO_VT`           | MAJOR   | UN has no Verification Tests in subtree. |
| `DI_AC_NONE`         | BLOCKER | DI has zero acceptance criteria. |
| `DI_AC_UNCOVERED`    | MAJOR   | DI ACs are 0% covered by VT/VAL. |
| `DI_NO_DO`           | BLOCKER | DI has no Design Output (`IMPLEMENTS`). |
| `DI_NO_VT`           | BLOCKER | DI has no Verification Test (`VERIFIES`). |
| `DI_NO_RISK`         | MAJOR   | DI has no `MITIGATES` from any Risk. |
| `DO_NO_VT`           | BLOCKER | DO has no Verification Test (`TESTS`). |
| `VT_NOT_PASSED`      | MAJOR   | VT executionStatus is not `passed`. |
| `VAL_NOT_PASSED`     | MAJOR   | VAL executionStatus is not `passed`. |
| `RISK_UNANALYSED`    | MAJOR   | Risk nextAction = `Perform risk analysis and scoring.` |

---

## 3. Headline numbers

```
Total active nodes audited: 1,267
Findings:                   2,418  across 1,264 unique dcIds

By severity:
  BLOCKER    417   (must fix before any audit submission)
  MAJOR      949   (must fix before next design review)
  LIFECYCLE 1052   (formal review/approval workflow gap)

By dcType:
  user-need          213
  design-input       738
  design-output      292
  risk               193
  verification-test  940
  validation-test     42
```

Atlas's own coverage view (which is consistent with this audit):

```
User Needs:            101 / 105 covered  (96%)
Design Inputs:         344 / 344 with DO  (100%)
Design Outputs:        253 / 253 with VT  (100% structural; 36 DO -> 0 VT pairs found below)
Verification Tests:    121 / 355 passed   (34%)
Validation Tests:        0 /  21 passed   (0%)
Risks:                 194 / 194 mitigated (100%)
```

Note the apparent contradiction: Atlas reports `DO 100% with VT` because
the structural `TESTS` edge presence is checked across the product, but
the per-DO traversal in this audit finds 36 DOs that have **no
incoming TESTS edge from any VT**. The Atlas roll-up appears to count
the existence of any DO-touching VT in the product as coverage. The
per-node check is the reliable signal.

---

## 4. Top finding codes

| Code | Severity | Count | Headline |
| --- | --- | --- | --- |
| `STATUS_DRAFT_STUB` | LIFECYCLE | 1,052 | 83% of nodes still in initial Draft state. Most have rich content; the lifecycle has not been promoted to Reviewed/Approved. ISO 13485 design-review obligation. |
| `DESC_EMPTY` | BLOCKER | 376 | 352 of 355 VTs and all 21 VALs have an empty description; 3 risks empty. VT/VAL test-design content is genuinely missing. |
| `DI_AC_UNCOVERED` | MAJOR | 342 | All 342 active DIs have 0% AC<->VT coverage. ACs exist, VTs exist, but they are not linked. Confirmed by `list_acceptance_criteria`: 500 of 500 sampled ACs have `vtCount=0`. |
| `VT_NOT_PASSED` | MAJOR | 234 | 234 of 355 VTs have no recorded passing run. (121 are passed.) |
| `RISK_UNANALYSED` | MAJOR | 183 | 183 of 194 risks still in `Identified` status with the `Perform risk analysis and scoring.` next action. |
| `UN_AC_UNCOVERED` | MAJOR | 102 | Same root cause as DI_AC_UNCOVERED -- ACs are not linked to passing VTs. |
| `DI_NO_RISK` | MAJOR | 53 | 53 DIs have no outgoing `MITIGATES`. Class B/C DIs MUST have at least one MITIGATES per the `atlas-vt-enforcement` rule. (Safety class on individual DIs not bulk-readable from matrix; the spot-fetched DIs all reported `safety_class=B`.) |
| `DO_NO_VT` | BLOCKER | 36 | 36 DOs have no incoming `TESTS` edge. Implementation exists, verification test does not. |
| `VAL_NOT_PASSED` | MAJOR | 21 | All 21 VALs unpassed and undescribed. Validation tier is uniformly stub. |
| `REVIEW_CANDIDATE` | MAJOR | 7 | Atlas itself flagged 7 risks as needing control review. |
| `UN_NO_DI` | BLOCKER | 4 | 4 UNs have no Design Inputs at all. |
| `UN_NO_VT` | MAJOR | 4 | Same 4 UNs have no Verification Tests in their subtree. |
| `DESC_EQUALS_TITLE` | MAJOR | 3 | 3 DOs duplicate the title in the description. |
| `DI_NO_VT` | BLOCKER | 1 | One DI lacks any verifying VT. |

---

## 5. Significant orphan / structural blockers

These are the BLOCKER / MAJOR cases an external auditor would write up
first.

### 5.1 User Needs without any Design Input (`UN_NO_DI`, BLOCKER)

| dcId | Title |
| --- | --- |
| `UN-653248E1` | Referral management administrators need the system to ingest incoming referrals from all channels |
| `UN-90507468` | GP practices subscribe to an ongoing audit volume that provides referral PPV |
| `UN-BD9E0F82` | System provides electronic safety-netting for patients with cancer-relevant symptoms |
| `UN-5885D9A5` | System imports patient records via FHIR R4 and exports audit results as FHIR resources |

Every UN MUST decompose into at least one DI per ISO 13485 7.3.3.

### 5.2 Design Inputs without any Verification Test (`DI_NO_VT`, BLOCKER)

| dcId | Title |
| --- | --- |
| `DI-B0A1E549` | FHIR PlanDefinition / ActivityDefinition pathway orchestration |

Every DI MUST be verifiable per IEC 62304 5.6.

### 5.3 Design Outputs without any Verification Test (`DO_NO_VT`, BLOCKER)

36 DOs total. Top of the list (full list in `findings.csv`):

```
DO-BC6C7DD5  Value Set and Concept Map Management (implementation)
DO-7EEBABB8  Per-Tenant Billing and Discount Management Implementation
DO-A6B89CC7  Global inclusive accessibility baseline (implementation)
DO-1536C1B7  Care Overview (Dashboard) inclusive redesign (implementation)
DO-2BA37B59  Operations workspace inclusive redesign (implementation)
DO-2DB8B203  NCDA Report Template Generation (implementation)
DO-E66A98C2  First-seen milestone for 2WW fast-track clinic attendances (implementation)
DO-BC098903  Diagnosis-aware open-episode completion (implementation)
DO-09AC56A0  Merge /admin/clinical into /admin/knowledge (implementation)
DO-A7C8A6BD  Practitioner role model (implementation)
... 26 more (see findings.csv WHERE code='DO_NO_VT')
```

Each DO MUST have a TESTS edge from at least one VT per IEC 62304 5.5.5.

### 5.4 Design Inputs without any MITIGATES to a Risk (`DI_NO_RISK`, MAJOR)

53 DIs total. The local pre-flight rule (`atlas-vt-enforcement.mdc`)
requires every Class B / Class C DI to MITIGATES at least one Risk. The
matrix view does not expose `safety_class` per DI, but the three DIs
sample-fetched in 2.2 were all `safety_class=B`. **Treat all 53 as
candidate breaches** until safety_class is verified per node.

Top of list (full list in `findings.csv`):

```
DI-21C63B6A  Single @leo/design-system workspace package
DI-61CB27B2  DM Sans typography via next/font
DI-8E82275B  NCDA Report Template Generation
DI-7EFE2326  ServiceDataRequirement registry: versioned per-service data completeness configuration
DI-9BF6087F  Conditional integration-fetch edge for missing data items
DI-90C08758  First-seen milestone for 2WW fast-track clinic attendances
DI-4710EF03  Text-based cancer-site classification from gold-mined surface forms
DI-5672762D  Diagnosis-aware open-episode completion
DI-A0D8090D  Milestone temporal integrity
DI-0338A282  Histology vocabulary expansion
... 43 more (see findings.csv WHERE code='DI_NO_RISK')
```

### 5.5 Risks Atlas itself flagged for review (`REVIEW_CANDIDATE`, MAJOR)

```
R-D0FC4793   Risk analysis complete; control review required.
R-24C3AAED   Risk analysis complete; control review required.
R-2183B9DC   Risk analysis complete; control review required.
R-259EBFD9   Risk analysis complete; control review required.
R-8C0CC94B   Risk analysis complete; control review required.
R-8B17BAFA   Risk analysis complete; control review required.
R-4E31D45A   Risk analysis complete; control review required.
```

### 5.6 Design Outputs whose description duplicates the title (`DESC_EQUALS_TITLE`, MAJOR)

```
DO-099877AE  ModelConfig Create and Delete API and UI
DO-C79DBA53  Security Gap Remediation Batch 1 -- Implementation Artefacts
DO-1D03A444  Security Gap Remediation Batch 2 -- Implementation Artefacts
```

---

## 6. Systemic findings

### 6.1 Verification-test descriptions are uniformly empty (BLOCKER class)

352 of 355 active VTs have no description distinct from their title and
no `protocol_steps` array. Spot-fetched `VT-AF6C96D0` confirms the
matrix signal is real -- the VT shell exists with title only.

**Impact:** without a documented test objective, scope, and steps, a VT
cannot pass an IEC 62304 5.6 review nor be re-executed by another tester.

### 6.2 Validation tier is uniformly stub (BLOCKER class)

All 21 VALs have empty descriptions and no recorded pass. ISO 13485
7.3.7 requires Design Validation evidence for the intended use, with
recorded results -- this tier is not yet defensible.

### 6.3 AC-to-VT linkage is universally absent (MAJOR class)

500 of 500 sampled ACs report `vtCount=0` and `valCount=0`.
Acceptance criteria are richly authored (UN/DI samples each carry 4-9
ACs) but no AC is structurally linked to a passing VT. This means the
"AC met / unmet" metric is currently untrustworthy across the product.

**Likely root cause:** AC nodes are not yet being created or linked when
VTs are recorded as passing. The AC->VT edge type is missing.

### 6.4 Risk analysis tier is back-logged (MAJOR class)

183 of 194 risks (94%) are still status=Identified and have not been
through the FMEA scoring step. This is a backlog from the
Phase 7 / Phase 10 risk migration. Atlas itself flagged 7 of those that
have completed analysis as needing control review (REVIEW_CANDIDATE).

### 6.5 Lifecycle promotion lag (LIFECYCLE class)

1,052 of 1,267 active nodes (83%) are still status=Draft with Atlas's
auto-generated nextAction prompt. Spot-checks show many of these have
factually rich content. Treat as a Design Review and approval workflow
gap, not a content gap. Per ISO 13485 7.3.4, design reviews must be
recorded against each lifecycle promotion.

---

## 7. Audit limitations

1. **Atlas QMS Graph API instability.** Bulk individual `get_design_control`
   calls fail ~70% of the time with an upstream timeout. The audit
   relies on the bulk traceability matrix (which always returns) plus a
   small number of spot-fetched records. Fields not in the matrix
   summary (`safety_class`, `rationale`, `acceptance_criteria` text,
   `source_reference`, `verification_method`, `protocol_steps`) cannot be
   audited at population scale until the API is stabilised or the
   matrix payload is enriched.
2. **`list_acceptance_criteria` capped at 500.** All 105 UNs and 79 of
   344 DIs are represented in the AC dataset. The remaining 265 DIs are
   under-sampled. The `vtCount=0` pattern is uniform within the 500
   shown, and per-row AC counts in the matrix (`acTotal`, `acCovered`)
   confirm 0% AC coverage extends to the population.
3. **`list_design_review_findings` returns an unparseable response** for
   this product. The audit therefore cannot enumerate prior design
   review findings.
4. **No safety_class checks at population scale.** Three sample DIs were
   `safety_class=B`. The 53 `DI_NO_RISK` cases are candidate breaches
   only until safety_class is verified per node.
5. **No `source_reference` file-existence checks.** This was originally
   in scope but the field is not exposed in the matrix and cannot be
   bulk-fetched. Recommend running a file-existence sweep once the
   per-node API is stable.

---

## 8. Recommended remediation order

1. Resolve the four `UN_NO_DI` cases (5.1). Each UN must decompose to
   at least one DI before next design review.
2. Resolve `DI-B0A1E549` -- create or link a VT (5.2).
3. Backfill the 36 `DO_NO_VT` cases (5.3). Each DO needs one or more VTs
   that test it.
4. Confirm `safety_class` for the 53 `DI_NO_RISK` DIs (5.4). For every
   Class B / Class C DI in that set, add at least one MITIGATES edge.
5. Action the 7 Atlas-flagged `REVIEW_CANDIDATE` risks (5.5).
6. Rewrite the three `DESC_EQUALS_TITLE` DO descriptions (5.6).
7. Author VT `description` and `protocol_steps` for the 352 stub VTs
   (6.1). Templates exist in `atlas-vt-enforcement.mdc`.
8. Author VAL `description` and `protocol_steps` for the 21 stub VALs
   and execute at least one validation run before the next clinical
   release (6.2).
9. Wire AC->VT linkage in the verification recording flow so future
   `record_verification_run` calls also link the relevant ACs (6.3).
   This is the highest-leverage fix because it unblocks the matrix
   `acCovered` and `vtCount` metrics for the entire product.
10. Schedule a risk-analysis sprint to clear the 183 `RISK_UNANALYSED`
    backlog (6.4).
11. Plan a lifecycle-promotion sweep so DI/DO/Risk/VT/VAL nodes that
    are content-complete are advanced from Draft to Reviewed/Approved,
    each with a recorded design review (6.5).

---

## 9. Reproducing this audit

```bash
# Bulk pulls (matrix + ACs + CRs + CAPAs)
.venv/bin/python /tmp/atlas-test-runs/audit/fetch_lists.py

# Findings + summary
.venv/bin/python /tmp/atlas-test-runs/audit/build_audit.py

# Spot-checks (uses MCP IDE wrapper internally; some calls may time out)
.venv/bin/python /tmp/atlas-test-runs/audit/sample_fetch.py
```

Outputs:

- `compliance/atlas-migration-evidence/factual-completeness-2026-04-20/findings.csv`
- `compliance/atlas-migration-evidence/factual-completeness-2026-04-20/summary.json`
- `compliance/atlas-migration-evidence/factual-completeness-2026-04-20/README.md` (this file)

Audit cache (machine-readable, not committed): `/tmp/atlas-test-runs/audit/`.
