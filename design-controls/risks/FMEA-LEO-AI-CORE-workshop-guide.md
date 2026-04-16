# FMEA Hazard Workshop - LEO Core AI
# ISO 14971 Failure Mode and Effects Analysis
# Status: DRAFT - For Workshop Review and Sign-off

## Purpose

This document is the pre-work for the LEO Core AI hazard identification workshop.
It maps all 73 User Needs (57 original + 16 newly identified from the codebase audit)
against their failure modes, existing risk records, and identified gaps.

The companion CSV (`FMEA-LEO-AI-CORE-workshop-draft.csv`) is the working dataset.
Import it into Excel for filtering and sorting during the workshop.

---

## How to Use

### Before the workshop
1. Review the CSV sorted by **RPN descending** - focus the first session on RPN >= 24.
2. Review the **GAP** rows - these are failure modes with no existing R-LEO-AI-XXX record.
   Each gap row carries a suggested new risk ID (R-LEO-AI-078 onwards, next available is 078).
3. For **EXISTING** rows, validate the referenced R-LEO-AI-XXX covers the failure mode described.
4. Flag any failure modes where the **Workshop_Status = EXISTING** but the risk record needs updating.

### During the workshop
- Work through each domain group (see below) in priority order.
- For each GAP: agree severity, probability, detectability, and identify mitigating controls.
- For each EXISTING: confirm the risk record is still accurate and complete.
- Record decisions in the CSV (add a "Decision" and "Owner" column).

### After the workshop
- Create R-LEO-AI-XXX YAML files for all confirmed new risks.
- Update existing R-LEO-AI-XXX YAMLs where controls need updating.
- Create risks in Atlas using `create_risk` and link via `HAS_RISK` (UN) and `MITIGATES` (DI).
- Update DC-TM-001 traceability matrix.

---

## Scoring Scales

### Severity (S) - ISO 14971
| Score | Label | Description |
|-------|-------|-------------|
| 1 | Negligible | No patient harm, no regulatory consequence |
| 2 | Minor | Temporary inconvenience, recoverable, no patient harm |
| 3 | Serious | Reversible patient harm or significant clinical/governance impact |
| 4 | Critical | Severe but reversible patient harm or major regulatory breach |
| 5 | Catastrophic | Death, permanent severe disability, or catastrophic data breach |

### Probability (P)
| Score | Label | Frequency |
|-------|-------|-----------|
| 1 | Remote | Less than 1 in 10,000 encounters |
| 2 | Unlikely | 1 in 1,000 to 10,000 encounters |
| 3 | Possible | 1 in 100 to 1,000 encounters |
| 4 | Likely | 1 in 10 to 100 encounters |
| 5 | Almost Certain | More than 1 in 10 encounters |

### Detectability (D) - probability of NOT detecting before harm
| Score | Label | Description |
|-------|-------|-------------|
| 1 | Almost Certain | Automatic detection - obviously visible or system-flagged |
| 2 | High | Likely detected in routine review or test runs |
| 3 | Moderate | May be detected by attentive reviewer or periodic audit |
| 4 | Low | Unlikely to be detected without targeted investigation |
| 5 | Remote | Almost impossible to detect without specific tooling |

### RPN = S x P x D
| RPN | Priority |
|-----|---------|
| > 50 | CRITICAL - block deployment |
| 25-50 | HIGH - must be mitigated before production |
| 10-24 | MEDIUM - mitigate within 3 months |
| < 10 | LOW - monitor; accept with rationale |

---

## Summary by Domain

### Clinical Safety (Class C) - Highest Priority
FMEA-001 to FMEA-021 | 21 failure modes | 8 GAPs

**Pre-assessed HIGH/CRITICAL (RPN >= 24):**
- FMEA-003: Absent coded as present (assertion inversion) - RPN 24 - EXISTING
- FMEA-004: Patient shortlisting false negative - RPN 27 - **GAP**
- FMEA-008: Episode quality check miss - RPN 27 - **GAP**
- FMEA-010: Encounter in wrong episode - RPN 27 - EXISTING
- FMEA-014: Critical result not flagged (safety net) - RPN 30 - EXISTING (confirm R-077 scope)
- FMEA-016: Alert flood / alarm fatigue - RPN 24 - **GAP**
- FMEA-017: Wrong reference range applied - RPN 24 - **GAP**
- FMEA-020: Automation bias rubber-stamping - RPN 36 - EXISTING

