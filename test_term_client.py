import sys
import os
sys.path.insert(0, os.path.join(os.getcwd(), 'services/api'))
sys.path.insert(0, os.getcwd())
from libs.terminology.client import TerminologyClient
import httpx
import logging
logging.basicConfig(level=logging.DEBUG)

client = TerminologyClient(timeout=10)
terms = ["weight loss", "blood pressure", "chest pain"] * 20
try:
    print("Resolving...")
    res = client.resolve(terms)
    print("Done:", len(res))
except Exception as e:
    print("Error:", e)
