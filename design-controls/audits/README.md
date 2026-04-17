# Design Controls - Retrospective DI Audit

This directory holds the batched retrospective audit of every Design Input (DI) currently registered in Atlas under product `PROD-LEO-CORE-AI-20260415-6AE8A23B`.

Goal: locate the implementation for each DI, assess it against the code-quality rules and acceptance criteria, close meaningful gaps via targeted code changes, and complete the Atlas paperwork (new DOs, amended DIs, new DIs for reverse gaps, new VTs, link edges).

## Inventory snapshot

- User Needs with DIs: 73
- Total DIs audited: 221
- Phases: 15

## Batch composition

| Phase | Theme | UNs | DIs | Status | Report |
|---|---|---|---|---|---|
| Phase 01 | SNOMED auto-coding core (8 new DIs + existing pipeline DIs) | 1 | 9 | pending | [batch-01.md](batch-01.md) |
| Phase 02 | Entity provenance and immutable source linking | 1 | 8 | pending | [batch-02.md](batch-02.md) |
| Phase 03 | ConText assertion rule maintenance | 1 | 4 | pending | [batch-03.md](batch-03.md) |
| Phase 04 | Multi-label NER classification | 1 | 6 | pending | [batch-04.md](batch-04.md) |
| Phase 05 | Ontology-grounded relation linking | 1 | 6 | pending | [batch-05.md](batch-05.md) |
| Phase 06 | Training-label audit with safe auto-fix | 1 | 3 | pending | [batch-06.md](batch-06.md) |
| Phase 07 | Canary NER rollout with regression halt | 1 | 2 | pending | [batch-07.md](batch-07.md) |
| Phase 08 | Surface form dictionary maintenance | 1 | 2 | pending | [batch-08.md](batch-08.md) |
| Phase 09 | SNOMED release alignment and diffing | 1 | 2 | pending | [batch-09.md](batch-09.md) |
| Phase 10 | Coding correction reviewer workspace | 1 | 6 | pending | [batch-10.md](batch-10.md) |
| Phase 11 | Clinical review queue | 1 | 2 | pending | [batch-11.md](batch-11.md) |
| Phase 12 | Encounter classification management | 1 | 2 | pending | [batch-12.md](batch-12.md) |
| Phase 13 | Override analytics, SBAR, interpretation, completeness, quality monitoring | 8 | 33 | pending | [batch-13.md](batch-13.md) |
| Phase 14 | Pathway, referral, episode, decision support | 12 | 33 | pending | [batch-14.md](batch-14.md) |
| Phase 15 | Change mgmt, approvals, RBAC, security, auth, data protection, ops, KB, misc | 42 | 103 | pending | [batch-15.md](batch-15.md) |

## Per-batch UN roster

### Phase 01 - SNOMED auto-coding core (8 new DIs + existing pipeline DIs)

| UN ID | DI count | Title |
|---|---|---|
| UN-0374FE26 | 10 | Clinical coders need free-text encounter narratives automatically coded to SNOMED CT |

### Phase 02 - Entity provenance and immutable source linking

| UN ID | DI count | Title |
|---|---|---|
| UN-B2C85448 | 8 | Clinical reviewers and auditors need every AI-extracted entity linked to its source text phrase with immuta... |

### Phase 03 - ConText assertion rule maintenance

| UN ID | DI count | Title |
|---|---|---|
| UN-06388412 | 4 | Clinical content managers need to maintain the ConText assertion rules that determine whether extracted ent... |

### Phase 04 - Multi-label NER classification

| UN ID | DI count | Title |
|---|---|---|
| UN-14FA847A | 6 | NLP engineers need the NER model to classify the same text span under multiple SNOMED semantic types simult... |

### Phase 05 - Ontology-grounded relation linking

| UN ID | DI count | Title |
|---|---|---|
| UN-83D9A46D | 6 | NLP engineers need ontology-grounded relation linking to connect extracted findings to body sites, disorder... |

### Phase 06 - Training-label audit with safe auto-fix

| UN ID | DI count | Title |
|---|---|---|
| UN-1AC15812 | 3 | NLP engineers need automated AI-assisted auditing of training labels with safe auto-fix and human review ro... |

### Phase 07 - Canary NER rollout with regression halt

| UN ID | DI count | Title |
|---|---|---|
| UN-AE5B5691 | 2 | NLP engineers need a canary rollout mechanism for new NER model versions with automatic halt on regression |

### Phase 08 - Surface form dictionary maintenance

| UN ID | DI count | Title |
|---|---|---|
| UN-B9FDC3CA | 2 | Clinical content managers need to maintain the surface form dictionary mapping free-text expressions to SNO... |

### Phase 09 - SNOMED release alignment and diffing