**Workshop questions:**
- Are the ConText double-negation risks (R-034, R-035) covered by VTs?
- Does R-074 (safety net) cover all result types including string results (see R-077)?
- Is the reference range change control gate architecturally enforced?

---

### Clinical Decision Support (Class B/C)
FMEA-022 to FMEA-034 | 13 failure modes | 13 GAPs (all new)

**Pre-assessed HIGH (RPN >= 24):**
- FMEA-022: Escalation threshold not surfaced - RPN 27 - **GAP**
- FMEA-023: Wrong threshold displayed - RPN 24 - **GAP**
- FMEA-026: Recovery markers not identified - RPN 24 - **GAP**
- FMEA-028: Wrong pathway stage in clinic list - RPN 27 - **GAP**
- FMEA-029: Wrong referral eligibility criteria - RPN 24 - **GAP**
- FMEA-032: SBAR misses safety netting - RPN 24 - **GAP**
- FMEA-034: Data completeness not surfaced - RPN 36 - **GAP**

**Workshop questions:**
- These UNs are relatively new to the codebase. Confirm clinical relevance of each failure mode.
- FMEA-034 (completeness not surfaced) is rated RPN 36 - should this be escalated to Class C?

---

### Model and NLP Pipeline (Class B)
FMEA-035 to FMEA-046 | 12 failure modes | 7 GAPs

**Pre-assessed HIGH (RPN >= 24):**
- FMEA-041: Encounter classified to wrong programme - RPN 27 - **GAP**
- FMEA-042: Encounter not classified at all - RPN 36 - **GAP** (detectability D=4)
- FMEA-043: Canary not halted on regression - RPN 24 - **GAP**

**Workshop questions:**
- FMEA-042 has D=4 (missed encounters are hard to detect without specific DQ tooling) -
  is this acceptable or does it need a monitoring control?
- Surface form risks (R-048, R-049) exist - do they need updating to cover the new
  CRUD management interface?

---

### Clinical Change Control and Governance (Class B)
FMEA-047 to FMEA-055 | 9 failure modes | 9 GAPs (all new)

**Pre-assessed HIGH (RPN >= 24):**
- FMEA-048: Wrong guideline implementation approved - RPN 24 - **GAP**
- FMEA-051: Impact assessment incomplete - RPN 27 - **GAP**

**Workshop questions:**
- These failure modes are all new (no existing R records).
- The deployment gate (FMEA-052) has low probability (P=1) but S=4 -
  workshop should decide if a formal risk record is warranted.
- FMEA-053 (missing rationale) is a regulatory compliance risk not a clinical safety risk -
  appropriate to document as a risk?

---

### Knowledge Base Management (Class B)
FMEA-056 to FMEA-068 | 13 failure modes | 11 GAPs

**Pre-assessed HIGH/MEDIUM:**
- FMEA-061: Guideline alert not received - RPN 24 (D=4) - **GAP**
- FMEA-064: NICE ingest fails silently - RPN 24 (D=4) - **GAP**
- FMEA-065: AI extracts incorrect rule - RPN 24 - **GAP**
- FMEA-066: Rule promoted without review (S=5) - RPN 10 - **GAP** - low RPN but catastrophic severity

**Workshop questions:**
- FMEA-066 has S=5 (catastrophic: AI-generated clinical logic in production with no review).
  RPN=10 is MEDIUM but the severity alone warrants explicit discussion.
  Recommend treating as HIGH regardless of RPN due to severity.
- FMEA-061 and FMEA-064 both have D=4 - the detection gap is a monitoring design issue.
  Do the alert mechanisms have enough redundancy?

---

### Platform and Operations (Class A/B)
FMEA-069 to FMEA-082 | 14 failure modes | 12 GAPs

**Pre-assessed HIGH (RPN >= 24):**
- FMEA-069: Episode validation miss - RPN 27 - **GAP**
- FMEA-071: Intelligence Console stale - RPN 27 - **GAP**
- FMEA-073: Pathway interval incorrect - RPN 24 - **GAP**
- FMEA-074: Coding quality regression alert missed - RPN 27 - EXISTING
- FMEA-076: Wrong population denominator in dashboard - RPN 27 - **GAP**
- FMEA-077: Failed encounters not surfaced (D=4) - RPN 36 - **GAP**
- FMEA-078: DQ rule not triggered - RPN 27 - **GAP**
- FMEA-079: Drift not detected (D=4) - RPN 36 - **GAP**
- FMEA-081: Incorrect cohort definition - RPN 27 - **GAP**

