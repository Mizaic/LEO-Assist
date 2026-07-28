# PB-E7 -- Neighbourhood diversion design (outline)

Catalogue reference: Module E7, "Neighbourhood diversion design" --
community-first outcomes and metrics
(`docs/marketing/build_coo_service_catalogue.py`, `module_menu()`). Bundled
into Package D (Neighbourhood Diversion Pilot).

Tier: 2 (researched outline). Density: Low -- this is explicitly an
"honest adjacency offer", not a Neighbourhood Health delivery module (per
the catalogue's own package description). Built from NHS policy plus the
catalogue's boundary slide.

## Purpose

Design a focused pilot so elective SPoA outcomes (Module E1) can safely
route to community and primary-care options, where that is clinically
appropriate -- without claiming to deliver the Neighbourhood Health
programme itself.

## Workshop agenda

Run a joint workshop with neighbourhood and elective leads:

1. **Scope confirmation (15 min).** Restate the non-scope register (below)
   before anything else, so the workshop does not drift into promising
   capability LEO does not have.
2. **Outcome mapping (30 min).** Walk the E1 outline's outcome taxonomy
   (advice given, STT, accept, redirect) and identify which "redirect"
   outcomes could plausibly point to a community or primary-care receiving
   service today.
3. **Receiving-service inventory (30 min).** List the community/primary
   options that actually exist locally and can receive a redirected
   patient (for example community physiotherapy, social prescribing,
   falls clinics) -- do not assume capacity that has not been confirmed.
4. **Metric design (20 min).** Agree how "diversion" will be counted (see
   metrics below).
5. **Non-scope sign-off (10 min).** Confirm every attendee understands what
   LEO will not do (below) before closing.

## Diversion outcome list

Build a shortlist of receiving services agreed in the workshop, for example:

- Community physiotherapy / MSK first-contact practitioner
- Social prescribing link worker
- Falls prevention service
- Primary care management with GP-held clinical support

Each entry needs a named local contact and a confirmed capacity assumption
before it is added to the outcome taxonomy used in Module E1.

## Metrics that link advice rates to demand diversion

| Metric | Definition |
|---|---|
| Redirect-to-community rate | Proportion of SPoA/A&G outcomes redirected to a community or primary-care option rather than an outpatient referral |
| Receiving-service capacity utilisation | Volume redirected against locally agreed capacity per receiving service |
| Re-referral rate | Proportion of redirected patients who are re-referred to secondary care within an agreed window (a safety and effectiveness check on the diversion, not just a volume count) |

## Non-scope register (explicit)

LEO does **not** provide, and this module does **not** deliver:

- Urgent community response (UCR) booking
- Virtual ward capacity management
- Ambulance stack / dispatch tools
- Integrated Neighbourhood Team (INT) case management
- Social care records or case management

Source for the policy context (not the non-scope list itself, which is a
LEO product boundary):
[../NHS-POLICY-EXTRACTS.md](../NHS-POLICY-EXTRACTS.md) ("Neighbourhood
health guidelines 2025/26"). The non-scope list itself mirrors the
catalogue's own boundary slide
(`docs/marketing/build_coo_service_catalogue.py`, `boundaries()`).

## Open gaps

No repo tooling tracks neighbourhood diversion outcomes beyond LEO's own
referral/A&G data -- capacity and re-referral tracking will need to draw on
the customer's own community-service systems. See
[../GAPS-AND-BLOCKERS.md](../GAPS-AND-BLOCKERS.md).
