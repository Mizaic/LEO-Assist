"""Prompt for relation linking between extracted entities.

Atlas trace:
  DO: DO-8E641A9E
  Also: DO-49256B13, DO-8620A68B
  DI: DI-6ACD24D2, DI-044827AD
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-8E641A9E")
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
3) Add text-only relations that SNOMED did not cover when the same
   phrase names both ends (a body site, a lab line, or a named drug).

Rules:
1) Create or confirm relations only when the text supports the link.
2) Use finding_site when an anatomy term specifies where a finding or
   procedure occurs in the same phrase.
3) Use interprets when a finding describes what an observable means
   on the same lab or vital line.
4) Use component_of when an observable is part of a named test on
   the same lab or vital line.
5) Use causative_agent when a reaction, allergy, or situation is
   caused by a drug or allergen named in the note.
6) Do not invent entities. Do not link two findings just because they
   appear in the same note.
7) Do not invent a body site from the code book if the letter did
   not name that site.
8) Keep relation direction as head_idx -> tail_idx.
9) If a body structure is only meaningful as a linked site, include it
   in suppress.
10) Do not use an organ-present or in-situ status phrase as finding_site.
    "has womb insitu" means the womb is still there. It is not the site
    of discharge, pain, or a polyp.

Allowed relation types:
- finding_site
- interprets
- component_of
- causative_agent

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
        "category": "no_cooccurrence",
        "description": "Co-occurring findings must NOT be linked",
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
        "category": "finding_site",
        "description": "Pain linked to abdomen; severity stays in the finding span",
        "core": True,
        "model_scope": "any",
        "input": "Encounter: severe abdominal pain. Entities: [{text:'pain',label:'finding'},{text:'abdomen',label:'body structure'}]",
        "output": '{"confirmed":[],"rejected":[],"additional":[{"head_idx":0,"tail_idx":1,"type":"finding_site","confidence":0.94}],"suppress":[1]}',
    },
    {
        "id": "rl-f",
        "category": "causative_agent",
        "description": "Allergy situation caused by a named drug",
        "core": True,
        "model_scope": "any",
        "input": (
            "Encounter: allergic to penicillin. "
            "Entities: [{text:'allergic',label:'situation'},{text:'penicillin',label:'substance'}]"
        ),
        "output": (
            '{"confirmed":[],"rejected":[],"additional":[{"head_idx":0,"tail_idx":1,'
            '"type":"causative_agent","confidence":0.93}],"suppress":[]}'
        ),
    },
    {
        "id": "rl-g",
        "category": "finding_site",
        "description": "Organ-present status is not a finding site",
        "core": True,
        "model_scope": "any",
        "input": (
            "Encounter: vaginal discharge. has womb insitu. "
            "Entities: [{text:'vaginal discharge',label:'finding'},"
            "{text:'has womb insitu',label:'body structure'}]"
        ),
        "output": '{"confirmed":[],"rejected":[],"additional":[],"suppress":[]}',
    },
]
