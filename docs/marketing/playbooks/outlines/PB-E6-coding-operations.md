# PB-E6 -- Coding operations (outline)

Catalogue reference: Module E6, "Coding operations" -- review queues, Ask
LEO assist, learning loop
(`docs/marketing/build_coo_service_catalogue.py`, `module_menu()`). Bundled
into Package C (Cancer Audit Factory), alongside Module E5.

Tier: 2 (researched outline). Density: high product / low SOP -- the coding
review UI, "Ask LEO" escalation assist, and terminology writeback loop all
exist and run in production, but there is no dedicated customer-facing
operating-rhythm SOP. This outline drafts one from the product's own
review-queue mechanics.

## Purpose

Give a customer's coding team a repeatable weekly rhythm for reviewing AI
coding proposals, using "Ask LEO" escalation where a case is ambiguous, and
feeding corrections back into the learning loop.

## What exists today (product evidence)

- A coding review queue surfaces AI-coded cases for human review, per the
  dual-path architecture rule (`.cursor/rules/dual-path-consistency.mdc`):
  the operations "Ask LEO" path processes `CodingReview` nodes when a
  reviewer clicks "Ask LEO" for escalation.
- Assertion review is governed by a shared `_VALID_ASSERTIONS` set applied
  consistently across the runtime pipeline and the review UI.
- Terminology writeback (`SurfaceForm` growth from clinician-reviewed
  coding) feeds a learning loop that is monitored quarterly for growth rate
  and accuracy (`compliance/policy/DC-SMP-001-maintenance-plan.md` section
  7).

## Operating-rhythm skeleton

1. **Daily triage.** Clinical coders work the review queue in priority
   order (safety-relevant assertions first -- see the assertion review
   queue set referenced in the dual-path rule).
2. **Ask LEO escalation.** For an ambiguous case, the reviewer clicks "Ask
   LEO" to get ranked candidate codes with rationale before making the
   final human decision -- the AI never auto-codes a blocked assertion
   without review.
3. **Weekly quality huddle.** Review a sample of completed cases against
   gold labels (where available) and discuss recurring ambiguity patterns.
4. **Quarterly writeback review.** Sample 50 `SurfaceForm` nodes to verify
   mapping correctness, per `DC-SMP-001` section 7 -- this is Mizaic's
   internal maintenance check, but the customer's coding lead should see
   the trend so they know the learning loop is working.
5. **Retraining trigger.** If more than 50 new gold-labelled encounters
   accumulate, a MedSpaCy model retrain is triggered per `DC-SMP-001`
   section 6 -- inform the customer this happens in the background and does
   not require their action.

## Roles

| Activity | Canonical app role |
|---|---|
| Daily coding review | `clinical_coder` |
| Escalation decisions | `clinical_coder`, `auditor` |
| Quality huddle facilitation | `referral_supervisor` |
| Learning-loop monitoring | Mizaic operations (internal, per `DC-SMP-001`) |

## Open gaps

No customer-facing operating-rhythm SOP exists yet for coding operations --
this skeleton should be piloted with one customer's coding team before
being presented as a fixed rhythm. See
[../GAPS-AND-BLOCKERS.md](../GAPS-AND-BLOCKERS.md).
