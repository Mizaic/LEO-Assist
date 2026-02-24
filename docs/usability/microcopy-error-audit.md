# Microcopy and Error Message Audit

| Field            | Value                          |
| ---------------- | ------------------------------ |
| Document ID      | MEA-001                       |
| Version          | 0.1.0-draft                   |
| Date             | 2026-02-24                    |

---

## 1. Error Messages

| Location | Current | Suggested |
| -------- | ------- | --------- |
| `api.ts` L9–10 | `err.detail ?? res.statusText` | Keep detail when present; map status: 404 → "Not found. Check the ID or return to the list."; 500 → "Server error. Try again or contact support." |
| `PatientList.tsx` L25 | "Failed to load patients" | "Could not load patients. Check your connection and try Refresh." |
| `EncounterList.tsx` L45, 64 | "Reset failed", "Sync failed" | "Reset failed: [detail]. No changes were made." / "Sync failed: [detail]. Approved data was not applied." |
| `EncounterList.tsx` L79 | "Failed to load" | "Could not load encounters. Check your connection and try again." |
| `ReviewView.tsx` L49 | "Failed to load" | "Could not load review task. It may have been completed. Return to the list." |
| `ReviewView.tsx` L181 | "Submit failed" | "Submit failed: [detail]. Your corrections are still in place. Try again." |
| `EncounterCodedView.tsx` L134, 186 | "Failed to load", "Inference failed" | "Could not load encounter." / "Inference failed: [detail]. The encounter was not changed." |
| `CodedLinksSection.tsx` L40, 59, 96 | "Failed to load", "Remove failed", "Recode failed" | "Could not load coded links." / "Remove failed: [detail]." / "Recode failed: [detail]." |
| `PipelinePanel.tsx` L211 | `stream.error` | Pass through; ensure API returns actionable message |
| `PipelineModal.tsx` L197 | "Pipeline Error" + error | Good. Add: "You can close and try again." |

---

## 2. API Error Details (Backend)

| Endpoint | Current | Suggested |
| -------- | ------- | --------- |
| `POST /patients/{id}/reset` | 404 "Patient not found" | Keep |
| `POST /patients/{id}/sync-gold` | 400 "No approved gold for this patient. Complete review and approve first." | Good — keep |
| `GET /review/tasks/{id}` | (implied 404) | "Review task not found. It may have been completed." |
| `POST /review/tasks/{id}/decision` | (validation) | "Reason is required (min 3 characters)." |

---

## 3. Labels and Instructions

| Location | Current | Suggested |
| -------- | ------- | --------- |
| `PatientList.tsx` L59 | "Filter by patient ID..." | "Search by patient ID..." |
| `PatientList.tsx` L154 | "No patients found. Run the pipeline to generate review tasks." | Good — keep |
| `PatientList.tsx` L159 | "No patients match \"{query}\"." | "No patients match your search. Try a different ID." |
| `EncounterList.tsx` L150 | "Reset patient" | "Reset patient" + tooltip: "Remove all coded links. Cannot be undone." |
| `EncounterList.tsx` L166 | "Sync gold to patient" | "Sync gold to patient" + tooltip: "Apply approved encounters to patient graph." |
| `EncounterList.tsx` L275 | "No encounters found for this patient." | Good |
| `ReviewView.tsx` L272 | "+ Add entity" | "Add entity manually" |
| `ReviewView.tsx` L302–306 | "A Approve R Reject C Correct & approve J/K Navigate" | "A Approve · R Reject · C Correct & approve · J/K Next/previous entity · Esc Close" |
| `EntityCard.tsx` L82 | `term.extraction_method` | Use friendly label: "LLM" → "AI proposal", "manual" → "Manual" |
| `CodedLinksSection.tsx` L108 | "Patient graph links ({n})" | "Coded terms ({n})" |
| `CodedLinksSection.tsx` L112 | "No coded links for this encounter." | "No coded terms yet. Select text and click 'Code selection' to add." |
| `PipelinePanel.tsx` L95 | "Patient IDs (comma-separated)" | "Patient IDs (comma or space separated)" |
| `PipelinePanel.tsx` L104 | "Max enc." | "Max encounters per patient" |
| `PipelinePanel.tsx` L129 | "Dry run" | "Dry run (no changes saved)" |
| `PipelinePanel.tsx` L245 | "Uses patient IDs above if set; otherwise exports all approved gold." | Good |
| `TermSearch.tsx` L204 | "Search SNOMED terms…" | Good |
| `TermSearch.tsx` L261 | "No results" | "No SNOMED terms found. Try a different search." |
| `TermSearch.tsx` L264 | "No results for selected tags..." | Good |
| `ManualEntityBanner.tsx` L46 | "Type text to match…" | "Type the exact text from the encounter to add…" |
| `SpanAdjustBanner.tsx` L43 | "Adjust span for \"{text}\"" | Good |
| `CorrectionsLog.tsx` L20 | "No corrections yet" | "No corrections yet. Click an entity to edit." |

---

## 4. Empty States

| Location | Current | Suggested |
| -------- | ------- | --------- |
| `PatientList` | "No patients found. Run the pipeline..." | Add: "Enter patient IDs above and click Run Pipeline." |
| `EncounterList` | "No encounters found for this patient." | Add: "Encounters are loaded from the patient graph." |
| `CodedLinksSection` | "No coded links for this encounter." | Add actionable: "Select text in the encounter and click 'Code selection' to add a SNOMED code." |
| `CorrectionsLog` | "No corrections yet" | Add: "Corrections you make will appear here before you submit." |
| `EntitySidebar` | (none when 0 entities) | "No entities extracted. Run the pipeline or add manually." |

---

## 5. Button Labels

| Current | Suggested |
| ------- | --------- |
| "Correct & Approve" | "Approve with corrections" |
| "Reassign" | "Change SNOMED code" |
| "Adjust span" | "Edit span" |
| "Recode" | "Change code" |
| "Remove" | Keep (consistent) |
| "Code selection" | Good |
| "+ Add code" | "Add code" |
| "Run inference" | "Run MedSpaCy inference (preview)" |
| "Export MedSpaCy training" | Good |

---

## 6. Confirmation Dialogs (Proposed Copy)

### Reset patient
- **Title:** Reset patient?
- **Body:** This will remove all coded links for this patient. The encounter text will remain, but you will need to run the pipeline and review again. This cannot be undone.
- **Buttons:** Cancel | Reset

### Sync gold
- **Title:** Sync gold to patient?
- **Body:** This will apply your approved encounters to the patient graph. Only encounters you have approved will be synced.
- **Buttons:** Cancel | Sync
