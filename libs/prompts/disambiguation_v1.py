"""V1 SNOMED disambiguation prompt.

Moved from services/api/app/services/v3/disambiguator.py.
"""
from libs.prompts.registry import register

DISAMBIGUATION_SYSTEM_V1 = """\
You are disambiguating SNOMED concepts for a clinical term in context.
Return strict JSON only with keys: conceptId, confidence, reason.
If none fit, return {"conceptId":"NONE","confidence":0.0,"reason":"..."}.\
"""

register("disambiguation", version=1, text=DISAMBIGUATION_SYSTEM_V1)
