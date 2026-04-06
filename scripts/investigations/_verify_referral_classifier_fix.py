"""Verify the classifier and splitter fixes for fast-track referral encounters."""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from libs.classifiers.encounter_textcat import classify_text
from libs.nlp.sentence_splitter import SentenceChunk, filter_header_sentences

# Exact text from the 13 admin_only encounters that were missed
MISSED_TEXTS = [
    ("skin cancer referral - secretary note",
     "09:46 - Surgery: BAKER, Dawn (Mrs) (Medical Secretary Access Role) \nFast track referral for suspected skin cancer"),
    ("breast cancer referral - secretary note",
     "12:52 - Surgery: HUBBARD, Siobhan (Medical Secretary Access Role) \nFast track referral for suspected breast cancer"),
    ("brain tumour referral - secretary note",
     "12:12 - Surgery: JONES, Emma (Medical Secretary Access Role) \nFast track referral for suspected brain tumour"),
    ("lower GI referral - secretary note",
     "10:12 - Surgery: JONES, Emma (Medical Secretary Access Role) \nFast track referral for suspected lower GI cancer"),
    ("head and neck referral - secretary note",
     "13:36 - Surgery: BAKER, Dawn (Mrs) (Medical Secretary Access Role) \nFast track referral for suspected head and neck cancer"),
    ("upper GI referral - prism note",
     "09:03 - Surgery: BRIDGES, Kirstie (Dr) \n- PRISM 2WW Upper GI -  \nFast track referral for suspected upper GI cancer"),
]

print("Classifier check -- all must now return 'clinical'")
print("=" * 70)
all_pass = True
for label, text in MISSED_TEXTS:
    result = classify_text(text)
    ok = result == "clinical"
    icon = "PASS" if ok else "FAIL"
    print(f"  [{icon}] {label}")
    print(f"         classify_text -> {result!r}")
    if not ok:
        all_pass = False

print()
print("Sentence splitter allowlist check")
print("=" * 70)
referral_chunk = SentenceChunk("s1", "Fast track referral for suspected breast cancer", 0, 47)
header_chunk   = SentenceChunk("s2", "Entered at: GP surgery", 48, 70)
result = filter_header_sentences([referral_chunk, header_chunk])
ok = referral_chunk in result and header_chunk not in result
print(f"  {'PASS' if ok else 'FAIL'} -- referral chunk preserved, header chunk removed")
if not ok:
    all_pass = False

print()
if all_pass:
    print("All checks PASSED -- referral milestones will no longer be dropped.")
else:
    print("SOME CHECKS FAILED.")
    sys.exit(1)
