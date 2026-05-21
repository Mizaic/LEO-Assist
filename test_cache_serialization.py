import json
from dataclasses import asdict
from services.terminology_api.app.services.coding_resolver import CodingCandidate

cand = CodingCandidate(
    snomed_concept_id="123",
    snomed_term="Ferritin",
    semantic_tag="observable entity",
    read_code="42..",
    score=1.0,
    source="lexical",
    surface_form_status="approved",
    had_exact_match=True,
    lexical_raw=1.2,
    vector_raw=0.0,
    related_concepts=[{"id": "456", "fsn": "Ferritin test", "semantic_tag": "procedure", "rel": "COMPONENT_OF"}]
)

d = asdict(cand)
s = json.dumps(d, default=str)
d2 = json.loads(s)
cand2 = CodingCandidate(**d2)
print("Original:", cand)
print("Deserialized:", cand2)
print("Equal?", cand == cand2)