**Workshop questions:**
- FMEA-077 and FMEA-079 both have D=4 - these are the "silent failure" operational risks.
  The Mission Control dashboard (UN-BB817C74) and audit quality loops (UN-AE5D7812)
  are the controls for these - are they sufficient?

---

### Developer Platform and Integration (Class A)
FMEA-083 to FMEA-093 | 11 failure modes | 9 GAPs

**Pre-assessed MEDIUM:**
- FMEA-085: Breaking API change without notice - RPN 12
- FMEA-087: API spec out of date - RPN 18
- FMEA-091: Non-conformant FHIR resource - RPN 12

**Workshop questions:**
- These are Class A items - lower clinical risk but may attract regulatory scrutiny
  (SOUP record, API spec, FHIR conformance are all in scope for a downstream technical file).
- Confirm FMEA-088 (real data in sandbox) - probability is set to 1 (remote).
  Is this assumption valid given how sandbox is provisioned?

---

## New Risk IDs Required

Next available: R-LEO-AI-078

| Suggested ID | FMEA_ID | Title |
|---|---|---|
| R-LEO-AI-078 | FMEA-004 | Patient shortlisting false negative |
| R-LEO-AI-079 | FMEA-005 | Patient shortlisting false positive |
| R-LEO-AI-080 | FMEA-008 | Episode quality check miss |
| R-LEO-AI-081 | FMEA-011 | Episode not created (false negative) |
| R-LEO-AI-082 | FMEA-013 | Over-deidentification removes clinical content |
| R-LEO-AI-083 | FMEA-015 | Safety netting alert incorrectly suppressed |
| R-LEO-AI-084 | FMEA-016 | Safety netting alert flood / alarm fatigue |
| R-LEO-AI-085 | FMEA-017 | Wrong reference range applied |
| R-LEO-AI-086 | FMEA-018 | Reference range outdated |
| R-LEO-AI-087 | FMEA-021 | Provenance link missing from coded entity |
| R-LEO-AI-088 | FMEA-022 | Guideline escalation threshold not surfaced |
| R-LEO-AI-089 | FMEA-024 | Outdated guideline recommendation at clinical use |
| R-LEO-AI-090 | FMEA-026 | Recovery markers not identified |
| R-LEO-AI-091 | FMEA-028 | Wrong pathway stage in clinic list |
| R-LEO-AI-092 | FMEA-029 | Wrong referral eligibility criteria |
| R-LEO-AI-093 | FMEA-030 | Incomplete MDT summary |
| R-LEO-AI-094 | FMEA-031 | SBAR used without human review |
| R-LEO-AI-095 | FMEA-032 | SBAR misses safety netting alerts |
| R-LEO-AI-096 | FMEA-033 | AI interpretation inaccurate |
| R-LEO-AI-097 | FMEA-034 | Data completeness not surfaced on clinical output |
| R-LEO-AI-098 | FMEA-036 | Auto-fix applies wrong label correction |
| R-LEO-AI-099 | FMEA-038 | Override miscategorised |
| R-LEO-AI-100 | FMEA-041 | Encounter classified to wrong programme |
| R-LEO-AI-101 | FMEA-042 | Encounter not classified at all |
| R-LEO-AI-102 | FMEA-043 | Canary not halted on F1 regression |
| R-LEO-AI-103 | FMEA-046 | Surface form bulk import bypasses review gate |
| R-LEO-AI-104 | FMEA-047 | Unapproved change activates on pipeline |
| R-LEO-AI-105 | FMEA-048 | Wrong guideline implementation approved |
| R-LEO-AI-106 | FMEA-049 | Conflict of interest not detected |
| R-LEO-AI-107 | FMEA-050 | Wrong replacement code approved |
| R-LEO-AI-108 | FMEA-051 | Impact assessment incomplete |
| R-LEO-AI-109 | FMEA-052 | Post-approval modification deployed |
| R-LEO-AI-110 | FMEA-053 | Decision submitted without rationale |
| R-LEO-AI-111 | FMEA-055 | Audit trail entry missing |
| R-LEO-AI-112 | FMEA-056 | Retired ICD-10/OPCS code not remapped |
| R-LEO-AI-113 | FMEA-057 | Content currency dashboard stale |
| R-LEO-AI-114 | FMEA-059 | Deprecated guideline still in active rules |
| R-LEO-AI-115 | FMEA-060 | Guideline staged without source reference |
| R-LEO-AI-116 | FMEA-061 | Guideline source monitoring alert not received |
| R-LEO-AI-117 | FMEA-062 | Mandatory NICE obligation not flagged as time-bound |
| R-LEO-AI-118 | FMEA-064 | NICE ingest fails silently |
| R-LEO-AI-119 | FMEA-065 | AI extracts incorrect rule from guideline |
| R-LEO-AI-120 | FMEA-066 | Guidance rule promoted without review |
| R-LEO-AI-121 | FMEA-067 | Context rule activates without impact test |
| R-LEO-AI-122 | FMEA-068 | Pipeline config change without validation |
| R-LEO-AI-123 | FMEA-069 | Episode validation misses quality issue |
| R-LEO-AI-124 | FMEA-070 | Incorrect benchmark comparison |
| R-LEO-AI-125 | FMEA-071 | Intelligence Console shows stale AI loop status |
| R-LEO-AI-126 | FMEA-072 | Research results without DQ caveats |
| R-LEO-AI-127 | FMEA-073 | Incorrect pathway interval calculation |
| R-LEO-AI-128 | FMEA-075 | New programme with misconfigured rules |
| R-LEO-AI-129 | FMEA-076 | Wrong population denominator in dashboard |
| R-LEO-AI-130 | FMEA-077 | Failed encounters not surfaced in Mission Control |
| R-LEO-AI-131 | FMEA-078 | DQ rule not triggered on episode |
| R-LEO-AI-132 | FMEA-079 | Coding drift not detected |
| R-LEO-AI-133 | FMEA-081 | Incorrect cohort definition |
| R-LEO-AI-134 | FMEA-082 | Cohort version not tracked on run |
| R-LEO-AI-135 | FMEA-084 | SOUP record incomplete |
| R-LEO-AI-136 | FMEA-085 | Breaking API change without deprecation notice |
| R-LEO-AI-137 | FMEA-087 | API spec out of date |
| R-LEO-AI-138 | FMEA-091 | Non-conformant FHIR resource |
| R-LEO-AI-139 | FMEA-092 | meta.source omitted from FHIR resource |
| R-LEO-AI-140 | FMEA-094 | Programme activated before onboarding complete |

