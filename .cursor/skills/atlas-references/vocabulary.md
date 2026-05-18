# Vocabulary And Wording Gate

The wording gate runs on every drafted artefact before any Atlas
write. It enforces plain clinician English, an in-scope
vocabulary, and a banned list. Wording rules are aligned with
`.cursor/rules/health-literacy.mdc`.

## Reading age and voice

- Target reading age 9 to 11.
- Audience: clinicians, not engineers, not patients.
- Active voice. Short sentences (target 15 to 20 words max).
- No acronyms on first use; spell out then abbreviate.
- One idea per sentence.

## In-scope vocabulary (prefer)

Use these terms consistently across UNs, DIs, DOs, VTs, VALs.

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

## Banned terms (refuse unless explicitly approved)

These terms have caused scope drift before. Refuse to use them
without an explicit user approval and a one-line rationale in
the audit report.

- `referral fit` - ambiguous; use `pathway match`.
- `dashboard` - out of scope for LEO CDS release.
- `read-aloud` / `read aloud` - downstream feature, not LEO CDS.
- `OCR` - upstream feature, not LEO CDS.
- `thumbnail` - upstream feature, not LEO CDS.
- `document conversion` - upstream feature, not LEO CDS.
- `FHIR export` - out of scope for LEO CDS release.
- `compliance dashboard` - downstream feature, not LEO CDS.
- `auto-code` / `autonomous coding` - violates the mandatory
  clinician review gate; would push the device to Class C,
  which Mizaic's manufacturing policy does not permit for this
  product.
- `auto-publish` - same reason as above.

## Common substitutions

| Avoid                  | Prefer                                |
|------------------------|---------------------------------------|
| hypertension           | high blood pressure                   |
| prevalence             | how common something is               |
| comorbidity            | other health conditions               |
| contraindicated        | not recommended / not safe            |
| asymptomatic           | no symptoms                           |
| exacerbation           | flare-up / getting worse              |
| aetiology              | cause                                 |
| prophylaxis            | prevention                            |
| suboptimal             | could be better                       |
| non-compliance         | not taking medicine as planned        |
| utilisation            | use                                   |
| facilitate             | help                                  |
| subsequently           | then / after that                     |
| aforementioned         | mentioned earlier                     |
| LLM / large language model | language model (then plain English) |

## Per-artefact wording cues

- **UN** - starts with "As a <stakeholder>, I need ...".
- **DI** - "The platform SHALL ...". One requirement. Testable.
- **DO** - "<implementation cluster> - implementation".
- **VT** - "<feature> - acceptance verification".
- **VAL** - "<UN topic> - clinician validation".
- **Risk** - title is one sentence describing the failure mode
  and the impact (e.g. "Missing source evidence misleads
  clinician triage").

## Quick checklist

Before writing any artefact, the language gate runs:

1. Is the title 4 to 8 words?
2. Are there any banned terms?
3. Are there any acronyms used without spelling out?
4. Are sentences short (15 to 20 words max)?
5. Does the artefact describe an outcome (UN), a requirement
   (DI), implemented behaviour (DO), a hazard chain (Risk), a
   verification step (VT), or a clinical validation (VAL)?
6. Does a near-duplicate already exist? Run
   `search_design_controls` to confirm.
