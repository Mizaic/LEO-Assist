# Phase 2 -- Create-Candidate Human Review

Total local items needing review: 13

For each 'create' candidate, the top-10 Atlas candidates (re-scored after fetching Atlas ACs) are listed.  
Assign one of: REMAP -> <atlas dc_id>  |  CREATE  |  SKIP

## UN UN-LEO-AI-003
**Title**: System flags abnormal laboratory and investigation results against reference ranges

**Summary**: Pathway coordinators need the system to automatically flag abnormal laboratory and investigation results by comparing values against reference ranges. This includes blood tests, imaging reports, and o

| Atlas DC | Title | seq | jac | max |
|---|---|---|---|---|
| UN-459367FA | Clinicians need abnormal investigation results and clinical red flags automatica | 0.014 | 0.108 | 0.108 |
| UN-FBBFD5CB | Clinical quality reviewers need coded encounters automatically checked against p | 0.022 | 0.09 | 0.09 |
| UN-06FD3F7D | Clinician reviewing investigation results needs guideline escalation thresholds  | 0.005 | 0.074 | 0.074 |
| UN-BD9E0F82 | System provides electronic safety-netting for patients with cancer-relevant symp | 0.033 | 0.068 | 0.068 |
| UN-E8A5B04A | Clinical content managers need a maintainable reference range library covering n | 0.018 | 0.068 | 0.068 |
| UN-A429E081 | Clinical NLP pipeline must completely capture test result values for observable  | 0.014 | 0.055 | 0.055 |
| UN-50102672 | A QA lead, knowledge author or NLP reviewer needs one place to keep test patient | 0.012 | 0.054 | 0.054 |
| UN-5C67AAD9 | Pathway coordinators need pathway intervals automatically calculated against pro | 0.008 | 0.051 | 0.051 |
| UN-F3300833 | Clinician ordering investigations needs guideline recommendations and comparable | 0.016 | 0.05 | 0.05 |
| UN-12EEF12D | Clinical content managers need NICE publications automatically ingested and cata | 0.021 | 0.049 | 0.049 |

**DECISION**: _to fill_

## UN UN-LEO-AI-005
**Title**: System identifies key milestone events that structure a clinical episode

**Summary**: Clinical audit teams need the system to identify key milestone events -- first presentation, referral, specialist visit, investigation, diagnosis, and treatment -- that define the structure of a clini

| Atlas DC | Title | seq | jac | max |
|---|---|---|---|---|
| UN-D2C20B2E | Per-episode specialist visit attribution without cross-pathway contamination | 0.01 | 0.113 | 0.113 |
| UN-44DD6240 | Infer cancer or benign pathway outcome from post-specialist encounter signals | 0.017 | 0.108 | 0.108 |
| UN-C98EBAA9 | Detect specialist letters and infer benign pathway completion when appropriate | 0.023 | 0.106 | 0.106 |
| UN-5C67AAD9 | Pathway coordinators need pathway intervals automatically calculated against pro | 0.022 | 0.1 | 0.1 |
| UN-7294050B | Platform administrators need a data quality engine with configurable rules, per- | 0.029 | 0.096 | 0.096 |
| UN-FBBFD5CB | Clinical quality reviewers need coded encounters automatically checked against p | 0.025 | 0.096 | 0.096 |
| UN-2C01CF40 | Audit team leads need completed episodes automatically validated for quality iss | 0.023 | 0.085 | 0.085 |
| UN-D92EB141 | Clinical leads need population-level pathway performance dashboards with nationa | 0.02 | 0.082 | 0.082 |
| UN-299200A0 | Audit teams need interpretable benchmark comparison charts in audit report outpu | 0.029 | 0.081 | 0.081 |
| UN-6FADC898 | System supports SNOMED CT terminology search, resolution, and value set manageme | 0.019 | 0.074 | 0.074 |

**DECISION**: _to fill_

## UN UN-LEO-AI-006
**Title**: System constructs structured clinical episodes linking encounters to milestones

**Summary**: Clinical audit teams need the system to construct a ClinicalEpisode for each distinct patient pathway, linking shortlisted encounters to detected milestones and classifying the episode status as confi

