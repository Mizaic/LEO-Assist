# UN-89E2AE36 VT confirmation

Date: 2026-05-19
Executed by: cursor-agent
Environment: local

## Summary

- 30/30 verification tests in the UN-89E2AE36 subtree have automated evidence files that cite the VT dcId.
- 30/30 verification tests have a fresh Atlas `record_verification_run` result of `pass`.
- `get_traceability_gaps(product_id="PROD-LEO-CLINICAL-DECISION-SUPPORT-20260515-118182E4")` returned no orphan design inputs and no orphan design outputs.
- `DO-416BA91D`, `DO-728930A1`, and `DO-4641EEE1` source references were updated in Atlas to include the new evidence files.

## Local Test Commands

```bash
cd services/ui && npx jest --testPathPatterns "extraction-scenarios-chrome|extraction-scenarios-run-lifecycle" --no-coverage
```

Result: 22 passed, 0 failed.

```bash
python3 -m pytest tests/test_clinical_extraction_scenario_fixtures.py tests/test_extraction_scenario_verification_vt29880cc8.py tests/test_pubsub_pipeline_neo4j_handoff_vt_b193debb.py tests/test_fact_finding_verification_vts.py tests/contracts/test_fact_finding_traceability.py tests/test_cds_pipeline_verification_vts.py -v
```

Result: 51 passed, 0 failed, 1 warning.

## Evidence Matrix

