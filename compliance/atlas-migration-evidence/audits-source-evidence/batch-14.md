# Batch 14 -- Pathway, referral, episode, MDT, guideline UNs grouped

Product: `PROD-LEO-CORE-AI-20260415-6AE8A23B`
Scope: 33 DIs across 12 UNs. Thematic report; per-DI verdicts in the
appendix.

## Theme A -- Episode construction, classification and quality (UN-FC99D533 + UN-2C01CF40)
DIs: DI-FF9C74E2, DI-37DDAADE, DI-4885D9FF, DI-8C236A1A, DI-BD696225,
DI-736B698B, DI-1206D9E8, DI-A0579B64, DI-C7A810AA.

Evidence:
- `libs/pipeline_graph/subgraphs/episode.py`
- `libs/prompts/episode_builder_v1.py`, `episode_builder_output_schema.py`
- `libs/dq/episodes.py`
- `tests/test_episode_builder.py`

Verdicts:
- DI-FF9C74E2 Deterministic episode construction: partial (subgraph exists;
  determinism not guaranteed via hash or pinned seed).
- DI-37DDAADE Classification status schema: partial.
- DI-4885D9FF Timeline + gap highlighting: partial.
- DI-8C236A1A Method disclosure (rule vs LLM): partial.
- DI-BD696225 Human-review gate before audit reporting use: missing (no
  explicit block on unreviewed episodes).
- DI-736B698B 85% F1 accuracy gate: missing (no evaluator threshold).
- DI-1206D9E8 Temporal quality checks: partial (`libs/dq/episodes.py`).
- DI-A0579B64 Block flagged episodes from reporting until resolved: missing.
- DI-C7A810AA Low-confidence flagging + intra-episode contradictions: partial.

## Theme B -- Pathway intervals + waiting times (UN-5C67AAD9 + UN-D92EB141)
DIs: DI-F3FD2B63, DI-B9109EF5, DI-EE4E6477, DI-35494904, DI-BA2C8F3E,
DI-94359E76.

Evidence:
- `services/analytics_api/app/routers/imd.py`, `_audit_helpers.py`
- `libs/cypher/admin_queries.py`
- `services/fhir_api/app/services/benchmark_loader.py`
- `scripts/build_ncda_*.py`, `verify_ncda_benchmarks.py`

Verdicts:
- DI-F3FD2B63 Configurable pathway intervals + breach detection: partial.
- DI-EE4E6477 HITL gate on pathway intervals (use only reviewer-accepted
  milestones): missing.
- DI-35494904 FDS 28d / DTT 31d / RTT 62d panel: partial.
- DI-BA2C8F3E Population dashboards with national benchmarks: partial.
- DI-B9109EF5 Multi-level org/PCN/ICB aggregation: partial (ODS identifiers
  in `services/ods_sync/`).
- DI-94359E76 IMD deprivation analysis: partial (`imd.py` router exists).

## Theme C -- Guideline conformance + rule set management (UN-FBBFD5CB + UN-6D46C832)
DIs: DI-2AFF691F, DI-5E25E872, DI-7913344A, DI-AA8014F9, DI-147C8EF0,
DI-F94EB13F.

Evidence:
- `services/terminology_api/app/services/guideline_evaluator.py`
- `services/terminology_api/app/routers/guidelines.py`
- `libs/pipeline_graph/subgraphs/guidance_rule_extraction_v2_impl.py`

Verdicts:
- DI-2AFF691F Automated guideline conformance: partial.
- DI-5E25E872 <= 5s p95: unknown (no perf test found).
- DI-7913344A Human-review gate for guideline alerts: missing.
- DI-AA8014F9 Programme-level rule-set config without deployment: partial.
- DI-147C8EF0 AI-generated guidance candidate structure: partial.
- DI-F94EB13F Review queue per-candidate decision + bidirectional link:
  missing.

## Theme D -- Triage, clinic prep, MDT (UN-9206EFF0 + UN-67663AAF + UN-9396A2FA)
DIs: DI-37B52693, DI-6C5D77CA, DI-CF03E4EA, DI-6D2B03E0, DI-45F83183,
DI-DBC2399F.

Evidence: referenced in `services/analytics_api/app/routers/dashboards.py`
and UI pages under `services/ui/src/components/pathway/`.

Verdict: mostly partial; MDT summary editability with edit-delta recording
(DI-45F83183) is missing.

## Theme E -- Population research / treatment / investigation (UN-1A6F1E0E + UN-2266BDAE + UN-F3300833)
DIs: DI-76C86329, DI-82D5359B, DI-49403C92, DI-BD826FA6, DI-F235845B,
DI-6079EC71.

Verdict: mostly missing / partial. Non-blocking investigation deviation
acknowledgement with logged rationale (DI-6079EC71) is missing. Neutral
unranked treatment option display (DI-76C86329) is missing as a distinct
surface.

## Appendix -- Per-DI verdict table

| DI | Theme | Verdict |
|----|-------|---------|
| DI-1206D9E8 | A | partial |
| DI-147C8EF0 | C | partial |
| DI-2AFF691F | C | partial |
| DI-35494904 | B | partial |
| DI-37B52693 | D | partial |
| DI-37DDAADE | A | partial |
| DI-45F83183 | D | missing |
| DI-4885D9FF | A | partial |
| DI-49403C92 | E | missing |
| DI-5E25E872 | C | missing |
| DI-6079EC71 | E | missing |
| DI-6C5D77CA | D | partial |
| DI-6D2B03E0 | D | partial |
| DI-736B698B | A | missing |
| DI-7913344A | C | missing |
| DI-76C86329 | E | missing |
| DI-82D5359B | E | partial |
| DI-8C236A1A | A | partial |
| DI-94359E76 | B | partial |
| DI-A0579B64 | A | missing |
| DI-AA8014F9 | C | partial |
| DI-B9109EF5 | B | partial |
| DI-BA2C8F3E | B | partial |
| DI-BD696225 | A | missing |
| DI-BD826FA6 | E | missing |
| DI-C7A810AA | A | partial |
| DI-CF03E4EA | D | partial |
| DI-DBC2399F | D | partial |
| DI-EE4E6477 | B | missing |
| DI-F235845B | E | missing |
| DI-F3FD2B63 | B | partial |
| DI-F94EB13F | C | missing |
| DI-FF9C74E2 | A | partial |

## Atlas actions

Umbrella DOs for themes A, B, C where implementation exists. Backlog entries
for all missing / partial items.