| Atlas DC | Title | seq | jac | max |
|---|---|---|---|---|
| UN-FC99D533 | Clinical auditors need related encounters automatically grouped into structured  | 0.085 | 0.119 | 0.119 |
| UN-7294050B | Platform administrators need a data quality engine with configurable rules, per- | 0.023 | 0.092 | 0.092 |
| UN-D2C20B2E | Per-episode specialist visit attribution without cross-pathway contamination | 0.011 | 0.087 | 0.087 |
| UN-B70ACD96 | Clinical audit teams need patient records automatically shortlisted for programm | 0.015 | 0.086 | 0.086 |
| UN-55011459 | Clinical reviewers need a structured queue where every AI proposal must be valid | 0.02 | 0.071 | 0.071 |
| UN-6FADC898 | System supports SNOMED CT terminology search, resolution, and value set manageme | 0.017 | 0.069 | 0.069 |
| UN-9A7C2AA3 | Developer validating an integration needs a sandbox environment with synthetic c | 0.009 | 0.065 | 0.065 |
| UN-575E8DCB | Clinical reviewers need plain-language AI interpretation of coded audit findings | 0.021 | 0.065 | 0.065 |
| UN-12EEF12D | Clinical content managers need NICE publications automatically ingested and cata | 0.015 | 0.064 | 0.064 |
| UN-BB817C74 | Operations teams need a real-time dashboard showing pipeline throughput, queue s | 0.013 | 0.063 | 0.063 |

**DECISION**: _to fill_

## UN UN-LEO-AI-008
**Title**: System calculates pathway durations against programme-defined waiting time targets

**Summary**: Quality improvement leads need the system to calculate pathway durations between milestones and compare them against programme-defined targets. For the NCDA programme this includes the Primary Care In

| Atlas DC | Title | seq | jac | max |
|---|---|---|---|---|
| UN-D92EB141 | Clinical leads need population-level pathway performance dashboards with nationa | 0.01 | 0.161 | 0.161 |
| UN-5C67AAD9 | Pathway coordinators need pathway intervals automatically calculated against pro | 0.054 | 0.13 | 0.13 |
| UN-9E66C163 | Platform administrators need to configure new audit programmes without code chan | 0.005 | 0.088 | 0.088 |
| UN-D2C20B2E | Per-episode specialist visit attribution without cross-pathway contamination | 0.015 | 0.088 | 0.088 |
| UN-44DD6240 | Infer cancer or benign pathway outcome from post-specialist encounter signals | 0.009 | 0.075 | 0.075 |
| UN-C98EBAA9 | Detect specialist letters and infer benign pathway completion when appropriate | 0.032 | 0.071 | 0.071 |
| UN-299200A0 | Audit teams need interpretable benchmark comparison charts in audit report outpu | 0.017 | 0.069 | 0.069 |
| UN-FB2DA651 | Platform administrators need AI spend tracking and configurable pricing per tena | 0.006 | 0.067 | 0.067 |
| UN-BD9E0F82 | System provides electronic safety-netting for patients with cancer-relevant symp | 0.012 | 0.064 | 0.064 |
| UN-E6195868 | Knowledge Base Author managing ODS reference data needs automated weekly synchro | 0.019 | 0.056 | 0.056 |

**DECISION**: _to fill_

## UN UN-LEO-AI-009
**Title**: System provides LLM-assisted clinical interpretation of audit findings

**Summary**: Clinical audit teams need LLM-assisted clinical interpretation of coded encounters, episode timelines, and quality findings. The interpretation provides narrative context explaining what happened in a

| Atlas DC | Title | seq | jac | max |
|---|---|---|---|---|
| UN-575E8DCB | Clinical reviewers need plain-language AI interpretation of coded audit findings | 0.027 | 0.174 | 0.174 |
| UN-55011459 | Clinical reviewers need a structured queue where every AI proposal must be valid | 0.015 | 0.141 | 0.141 |
| UN-B70ACD96 | Clinical audit teams need patient records automatically shortlisted for programm | 0.017 | 0.087 | 0.087 |
| UN-44DD6240 | Infer cancer or benign pathway outcome from post-specialist encounter signals | 0.014 | 0.083 | 0.083 |
| UN-87632C9E | Operations teams need continuous coding quality monitoring with automated regres | 0.026 | 0.083 | 0.083 |
| UN-C98EBAA9 | Detect specialist letters and infer benign pathway completion when appropriate | 0.026 | 0.08 | 0.08 |
| UN-8659DD53 | Clinical safety officers need the review interface to require active evidence en | 0.012 | 0.074 | 0.074 |
| UN-FC99D533 | Clinical auditors need related encounters automatically grouped into structured  | 0.036 | 0.072 | 0.072 |
| UN-66396DEA | Clinical teams need to define and manage patient cohorts by clinical and demogra | 0.015 | 0.07 | 0.07 |
| UN-67663AAF | Clinician preparing a clinic list needs pathway stage context and comparable pat | 0.017 | 0.07 | 0.07 |

**DECISION**: _to fill_

## UN UN-LEO-AI-024
**Title**: System provides an out-of-the-box NCDA proforma report template built with the no-code report builder

