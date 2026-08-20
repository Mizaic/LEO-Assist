"""Cypher for learned form fingerprints and de-identified few-shots.

Atlas trace:
  DI: DI-0C766F85
  DI: DI-4A012A59
  DO: DO-83EB8C56
  DO: DO-E7824FED
"""

FORM_LEARNING_CONSTRAINTS = [
    (
        "CREATE CONSTRAINT form_fingerprint_hash IF NOT EXISTS "
        "FOR (f:FormFingerprint) REQUIRE f.fingerprint IS UNIQUE"
    ),
    (
        "CREATE CONSTRAINT extraction_few_shot_id IF NOT EXISTS "
        "FOR (e:ExtractionFewShot) REQUIRE e.example_id IS UNIQUE"
    ),
]

UPSERT_FORM_FINGERPRINT = """
MERGE (f:FormFingerprint {fingerprint: $fingerprint})
ON CREATE SET
    f.name = $name,
    f.source = $source,
    f.created_at = datetime()
SET
    f.updated_at = datetime()
RETURN f.name AS name, f.fingerprint AS fingerprint
"""

LIST_FORM_FINGERPRINTS = """
MATCH (f:FormFingerprint)
RETURN f.name AS name, f.fingerprint AS fingerprint
"""

UPSERT_EXTRACTION_FEW_SHOT = """
MERGE (e:ExtractionFewShot {example_id: $example_id})
ON CREATE SET
    e.created_at = datetime()
SET
    e.input = $input,
    e.output = $output,
    e.category = $category,
    e.deidentified = $deidentified,
    e.fingerprint = $fingerprint,
    e.updated_at = datetime()
RETURN e.example_id AS example_id
"""

LIST_EXTRACTION_FEW_SHOTS = """
MATCH (e:ExtractionFewShot)
WHERE e.deidentified = true
RETURN e.input AS input,
       e.output AS output,
       e.category AS category,
       e.deidentified AS deidentified,
       e.fingerprint AS fingerprint
"""
