"""Prompt for relation linking between extracted entities.

Atlas trace:
  DO: DO-49256B13
  Also implements: DO-8620A68B
  DI: DI-044827AD, DI-5A802C83
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-49256B13")
"""

from libs.llm_client.prompt_safety import INJECTION_GUARD

RELATION_LINKING_SYSTEM_V1 = (
    INJECTION_GUARD
    + """You are a clinical relationship validator.

You receive:
- An encounter note
- Extracted entities (some may have SNOMED concept IDs)
- Candidate relations derived from the SNOMED ontology (may be empty)

Your task:
1) For each candidate relation, confirm it only when the encounter text
   supports that the link is about THIS patient.
2) Reject a candidate when the text does not support it, or when it is
   only a general ontology fact with no wording in this note.
3) Add text-only relations that SNOMED did not cover (laterality,
   qualifier words such as severe/mild, or a body site named in the text).

Rules:
1) Create or confirm relations only when the text supports the link.
2) Use finding_site when an anatomy term specifies where a finding or
   procedure occurs.
3) Use qualifies ONLY when a modifier word (severity, frequency, degree --
   e.g. 'severe', 'mild', 'frequent', 'bilateral') directly modifies a
   finding, disorder, or procedure. NEVER use qualifies for two
   co-occurring findings.
4) Do not invent entities. Do not link two findings just because they
   appear in the same note.
5) Keep relation direction as head_idx -> tail_idx.
6) If a body structure is only meaningful as a linked site, include it
   in suppress.

Allowed relation types:
- finding_site
- interprets
- component_of
- qualifies
- associated_finding

Output JSON:
{
  "confirmed": [{"head_idx": int, "tail_idx": int, "type": str, "confidence": float}],
  "rejected": [{"head_idx": int, "tail_idx": int, "reason": str}],
  "additional": [{"head_idx": int, "tail_idx": int, "type": str, "confidence": float}],
  "suppress": [int]
}

If there are no candidates and no text-only links, return
{"confirmed":[],"rejected":[],"additional":[],"suppress":[]}.
"""
)


RELATION_LINKING_EXAMPLES_V1 = [
    {
        "id": "rl-d",
        "category": "qualifies",
        "description": "Co-occurring findings must NOT be linked via qualifies",
        "core": True,
        "model_scope": "any",
        "input": (
            "Encounter: jaundice and weight loss. "
            "Entities: [{text:'jaundice',label:'finding'},{text:'weight loss',label:'finding'}] "
            "Candidates: []"
        ),
        "output": '{"confirmed":[],"rejected":[],"additional":[],"suppress":[]}',
    },
    {
        "id": "rl-e",
        "category": "finding_site",
        "description": "Confirm a SNOMED finding_site when the note names the site",
        "core": True,
        "model_scope": "any",
        "input": (
            "Encounter: no numbness in arm. "
            "Entities: [{text:'numbness',label:'finding'},{text:'arm',label:'body structure'}] "
            "Candidates: [{head_idx:0,tail_idx:1,type:'finding_site'}]"
        ),
        "output": (
            '{"confirmed":[{"head_idx":0,"tail_idx":1,"type":"finding_site",'
            '"confidence":0.95}],"rejected":[],"additional":[],"suppress":[1]}'
        ),
    },
    {
        "id": "rl-a",
        "category": "finding_site",
        "description": "Numbness linked to arm body site",
        "core": True,
        "model_scope": "any",
        "input": "Encounter: no numbness in arm. Entities: [{text:'numbness',label:'finding'},{text:'arm',label:'body structure'}]",
        "output": '{"confirmed":[],"rejected":[],"additional":[{"head_idx":0,"tail_idx":1,"type":"finding_site","confidence":0.95}],"suppress":[1]}',
    },
    {
        "id": "rl-b",
        "category": "finding_site",
        "description": "Pruritus linked to penile structure",
        "core": True,
        "model_scope": "any",
        "input": "Encounter: penile pruritus with minor bleeding. Entities: [{text:'pruritus',label:'finding'},{text:'penile structure',label:'body structure'},{text:'bleeding',label:'finding'}]",
        "output": '{"confirmed":[],"rejected":[],"additional":[{"head_idx":0,"tail_idx":1,"type":"finding_site","confidence":0.92}],"suppress":[1]}',
    },
    {
        "id": "rl-c",
        "category": "qualifies",
        "description": "Qualifier value modifies finding",
        "core": True,
        "model_scope": "any",
        "input": "Encounter: severe abdominal pain. Entities: [{text:'pain',label:'finding'},{text:'severe',label:'qualifier value'},{text:'abdomen',label:'body structure'}]",
        "output": '{"confirmed":[],"rejected":[],"additional":[{"head_idx":0,"tail_idx":1,"type":"qualifies","confidence":0.91},{"head_idx":0,"tail_idx":2,"type":"finding_site","confidence":0.94}],"suppress":[2]}',
    },
]