**Summary**: Clinical audit teams need a ready-to-use report template that produces an audit-ready dataset aligned to the NCDA proforma, without requiring any configuration or development. The report template is b

| Atlas DC | Title | seq | jac | max |
|---|---|---|---|---|
| UN-9E66C163 | Platform administrators need to configure new audit programmes without code chan | 0.005 | 0.102 | 0.102 |
| UN-D92EB141 | Clinical leads need population-level pathway performance dashboards with nationa | 0.012 | 0.071 | 0.071 |
| UN-299200A0 | Audit teams need interpretable benchmark comparison charts in audit report outpu | 0.015 | 0.071 | 0.071 |
| UN-8663A98C | NLP engineers need encounter classification rules and model to be manageable and | 0.014 | 0.07 | 0.07 |
| UN-AFFA1FB3 | Clinicians need an AI-generated SBAR clinical summary from the coded record for  | 0.015 | 0.064 | 0.064 |
| UN-7294050B | Platform administrators need a data quality engine with configurable rules, per- | 0.019 | 0.061 | 0.061 |
| UN-5885D9A5 | System imports patient records via FHIR R4 and exports audit results as FHIR res | 0.02 | 0.061 | 0.061 |
| UN-16116C5F | Platform administrators need a structured guided onboarding workflow to provisio | 0.012 | 0.054 | 0.054 |
| UN-4DCD5891 | Platform administrators need configuration validation and test mode before activ | 0.007 | 0.053 | 0.053 |
| UN-D2C20B2E | Per-episode specialist visit attribution without cross-pathway contamination | 0.008 | 0.052 | 0.052 |

**DECISION**: _to fill_

## UN UN-LEO-AI-026
**Title**: GP practices subscribe to an ongoing audit volume that provides referral Positive Predictive Values between national NCDA cycles

**Summary**: GP practices and PCNs need to run ongoing cancer pathway audit between national NCDA cycles without waiting for a national round. The system offers a subscription model where a practice commits to aud

| Atlas DC | Title | seq | jac | max |
|---|---|---|---|---|
| UN-D92EB141 | Clinical leads need population-level pathway performance dashboards with nationa | 0.012 | 0.103 | 0.103 |
| UN-299200A0 | Audit teams need interpretable benchmark comparison charts in audit report outpu | 0.015 | 0.082 | 0.082 |
| UN-D2C20B2E | Per-episode specialist visit attribution without cross-pathway contamination | 0.014 | 0.072 | 0.072 |
| UN-BD9E0F82 | System provides electronic safety-netting for patients with cancer-relevant symp | 0.008 | 0.068 | 0.068 |
| UN-44DD6240 | Infer cancer or benign pathway outcome from post-specialist encounter signals | 0.015 | 0.061 | 0.061 |
| UN-FB2DA651 | Platform administrators need AI spend tracking and configurable pricing per tena | 0.007 | 0.061 | 0.061 |
| UN-A429E081 | Clinical NLP pipeline must completely capture test result values for observable  | 0.023 | 0.057 | 0.057 |
| UN-87632C9E | Operations teams need continuous coding quality monitoring with automated regres | 0.008 | 0.056 | 0.056 |
| UN-5C67AAD9 | Pathway coordinators need pathway intervals automatically calculated against pro | 0.003 | 0.056 | 0.056 |
| UN-7294050B | Platform administrators need a data quality engine with configurable rules, per- | 0.011 | 0.054 | 0.054 |

**DECISION**: _to fill_

## UN UN-LEO-AI-056
**Title**: Admin Data Quality Toolkit

**Summary**: Platform administrators need a comprehensive, reusable data quality toolkit to inspect, audit, and remediate patient graph data without writing one-off scripts. The toolkit must be accessible from the

| Atlas DC | Title | seq | jac | max |
|---|---|---|---|---|
| UN-7294050B | Platform administrators need a data quality engine with configurable rules, per- | 0.038 | 0.124 | 0.124 |
| UN-6FADC898 | System supports SNOMED CT terminology search, resolution, and value set manageme | 0.011 | 0.072 | 0.072 |
| UN-1AC15812 | NLP engineers need automated AI-assisted auditing of training labels with safe a | 0.026 | 0.071 | 0.071 |
| UN-BB817C74 | Operations teams need a real-time dashboard showing pipeline throughput, queue s | 0.025 | 0.068 | 0.068 |
| UN-FB2DA651 | Platform administrators need AI spend tracking and configurable pricing per tena | 0.008 | 0.065 | 0.065 |
| UN-87632C9E | Operations teams need continuous coding quality monitoring with automated regres | 0.038 | 0.061 | 0.061 |
| UN-4DCD5891 | Platform administrators need configuration validation and test mode before activ | 0.012 | 0.061 | 0.061 |
| UN-D2C20B2E | Per-episode specialist visit attribution without cross-pathway contamination | 0.031 | 0.059 | 0.059 |
| UN-FBBFD5CB | Clinical quality reviewers need coded encounters automatically checked against p | 0.034 | 0.058 | 0.058 |
| UN-9E66C163 | Platform administrators need to configure new audit programmes without code chan | 0.024 | 0.056 | 0.056 |

