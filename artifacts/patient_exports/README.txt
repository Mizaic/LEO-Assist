Patient identifier exports (CSV/JSON) from Neo4j are generated locally and must not be committed.

Generate a list of practice patient identifiers (NHS numbers where configured as :Patient.id)
with at least one coded cancer-diagnosis SNOMED hit on :DOCUMENTS:

  python3 scripts/export_patients_with_cancer_diagnosis.py --output artifacts/patient_exports/out.csv

Requires secrets/.env.config and secrets/.env.secrets (Neo4j credentials).
