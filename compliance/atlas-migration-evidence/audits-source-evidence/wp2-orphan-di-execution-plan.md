# WP2 Orphan DI Execution Plan

137 Design Inputs across 52 User Needs currently have no linked Design
Output. This plan breaks the closure work into thematic batches. For each
batch the owner runs the code-verification step, creates an umbrella DO,
links it to the DIs with an `IMPLEMENTS` edge, and creates a matching VT.

## Process per batch

1. Read the DI set for the batch and the cited source directories.
2. For each DI: verify the code exists and matches the acceptance criteria.
3. If code exists -> include DI in the umbrella DO.
4. If code does not exist or is materially incomplete -> add a
   `code-gap` entry to `improvements-backlog.md` with the DI ID, what is
   missing, and estimated effort.
5. Create one umbrella DO per batch:
   `DO title: "<UN theme> implementation surface"`
   Description lists each DI and notes fully / partial / code-gap status.
6. Link the DO to every covered DI with `IMPLEMENTS`.
7. Create one VT per DO with AC aggregated from the DIs it covers.
8. Update `DC-TM-001-traceability-matrix.md` with the new rows.

## Batches (by orphan count descending)

### Batch A - Provenance + audit trail (UN-B2C85448, 6 DIs)
Owner: platform.
DIs:
- DI-B2512CB3 Immutable source-span linkage (span_resolver, :Entity snippet_hash)
- DI-E81545BE Source-text highlight linking (review UI)
- DI-23822663 Assertion evidence text context (context_engine)
- DI-080A2454 7-year retention policy (policy only - code-gap)
- DI-4F67189B Reviewer correction event schema
- DI-09E26C1D Audit trail API

Likely umbrella DO: `Entity provenance and audit trail surface`.
Code-gap notes: DI-080A2454 is policy-only; needs retention enforcement code.

### Batch B - SNOMED coding core (UN-0374FE26, 6 DIs)
DIs: DI-1795254D, DI-4247C7E5, DI-31126C6C, DI-375C7EB1, DI-12015DBC,
DI-88C8BBCD.
Umbrella DO: `NER + SNOMED coding with assertion surface`.
Code-gap notes: F1 gold evaluator (DI-12015DBC) lives in improvements-backlog.

### Batch C - Coding correction review (UN-7D740697, 6 DIs)
DIs: DI-1B8AC856, DI-13F340B9, DI-26CBDB16, DI-04105500, DI-22F4E3CE,
DI-4221A226.
Umbrella DO: `Coding correction review + dependency display`.
Code location to verify: `services/terminology_api`, correction review UI.

### Batch D - Platform architecture + secrets (UN-2C6E6933, 6 DIs)
DIs: DI-A90B19EB, DI-3FDBB57B, DI-2C56591B, DI-6EBF12F1, DI-932C270C,
DI-693FFEEA.
Umbrella DO: `LangGraph executor, AI model registry, Key Vault, CI gates`.
Mostly already implemented; CI gates for function-length need verification.

### Batch E - Plain-language interpretation (UN-575E8DCB, 5 DIs)
DIs: DI-66F1B177, DI-604767B1, DI-A3107424, DI-DA7584D8, DI-69C29EEF.
Code location: interpretation prompts + UI. Safety gates: human-review gate.

### Batch F - Research workspace (UN-47B82B96, 4 DIs)
DIs: DI-DD67ACFF, DI-93162C3C, DI-9DCBC4BA, DI-58988BF2.
Code location to verify: research workspace / cohort builder services.

### Batch G - Patient shortlisting (UN-B70ACD96, 4 DIs)
DIs: DI-143F69EB, DI-4746A178, DI-10BB41E9, DI-1501326A.
Code location: shortlisting service + recall evaluation.

### Batch H - Data-gap disclosure (UN-A949A642, 4 DIs)
DIs: DI-00E16F9E, DI-88F20177, DI-CB3DF3E1, DI-0D7DCC52.
Code location: coverage service + small-cohort suppression logic.

### Batch I - Knowledge base + guidelines (UNs E6195868, 12EEF12D, A412610D,
87CB1498, 319F33F0, 16E151CB, 407F090F, 06388412, 4BD56518, 4AEB2F29,
06FDC315, B9FDC3CA - 24 DIs combined)
Multiple small UNs; bundle by source (NICE, ODS, SNOMED, ConText, surface
forms, guideline authoring). Expect 5-6 umbrella DOs from this group.

### Batch J - Reviewer workflow + change control (UNs F6A0C5BA, ED00ED74,
8659DD53, EA93F7B7, 785DFCDE - 12 DIs combined)
Code location: review + approval + change queue services.

### Batch K - Developer / integration surface (UNs 395B630E, F2372DE0,
9A7C2AA3, 21D88B69, 718B7AF3, 16116C5F - 13 DIs combined)
Code location: API layer + sandbox + onboarding wizard.

### Batch L - Clinical Intelligence output DIs (UNs 1A6F1E0E, F3300833,
9206EFF0, 2266BDAE, 67663AAF, 06FD3F7D, 9396A2FA - 16 DIs combined)
Code location: clinical intelligence subgraphs + view rendering.

### Batch M - Operations + admin + DQ (UNs BB817C74, 3376B57D, 4DCD5891,
7294050B, 9E66C163, FB2DA651, 66396DEA, EA93F7B7 - 14 DIs combined)
Code location: Mission Control dashboard + DQ engine + admin.

### Batch N - NLP pipeline improvements (UNs 5236129E, 1AC15812, 299200A0,
94833CA3, 5C67AAD9 - 10 DIs combined)
Code location: training pipeline + audit agent + FHIR exposure.

### Batch O - Unassigned catch-all
Any DIs not covered by the above; expected to be zero after the batches
above are processed.

## Success metrics

- Atlas `get_design_control_stats` reports `linkedToDO` at or near 221/221.
- `DO coverage = (DOs with VT)` stays at 100% (tighten after each batch).
- `improvements-backlog.md` lists every DI flagged `code-gap` with a
  remediation plan.
- New `design-controls/audits/batch-wp2-<letter>.md` file per batch with
  verdict per DI.
