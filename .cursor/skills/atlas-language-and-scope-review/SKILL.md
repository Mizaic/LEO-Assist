---
name: atlas-language-and-scope-review
description: Reviews drafted or existing Atlas design controls for clinician-readable plain English, release boundary drift, duplicate requirements, and banned terms. Use when drafting any UN, DI, DO, Risk, VT, or VAL, when reviewing existing controls for the LEO Clinical Decision Support release, or when the user asks to "rewrite for clinicians", "check for scope drift", or "remove jargon".
---

# Atlas Language And Scope Review

## When to use

- The orchestrator (`atlas-control-author`) has drafts to review
  before any Atlas write.
- The user asks to "rewrite for clinicians", "simplify the
  language", "check for jargon", or "check for scope drift".
- A periodic sweep of active artefacts is needed to catch
  wording drift.

This skill is read-only on Atlas in the review phase. It returns
either a clean set of drafts or a list of rejections with
specific reasons.

## Four gates

Every artefact must pass all four gates. See
`.cursor/skills/atlas-references/vocabulary.md` for the full
lists.

### Gate 1 - Plain English

- Reading age 9 to 11.
- Audience: clinicians.
- Active voice.
- Short sentences (15 to 20 words max).
- One idea per sentence.
- No acronyms on first use; spell out then abbreviate.

If a sentence is over 25 words, split it. If a sentence uses
more than two clauses, split it.

### Gate 2 - Banned terms

Reject any artefact containing these without explicit user
approval:

- `referral fit`
- `dashboard`, `compliance dashboard`
- `read-aloud`, `read aloud`
- `OCR`
- `thumbnail`
- `document conversion`
- `FHIR export`
- `auto-code`, `autonomous coding`, `auto-publish`

If the user explicitly approves a banned term, note it in the
audit report's `Refusals and warnings` section with a one-line
rationale.

### Gate 3 - In-scope vocabulary

Prefer the canonical terms:

| Concept                          | Preferred term                  |
|----------------------------------|---------------------------------|
| Why the patient is being seen    | `presenting complaint`          |
| Why the referral was made        | `referral reason`               |
| Why the request was made         | `request`                       |
| Pathway suitability              | `pathway match`                 |
| Pathway suitability status       | `matches` / `does not clearly match` / `unclear` |
| Clinician sign-off step          | `clinician review`              |
| Source text behind a fact        | `source evidence`               |
| Persistence to Neo4j             | `Neo4j result handoff`          |
| Async completion signal          | `pipeline completion event`     |
| Pipeline kick-off                | `pipeline trigger message`      |
| Coded fact                       | `coded clinical fact`           |
| SNOMED code                      | `clinical code`                 |

Suggest replacements for any near-synonyms.

### Gate 4 - Duplication and boundary drift

Run `search_design_controls(query=<title or core requirement>,
dc_type=...)` for each draft. If a near-duplicate exists, prefer
update over create.

Watch for release boundary drift:

- Upstream of LEO CDS: document conversion, OCR, thumbnails.
- Downstream of LEO CDS: SBAR read-aloud, guideline /
  completeness dashboards, FHIR export.

If a draft claims an upstream or downstream behaviour, reject.

## Workflow

```
Language review progress:
- [ ] Receive drafts (or active artefacts to review)
- [ ] Run Gate 1: plain English
- [ ] Run Gate 2: banned terms
- [ ] Run Gate 3: in-scope vocabulary
- [ ] Run Gate 4: duplication and boundary drift
- [ ] Apply rewrites in place where straightforward
- [ ] Return clean drafts or a rejection list
```

### Step 1 - Receive drafts

The orchestrator passes drafts in shape:

```
drafts:
  - dc_type: design-input
    title: ...
    description: ...
    rationale: ...
    acceptance_criteria: [...]
  - dc_type: design-output
    ...
```

### Step 2 to 5 - Run the gates

Apply each gate in order. For each violation, record:

- artefact (by title or proposed dcId)
- gate (1, 2, 3, or 4)
- offending phrase
- suggested replacement (where possible)

### Step 6 - Rewrite in place where straightforward

Examples of straightforward rewrites:

- `referral fit` -> `pathway match`
- `hypertension` -> `high blood pressure`
- `subsequently` -> `then`
- Acronyms first use -> spell out, then abbreviate.

### Step 7 - Return drafts

Return the cleaned drafts or, if any draft cannot be saved
without user input, return the rejection list with a short
explanation per item.

## Per-artefact wording cues

- **UN** - starts with "As a <stakeholder>, I need ...".
- **DI** - "The platform SHALL ...". One requirement. Testable.
- **DO** - "<implementation cluster> - implementation".
- **VT** - "<feature> - acceptance verification".
- **VAL** - "<UN topic> - clinician validation".
- **Risk** - title is one sentence describing the failure mode
  and the impact.

## Examples

### Good rewrite

Before:
"The system will subsequently surface the contextually-relevant
SNOMED-coded entities to the operator via the dashboard."

After:
"The platform SHALL show the clinician the matched clinical
codes from the patient record."

### Refusal (banned term, no approval)

Before:
"The platform SHALL display the referral fit result on the
clinician dashboard."

After:
"Rejected. Two banned terms: `referral fit` (use `pathway
match`), `dashboard` (out of scope for this release)."

## Related

- Reference: `.cursor/skills/atlas-references/vocabulary.md`
- Reference: `.cursor/skills/atlas-references/artefact-templates.md`
- Rule: `.cursor/rules/health-literacy.mdc`
- Orchestrator: `atlas-control-author`