**DECISION**: _to fill_

## DI DI-LEO-AI-009
**Title**: 

**Summary**: The system SHALL identify clinical milestones (first presentation, referral, specialist visit, investigation, diagnosis, treatment) from coded encounters using programme-defined milestone definitions 

| Atlas DC | Title | seq | jac | max |
|---|---|---|---|---|
| DI-F3FD2B63 | Configurable pathway interval calculation and waiting time target breach detecti | 0.03 | 0.15 | 0.15 |
| DI-F93ACEDB | Avoidable delay assessment with cause classification and impact calculation | 0.016 | 0.097 | 0.097 |
| DI-31126C6C | NER-to-SNOMED entity extraction with confidence score and full provenance metada | 0.023 | 0.094 | 0.094 |
| DI-147F7B47 | Per-episode temporal claiming of specialist visit anchors | 0.02 | 0.093 | 0.093 |
| DI-4746A178 | Ranked patient shortlist with fused relevance score and supporting evidence span | 0.093 | 0.053 | 0.093 |
| DI-12015DBC | SNOMED coding accuracy quality gate: minimum F1 0.85 on gold-standard dataset | 0.01 | 0.089 | 0.089 |
| DI-79509E39 | Alert fatigue suppression for normal-range investigation results with configurab | 0.089 | 0.034 | 0.089 |
| DI-1206D9E8 | Episode temporal quality checks: duration outliers, missing milestones, and sequ | 0.011 | 0.088 | 0.088 |
| DI-2AFF691F | Automated guideline conformance evaluation on coded encounters | 0.011 | 0.085 | 0.085 |
| DI-FC4CA3C1 | Guideline withdrawal notification to prior users and permanent audit-trail reten | 0.083 | 0.016 | 0.083 |

**DECISION**: _to fill_

## DI DI-LEO-AI-011
**Title**: 

**Summary**: The system SHALL consolidate overlapping or duplicate episodes for the same patient, merging milestone timelines and resolving conflicts between competing episode classifications

| Atlas DC | Title | seq | jac | max |
|---|---|---|---|---|
| DI-82D5359B | Surface guideline treatment recommendations with comparable outcome summaries | 0.095 | 0.0 | 0.095 |
| DI-3FDBB57B | Unified LangGraph coding agent as the single execution path for all coding and p | 0.094 | 0.036 | 0.094 |
| DI-54D00E21 | Audit agent resource bounds: configurable iteration limit and token/cost budget  | 0.091 | 0.0 | 0.091 |
| DI-23822663 | Assertion evidence text context stored alongside assertion label | 0.086 | 0.0 | 0.086 |
| DI-A3107424 | Diagnostic and treatment recommendation exclusion from generated interpretations | 0.084 | 0.018 | 0.084 |
| DI-E5609239 | Knowledge base currency dashboard with exportable surveillance evidence | 0.083 | 0.056 | 0.083 |
| DI-091CBBAB | Unified pipeline-jobs queue with PipelineJobMessage dispatch and progress events | 0.083 | 0.0 | 0.083 |
| DI-EF37BDF9 | Authoritative source change detection with routed alerts | 0.081 | 0.022 | 0.081 |
| DI-604767B1 | Human-review gate blocking publication of AI-generated interpretations without r | 0.08 | 0.033 | 0.08 |
| DI-93162C3C | Research workspace results data coverage indicator with low-coverage advisory | 0.079 | 0.022 | 0.079 |

**DECISION**: _to fill_

## DI DI-LEO-AI-124
**Title**: 

**Summary**: The episode builder SHALL enforce a minimum referral-to-diagnosis gap of MIN_REFERRAL_TO_DIAG_DAYS days (default 3) when selecting the best-match referral for a diagnosis anchor. Referrals falling ins

