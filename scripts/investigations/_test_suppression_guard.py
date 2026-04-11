"""Quick smoke-test for the concept suppression guard in post_processing.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from libs.pipeline.post_processing import _suppress_screening_false_positives

SCREENING_FP = [
    {
        "snomed_concept_id": "395100000",
        "text": "Negative cervical cytology. Normal recall.",
    },
    {"snomed_concept_id": "395100000", "text": "HPV Test: High risk HPV not detected"},
    {"snomed_concept_id": "395100000", "text": "NEGATIVE FIT - No Further Action"},
    {"snomed_concept_id": "395100000", "text": "overall negative result"},
    {
        "snomed_concept_id": "395100000",
        "text": "Sent following an overall negative result",
    },
    {"snomed_concept_id": "395100000", "text": "Cervical smear: negative"},
    {
        "snomed_concept_id": "395100000",
        "text": "Bowel cancer screening programme: faecal occult blood",
    },
    {
        "snomed_concept_id": "395100000",
        "text": "no detectable blood and the risk of CRC is less than 1 in 1000",
    },
]

LEGITIMATE = [
    {"snomed_concept_id": "395100000", "text": "No evidence of cancer found"},
    {"snomed_concept_id": "395100000", "text": "No evidence of malignancy"},
    {"snomed_concept_id": "395100000", "text": "no cancer on CT"},
    {
        "snomed_concept_id": "395100000",
        "text": "No evidence of cancer was seen on this endoscopy",
    },
    {"snomed_concept_id": "395100000", "text": "benign on histology"},
    {"snomed_concept_id": "363358000", "text": "Malignant neoplasm of breast"},
]

all_entities = SCREENING_FP + LEGITIMATE
result = _suppress_screening_false_positives(all_entities)

print(f"Input : {len(all_entities)} entities")
print(f"Output: {len(result)} entities")
print()
print("Kept (should be legitimate only):")
for e in result:
    cid = e["snomed_concept_id"]
    txt = e["text"][:70]
    print(f"  [{cid}] {txt}")

print()
suppressed = len(all_entities) - len(result)
expected = len(SCREENING_FP)
legitimate_all_kept = all(e in result for e in LEGITIMATE)
ok = suppressed == expected and legitimate_all_kept

if ok:
    print(
        f"PASS -- suppressed {suppressed}/{expected} screening false positives, all legitimate kept"
    )
else:
    print(
        f"FAIL -- suppressed {suppressed}/{expected}, legitimate_all_kept={legitimate_all_kept}"
    )
    sys.exit(1)