| UN ID | DI count | Title |
|---|---|---|
| UN-4AEB2F29 | 2 | Knowledge Base Author managing SNOMED CT alignment needs automated release diffing and a mandatory resoluti... |

### Phase 10 - Coding correction reviewer workspace

| UN ID | DI count | Title |
|---|---|---|
| UN-7D740697 | 6 | Mizaic clinical reviewer assessing a coding correction needs full dependency mapping and terminology valida... |

### Phase 11 - Clinical review queue

| UN ID | DI count | Title |
|---|---|---|
| UN-55011459 | 2 | Clinical reviewers need a structured queue where every AI proposal must be validated before becoming final ... |

### Phase 12 - Encounter classification management

| UN ID | DI count | Title |
|---|---|---|
| UN-8663A98C | 2 | NLP engineers need encounter classification rules and model to be manageable and testable via the platform ... |

### Phase 13 - Override analytics, SBAR, interpretation, completeness, quality monitoring

| UN ID | DI count | Title |
|---|---|---|
| UN-06FD3F7D | 3 | Clinician reviewing investigation results needs guideline escalation thresholds and comparable result traje... |
| UN-459367FA | 5 | Clinicians need abnormal investigation results and clinical red flags automatically surfaced with a tracked... |
| UN-575E8DCB | 5 | Clinical reviewers need plain-language AI interpretation of coded audit findings |
| UN-6C8AEB83 | 3 | AI engineering teams need every coding override categorised by error type for model improvement |
| UN-87632C9E | 5 | Operations teams need continuous coding quality monitoring with automated regression alerts |
| UN-A949A642 | 7 | Any clinician-facing output must surface the completeness and reliability of the underlying data before a d... |
| UN-AE5D7812 | 2 | Operations teams need automated detection of longitudinal drift in coding patterns with root cause labellin... |
| UN-AFFA1FB3 | 3 | Clinicians need an AI-generated SBAR clinical summary from the coded record for handover and MDT use |

### Phase 14 - Pathway, referral, episode, decision support

| UN ID | DI count | Title |
|---|---|---|
| UN-1A6F1E0E | 2 | Clinician discussing treatment options needs guideline recommendations and real-world outcome context to su... |
| UN-2266BDAE | 2 | Clinician reviewing a patient after treatment needs expected recovery markers and comparable recovery traje... |
| UN-2C01CF40 | 4 | Audit team leads need completed episodes automatically validated for quality issues before reporting |
| UN-5C67AAD9 | 4 | Pathway coordinators need pathway intervals automatically calculated against programme waiting time targets |
| UN-67663AAF | 2 | Clinician preparing a clinic list needs pathway stage context and comparable patient profiles to prioritise... |
| UN-6D46C832 | 2 | Clinical content managers need AI-assisted extraction of structured pathway decision rules from guideline t... |
| UN-9206EFF0 | 2 | Clinician reviewing a referral needs pathway criteria and comparable referral outcomes to support consisten... |
| UN-9396A2FA | 2 | Clinician preparing a case for MDT needs a structured summary aligned to pathway requirements and comparabl... |
| UN-D92EB141 | 3 | Clinical leads need population-level pathway performance dashboards with national benchmark comparison |
| UN-F3300833 | 2 | Clinician ordering investigations needs guideline recommendations and comparable ordering patterns to reduc... |
| UN-FBBFD5CB | 4 | Clinical quality reviewers need coded encounters automatically checked against programme guidelines |
| UN-FC99D533 | 6 | Clinical auditors need related encounters automatically grouped into structured clinical episodes |

### Phase 15 - Change mgmt, approvals, RBAC, security, auth, data protection, ops, KB, misc

