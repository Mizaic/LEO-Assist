"""Prompts for lightweight extraction quality checks.

Atlas trace:
  DO: DO-8620A68B
  DI: DI-5A802C83
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-8620A68B")
"""

EXTRACTION_CHECK_SYSTEM_V1 = """You are a clinical extraction quality checker.

Task:
- Review extracted entities against the encounter text.
- Return JSON only.
- Keep decisions conservative and evidence-based.

Rules:
1) Drop entities that are template noise, admin checklist text, or non-clinical imports.
2) Correct assertion when a mention is family or historical, not present.
3) Correct semantic label when clearly wrong.
4) Add only clinically meaningful spans that are explicitly present in the text.
5) Do not infer a diagnosis from exclusion or screening language.
6) Do not add entities that are not in the encounter text.
7) Referral workflow text is not a confirmed diagnosis.
   Example: "seen in fast track suspected colorectal cancer clinic" does not create a disorder entity.

Output JSON:
{
  "drop": [int],
  "correct_assertion": [{"index": int, "assertion": "present|absent|historical|family|planned|possible|hypothetical|declined|cancelled"}],
  "correct_label": [{"index": int, "label": "disorder|finding|procedure|observable entity|substance|product|situation|event|qualifier value|body structure"}],
  "add": [{"text": str, "label": str, "assertion": str, "lookup_term": str}]
}

If no changes are needed, return empty arrays for all fields.
"""


EXTRACTION_CHECK_SYSTEM_V2 = """You are a clinical extraction quality checker.

Task:
- Review extracted entities and relations against the encounter text.
- Return JSON only.
- Keep decisions conservative and evidence-based.

Rules:
1) Drop entities that are template noise, admin checklist text, or non-clinical imports.
2) Correct assertion when a mention is family or historical, not present.
3) Correct semantic label when clearly wrong.
4) Add only clinically meaningful spans explicitly present in the text.
5) Correct relation links when body site or qualifier links are wrong.
6) Add relation links only when the text explicitly supports them.
7) Do not infer a diagnosis from exclusion or screening language.
8) Do not add entities or relations that are not in the encounter text.
9) Referral workflow text is not a confirmed diagnosis.

Output JSON:
{
  "drop": [int],
  "correct_assertion": [{"index": int, "assertion": "present|absent|historical|family|planned|possible|hypothetical|declined|cancelled"}],
  "correct_label": [{"index": int, "label": "disorder|finding|procedure|observable entity|substance|product|situation|event|qualifier value|body structure"}],
  "add": [{"text": str, "label": str, "assertion": str, "lookup_term": str}],
  "correct_relation": [{"index": int, "relations": [{"type": str, "target_idx": int, "target_text": str, "confidence": float}]}],
  "add_relation": [{"index": int, "type": str, "target_idx": int, "target_text": str, "confidence": float}]
}

If no changes are needed, return empty arrays for all fields.
"""


