# UX Audit Report — NLP Training and Inference Pipeline UI

| Field            | Value                          |
| ---------------- | ------------------------------ |
| Document ID      | UX-AUDIT-001                   |
| Version          | 0.1.0-draft                   |
| Status           | Draft                         |
| Date             | 2026-02-24                    |
| Classification   | QMS — Usability Engineering   |
| Scope            | services/ui, services/api      |

---

## Part 1: UX Principles (Cognitive Cost Reduction)

### 1. Visibility of System Status

| Finding | Location | Current behaviour | Suggested improvement | Priority |
| ------- | -------- | ----------------- | --------------------- | -------- |
| **Generic error messages** | `api.ts` L9–10 | `err.detail ?? res.statusText` — user sees "Not Found" or raw API detail | Surface specific, actionable copy: "Patient not found. Check the ID or return to the list." | High |
| **Reset/Sync no confirmation** | `EncounterList.tsx` L32–67 | Reset and Sync gold run immediately; no confirmation | Add confirmation modal for Reset ("This removes all coded links. Continue?") and Sync ("Apply approved gold to patient graph?") | High |
| **Export result not surfaced on error** | `PipelinePanel.tsx` L38–41 | `catch` logs to console; user sees nothing | Show error state: "Export failed: [message]" | Medium |
| **Pipeline running, no cancel** | `PipelineModal.tsx` | User can minimize but not cancel a running pipeline | Add "Cancel" button when running; document that workers will finish current encounter | Medium |
| **Submit decision no confirmation** | `ReviewView.tsx` L168–184 | Approve/Reject/Edit submit immediately | Add brief confirmation: "Decision submitted" toast; on error, keep user on page with retry | Medium |
| **Patient progress bar undefined** | `PatientList.tsx` L136–147 | Uses `p.progress`, `p.reviewed_count` but API returns only `patient_id`, `encounter_count` | Fix API to return progress/reviewed_count or remove progress bar until available | High |
| **Loading states minimal** | Multiple | "Loading…" text only | Add skeleton loaders or spinner; indicate what is loading | Low |

### 2. Match Between System and Mental Model

| Finding | Location | Current behaviour | Suggested improvement | Priority |
| ------- | -------- | ----------------- | --------------------- | -------- |
| **"Patient graph links" vs "Coded links"** | `CodedLinksSection.tsx` L108 | Header says "Patient graph links" — technical term | Use "Coded terms" or "SNOMED codes" — matches coder mental model | Medium |
| **Encounter list mixes task and encounter** | `EncounterList.tsx` L183–186 | Click goes to task if exists, else view; "task {id}" shown | Separate "Review" (task) from "View" (encounter); make workflow explicit | Medium |
| **"Correct & approve" vs "Approve"** | `ReviewView.tsx` L311–314 | Two approve paths; "Correct" implies edits | Clarify: "Approve as-is" vs "Approve with corrections" | Medium |
| **Pipeline panel order** | `PipelinePanel.tsx` | Run Pipeline first, Export second | Match workflow: Run → Review → Sync → Export; add brief workflow hint | Low |
| **"Run inference" vs "Run pipeline"** | `EncounterCodedView.tsx` L218 vs `PipelinePanel` | Different "run" actions in different contexts | Label: "Run MedSpaCy inference" (encounter) vs "Run LLM pipeline" (patients) | Low |

### 3. User Control and Freedom

| Finding | Location | Current behaviour | Suggested improvement | Priority |
| ------- | -------- | ----------------- | --------------------- | -------- |
| **No undo after submit** | `ReviewView.tsx` | Submit navigates away; no undo | After submit, show "View next task" or "Back to list"; consider soft-undo for accidental submit | High |
| **Reset is destructive, no confirmation** | `EncounterList.tsx` L32–49 | Reset deletes all DOCUMENTS; no confirmation | Require confirmation: "Reset removes all coded links for this patient. This cannot be undone." | High |
| **TermSearch modal closes on backdrop click** | `TermSearch.tsx` L184 | Click outside closes; user may lose selection | Consider "Are you sure?" if user has selected a result but not confirmed | Low |
| **No back from ReviewView without submitting** | `ReviewView.tsx` | Back button exists (L244) | Good — keep. Ensure keyboard Esc also navigates back when popover closed | Low |

### 4. Consistency

| Finding | Location | Current behaviour | Suggested improvement | Priority |
| ------- | -------- | ----------------- | --------------------- | -------- |
| **Inconsistent "Back" labels** | `EncounterList` L125, `ReviewView` L244, `EncounterCodedView` L204 | "← Back to patients" vs "← Back to encounters" | Standardise: "← Back" with context in breadcrumb | Low |
| **Reason field not used** | `ReviewView.tsx` L175 | `reason` auto-filled as "N corrections applied" or empty; API requires min 3 chars | Add explicit reason input; require user to enter reason for Reject | High |
| **EntityCard vs CodedLinksSection** | Different components | EntityCard: Reassign, Adjust span, Remove. CodedLinks: Recode, Remove | Align terminology: "Recode" = change SNOMED; "Remove" = delete | Medium |
| **Confidence display** | `EntityCard` L104–108, `EntitySidebar` L44 | EntityCard shows bar + %; Sidebar shows % only | Keep both; ensure same colour scale (green/amber/red) | Low |

### 5. Error Prevention Over Error Handling

