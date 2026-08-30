# Watch-outs (from live SFH breast and gynae teaching)

These failed on production letters. Check them on every new form.

## Guidance becomes patient facts

Gynae "Points to remember" listed bloating, constipation, abdominal pain,
urinary symptoms. Those words were coded onto real patients. NG12 then
fired ovarian tests, FIT, and a prostate rule.

Mark that block `template_noise`. Do the same for mastalgia advice,
NICE boxes, and "must not be rejected" cover-sheet lines.

## Coarse org/service bind

A schema bound to organisation + service attaches to every letter for
that clinic: 2WW form, Clinical Information Summary, cover sheet.

Do not rewrite the 2WW template because one free-text letter paused.
Do not invent Section A boxes that are not on that letter.

## Printed codes drift

The same row may print `A2` or `A.2`. Use `A\.?2`.
A short pattern `0` matches the ECOG heading. Use `0` plus "Fully active".

## Packed boxes

Several Yes boxes on one line (A3-A6) pair in order. Confirm the
ticked box seeds its own entity text, not its neighbour.

## Completeness vacancy

The teach tab seeds Section A/B rules from item names. Site names often
have **no** SNOMED codes. A group with no `concept_ids` can score as met.

Delete those rules or add codes before save.

## Ask LEO again / detect

Fresh detect replaces every section in the editor. Do not throw away a
working library copy to re-detect. Patch the saved sections instead.

## Wrapper vs form

Pause reason `wrapper_admin_only` means the first page is a cover sheet.
Teach the clinical form. Seal the wrapper.

## Denied text

"No known family history" and "no bleeding noted" must not seed as present.
That is a Review facts / guard issue, not a missing tick-box row.

## What the earlier session did (do not copy)

It read letters with Neo4j Cypher and wrote the breast schema with
`scripts/seed_sfh_breast_2ww_template.py --write-graph`.

This skill uses the product save path instead.