EXTRACTION_CHECK_EXAMPLES_V1 = [
    {
        "id": "ec-a",
        "category": "template_noise",
        "description": "Counselling checkbox line should be dropped",
        "core": True,
        "model_scope": "any",
        "input": "Encounter: Discussed smoking cessation and leaflet given. Entities: [{text: 'smoking cessation leaflet', label: 'procedure'}]",
        "output": '{"drop":[0],"correct_assertion":[],"correct_label":[],"add":[]}',
    },
    {
        "id": "ec-b",
        "category": "dmd_noise",
        "description": "DM+D style product line should be dropped",
        "core": True,
        "model_scope": "any",
        "input": "Encounter: Salbutamol 100 mcg/dose inhaler. Entities: [{text:'salbutamol 100 mcg/dose inhaler',label:'disorder'}]",
        "output": '{"drop":[0],"correct_assertion":[],"correct_label":[],"add":[]}',
    },
    {
        "id": "ec-c",
        "category": "assertion_fix",
        "description": "Family history should be situation present",
        "core": True,
        "model_scope": "any",
        "input": "Encounter: Family history of bowel cancer. Entities: [{text:'bowel cancer',label:'disorder',assertion:'present'}]",
        "output": '{"drop":[],"correct_assertion":[{"index":0,"assertion":"present"}],"correct_label":[{"index":0,"label":"situation"}],"add":[]}',
    },
    {
        "id": "ec-d",
        "category": "assertion_fix",
        "description": "Past history should be historical",
        "core": True,
        "model_scope": "any",
        "input": "Encounter: Previous myocardial infarction in 2019. Entities: [{text:'myocardial infarction',label:'disorder',assertion:'present'}]",
        "output": '{"drop":[],"correct_assertion":[{"index":0,"assertion":"historical"}],"correct_label":[],"add":[]}',
    },
    {
        "id": "ec-e",
        "category": "label_fix",
        "description": "Medication mislabelled as disorder",
        "core": True,
        "model_scope": "any",
        "input": "Encounter: Started metformin 500mg. Entities: [{text:'metformin',label:'disorder',assertion:'present'}]",
        "output": '{"drop":[],"correct_assertion":[],"correct_label":[{"index":0,"label":"substance"}],"add":[]}',
    },
    {
        "id": "ec-f",
        "category": "missed_surface_form",
        "description": "Add explicit missed finding",
        "core": True,
        "model_scope": "any",
        "input": "Encounter: Iron deficiency anaemia discussed. Entities: []",
        "output": '{"drop":[],"correct_assertion":[],"correct_label":[],"add":[{"text":"iron deficiency anaemia","label":"disorder","assertion":"present","lookup_term":"iron deficiency anaemia"}]}',
    },
    {
        "id": "ec-g",
        "category": "screening_exclusion",
        "description": "No disease inference from exclusion language",
        "core": True,
        "model_scope": "any",
        "input": "Encounter: No red flags for cancer. Entities: []",
        "output": '{"drop":[],"correct_assertion":[],"correct_label":[],"add":[]}',
    },
    {
        "id": "ec-h",
        "category": "admin_import",
        "description": "Bare coded import lines are dropped",
        "core": True,
        "model_scope": "any",
        "input": "Encounter: Fast track referral: XA12345. Entities: [{text:'XA12345',label:'situation'}]",
        "output": '{"drop":[0],"correct_assertion":[],"correct_label":[],"add":[]}',
    },
    {
        "id": "ec-i",
        "category": "label_fix",
        "description": "Referral action should be procedure",
        "core": True,
        "model_scope": "any",
        "input": "Encounter: Urgent referral arranged. Entities: [{text:'urgent referral',label:'situation',assertion:'planned'}]",
        "output": '{"drop":[],"correct_assertion":[],"correct_label":[{"index":0,"label":"procedure"}],"add":[]}',
    },
    {
        "id": "ec-j",
        "category": "no_change",
        "description": "Correct extraction should remain unchanged",
        "core": True,
        "model_scope": "any",
        "input": "Encounter: Type 2 diabetes mellitus reviewed. Entities: [{text:'Type 2 diabetes mellitus',label:'disorder',assertion:'present'}]",
        "output": '{"drop":[],"correct_assertion":[],"correct_label":[],"add":[]}',
    },
]

EXTRACTION_CHECK_EXAMPLES_V2 = EXTRACTION_CHECK_EXAMPLES_V1 + [
    {
        "id": "ec-v2-a",
        "category": "relation_add",
        "description": "Add finding_site relation for numbness in arm",
        "core": True,
        "model_scope": "any",
        "input": "Encounter: no numbness in arm. Entities: [{text:'numbness',label:'finding',assertion:'absent'},{text:'arm',label:'body structure',assertion:'present'}]",
        "output": '{"drop":[],"correct_assertion":[],"correct_label":[],"add":[],"correct_relation":[],"add_relation":[{"index":0,"type":"finding_site","target_idx":1,"target_text":"arm","confidence":0.94}]}',
    },
    {
        "id": "ec-v2-b",
        "category": "relation_correct",
        "description": "Correct wrong relation target",
        "core": True,
        "model_scope": "any",
        "input": "Encounter: severe abdominal pain. Entities: [{text:'pain',label:'finding'},{text:'abdomen',label:'body structure'},{text:'severe',label:'qualifier value'}] Relations: pain->severe finding_site",
        "output": '{"drop":[],"correct_assertion":[],"correct_label":[],"add":[],"correct_relation":[{"index":0,"relations":[{"type":"finding_site","target_idx":1,"target_text":"abdomen","confidence":0.93},{"type":"qualifies","target_idx":2,"target_text":"severe","confidence":0.90}]}],"add_relation":[]}',
    },
]
