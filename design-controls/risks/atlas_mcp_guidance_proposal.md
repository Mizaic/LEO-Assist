# Proposal: Embed Risk-Writing Guidance into the Atlas Design Controls MCP

**Audience:** Atlas Design Controls MCP server team
**From:** LEO AI Core
**Date:** 2026-04-18
**Why now:** during a 156-risk bulk load against `PROD-LEO-CORE-AI-20260415-6AE8A23B`
we found that (a) there is no in-server guidance on how to write risks to
DCB0129 / ISO 14971 standard, (b) there is a silent field-name mismatch
between `update_risk` arguments and what the server actually persists, and
(c) without explicit prompting agents tend to leave key safety-case fields
blank, technical, or incomplete.

This document proposes three concrete changes to the MCP that would prevent
those problems for every tenant -- not just LEO.

---

## 1. Update `INSTRUCTIONS.md` (server-level guidance)

The current file is one sentence:

> Atlas design controls MCP server. Use this server to read and write UN, DI,
> DO, VT, VAL, Risk nodes and traceability edges, manage change requests and
> CAPAs, and record verification/validation test evidence. Every mutation
> requires qa-ra-lead, developer, or admin role.

**Proposed replacement:**

````markdown
Atlas Design Controls MCP server. Use this server to read and write UN, DI,
DO, VT, VAL, Risk nodes and traceability edges, manage change requests and
CAPAs, and record verification/validation test evidence. Every mutation
requires qa-ra-lead, developer, or admin role.

## Risk-writing standard (DCB0129 / ISO 14971)

All risk text fields are part of a clinical safety case that will be read
by a clinician (GP, nurse, pharmacist), a regulator, or both. Apply the
following rules to EVERY risk you create or update.

### Audience

- UK reading age 11. Clinical terms a clinician already knows (hypertension,
  pathway, encounter, register) are fine. Software/AI jargon (NLP, SNOMED
  concept ID, embedding, pipeline, writeback, F1, ConText) is NOT.
- Use UK English. Active voice. Short sentences (15-20 words max).

### What each field must contain

| Field                       | What to write                                                                                               | Bad                                                            | Good                                                                                                |
| --------------------------- | ----------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| `title`                     | One sentence, plain English, names the failure in user terms.                                               | "Incorrect SNOMED CT coding from NLP extraction"               | "Wrong clinical code assigned by the AI tool that reads notes"                                      |
| `hazard_description`        | The system condition that could cause harm. 1-2 sentences.                                                  | "Currency review not triggered when guideline updated"         | "When a clinical guideline changes, the system may not prompt anyone to update the stored range."   |
| `hazardous_situation`       | What happens when that hazard meets a real clinical workflow. Name the user, the action, the consequence.   | "System assigns incorrect code"                                | "A clinician reviews a result. The system shows it as normal against an out-of-date range."         |
| `harm_description`          | What could happen to the patient if the situation is not caught. Be concrete about the clinical outcome.    | "Distorts audit data"                                          | "The clinician misses an abnormal result. The patient does not receive timely follow-up."          |
| `mitigation_measures_detail` | Named controls, what each does, who runs it, how often. Cite linked DI IDs in brackets. Close with monitoring cadence. | "Existing YAML risk" or empty. | See template below.                                                                                  |

### Mitigation plan template (DCB0129-compliant)

```
[N] controls reduce this risk.

First, [what control 1 does in plain words], which [how it reduces the
hazard]. [Who is responsible], [how often] (DI-XXXXXXXX).

Second, [control 2 ...] (DI-XXXXXXXX).

[... up to 5 controls ...]

The clinical safety committee reviews [audit log / dashboard / metric] every
[quarter / month] to confirm these controls remain effective.
```

Rules:

- Cite ONLY design inputs (DIs) that are linked to this risk via `MITIGATES`.
  Do NOT invent controls.
- If fewer than 2 DIs are linked, write the plan with what you have and add
  a final sentence: "Additional controls are being identified."
- Do NOT restate severity, probability, or RPN scores in this field -- they
  live in their own structured fields.

### Scoring (do not confuse the two scales)

| Scale       | Used by                          | Range | Field examples                                              |
| ----------- | -------------------------------- | ----- | ----------------------------------------------------------- |
| FMEA SOD    | `add_fmea_item`, `update_fmea_item` | 1-10  | `severity`, `occurrence`, `detection`                       |
| ISO 14971   | `create_risk`, `update_risk`     | 1-5   | `initial_severity`, `initial_probability`, `initial_detectability`, `residual_*` |

When promoting an FMEA item to a risk, you MUST convert SOD (1-10) to ISO
14971 (1-5). A simple ceiling-divide-by-2 mapping is acceptable for most
cases (1-2 -> 1, 3-4 -> 2, 5-6 -> 3, 7-8 -> 4, 9-10 -> 5).

### Required minimum set on every Risk node

A risk is not safety-case-ready until ALL of the following are populated:

- `title`, `description`
- `hazard_description`, `hazard_category`
- `hazardous_situation`
- `harm_description`, `harm_severity`
- `initial_severity`, `initial_probability`, `initial_detectability`,
  `initial_rpn`
- `mitigation_measures_detail`, `mitigation_control_type`,
  `mitigation_effectiveness`
- `monitoring_plan`, `monitoring_metrics`, `review_frequency`
- `status` (one of: Identified, Analyzed, Control Implemented,
  Residual Accepted, Closed, Inactive, Obsolete)
