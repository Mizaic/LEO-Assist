"""Prompt for relation linking between extracted entities."""

RELATION_LINKING_SYSTEM_V1 = """You are a clinical relation-linking checker.

Task:
- Review extracted entities against encounter text.
- Add explicit relations between entities when wording supports it.
- Return JSON only.

Rules:
1) Create relations only when the text explicitly supports the link.
2) Use finding_site when an anatomy term specifies where a finding/procedure occurs.
3) Use qualifies for severity, frequency, and qualifier-value context.
4) Do not invent entities or relations not present in the text.
5) Keep relation direction as head_idx -> tail_idx.
6) If a body structure is only meaningful as a linked site, include it in suppress.

Allowed relation types:
- finding_site
- interprets
- component_of
- qualifies
- associated_finding

Output JSON:
{
  "relations": [
    {"head_idx": int, "tail_idx": int, "type": str, "confidence": float}
  ],
  "suppress": [int]
}

If no changes are needed, return {"relations":[],"suppress":[]}.
"""


RELATION_LINKING_EXAMPLES_V1 = [
    {
        "id": "rl-a",
        "category": "finding_site",
        "description": "Numbness linked to arm body site",
        "core": True,
        "model_scope": "any",
        "input": "Encounter: no numbness in arm. Entities: [{text:'numbness',label:'finding'},{text:'arm',label:'body structure'}]",
        "output": '{"relations":[{"head_idx":0,"tail_idx":1,"type":"finding_site","confidence":0.95}],"suppress":[1]}',
    },
    {
        "id": "rl-b",
        "category": "finding_site",
        "description": "Pruritus linked to penile structure",
        "core": True,
        "model_scope": "any",
        "input": "Encounter: penile pruritus with minor bleeding. Entities: [{text:'pruritus',label:'finding'},{text:'penile structure',label:'body structure'},{text:'bleeding',label:'finding'}]",
        "output": '{"relations":[{"head_idx":0,"tail_idx":1,"type":"finding_site","confidence":0.92}],"suppress":[1]}',
    },
    {
        "id": "rl-c",
        "category": "qualifies",
        "description": "Qualifier value modifies finding",
        "core": True,
        "model_scope": "any",
        "input": "Encounter: severe abdominal pain. Entities: [{text:'pain',label:'finding'},{text:'severe',label:'qualifier value'},{text:'abdomen',label:'body structure'}]",
        "output": '{"relations":[{"head_idx":0,"tail_idx":1,"type":"qualifies","confidence":0.91},{"head_idx":0,"tail_idx":2,"type":"finding_site","confidence":0.94}],"suppress":[2]}',
    },
]
