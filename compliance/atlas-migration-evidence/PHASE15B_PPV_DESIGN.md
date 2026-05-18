# Phase 15b - EpisodeOfCare PPV analytics design note

## Purpose

This note defines the planned design for the EpisodeOfCare-derived
Positive Predictive Value (PPV) analytics described in
`UN-90507468` and the umbrella `DI-58C55352`. It exists so the
Atlas Design Inputs, Design Outputs, and Verification Tests for
this capability can be created BEFORE the code lands - and so the
trace headers stamped into the new files line up with the Atlas
DO IDs from day one.

This is a planning note, not a final SAD section. The product-level
SAD (one-per-product Atlas artefact) is not modified by this work;
when the capability ships, the relevant SAD sections (architecture
overview, component descriptions, data design) get a brief update
as a separate task.

## Scope

In scope:

- A reusable EpisodeOfCare-PPV calculation primitive that joins
  Situation nodes (e.g. `2WW referral`, `urgent suspected cancer`)
  to Disorder nodes (e.g. `confirmed colorectal cancer`,
  `cancer excluded`) via the `EpisodeOfCare` milestone chain
  already established by the episode builder.
- A subscription cohort model so a GP practice / PCN /
  organisation can opt into a recurring audit with a configurable
  minimum cohort size (default 500 patients) and a continuous
  trigger (run as pathways complete, not on a fixed national
  cycle).
- An NCDA-compatible export so the same cohort that drives the
  in-product PPV dashboard can also be submitted to the national
  cancer diagnosis audit during a national submission window.

Out of scope (kept as separate DIs / DOs):

- Multi-channel referral ingestion (already covered by
  `DI-93D89DC6` - upstream `PROD-LEO-BY-HEALTHCARE-CO-20251114`).
- Episode builder / milestone definitions (already covered by
  the episode-engine DOs).
- The existing NCDA dashboard (`/audit` page, audit routers in
  `services/analytics_api`) - this work composes those primitives
  into the new PPV view.

## Graph traversal contract

The PPV cohort is the union of confirmed-cancer and
cancer-excluded EpisodeOfCare nodes for the subscription cohort:

```
PPV_numerator   = count(confirmed_cancer EpisodeOfCare with
                        an originating 2WW or USC situation)
PPV_denominator = count(EpisodeOfCare with an originating 2WW
                        or USC situation, regardless of outcome)
PPV             = PPV_numerator / PPV_denominator
```

Reuse:

- `confirmed_cancer_where(alias)` and `suspected_cancer_referral_where(alias)`
  in `libs/analytics/cohorts.py` already encode the canonical
  NCDA confirmed-cancer clauses; the new PPV calculator MUST
  compose these instead of redefining the predicates.
- The episode builder already attaches `referral`,
  `diagnosis_confirmed`, and `benign_closure` milestones to
  `EpisodeOfCare`; the PPV calculator MUST traverse those edges
  rather than scanning raw encounters.

The novel work is the situation -> disorder traversal that bridges
referral situations (entry into the pathway) and the disorder /
benign-closure outcomes at the other end. The traversal MUST be a
single Cypher `MATCH` with no Python-side joining so the result
set is deterministic.

## Planned files (Atlas DO source_reference will name these)

| Capability | Planned file | Tests |
|---|---|---|
| PPV calculation primitive | `libs/analytics/ppv.py` | `tests/analytics/test_ppv.py` |
| PPV Cypher templates | `libs/cypher/ppv_queries.py` | `tests/cypher/test_ppv_queries.py` |
| Subscription cohort model | `libs/analytics/subscription_cohort.py` | `tests/analytics/test_subscription_cohort.py` |
| Subscription Cypher | `libs/cypher/subscription_audit_queries.py` | `tests/cypher/test_subscription_audit_queries.py` |
| Analytics REST routes | `services/analytics_api/app/routers/ppv.py` | `tests/analytics_api/test_ppv_router.py` |
| NCDA exporter | `libs/analytics/ncda_export.py` | `tests/analytics/test_ncda_export.py` |
| PPV dashboard surface | `services/ui/src/app/audit/ppv/page.tsx` and `services/ui/src/components/audit/PpvBenchmarkCard.tsx` | `services/ui/src/__tests__/ppv-dashboard-chrome.test.tsx` |