- `safety_class` (A, B or C per IEC 62304)
- At least one `MITIGATES` edge from a DI

If `residual_severity` x `residual_probability` x `residual_detectability`
yields a residual_rpn higher than the agreed acceptability threshold for
the product, also populate `residual_acceptability` (must be `alarp` or
`unacceptable` with a `residual_justification`).
````

---

## 2. Per-tool descriptions

The current per-tool `description` strings are mechanical ("Update a risk
record with ISO 14971 risk and residual fields"). Add a short writing brief
to each one so an LLM that has only the tool description in scope still gets
the standard.

### `create_risk` -- proposed description

```
Create a new Risk linked to a product.

Writing standard: every text field is part of a clinical safety case. Use UK
reading age 11, active voice, short sentences. Translate IT/AI jargon into
plain clinical language (e.g. "NLP" -> "the AI tool that reads notes",
"SNOMED concept ID" -> "clinical code"). See server INSTRUCTIONS for the full
field-by-field standard and the mitigation-plan template.

Link to mitigating Design Inputs with link_design_controls using relationship
MITIGATES (source=DI IDs, target=Risk ID). Pass workshop_id to also link the
new Risk to an FMEA workshop via IDENTIFIED_RISK.

Requires write role.
```

### `update_risk` -- proposed description

```
Update an existing Risk with ISO 14971 fields.

Field naming (IMPORTANT): the long-form mitigation narrative goes in
`mitigation_measures_detail`. The server stores this and exposes it on read
under both `mitigation_plan_description` (snake_case) and
`mitigationPlanDescription` (camelCase). DO NOT pass `mitigation_plan_description`
on write -- it is silently ignored.

Writing standard: see server INSTRUCTIONS. The mitigation_measures_detail
must name the linked DIs explicitly in brackets (e.g. "(DI-340279C1)") and
must close with the monitoring cadence sentence (e.g. "The clinical safety
committee reviews this every quarter.").

Scoring: initial_severity / initial_probability / initial_detectability and
the residual_* equivalents are 1-5 (ISO 14971), NOT 1-10 (FMEA). If you
arrived here from an FMEA item, convert before calling.

Requires write role.
```

### `add_fmea_item` -- proposed description

```
Add a row to an existing FMEA workshop's analysis board.

Scoring: severity / occurrence / detection are 1-10 (FMEA convention). The
server computes RPN = S * O * D and a risk_level from RPN.

Use update_fmea_item to revise scores or status, and
promote_fmea_item_to_risk to convert a high-RPN item into a first-class Risk
node. When promoting, the corresponding Risk uses ISO 14971 scoring (1-5),
not FMEA (1-10) -- you will need to convert before calling update_risk.

Writing standard: failure_mode, failure_effect and failure_cause are read by
clinicians during the safety-case review. Write in plain English (UK reading
age 11), active voice, short sentences. See server INSTRUCTIONS.

Requires write role.
```

### `promote_fmea_item_to_risk` -- proposed description

```
Promote an FMEA item to a first-class Risk node and create the
PROMOTED_TO_RISK edge.

Note: this creates a Risk in `Identified` status with empty ISO 14971 fields.
You MUST follow this call with `update_risk` to populate hazard_description,
hazardous_situation, harm_description, mitigation_measures_detail, scoring,
and monitoring fields, otherwise the Risk is not safety-case-ready.
See server INSTRUCTIONS for the field-by-field writing standard.

Requires write role.
```

---

## 3. Bug to fix while you're in there

`update_risk` accepts `mitigation_measures_detail` as input, but the server
stores it under the property name `mitigation_plan_description` (and
`mitigationPlanDescription` for the UI). If a caller (very reasonably) passes
`mitigation_plan_description` thinking that matches the read shape, the
input is silently dropped -- the call returns 200 OK and nothing is written.

**Suggested fix, in priority order:**

1. **Best:** accept BOTH `mitigation_measures_detail` and
   `mitigation_plan_description` as input, normalising to whatever the
   server stores. Add a deprecation note in the response if the legacy alias
   is used.
2. **Acceptable:** keep input as `mitigation_measures_detail` only, but
   rename the read shape to match (`mitigation_measures_detail` everywhere).
3. **Minimum:** if neither rename is feasible, log a warning when an
   unrecognised field is passed to `update_risk` (currently it is silently
   discarded, which is the worst possible behaviour for a safety-relevant
   API).

The same `snake_case` vs `camelCase` mismatch was previously observed for
`hazard_description` / `hazardDescription`, `hazardous_situation` /
`hazardousSituation`, and `harm_description` / `potentialHarm`. The UI
forms appear to bind to camelCase but the API stores both -- so risks
written via the API show up in the UI for those fields but not always for
others. A consistent contract (one shape on read, both accepted on write)
would close this whole class of bug.

---

## Why this matters for tenants

Without server-level guidance, every team that adopts Atlas has to
re-invent:

- the plain English standard (and most won't, leaving the safety case
  technical and unauditable);
- the mitigation plan structure (and most will leave it blank or write
  "Existing risk", which DCB0129 reviewers will reject);
- the FMEA-to-ISO-14971 score conversion (and most will mix the scales,
  giving false RPNs);
- the field-name discovery loop (we burned a full bulk load on
  `mitigation_plan_description` vs `mitigation_measures_detail`).

Putting the guidance in the MCP itself means every LLM-driven workflow
across every tenant gets a compliant safety case by default.
