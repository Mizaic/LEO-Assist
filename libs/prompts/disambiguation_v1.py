"""V1 SNOMED disambiguation prompt — INSTRUCTIONS ONLY.

Output schema and few-shot examples are stored separately in Neo4j and
assembled at runtime. Do NOT add output format sections or inline examples
to this file — manage them via the Admin UI at /admin/prompts
(name='disambiguation', version=1).

Run ``python -m scripts.seed_prompt_configs`` to push changes to Neo4j.
"""

DISAMBIGUATION_SYSTEM_V1 = """\
You are disambiguating SNOMED concepts for a clinical term in context.

You receive a clinical term, its source text context, and a ranked list of
candidate SNOMED CT concepts. Select the single candidate that best represents
the clinical meaning of the term as used in the provided context.

Prefer the most specific concept that the evidence supports. If the context
does not provide enough information to distinguish between near-synonyms,
choose the more general concept.

Do not guess SNOMED concept IDs. Only select from the provided candidate list.\
"""

