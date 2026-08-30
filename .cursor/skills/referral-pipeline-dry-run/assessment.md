# Clinical assessment (every referral)

Read the de-id chunks first. Judge LEO against the letter, not
against itself.

Plain English. UK reading age about 11. UBRN only in the heading.

## A. Extraction completeness

- Every clinically important fact on the form or letter is present
  (symptoms, site, exam, imaging, bloods, FIT, performance status,
  suspected site).
- Checkboxes marked [X] or equivalent must appear as facts.
- Form chrome, "points to remember", and guidance must not become
  patient facts.
- Narrative in free-text sections must not be truncated.

## B. Coding and assertions

- SNOMED concept matches the span (not a neighbour, not the wrong
  laterality, not a procedure when it is a finding).
- Assertion is right: present / absent / historical / possible.
  Watch inversion on "no X" and unchecked boxes.
- Do not treat a missing code as "the patient does not have it"
  if extraction failed.

## C. Completeness / appropriateness

- Gaps must be real gaps in the record, not facts LEO failed to
  extract.
- Do not invent missing data.

## D. Guideline / already-done

- The matched pathway must match the suspected site.
- If the letter already reports a result for a recommended action,
  that action must be suppressed via already-done. If it is still
  recommended, that is a defect.
- Name the rule id and the recommended actions.

## E. SBAR

- Situation should lead with the referral reason and suspected
  site, not an older unrelated letter.
- Background must not drop key positives or invent negatives.
- Assessment must not recommend something already done.
- If SBAR failed (`too_many_parts`, degraded), say so. Do not
  treat a partial note as a pass.

## Known failure modes

- Guidance / template text extracted as findings.
- Section narrative lost when checkboxes share a line.
- Marked checkboxes not extracted.
- Assertion inversion.
- Wrong NICE NG12 pathway from a secondary symptom.
- `already_done` not firing because only exact procedure codes
  were checked.
- SBAR Situation using an older letter when
  `ReferralRequest.reason` is empty.
- Completeness asking for a score that was already ticked.
- GI: FIT result ignored; IBD coded as lower-GI medical or the
  reverse; 2WW pathway on a routine GI and Liver referral.

## Report (each referral)

Start with one line: Pass / Issues / Fail.

Then:

1. Who they are (age/sex if present, suspected site, why referred).
   No extra identifiers.
2. Pipeline: status, stage failures, report path. No live `run_id`
   on a dry-run.
3. What the letter actually says (5-10 key facts from the chunks).
4. What LEO got right.
5. What LEO got wrong, each with: evidence span, coded or missing
   fact, why it matters clinically.
6. SBAR quality in one short paragraph.
7. Expert advice: accept for a clinician to review, or fix first?
8. If fixes are needed: smallest change, which file or rule, and
   whether it would regress others in this batch.