```csv
vt_id,title,test_file,test_command,status
VT-24D7A846,Extraction scenarios admin UI chrome,services/ui/src/__tests__/extraction-scenarios-chrome.test.ts,npx jest --testPathPatterns "extraction-scenarios-chrome|extraction-scenarios-run-lifecycle" --no-coverage,pass
VT-C0D7D50C,Extraction validation run lifecycle and Neo4j persistence,services/ui/src/__tests__/extraction-scenarios-run-lifecycle.test.ts,npx jest --testPathPatterns "extraction-scenarios-chrome|extraction-scenarios-run-lifecycle" --no-coverage,pass
VT-29880CC8,Extraction against expected strings,tests/test_extraction_scenario_verification_vt29880cc8.py; tests/test_clinical_extraction_scenario_fixtures.py,python3 -m pytest <VT pytest bundle> -v,pass
VT-36FDBFAE,Fact-finding traceability,tests/contracts/test_fact_finding_traceability.py,python3 -m pytest tests/test_fact_finding_verification_vts.py tests/contracts/test_fact_finding_traceability.py -v,pass
VT-575882D6,Extraction source text loading,tests/test_fact_finding_verification_vts.py,python3 -m pytest tests/test_fact_finding_verification_vts.py tests/contracts/test_fact_finding_traceability.py -v,pass
VT-948B7CD4,Source text before coding,tests/test_fact_finding_verification_vts.py,python3 -m pytest tests/test_fact_finding_verification_vts.py tests/contracts/test_fact_finding_traceability.py -v,pass
VT-08DC830C,Missing source text failure,tests/test_fact_finding_verification_vts.py,python3 -m pytest tests/test_fact_finding_verification_vts.py tests/contracts/test_fact_finding_traceability.py -v,pass
VT-F9438948,Unavailable evidence marker,tests/test_fact_finding_verification_vts.py,python3 -m pytest tests/test_fact_finding_verification_vts.py tests/contracts/test_fact_finding_traceability.py -v,pass
VT-708F6642,Extracted string source reference,tests/test_fact_finding_verification_vts.py,python3 -m pytest tests/test_fact_finding_verification_vts.py tests/contracts/test_fact_finding_traceability.py -v,pass
VT-1940CF13,Extracted string source location,tests/test_fact_finding_verification_vts.py,python3 -m pytest tests/test_fact_finding_verification_vts.py tests/contracts/test_fact_finding_traceability.py -v,pass
VT-B1C9FF0B,Source evidence before coding,tests/test_fact_finding_verification_vts.py,python3 -m pytest tests/test_fact_finding_verification_vts.py tests/contracts/test_fact_finding_traceability.py -v,pass
VT-5FF4FE03,No fact input empty output,tests/test_fact_finding_verification_vts.py,python3 -m pytest tests/test_fact_finding_verification_vts.py tests/contracts/test_fact_finding_traceability.py -v,pass
VT-1A36E7D0,Terms text before coding,tests/test_fact_finding_verification_vts.py,python3 -m pytest tests/test_fact_finding_verification_vts.py tests/contracts/test_fact_finding_traceability.py -v,pass
VT-54ED1672,Clinical fact string emission,tests/test_fact_finding_verification_vts.py,python3 -m pytest tests/test_fact_finding_verification_vts.py tests/contracts/test_fact_finding_traceability.py -v,pass
VT-87B6067E,Unsupported strings blocked,tests/test_fact_finding_verification_vts.py,python3 -m pytest tests/test_fact_finding_verification_vts.py tests/contracts/test_fact_finding_traceability.py -v,pass
VT-264F90B7,Extraction audit identity,tests/test_fact_finding_verification_vts.py,python3 -m pytest tests/test_fact_finding_verification_vts.py tests/contracts/test_fact_finding_traceability.py -v,pass
VT-27EF1B27,Extraction audit metadata,tests/test_fact_finding_verification_vts.py,python3 -m pytest tests/test_fact_finding_verification_vts.py tests/contracts/test_fact_finding_traceability.py -v,pass
VT-895C7DD0,Failed extraction audit logging,tests/test_fact_finding_verification_vts.py,python3 -m pytest tests/test_fact_finding_verification_vts.py tests/contracts/test_fact_finding_traceability.py -v,pass
VT-BF5E13E3,Audit text minimisation,tests/test_fact_finding_verification_vts.py,python3 -m pytest tests/test_fact_finding_verification_vts.py tests/contracts/test_fact_finding_traceability.py -v,pass
VT-B193DEBB,Pub/sub pipeline Neo4j handoff,tests/test_pubsub_pipeline_neo4j_handoff_vt_b193debb.py,python3 -m pytest tests/test_cds_pipeline_verification_vts.py tests/test_pubsub_pipeline_neo4j_handoff_vt_b193debb.py -v,pass
VT-E5F38835,Completion event run status,tests/test_cds_pipeline_verification_vts.py,python3 -m pytest tests/test_cds_pipeline_verification_vts.py tests/test_pubsub_pipeline_neo4j_handoff_vt_b193debb.py -v,pass
VT-EEBF460C,Completion readback context,tests/test_cds_pipeline_verification_vts.py,python3 -m pytest tests/test_cds_pipeline_verification_vts.py tests/test_pubsub_pipeline_neo4j_handoff_vt_b193debb.py -v,pass
VT-1B3A081F,Event excludes clinical payload,tests/test_cds_pipeline_verification_vts.py,python3 -m pytest tests/test_cds_pipeline_verification_vts.py tests/test_pubsub_pipeline_neo4j_handoff_vt_b193debb.py -v,pass
VT-B91EE9F2,Worker receives job messages,tests/test_cds_pipeline_verification_vts.py,python3 -m pytest tests/test_cds_pipeline_verification_vts.py tests/test_pubsub_pipeline_neo4j_handoff_vt_b193debb.py -v,pass
VT-37607F4B,Valid job starts workflow,tests/test_cds_pipeline_verification_vts.py,python3 -m pytest tests/test_cds_pipeline_verification_vts.py tests/test_pubsub_pipeline_neo4j_handoff_vt_b193debb.py -v,pass
VT-CBB3C8E8,Job message context fields,tests/test_cds_pipeline_verification_vts.py,python3 -m pytest tests/test_cds_pipeline_verification_vts.py tests/test_pubsub_pipeline_neo4j_handoff_vt_b193debb.py -v,pass
VT-BE8D8651,Invalid job fails safely,tests/test_cds_pipeline_verification_vts.py,python3 -m pytest tests/test_cds_pipeline_verification_vts.py tests/test_pubsub_pipeline_neo4j_handoff_vt_b193debb.py -v,pass
VT-36E2C3B1,Results write before completion,tests/test_cds_pipeline_verification_vts.py,python3 -m pytest tests/test_cds_pipeline_verification_vts.py tests/test_pubsub_pipeline_neo4j_handoff_vt_b193debb.py -v,pass
VT-3902EBF7,Neo4j failure blocks success,tests/test_cds_pipeline_verification_vts.py,python3 -m pytest tests/test_cds_pipeline_verification_vts.py tests/test_pubsub_pipeline_neo4j_handoff_vt_b193debb.py -v,pass
VT-F9794391,Audit write before completion,tests/test_cds_pipeline_verification_vts.py,python3 -m pytest tests/test_cds_pipeline_verification_vts.py tests/test_pubsub_pipeline_neo4j_handoff_vt_b193debb.py -v,pass
```