**Total new risks to create: 63**
**Total existing risks to validate: 31**
**Total FMEA rows: 94**

---

## Workshop Agenda Suggestion

| Session | Duration | Content |
|---------|----------|---------|
| 1 | 60 min | Clinical Safety domain (FMEA-001 to FMEA-021) - Class C focus |
| 2 | 45 min | Clinical Decision Support (FMEA-022 to FMEA-034) - new UNs |
| 3 | 45 min | Model/NLP Pipeline (FMEA-035 to FMEA-046) |
| 4 | 45 min | Clinical Change Control (FMEA-047 to FMEA-055) |
| 5 | 45 min | Knowledge Base Management (FMEA-056 to FMEA-068) |
| 6 | 45 min | Platform / Operations (FMEA-069 to FMEA-082) |
| 7 | 30 min | Developer Platform (FMEA-083 to FMEA-094) |
| 8 | 30 min | Sign-off: agree acceptability, assign owners, confirm next steps |

**Estimated total: 5 hours (split across 2 sessions recommended)**

---

## Attendees (suggested)

| Role | Session |
|------|---------|
| Clinical Safety Officer | All sessions |
| Regulatory Affairs / QA Lead | All sessions |
| Lead NLP Engineer | Sessions 1, 3, 4 |
| Clinical Informatics Lead | Sessions 1, 2, 5 |
| Platform Engineering Lead | Sessions 3, 6, 7 |
| Knowledge Base Author | Sessions 5, 6 |

---

## Files

| File | Purpose |
|------|---------|
| `FMEA-LEO-AI-CORE-workshop-draft.csv` | Full FMEA table - use in Excel during workshop |
| `FMEA-LEO-AI-CORE-workshop-guide.md` | This document |
| `risks/R-LEO-AI-001.yaml to R-LEO-AI-077.yaml` | Existing risk records |
| `DC-RM-001-risk-management.md` | Risk management plan |

---

_Prepared: 2026-04-16 | Status: DRAFT - Pending hazard workshop_
_Next step: Schedule workshop, complete sessions 1-8, then create R-LEO-AI-078 onwards_