| UN ID | DI count | Title |
|---|---|---|
| UN-06FDC315 | 1 | Knowledge Base Author managing ICD-10 and OPCS alignment needs structured release diffing with separate man... |
| UN-07AB5B97 | 3 | Developer building a regulated product on LEO Core AI needs audit documentation and API-level traceability ... |
| UN-12EEF12D | 2 | Clinical content managers need NICE publications automatically ingested and catalogued with coverage status... |
| UN-16116C5F | 2 | Platform administrators need a structured guided onboarding workflow to provision new healthcare organisati... |
| UN-16E151CB | 2 | Mizaic clinical reviewer assessing a guideline update needs to verify source accuracy and implementation sa... |
| UN-17724530 | 2 | Mizaic clinical reviewer approval process must enforce credential scoping and conflict of interest controls... |
| UN-21D88B69 | 2 | Developer maintaining a product built on LEO Core AI needs a predictable versioning and deprecation policy ... |
| UN-299200A0 | 2 | Audit teams need interpretable benchmark comparison charts in audit report outputs |
| UN-2C6E6933 | 6 | Engineering leads need the platform to follow Mizaic standard architecture and engineering design principle... |
| UN-319F33F0 | 2 | Knowledge Base Author needs a consolidated currency dashboard showing verified status and next review date ... |
| UN-3376B57D | 2 | Technical administrators need a unified Intelligence Console showing the AI learning loop status and next b... |
| UN-395B630E | 3 | Developer integrating long-running operations needs a consistent async job pattern with predictable status ... |
| UN-407F090F | 2 | Knowledge Base Author needs a structured authoring environment with mandatory source traceability and stage... |
| UN-412D1ECD | 2 | Platform must enforce physical database-level separation of patient data between tenants with automated pro... |
| UN-47B82B96 | 4 | Clinical informaticians need a guided research workspace to investigate populations and analyse pathway bot... |
| UN-4BD56518 | 2 | Knowledge Base Author withdrawing a superseded guideline needs full dependency enumeration and mandatory re... |
| UN-4DCD5891 | 2 | Platform administrators need configuration validation and test mode before activating pipeline changes |
| UN-5236129E | 3 | NLP engineers need active learning prioritisation, per-entity F1 metrics, golden evaluation set, and warm-s... |
| UN-66396DEA | 2 | Clinical teams need to define and manage patient cohorts by clinical and demographic criteria for audit, re... |
| UN-70A35225 | 3 | NLP engineers need a de-identified labelled training corpus with a protected holdout evaluation set |
| UN-718B7AF3 | 2 | Developer beginning integration needs a complete, versioned API specification available before writing any ... |
| UN-7294050B | 2 | Platform administrators need a data quality engine with configurable rules, per-episode results, and an exp... |
| UN-785DFCDE | 2 | Mizaic clinical reviewer needs a structured change queue with risk-prioritised triage so nothing unapproved... |
| UN-8659DD53 | 4 | Clinical safety officers need the review interface to require active evidence engagement to prevent automat... |
| UN-87CB1498 | 2 | Knowledge Base Author needs automated alerting when authoritative guideline sources publish updates relevan... |
| UN-94833CA3 | 2 | Downstream products need LEO Core AI clinical outputs exposed as standard FHIR R4 resources conformant to U... |
| UN-9A7C2AA3 | 2 | Developer validating an integration needs a sandbox environment with synthetic clinical data, fault injecti... |
| UN-9E66C163 | 2 | Platform administrators need to configure new audit programmes without code changes |
| UN-A031A603 | 2 | Developer implementing authentication needs a standards-compliant auth model with documented token lifecycl... |
| UN-A412610D | 3 | Knowledge Base Author tracking NICE output needs structured assessment of Technology Appraisals and Quality... |
| UN-B70ACD96 | 6 | Clinical audit teams need patient records automatically shortlisted for programme relevance |
| UN-BB817C74 | 2 | Operations teams need a real-time dashboard showing pipeline throughput, queue status, and data quality ind... |
| UN-C2F187E9 | 4 | Data protection leads need patient identifiers automatically removed from clinical text before transmission... |
| UN-E6195868 | 3 | Knowledge Base Author managing ODS reference data needs automated weekly synchronisation with mandatory res... |
| UN-E8A5B04A | 3 | Clinical content managers need a maintainable reference range library covering normal, borderline, and crit... |
| UN-EA93F7B7 | 2 | Mizaic clinical reviewer needs assurance that approved changes are deployed without post-approval modificat... |
| UN-ED00ED74 | 3 | Mizaic clinical reviewer recording a decision needs a structured approval workflow with mandatory rationale... |
| UN-F2372DE0 | 2 | Developer handling integration failures needs a structured, consistent error response schema with sufficien... |
| UN-F6A0C5BA | 3 | Mizaic clinical reviewer assessing a proposed change needs a systematic clinical impact assessment to make ... |
| UN-F8E1F0D0 | 2 | Mizaic clinical reviewer needs a complete tamper-evident audit trail of all review decisions exportable for... |
| UN-FB2DA651 | 2 | Platform administrators need AI spend tracking and configurable pricing per tenant |

## Files

- `di-inventory.csv` - authoritative DI roster. Updated cumulatively as each batch lands.
- `un-index.json` - UN -> DI map generated from the Atlas trace matrix (`get_traceability_matrix`).
- `atlas-summary.md` - high-level DI counts per UN.
- `improvements-backlog.md` - anything deferred during a batch gate.
- `batch-NN.md` - per-batch report with verdict, improvements, and Atlas mutations per DI.

## Rules followed

- `.cursor/rules/code-quality.mdc` (function/file/complexity/nesting limits)
- `.cursor/rules/dual-path-consistency.mdc` (unified pipeline + Ask LEO parity)
- `.cursor/rules/design-controls-first.mdc` (DI -> DO -> VT -> Risk traceability)
- `.cursor/rules/vt-enforcement.mdc` (VT creation and link discipline)
- `.cursor/rules/ascii-only.mdc`
