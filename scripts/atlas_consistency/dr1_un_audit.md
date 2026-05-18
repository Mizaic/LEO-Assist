# DR-1 UN Audit Report

- Source UN snapshot: all_leo_uns_full.json (137 UNs)
- Candidate pool size (server): 138 UNs, 160 Risks

## Decision summary

- **attach**: 77
- **exclude-post-mvp**: 56
- **skip-not-candidate**: 1
- **reject**: 3

## Release-wave distribution (all UNs)

- R1: 8
- R3: 41
- R4: 16
- R5: 15
- R7: 1
- post-MVP: 56

## Persona distribution (all UNs)

- Clinician: 48
- Quality Manager: 18
- Quality Engineer: 16
- Knowledge Base Author: 15
- Developer: 11
- Engineering Lead: 9
- IT Admin: 7
- Administrator: 7
- Regulatory Affairs / QA Lead: 2
- Clinical Safety Officer: 1
- AI Coding Agent: 1
- Other: 1
- Pathway Supervisor: 1

## Rejected UNs (not attached to DR-1)

- `UN-23B49E70` persona=`Clinician` wave=`R3` :: AI first-pass candidate generation surface for the coding worker pipeline
  - reason: machine-centric UN: subject='coding worker pipeline'
- `UN-650351EB` persona=`Clinician` wave=`R5` :: FastAPI router surface surface for an integrating service or the UI
  - reason: machine-centric UN: subject='integrating service or the ui'
- `UN-D589BF05` persona=`Clinician` wave=`R3` :: API service tier surface for a FastAPI router
  - reason: machine-centric UN: subject='fastapi router'

## Flagged UNs (still attached, but need review)

- `UN-FDB48D4A` persona=`Other` wave=`post-MVP` :: System protects patient data with encryption, authentication, and authorisation controls
  - reason: release wave = post-MVP; FLAG: persona 'Other' is ambiguous

## Final DR-1 attach payload

- UNs:            77
- Design Inputs:  273
- Risks:          157

## Accepted MVP UNs (attach list)

### R1 (8)

- `UN-0374FE26` (Quality Engineer) :: Clinical coders need free-text encounter narratives automatically coded to SNOMED CT
- `UN-412D1ECD` (IT Admin) :: Platform must enforce physical database-level separation of patient data between tenants with automa
- `UN-575E8DCB` (Quality Engineer) :: Clinical reviewers need plain-language AI interpretation of coded audit findings
- `UN-AA722A75` (Clinician) :: Service-aware data completeness check before any clinical output is generated
- `UN-AFFA1FB3` (Clinician) :: Clinicians need an AI-generated SBAR clinical summary from the coded record for handover and MDT use
- `UN-C2F187E9` (Regulatory Affairs / QA Lead) :: Data protection leads need patient identifiers automatically removed from clinical text before trans
- `UN-FBBFD5CB` (Quality Engineer) :: Clinical quality reviewers need coded encounters automatically checked against programme guidelines
- `UN-A949A642` (Clinician) :: Any clinician-facing output must surface the completeness and reliability of the underlying data bef

### R3 (38)

