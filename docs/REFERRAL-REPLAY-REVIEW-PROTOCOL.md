# Referral Replay Review Protocol

How to review one real referral end-to-end using `scripts/replay_referral.py`,
and how to classify what you find. Written after the first six-site pilot
(BR7 breast, LC12 lung, LGI5 lower GI, _UGI18 upper GI, UR16 urology, GY22
gynaecology) -- see "Six-site pilot findings" in
`.cursor/plans/extraction_accuracy_programme_02cdfcc8.plan.md` for the
results this protocol produced.

## 1. Run the replay

```bash
python scripts/replay_referral.py --referral-id <ubrn> --timeout-s 300 --poll-interval-s 8
```

This resets the patient and any draft assessments for the referral, then
drives the real production reprocess path
(`libs.patient_document_runs.service.start_document_run`) to completion and
writes a review bundle to `artifacts/replay/<referral_id>/<run_id>.json`
(gitignored).

If you need to re-inspect entity-level detail after a code change to the
review tooling itself (not the pipeline), you do not need to re-run the whole
pipeline -- `scripts.replay_referral._chunk_documents(client, chunk_ids)` can
be called directly against the chunk ids already in an existing bundle to
re-pull `documented_concepts` with the fix applied.

## 2. Read chunk text BEFORE reading the pipeline output

For each chunk, in order:

1. Read `chunks[i].text` only. Do not look at `documented_concepts` yet.
2. Write down (mentally or on paper) what a clinician would expect to be
   extracted: findings, disorders, observables with values, procedures,
   assertions (present / historical / possible / absent / planned).
3. Only then look at `chunks[i].documented_concepts` and diff against your
   expectation.

This ordering matters. Reading the pipeline's output first anchors your
judgement to what it already decided -- you stop noticing what it missed.

## 3. What to check per entity

- **Concept correctness** -- does the SNOMED term actually mean what the
  evidence text says? Watch for lexical-similarity traps: superficially
  similar words mapped to a clinically unrelated concept (confirmed example:
  "intermittent bleeding" -> "Intermittent claudication (finding)").
- **Assertion correctness** -- does `assertion` (present / historical /
  possible / absent / planned) match what the sentence actually says?
  Watch specifically for:
  - Current, ongoing presenting-complaint symptoms in a "reason for
    referral" narrative marked `historical` instead of `present`.
  - A reported numeric lab value (e.g. "CA125 3", "FIT 25ug/g") marked
    `absent` or `possible` -- a reported value is, by definition, present.
  - Hedge words attached to the wrong span: a form's own uncertainty
    language ("The reason I am concerned...") bleeding into the assertion
    of unrelated values later in the same sentence.
- **Value/unit linking** -- for any observable entity, does `value` (and
  `unit`) match the number actually reported for *this patient*, not a
  threshold, reference range, or cutoff quoted in the same sentence
  (confirmed example: "FIT >10 ug/g faeces, ... FIT 25ug/g" extracted with
  `value: "10"` -- the referral criterion, not the patient's actual 25).
- **Boilerplate vs. patient-specific fact** -- protocol/appendix text
  (investigation checklists, referral-criteria tables) describes what the
  *form* requires, not what happened to *this patient*. Watch for a whole
  investigations checklist being coded as a burst of `[PLANNED]` procedure
  facts from a single generic paragraph.

## 4. What to check at the run level

- `assessment.matching_rules` -- did the guideline rules you would expect to
  fire, fire? If none fired on a referral with a specific named red flag
  (positive FIT, unexplained lump, haematuria), work backwards: which entity
  or assertion in step 3 broke the chain?
- `assessment.sbar_markdown` -- does the narrative reflect the same facts,
  or does it drift (e.g. asserting something not actually coded)?
- `run.stage_progress` -- did every durable step complete, and does the
  order make sense (extract -> post-process -> terminology -> coding-verify
  -> persist-facts -> compliance -> completeness -> referral-reason -> sbar)?

## 5. Classifying a gap

For each gap found, record:

1. **Layer**: extraction (LLM missed/hallucinated an entity), coding
   (right entity, wrong/too-generic SNOMED concept), assertion (right
   concept, wrong present/historical/possible/absent/planned), value-linking
   (right concept, wrong or missing value/unit), guideline (right facts,
   rule still didn't fire), or SBAR (right facts, narrative doesn't reflect
   them).
2. **Frequency signal**: is this tied to a recurring template phrase (e.g.
   the "reason I am concerned..." sentence, or the Appendix A investigations
   checklist) that will recur across many referrals, or is it a one-off?
   Recurring-template gaps are the highest-value fixes.
3. **Severity**: does it change a coded fact a clinician would rely on
   (wrong disorder, missed red flag), or is it cosmetic (a slightly generic
   but not wrong concept)?

Do not fix inline during review. Log every gap first, then batch fixes by
layer once the six-site pass is complete -- a prompt/post-processing change
made mid-review is much harder to verify than one made against a written-down
defect list.
