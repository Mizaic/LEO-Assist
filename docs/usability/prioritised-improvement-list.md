# Prioritised Improvement List — NLP Pipeline UI

| Field            | Value                          |
| ---------------- | ------------------------------ |
| Document ID      | PIL-001                       |
| Version          | 0.1.0-draft                   |
| Date             | 2026-02-24                    |

---

## Ordering Criteria

1. **Reduce cognitive cost** (Part 1 UX principles)
2. **Reduce use-related risk** (Part 2 IEC 62366)
3. **Feasibility** in current codebase

---

## Prioritised List

| # | Improvement | Rationale | Effort | Files |
|---| ----------- | --------- | ------ | ----- |
| 1 | **Add confirmation for Reset** | Prevents accidental data loss (CT-03); high risk | Low | EncounterList.tsx |
| 2 | **Add confirmation for Sync gold** | Prevents premature/wrong sync (CT-04) | Low | EncounterList.tsx |
| 3 | **Require reason for Reject** | URH-02, URH-05; audit trail | Medium | ReviewView.tsx, API contracts |
| 4 | **Fix Patient progress bar** | API returns no progress/reviewed_count; bar shows undefined | Medium | PatientList.tsx, API LIST_PATIENTS |
| 5 | **Improve error messages** | Generic "Failed to load" → specific, actionable | Low | api.ts, all catch blocks |
| 6 | **Show export error to user** | PipelinePanel catch hides error | Low | PipelinePanel.tsx |
| 7 | **Disable Run Pipeline when no IDs** | Error prevention; no silent no-op | Low | PipelinePanel.tsx |
| 8 | **Rename "Patient graph links" → "Coded terms"** | Match coder mental model | Low | CodedLinksSection.tsx |
| 9 | **Add tooltip for Sync gold when disabled** | "Approve at least one encounter first" | Low | EncounterList.tsx |
| 10 | **Make Progress tab default in Pipeline modal** | Reduce distraction; games optional | Low | PipelineModal.tsx |
| 11 | **Add "Review queue" entry point** | Tasks across patients; coder workflow | High | New route, API |
| 12 | **Add keyboard shortcut help** | ? for help overlay | Low | ReviewView.tsx |
| 13 | **Add success toast after submit** | Feedback loop; reduce anxiety | Low | ReviewView.tsx |
| 14 | **Validate SpanAdjust start < end** | Error prevention | Low | SpanAdjustBanner.tsx |
| 15 | **Add CTX_FLAGS tooltips** | Neg → Negated, etc. | Low | EntityCard.tsx |

---

## Quick Wins (Effort: Low, Impact: Medium+)

- #1, #2, #5, #6, #7, #8, #9, #10, #12, #13, #14, #15

## Medium Effort

- #3, #4

## High Effort

- #11

---

## Implementation Order (Suggested)

**Phase 1 (Safety):** 1, 2, 3  
**Phase 2 (Clarity):** 4, 5, 6, 7, 8, 9  
**Phase 3 (Polish):** 10, 12, 13, 14, 15  
**Phase 4 (Workflow):** 11