| Atlas DC | Title | seq | jac | max |
|---|---|---|---|---|
| DI-FC264BBF | Two-pass referral matching with strict-then-fallback claim and honest NULL | 0.017 | 0.084 | 0.084 |
| DI-527848A8 | Staging enrichment uses post-diagnosis window with site-specialty filter | 0.017 | 0.079 | 0.079 |
| DI-147F7B47 | Per-episode temporal claiming of specialist visit anchors | 0.016 | 0.079 | 0.079 |
| DI-6051F076 | Specialist outcome letter inference for benign episode closure | 0.016 | 0.063 | 0.063 |
| DI-7A7BFA0C | Terminology hybrid retrieval skips vector search only when top lexical score >=  | 0.036 | 0.044 | 0.044 |
| DI-10BB41E9 | Shortlisting recall quality gate: minimum 95% recall on gold-standard labelled d | 0.041 | 0.02 | 0.041 |
| DI-55C1C21F | DI-LEO-AI-526: Server-side search term expansion for the dry-run review queue | 0.008 | 0.038 | 0.038 |
| DI-FF9C74E2 | Deterministic episode construction from related encounters | 0.038 | 0.031 | 0.038 |
| DI-DC61F5B6 | Multi-type span classification for overlapping SNOMED concepts | 0.004 | 0.037 | 0.037 |
| DI-9DDC5471 | Motion layer with framer-motion and prefers-reduced-motion gating | 0.036 | 0.009 | 0.036 |

**DECISION**: _to fill_

## DI DI-LEO-AI-149
**Title**: 

**Summary**: The text-based anchor detector SHALL recognise standard histology-letter vocabulary as confirmed-cancer evidence and standard benign-histology vocabulary as benign-closure evidence so that text-only e

| Atlas DC | Title | seq | jac | max |
|---|---|---|---|---|
| DI-C0AD09D2 | Breast specialty marker recall extension for UK primary-care vocabulary | 0.006 | 0.082 | 0.082 |
| DI-6051F076 | Specialist outcome letter inference for benign episode closure | 0.008 | 0.064 | 0.064 |
| DI-527848A8 | Staging enrichment uses post-diagnosis window with site-specialty filter | 0.01 | 0.049 | 0.049 |
| DI-147F7B47 | Per-episode temporal claiming of specialist visit anchors | 0.008 | 0.044 | 0.044 |
| DI-F46D7A68 | Post-specialist outcome inference engine for stale episodes | 0.009 | 0.041 | 0.041 |
| DI-55C1C21F | DI-LEO-AI-526: Server-side search term expansion for the dry-run review queue | 0.016 | 0.04 | 0.04 |
| DI-FC264BBF | Two-pass referral matching with strict-then-fallback claim and honest NULL | 0.006 | 0.039 | 0.039 |
| DI-59824215 | The system shall keep test patients in the same shape as real patients, with a c | 0.012 | 0.036 | 0.036 |
| DI-EC96F102 | Lab-value guard prevents diagnostic inference from observable measurements | 0.005 | 0.035 | 0.035 |
| DI-6E6E985B | Layer 6 value-unit linker extension for string descriptors and raw-text fallback | 0.007 | 0.034 | 0.034 |

**DECISION**: _to fill_

## DI DI-LEO-AI-155
**Title**: 

**Summary**: The episode builder SHALL classify the cancer site of every EpisodeOfCare from the encounter free text when no coded SNOMED edges are available, using a per-site dictionary of literal surface forms mi

| Atlas DC | Title | seq | jac | max |
|---|---|---|---|---|
| DI-147F7B47 | Per-episode temporal claiming of specialist visit anchors | 0.014 | 0.105 | 0.105 |
| DI-FC264BBF | Two-pass referral matching with strict-then-fallback claim and honest NULL | 0.011 | 0.092 | 0.092 |
| DI-D2D0117E | Surface form revocation with cascade CodingReview creation | 0.018 | 0.085 | 0.085 |
| DI-6051F076 | Specialist outcome letter inference for benign episode closure | 0.017 | 0.071 | 0.071 |
| DI-C0AD09D2 | Breast specialty marker recall extension for UK primary-care vocabulary | 0.02 | 0.07 | 0.07 |
| DI-FE3FFE50 | Cohort builder: rule-based inclusion/exclusion across coded entities, pathway st | 0.009 | 0.064 | 0.064 |
| DI-DC61F5B6 | Multi-type span classification for overlapping SNOMED concepts | 0.004 | 0.057 | 0.057 |
| DI-527848A8 | Staging enrichment uses post-diagnosis window with site-specialty filter | 0.019 | 0.054 | 0.054 |
| DI-5E25E872 | Guideline evaluation completion within 5 seconds per patient at p95 | 0.006 | 0.05 | 0.05 |
| DI-AF5A1668 | Multi-tenancy: dedicated Neo4j patient graph per tenant with automated provision | 0.015 | 0.049 | 0.049 |

**DECISION**: _to fill_

