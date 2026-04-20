"""V1 SNOMED disambiguation prompt — INSTRUCTIONS ONLY.

Atlas trace:
  DO: DO-64BDC193
  DI: DI-88C8BBCD
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-64BDC193")

Output schema and few-shot examples are stored separately in Neo4j and
assembled at runtime. Do NOT add output format sections or inline examples
to this file — manage them via the Admin UI at /admin/prompts
(name='disambiguation', version=1).

Run ``python -m scripts.seed_prompt_configs`` to push changes to Neo4j.
"""

DISAMBIGUATION_SYSTEM_V1 = """\
You are choosing the best SNOMED CT concept for a clinical term in context.

You receive a clinical term, its source text context, and a ranked list of
candidate SNOMED CT concepts. Select the single candidate that best matches
the clinical meaning of the term as used in the context.

Choose the most specific concept the evidence supports. If the context does not
clearly distinguish between near-synonyms, choose the more general concept.

Only select from the provided candidate list. Do not guess SNOMED concept IDs.\
"""
