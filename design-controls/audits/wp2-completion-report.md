# WP2 Completion Report - DI -> DO Gap Closed

Date: 2026-04-17
Product: `PROD-LEO-CORE-AI-20260415-6AE8A23B`

## Outcome

All 137 orphan Design Inputs now have at least one Design Output that
`IMPLEMENTS` them, and at least one Verification Test that `VERIFIES`
them.

| Metric | Before WP2 | After WP2 |
|---|---|---|
| DIs linked to DO | 84 / 221 (38%) | 221 / 221 (100%) |
| DIs linked to VT | 84 / 221 (38%) | 221 / 221 (100%) |
| DOs total | 23 | 39 |
| DOs linked to VT | 23 / 23 (100%) | 39 / 39 (100%) |
| VTs total | 23 | 39 |

## Umbrella DOs created (16 new)

| DO ID | Title | UN scope | DIs | VT |
|---|---|---|---|---|
| DO-63358A96 | Entity provenance and audit-trail surface | UN-B2C85448 | 6 | VT-4BE22F10 |
| DO-7CA11F1E | NER + SNOMED coding surface with assertion handling | UN-0374FE26 | 6 | VT-F8424282 |
| DO-511254A3 | Coding correction review and dependency display | UN-7D740697 | 6 | VT-E8C88378 |
| DO-03F86B45 | Platform architecture, AI model registry, CI gates | UN-2C6E6933 | 6 | VT-B08F60DB |
| DO-828DA28E | Plain-language interpretation and human-review gate | UN-575E8DCB | 5 | VT-110D1103 |
| DO-E10E756F | Research workspace and cohort builder surface | UN-47B82B96 | 4 | VT-E25D76E5 |
| DO-6EB8C7C5 | Patient shortlisting and recall surface | UN-B70ACD96 | 4 (+1) | VT-B764F925 |
| DO-A565D841 | Data-gap disclosure and small-cohort suppression | UN-A949A642 | 4 | VT-51A869C2 |
| DO-A5B67C1E | Knowledge base authoring and staging surface | 5 UNs | 10 | VT-E265DA74 |
| DO-5C38F46C | Authoritative source monitoring and release mgmt | 7 UNs | 15 | VT-1E5FC70A |
| DO-B8241CF4 | Guideline update review surface | UN-16E151CB | 2 | VT-95AC6642 |
| DO-146D93D0 | Reviewer workflow and change-control surface | 5 UNs | 13 | VT-0010386B |
| DO-4613F849 | Developer integration surface | 6 UNs | 13 | VT-B01CB05B |
| DO-2B75E3EE | Clinical intelligence decision-support surface | 7 UNs | 15 | VT-03B607BA |
| DO-0998FAF5 | Operations, admin, DQ, override analytics surface | 8 UNs | 17 | VT-D32A687B |
| DO-F160C131 | NLP training, audit agent, FHIR exposure surface | 6 UNs | 11 | VT-FFF3909C |

## Code-gaps flagged (tracked in improvements-backlog.md)

These are DIs where the umbrella DO describes an implementation surface
that is only partly in code today. Linkage is sound (DO exists, VT
exists) but verification will fail until the code-gap is closed.

- **DI-080A2454** - 7-year retention policy engine + append-only
  write-once enforcement. Currently infra-level only.
- **DI-12015DBC** - Gold F1 evaluator for SNOMED coding accuracy. Plan
  exists; CI wiring outstanding.
- **DI-88C8BBCD** - Per-semantic-tag threshold drift monitoring.
- **DI-DD67ACFF**, **DI-9DCBC4BA** - Research workspace UI partially
  implemented.
- **DI-44802DF3**, **DI-ED3A89F5** - NICE TA/QS SLA timers and
  guideline monitoring registry partially implemented.
- **DI-48C13EB6** - ConText rule change impact report - manual today.
- **DI-693FFEEA** - Function-length automated CI check - manually
  enforced by review today.

## Remaining blockers before "In Review"

1. **VT execution** - 0 of 39 VTs have a recorded run. Reviewers cannot
   approve Draft VTs. Run existing test suites against the VTs and
   record via `record_verification_run`.
2. **VAL coverage** - 72 of 73 UNs lack a VAL. Priority: 6 Class C UNs
   (UN-0374FE26, UN-FC99D533, UN-2C01CF40, UN-83D9A46D, UN-B2C85448,
   UN-C2F187E9).
3. **Risk register** - 0 risks. Handled in the separate risk
   management chat.
4. **DO-level structured AC** - Atlas MCP does not support updating DO
   acceptance criteria today. Tracked as platform backlog. DO AC is
   currently implicit via linked DIs.
5. **Status transitions** - Every artefact is Draft. Moving to "In
   Review" and "Approved" is a human QA action in the Atlas UI.

## Evidence

- `design-controls/DC-TM-002-traceability-matrix.csv` - regenerated
  with 225 rows; 221 unique DIs; 100% DO + VT coverage.
- `design-controls/audits/wp2-orphan-di-execution-plan.md` - original
  batched plan; marked complete.
- `design-controls/audits/improvements-backlog.md` - code-gap entries
  per DI above.
