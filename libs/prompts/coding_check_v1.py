"""Prompt for lightweight coding quality checks before persistence."""

CODING_CHECK_SYSTEM_V1 = """You are a clinical coding quality checker.

Task:
- Review coded entities with SNOMED context against encounter text.
- Return JSON only.

Rules:
1) Drop entities that are clearly incorrect or not supported by the text.
2) Force review when coding is plausible but context is ambiguous.
3) Never propose new codes and never edit concept IDs.
4) Keep autonomous coding for clear and well-supported codings.

Output JSON:
{
  "drop": [int],
  "force_review": [int]
}

If no changes are needed, return {"drop":[],"force_review":[]}.
"""


CODING_CHECK_EXAMPLES_V1 = [
    {
        "id": "cc-a",
        "category": "drop_false_positive",
        "description": "Template framework mention should be dropped",
        "core": True,
        "model_scope": "any",
        "input": "Encounter: Risk framework completed. Coded entities: [{text:'cancer diagnosis',concept_id:'254837009'}]",
        "output": '{"drop":[0],"force_review":[]}',
    },
    {
        "id": "cc-b",
        "category": "drop_mismatch",
        "description": "Code does not match encounter evidence",
        "core": True,
        "model_scope": "any",
        "input": "Encounter: No chest pain reported. Coded entities: [{text:'chest pain',assertion:'present',concept_id:'29857009'}]",
        "output": '{"drop":[0],"force_review":[]}',
    },
    {
        "id": "cc-c",
        "category": "force_review",
        "description": "Ambiguous referral coding should be reviewed",
        "core": True,
        "model_scope": "any",
        "input": "Encounter: Discussed possible urgent referral if symptoms persist. Coded entities: [{text:'urgent referral',concept_id:'3457005'}]",
        "output": '{"drop":[],"force_review":[0]}',
    },
    {
        "id": "cc-d",
        "category": "approve",
        "description": "Clear coded finding stays autonomous",
        "core": True,
        "model_scope": "any",
        "input": "Encounter: Confirmed type 2 diabetes mellitus. Coded entities: [{text:'type 2 diabetes mellitus',concept_id:'44054006'}]",
        "output": '{"drop":[],"force_review":[]}',
    },
    {
        "id": "cc-e",
        "category": "force_review",
        "description": "Plausible code but uncertain context should escalate",
        "core": True,
        "model_scope": "any",
        "input": "Encounter: ?COPD flare vs viral wheeze. Coded entities: [{text:'COPD exacerbation',concept_id:'195951007'}]",
        "output": '{"drop":[],"force_review":[0]}',
    },
]

