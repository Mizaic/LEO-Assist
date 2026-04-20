# Phase 4 -- Risk Review Band (0.40 <= score < 0.55)

Total candidates needing manual confirmation: 38

Default decision: CREATE (do NOT silently merge).
To remap a row to its best-match Atlas risk instead of creating
a new one, add an entry to `scripts/atlas/phase4_decisions.json`
in the form `{"R-LEO-AI-XXX": {"decision": "remap", "atlas_dc_id": "R-XXXXXXXX"}}`
and re-run with --live.

| Local ID | Score | Best Atlas | Local Title | Atlas Title |
|---|---|---|---|---|
| R-LEO-AI-027 | 0.497 | R-EF36D546 | Overly broad suppress rule causes systematic under-coding of a clinical term | An AI-suggested text alias causes the system to wrongly flag a clinical term in patient notes |
| R-LEO-AI-004 | 0.483 | R-72C9B609 | Terminology resolver selects wrong SNOMED concept from multiple candidates | Incorrect SNOMED CT coding from NLP extraction |
| R-LEO-AI-072 | 0.48 | R-402309F7 | Corrupt or non-present clinical entities in training data cause NER model to produce clinically incorrect outputs | A routine clinical coding update breaks how the AI tool matches terms to clinical codes |
| R-LEO-AI-189 | 0.48 | R-8B17BAFA | Raw encounter text from a dry-run reviewer click leaks PHI into the gold training dataset | Cross-graph copy from a real patient leaks identifying details into the knowledge database |
| R-LEO-AI-007 | 0.476 | R-7EA57C76 | Entire clinical domain consistently miscoded, masking pathway failures | A wrongly written clinical guideline is approved and used in patient care |
| R-LEO-AI-026 | 0.473 | R-88F804F2 | Autonomous coding mode operates without human review gate | AI quality check wrongly removes correct clinical codes or sends too many for manual review |
| R-LEO-AI-019 | 0.47 | R-8703472A | SNOMED CT terminology update introduces new concepts or changed relationships that break resolution | AI tool produces an incomplete or wrong summary for a multidisciplinary team meeting |
| R-LEO-AI-175 | 0.469 | R-48544281 | Reviewer diagnostic disagrees with the production rule firing decision | Reviewers stop checking AI suggestions carefully over time |
| R-LEO-AI-503 | 0.465 | R-E6A69C00 | Milestone extractor picks an administrative event as the canonical milestone | System error message reveals internal technical detail to the user |
| R-LEO-AI-005 | 0.461 | R-471FDE69 | Reviewer-approved incorrect SurfaceForm mapping propagates to future encounters | A reviewer picks the wrong clinical code when correcting a patient record |
| R-LEO-AI-075 | 0.457 | R-6FEF2A2F | Graph algorithm results are misinterpreted and acted on clinically without understanding the data limitations | The AI tool that reads notes misses a clinically important finding |
| R-LEO-AI-504 | 0.455 | R-5C8D895A | Reconciler invents merges or drops candidate windows without supporting evidence | A clinician reviews or approves their own work without this being detected |
| R-LEO-AI-076 | 0.45 | R-1E67A4A9 | Algorithm terminology exposed in the UI causes users to misinterpret findings and take incorrect action | Non-admin users accessing private pricing and discount information |
| R-LEO-AI-041 | 0.444 | R-AEC97089 | SurfaceForm knowledge graph stores user identifiers | Teaching examples stored with patient-identifying details |
| R-LEO-AI-505 | 0.443 | R-52821F7F | Writer leaves stale or duplicate EpisodeOfCare nodes after a partial failure | The AI tool that merges duplicate episodes could wrongly combine two separate primary cancers into one record |
| R-LEO-AI-511 | 0.443 | R-D28FB644 | The SBAR Background reduce step silently loses a clinical fact, or invents a fact, while merging partial Background sections | A reviewer approves a wrong clinical code that then influences future coding suggestions |
| R-LEO-AI-093 | 0.439 | R-596AC97F | Users lose access to admin reference pages because bookmarked links break when /admin/clinical is removed | Reference range out of date because a clinical guideline has changed |
| R-LEO-AI-038 | 0.438 | R-AC248A00 | ODS API unavailable — nightly sync completes silently with no data freshness checks | A new system component is added without a safety check |
| R-LEO-AI-064 | 0.431 | R-72C9B609 | Incorrect episode stage assignment from explicit stage or TNM evidence | Incorrect SNOMED CT coding from NLP extraction |
| R-LEO-AI-500 | 0.431 | R-B31F7486 | Timeline loader feeds unsanitised text or drops valid encounters into the LLM chain | Audit trail records altered or deleted after they are created |
| R-LEO-AI-501 | 0.429 | R-402309F7 | Segmenter splits a single episode in two or merges two distinct episodes into one | A routine clinical coding update breaks how the AI tool matches terms to clinical codes |
| R-LEO-AI-510 | 0.427 | R-479839AC | Reviewer mistakes a partially-failed SBAR for a complete one because errors are hidden behind a green 'Done' button | A single reviewer approves a wrong clinical code for a common phrase, causing every future patient record with that phra |
| R-LEO-AI-089 | 0.426 | R-69A62FC7 | Role-scoped navigation hides a task the user needs to act on | A common GP abbreviation is matched to the wrong clinical code |
| R-LEO-AI-164 | 0.426 | R-2DFCA488 | dq_letter_stub_unfilled may produce too many or too few alerts, delaying triage of real letter-ingestion gaps | A combined task list could hide a backlog of safety-net alerts, delaying action |
| R-LEO-AI-198 | 0.426 | R-4732D911 | Family-history-of-cancer mention misread as a patient cancer event, opening phantom pathways for unaffected patients | A user from one organisation can see patient records belonging to another organisation |
| R-LEO-AI-187 | 0.424 | R-402309F7 | Auto-prune deletes a TrainingCandidate that the model actually needed to learn from | A routine clinical coding update breaks how the AI tool matches terms to clinical codes |
| R-LEO-AI-176 | 0.422 | R-D0B86271 | Reviewer interprets a silent zero-match as 'rule does not match' when no ruleset is compiled | A quality problem in a patient episode is not caught by the checking rules |
| R-LEO-AI-163 | 0.418 | R-162890AD | Curated Read/CTV3 code matching could misclassify an episode outcome (false benign closure or false diagnosis) | A patient visit is not classified and is left out of all care programmes |
| R-LEO-AI-506 | 0.418 | R-B52E08BD | Non-coding LLM pipelines write no cost telemetry, so per-tenant invoicing under-counts AI spend | Clinical guidelines shown to clinicians may be out of date |
| R-LEO-AI-014 | 0.413 | R-D67356D9 | Malicious or unexpected content in encounter text causes LLM misbehaviour | Failed patient encounters not shown to clinical staff |
| R-LEO-AI-171 | 0.412 | R-EC5CFF45 | Adjuvant-therapy drug detection may produce false-positive cancer diagnoses or wrong-site classifications | Dashboard shows out-of-date information — an overdue item is not flagged to the clinician |
| R-LEO-AI-017 | 0.411 | R-43911AF2 | spaCy or MedSpaCy SOUP update introduces NER regression | An unauthorised person views private patient records |
| R-LEO-AI-044 | 0.411 | R-2D68A774 | NICE-sourced AuditDomain misclassification could propagate incorrect SNOMED concepts to audit pipelines | The AI tool takes staging information from the wrong cancer pathway on the same patient |
| R-LEO-AI-170 | 0.41 | R-EC5CFF45 | Missed cancer or wrong-site classification despite problem-list malignancy term, active-care code, or site reconciliation | Dashboard shows out-of-date information — an overdue item is not flagged to the clinician |
| R-LEO-AI-193 | 0.41 | R-162890AD | Malignancy term in 'Past medical history' section is mis-classified as a new diagnosis and falsely closes an open cancer pathway | A patient visit is not classified and is left out of all care programmes |
| R-LEO-AI-043 | 0.408 | R-A5E2DA61 | Bitmap may become stale after approved rules are added or changed in Neo4j | Admin appointment details are saved as clinical findings in the patient record |
| R-LEO-AI-206 | 0.402 | R-B510BA53 | Dual-save editor on /care surfaces silently overwrites pipeline writes or peer reviewer edits, causing loss of clinically-relevant coded data | Alert incorrectly suppressed because a clinical response code was recorded in error |
| R-LEO-AI-191 | 0.4 | R-40A44BA0 | Narrative reference to '2WW clinic' fires phantom first_seen anchor and rescues open referrals to false 'completed' status | A patient or clinician on a touch screen taps the wrong button because touch targets are too small |