- `UN-033A8658` (Clinician) :: Operations console and tenant integration surface for a platform operator
- `UN-06388412` (Knowledge Base Author) :: Clinical content managers need to maintain the ConText assertion rules that determine whether extrac
- `UN-06FD3F7D` (Clinician) :: Clinician reviewing investigation results needs guideline escalation thresholds and comparable resul
- `UN-0A3167F4` (Clinician) :: Encounter Mission Control surface for a clinical reviewer
- `UN-0F2ADD87` (Quality Manager) :: Audit and coding staff see every task they need to action in one unified queue
- `UN-109EEB10` (Clinician) :: Experienced clinicians with age-related vision, hearing, or dexterity changes can use LEO at full pr
- `UN-14FA847A` (Engineering Lead) :: NLP engineers need the NER model to classify the same text span under multiple SNOMED semantic types
- `UN-16E151CB` (Quality Manager) :: Mizaic clinical reviewer assessing a guideline update needs to verify source accuracy and implementa
- `UN-1AC15812` (Engineering Lead) :: NLP engineers need automated AI-assisted auditing of training labels with safe auto-fix and human re
- `UN-2266BDAE` (Clinician) :: Clinician reviewing a patient after treatment needs expected recovery markers and comparable recover
- `UN-299200A0` (Quality Manager) :: Audit teams need interpretable benchmark comparison charts in audit report outputs
- `UN-2E60AB0A` (Clinician) :: Clinician sees one SBAR per pathway, not one per patient
- `UN-319F33F0` (Knowledge Base Author) :: Knowledge Base Author needs a consolidated currency dashboard showing verified status and next revie
- `UN-407F090F` (Knowledge Base Author) :: Knowledge Base Author needs a structured authoring environment with mandatory source traceability an
- `UN-429A1909` (Clinician) :: Reconcile in-review pathway and lock corrections
- `UN-43224AC9` (Clinician) :: Care portal surface for a clinician or oncology data nurse
- `UN-44DD6240` (Quality Manager) :: Infer cancer or benign pathway outcome from post-specialist encounter signals
- `UN-50FDA4C0` (Clinician) :: UN-LEO-AI-096: One consistent encounter row + search experience across encounter surfaces
- `UN-5236129E` (Engineering Lead) :: NLP engineers need active learning prioritisation, per-entity F1 metrics, golden evaluation set, and
- `UN-55011459` (Quality Engineer) :: Clinical reviewers need a structured queue where every AI proposal must be validated before becoming
- `UN-6C8AEB83` (Engineering Lead) :: AI engineering teams need every coding override categorised by error type for model improvement
- `UN-70A35225` (Engineering Lead) :: NLP engineers need a de-identified labelled training corpus with a protected holdout evaluation set
- `UN-763F8F61` (Clinician) :: Detector flags reasoner disagreement for human review
- `UN-782EE657` (Clinician) :: Coding sees pathway context and rejects contradictory codings
- `UN-8225F9E1` (Clinician) :: Cancer pathway dashboard headline counts always agree with the Episode Engine's view of which pathwa
- `UN-852649B0` (Clinician) :: LEO presents each user the slimmest viable experience for their role
- `UN-8659DD53` (Clinical Safety Officer) :: Clinical safety officers need the review interface to require active evidence engagement to prevent 
- `UN-9206EFF0` (Clinician) :: Clinician reviewing a referral needs pathway criteria and comparable referral outcomes to support co
- `UN-9481FFEB` (Clinician) :: Document and gold-label editor surface for a clinical reviewer or label author
- `UN-B5BE2BD1` (Clinician) :: Dashboard hero cards summarise every cancer pathway exactly once across four lifecycle buckets
- `UN-BFB531AD` (Quality Engineer) :: MCP server workflows for analyst and reviewer use
- `UN-FD9BE3CA` (Clinician) :: Junior clinical and coding staff can complete audit, coding review, and pathway tasks on LEO without
- `UN-C98EBAA9` (Quality Manager) :: Detect specialist letters and infer benign pathway completion when appropriate
- `UN-AE5D7812` (IT Admin) :: Operations teams need automated detection of longitudinal drift in coding patterns with root cause l
- `UN-B2C85448` (Quality Engineer) :: Clinical reviewers and auditors need every AI-extracted entity linked to its source text phrase with
- `UN-FC99D533` (Quality Engineer) :: Clinical auditors need related encounters automatically grouped into structured clinical episodes
- `UN-B70ACD96` (Quality Engineer) :: Clinical audit teams need patient records automatically shortlisted for programme relevance
- `UN-F8E1F0D0` (Quality Manager) :: Mizaic clinical reviewer needs a complete tamper-evident audit trail of all review decisions exporta

