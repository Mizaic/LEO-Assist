import sys
import os
sys.path.insert(0, os.path.join(os.getcwd(), 'services/api'))
sys.path.insert(0, os.getcwd())
from libs.ner.referral_routing_guard import is_informational_referral_routing, should_suppress_referral_routing_entity

phrases = [
    "suspected head and neck cancer",
    "head and neck urgent suspected cancer referral",
    "suspected brain and CNS cancer pathway",
    "two-week wait pathway",
    "urgent haematology suspected cancer referral"
]

for p in phrases:
    print(f"'{p}' -> is_routing: {is_informational_referral_routing(p)}, should_suppress: {should_suppress_referral_routing_entity({'text': p})}")