| Finding | Location | Current behaviour | Suggested improvement | Priority |
| ------- | -------- | ----------------- | --------------------- | -------- |
| **Empty patient IDs** | `PipelinePanel.tsx` L51 | `if (ids.length === 0) return` — silent no-op | Disable "Run Pipeline" when empty; show hint: "Enter at least one patient ID" | Medium |
| **Max enc. / Workers validation** | `PipelinePanel.tsx` L53–55 | `Number.isNaN` fallback; workers clamped 1–8 | Validate on blur; show error if invalid (e.g. "Max encounters must be 1–500") | Low |
| **Reject without reason** | `ReviewView.tsx` L175 | Reason can be empty for approve; API may enforce | Require reason for Reject; suggest "Incorrect SNOMED mapping" etc. | High |
| **Sync gold when no approved** | `EncounterList.tsx` L154 | Button disabled when `approved === 0` | Good. Add tooltip: "Approve at least one encounter first" | Low |
| **Manual add "Not found"** | `ManualEntityBanner.tsx` L55–56 | Shows "Not found in text" when no match | Good. Disable Add button — already done | Low |

### 6. Recognition Over Recall

| Finding | Location | Current behaviour | Suggested improvement | Priority |
| ------- | -------- | ----------------- | --------------------- | -------- |
| **Keyboard shortcuts not discoverable** | `ReviewView.tsx` L302–306 | A/R/C/J/K shown in footer bar | Add tooltip or help icon: "Keyboard shortcuts" | Medium |
| **CTX_FLAGS abbreviations** | `EntityCard.tsx` L114–127 | Neg, Unc, Hist, Fam, Hyp, Res | Add tooltips: "Negated", "Uncertain", etc. | Low |
| **Term search semantic tags** | `TermSearch.tsx` L213–228 | Tags shown as filter chips | Good — recognition. Consider "Recent searches" for power users | Low |
| **Patient ID placeholder** | `PipelinePanel.tsx` | "e.g. 999 000 0001, 999 000 0002" (synthetic test IDs — real NHS numbers removed) | Supports plain digits, spaced and hyphenated formats | Low |

### 7. Flexibility and Efficiency

| Finding | Location | Current behaviour | Suggested improvement | Priority |
| ------- | -------- | ----------------- | --------------------- | -------- |
| **Keyboard shortcuts** | `ReviewView.tsx` L193–217 | A, R, C, J, K, Escape | Good. Add E for Escalate, ? for help | Medium |
| **No bulk review** | — | One task at a time | Future: "Approve all" for batch with low-risk items | Low |
| **Pipeline games during wait** | `PipelineModal.tsx` | Snake, Space Invaders, Breakout | Novel — reduces perceived wait. Ensure Progress tab is default | Low |
| **Export name default** | `PipelinePanel.tsx` L15 | "medspacy_v1" | Good default. Consider date-based: "medspacy_2024-02-24" | Low |

### 8. Aesthetic and Minimalist Design

| Finding | Location | Current behaviour | Suggested improvement | Priority |
| ------- | -------- | ----------------- | --------------------- | -------- |
| **Pipeline modal games** | `PipelineModal.tsx` | Games compete with progress | Make Progress tab default; games optional for long waits | Medium |
| **CodedLinksSection in ReviewView** | `ReviewView.tsx` L328–332 | Shows "Patient graph links" in review context | In review context, this is for viewing gold; consider hiding or collapsible when not relevant | Low |
| **Corrections log always visible** | `ReviewView.tsx` L334–338 | Takes space even when empty | Collapse when empty; expand when corrections exist | Low |
| **SpanAdjustBanner** | `SpanAdjustBanner.tsx` L44–67 | Start/End as raw numbers | Add character counter or preview; validate start < end | Low |

---

## What Separates Good from Great

### Information Architecture

| Finding | Current | Suggested |
| ------- | ------- | --------- |
| **Entry point** | Patient list → Patient → Encounter/Task | Add "Review queue" as primary entry for coders (tasks across patients) |
| **Task vs encounter** | Encounter list mixes both; click behaviour varies | Separate "Review queue" (tasks) from "Patient encounters" (view) |
| **Pipeline vs Export** | Same panel; workflow not clear | Add workflow stepper: 1. Run pipeline 2. Review 3. Sync gold 4. Export |

### Progressive Disclosure

| Finding | Current | Suggested |
| ------- | ------- | --------- |
| **Pipeline params** | All visible: patient IDs, max enc, workers, dry run | Collapse "Advanced" (workers, dry run) by default |
| **EntityCard context flags** | All 6 flags visible | Keep; they're compact. Add tooltips for clarity |
| **TermSearch value/unit** | Shown when captureValueUnit | Good — progressive disclosure |

### Feedback Loops

| Finding | Current | Suggested |
| ------- | ------- | --------- |
| **Submit decision** | Navigates away | Show toast "Decision submitted" + link to next task |
| **Reset/Sync** | Refreshes list; error shown inline | Success: "Reset complete. X links removed." |
| **Add coded link** | Corrections log updated | Good. Add brief highlight on new link in sidebar |

### Sensible Defaults

| Finding | Current | Suggested |
| ------- | ------- | --------- |
| **Max encounters** | 50 | Good default |
| **Workers** | 4 | Good |
| **Dry run** | false | Consider default true for safety |
| **Export name** | "medspacy_v1" | Good |

---

## What Makes UX Fail in Practice

- **Building for stakeholders** — Games in pipeline modal may delight stakeholders but distract from task completion. Progress should be primary.
- **Skipping research** — No evidence of user testing with real coders. Validate: Do coders use keyboard shortcuts? Do they understand "Patient graph links"?
- **UX as phase** — Reset/Sync/Export lack confirmation; reason field bypassed. These suggest UX bolted on after architecture.