### R4 (16)

- `UN-17724530` (Quality Manager) :: Mizaic clinical reviewer approval process must enforce credential scoping and conflict of interest c
- `UN-341955D8` (Knowledge Base Author) :: Terminology loaders for SNOMED, dm+d, OPCS-4, ICD-10
- `UN-50102672` (Regulatory Affairs / QA Lead) :: A QA lead, knowledge author or NLP reviewer needs one place to keep test patients that check every p
- `UN-6670B2D6` (Clinician) :: Terminology tooling and Neo4j MCP tools surface for a terminology engineer or platform operator
- `UN-6D46C832` (Knowledge Base Author) :: Clinical content managers need AI-assisted extraction of structured pathway decision rules from guid
- `UN-6DEC0889` (Administrator) :: Admin Data Quality Toolkit
- `UN-6FADC898` (Quality Manager) :: System supports SNOMED CT terminology search, resolution, and value set management
- `UN-785DFCDE` (Quality Manager) :: Mizaic clinical reviewer needs a structured change queue with risk-prioritised triage so nothing una
- `UN-7D740697` (Quality Manager) :: Mizaic clinical reviewer assessing a coding correction needs full dependency mapping and terminology
- `UN-9E66C163` (Administrator) :: Platform administrators need to configure new audit programmes without code changes
- `UN-FCA472D7` (Knowledge Base Author) :: Clinical knowledge author needs plain-English rule editor without misleading test surfaces
- `UN-FA198FC9` (Quality Manager) :: Platform security baseline
- `UN-A412610D` (Knowledge Base Author) :: Knowledge Base Author tracking NICE output needs structured assessment of Technology Appraisals and 
- `UN-EA93F7B7` (Quality Manager) :: Mizaic clinical reviewer needs assurance that approved changes are deployed without post-approval mo
- `UN-ED00ED74` (Quality Manager) :: Mizaic clinical reviewer recording a decision needs a structured approval workflow with mandatory ra
- `UN-F6A0C5BA` (Quality Manager) :: Mizaic clinical reviewer assessing a proposed change needs a systematic clinical impact assessment t

### R5 (14)

- `UN-06133F88` (IT Admin) :: Tenant admin self-serves domain, user, and group management from /admin/portal
- `UN-16116C5F` (IT Admin) :: Platform administrators need a structured guided onboarding workflow to provision new healthcare org
- `UN-26E57FA1` (Clinician) :: Tenant admin portal surface for a tenant administrator
- `UN-3376B57D` (Engineering Lead) :: Technical administrators need a unified Intelligence Console showing the AI learning loop status and
- `UN-3695093F` (Quality Engineer) :: Read-only Cypher access for data quality and analytics
- `UN-4DCD5891` (Administrator) :: Platform administrators need configuration validation and test mode before activating pipeline chang
- `UN-5885D9A5` (Administrator) :: System imports patient records via FHIR R4 and exports audit results as FHIR resources
- `UN-653248E1` (Administrator) :: Referral management administrators need the system to ingest incoming referrals from all channels in
- `UN-7294050B` (IT Admin) :: Platform administrators need a data quality engine with configurable rules, per-episode results, and
- `UN-8F0D92F8` (Developer) :: Platform reliability and infrastructure components
- `UN-D4BC1356` (Clinician) :: Analytics API and ODS sync surface for a quality assurance lead
- `UN-E811A9C1` (Clinician) :: Settings, auth and onboarding surface for any authenticated user
- `UN-A449F651` (IT Admin) :: Tenant administrator manages user access using their existing Entra security groups
- `UN-FB2DA651` (Administrator) :: Platform administrators need AI spend tracking and configurable pricing per tenant

### R7 (1)

- `UN-64F0E9C3` (Clinician) :: LEO-by-Mizaic embeddable AI surface across the Mizaic product portfolio