When the developer lands the code, the Atlas trace headers in
each new file MUST point at the Atlas DO IDs created by Phase 15b
(see the per-DO mapping below).

## Sub-DI / DO / VT split

The umbrella DI `DI-58C55352` is left as the high-level
"continuous subscription audit with PPV" requirement. Three
narrower DIs are created so each capability has its own
implementable contract:

1. EpisodeOfCare PPV calculation primitive (situation -> disorder
   join via episode milestones, deterministic Cypher).
2. Practice / PCN subscription cohort with a configurable
   minimum cohort size and a continuous trigger.
3. NCDA-compatible audit export aligned with the national
   submission file format.

Each gets a DO whose `source_reference` names the planned files,
and a VT whose `description` names the planned test files. The VT
test files do not need to exist yet - the VT execution_history
is left empty until Phase 15e re-runs the suite after the code
lands.

## Atlas artefacts created (Phase 15b)

Parent: `UN-90507468` (existing) -> `DI-58C55352` (existing
umbrella, kept as-is).

Sub-DIs (each MITIGATES `R-732325CF`):

| DI | Title |
|---|---|
| `DI-9D080448` | EpisodeOfCare PPV calculation primitive |
| `DI-10A581D2` | Continuous-trigger subscription cohort |
| `DI-C2A206A3` | NCDA-compatible audit export |

DOs and source_reference paths:

| DO | source_reference | Implements |
|---|---|---|
| `DO-AE402D85` | `libs/analytics/ppv.py`, `libs/cypher/ppv_queries.py` | `DI-9D080448` |
| `DO-2FA6DB4B` | `libs/analytics/subscription_cohort.py`, `libs/cypher/subscription_audit_queries.py`, `services/analytics_api/app/routers/ppv.py` | `DI-10A581D2` |
| `DO-8A25D759` | `libs/analytics/ncda_export.py` | `DI-C2A206A3` |
| `DO-D4F4A538` | `services/ui/src/app/audit/ppv/page.tsx`, `services/ui/src/components/audit/PpvBenchmarkCard.tsx` | `DI-9D080448`, `DI-10A581D2` |

VTs (each will run after the implementation lands):

| VT | Verifies | Tests | Test files |
|---|---|---|---|
| `VT-F4B33EA4` | `DI-9D080448` | `DO-AE402D85` | `tests/analytics/test_ppv.py`, `tests/cypher/test_ppv_queries.py` |
| `VT-F79DC6AC` | `DI-10A581D2` | `DO-2FA6DB4B` | `tests/analytics/test_subscription_cohort.py`, `tests/cypher/test_subscription_audit_queries.py`, `tests/analytics_api/test_ppv_router.py` |
| `VT-89618F57` | `DI-C2A206A3` | `DO-8A25D759` | `tests/analytics/test_ncda_export.py` |
| `VT-22E4478D` | `DI-9D080448`, `DI-10A581D2` | `DO-D4F4A538` | `services/ui/src/__tests__/ppv-dashboard-chrome.test.tsx` |

When the implementing developer lands the code, the file-level
`Atlas trace:` headers MUST point at the DOs above, and the VTs
should be run via Phase 15e to populate `execution_history` in
Atlas.

## Risk and safety notes

- This work mitigates `R-732325CF` (the 2WW undercount risk).
  The existing two-pass referral matching, NULL-on-no-referral
  contract, and `confirmed_cancers_via_2ww_pct` exposure are
  upstream of PPV and MUST remain in place.
- PPV is a quality-improvement signal, not a clinical decision
  signal. The PPV dashboard MUST NOT be presented as an
  alert / safety indicator; it is benchmarked against national
  reference values for review.
- Any patient-readable output (UI labels, exported summary text)
  follows the health-literacy rule: reading age 9-11, plain
  English, no acronyms on first use ("Positive Predictive Value
  (PPV)").
