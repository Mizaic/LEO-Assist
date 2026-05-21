import sys
import os
sys.path.insert(0, os.path.join(os.getcwd(), 'services/api'))
sys.path.insert(0, os.getcwd())
from tests.helpers.clinical_extraction_scenario_loader import _greedy_phrase_match
rules = {"casefold": True, "trim": True, "collapse_whitespace": True, "strip_terminal_punctuation": True, "containment_match": True}
exp = [{"text": "visual disturbance", "semantic_tag": "disorder"}]
ext = [{"text": "visual disturbance", "semantic_tag": "finding"}]
print(_greedy_phrase_match(exp, ext, rules))
