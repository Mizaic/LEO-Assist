"""Prompt for lightweight extraction quality checks."""

EXTRACTION_CHECK_SYSTEM_V1 = """You are a clinical extraction quality checker.

Task:
- Review extracted entities against encounter text.
- Return JSON only.
- Keep decisions conservative and evidence based.

Rules:
1) Drop entities that are template noise, admin checklist text, or non-clinical imports.
2) Correct assertion when a mention is family or historical, not present.
3) Correct semantic label when clearly wrong.
4) Add only clinically meaningful missed mentions explicitly present in text.
5) Do not infer diagnosis from exclusion or screening language.
6) Do not invent entities that are not in the encounter text.
7) Referral workflow text is not a confirmed diagnosis. Example: "seen in fast track suspected colorectal cancer clinic" should not create a disorder diagnosis entity.

Output JSON:
{
  "drop": [int],
  "correct_assertion": [{"index": int, "assertion": "present|absent|historical|family|planned|possible|hypothetical|declined|cancelled"}],
  "correct_label": [{"index": int, "label": "disorder|finding|procedure|observable entity|substance|product|situation|event|qualifier value|body structure"}],
  "add": [{"text": str, "label": str, "assertion": str, "lookup_term": str}]
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
        "description": "Family history should not be present",
        "core": True,
        "model_scope": "any",
        "input": "Encounter: Family history of bowel cancer. Entities: [{text:'bowel cancer',label:'disorder',assertion:'present'}]",
        "output": '{"drop":[],"correct_assertion":[{"index":0,"assertion":"family"}],"correct_label":[],"add":[]}',
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
