# Acceptance -- form is trained

A letter is **Trained** only when all of these are true.

## Letter type

- The letter is a structured form (tick boxes or labelled sections).
- You did not bind a 2WW tick-box schema to a free-text summary.

## Extraction rewrite

Run `probe_form_schema.py` on the saved schema and this letter.

- Every clinical `[X]` / `(X)` seeds one `entity_text`.
- Packed boxes on one line (A3-A6, ECOG 0-4) seed the **ticked** item only.
- Unticked boxes do not seed.
- Blank blood tables do not become results.
- `template_noise` and `admin` lines are sealed with `[NON_EXTRACTABLE]`.
- "Points to remember", mastalgia advice, NICE reminder, and cover-sheet
  contract lines are sealed.
- Free-text history / exam lines stay unsealed.
- `teach_problems` in the probe report is empty.

## Bind

- Schema has a real fingerprint (not `unknown`).
- `organization_id` and `service_id` are the live node ids from the referral.
- Completeness groups are either empty or every leaf has `concept_ids`
  or `semantic_categories`. No vacant "always complete" rules.

## After save

- `PUT /api/form-schemas/{fingerprint}` returned the schema.
- A later letter of the **same** form should resolve `known_schema=true`
  and should not pause for `unknown_form_template` or `few_shot_ood`.

## Not enough

These are **Partial**, not Trained:

- Probe green but you have not written the graph.
- Graph written but completeness still has empty members.
- Only this letter works; a second same-form letter still leaks guidance.
- You reviewed facts on one letter and did not save a schema.
