"""Cypher queries for PromptConfig CRUD in Neo4j."""

CREATE_CONSTRAINT = """
CREATE CONSTRAINT prompt_config_id IF NOT EXISTS
FOR (p:PromptConfig) REQUIRE p.id IS UNIQUE
"""

CREATE_INDEX_NAME = """
CREATE INDEX prompt_config_name IF NOT EXISTS
FOR (p:PromptConfig) ON (p.name, p.version)
"""

LIST_PROMPTS = """
MATCH (p:PromptConfig)
RETURN p.id AS id,
       p.name AS name,
       p.description AS description,
       p.version AS version,
       p.verification AS verification,
       size(coalesce(p.few_shot_examples, '[]')) > 2 AS hasFewShot,
       p.updated_at AS updatedAt,
       p.created_at AS createdAt
ORDER BY p.name, p.version
"""

GET_PROMPT = """
MATCH (p:PromptConfig {id: $id})
RETURN p.id AS id,
       p.name AS name,
       p.description AS description,
       p.version AS version,
       p.system_prompt AS systemPrompt,
       p.output_schema AS outputSchema,
       p.verification AS verification,
       p.few_shot_examples AS fewShotExamples,
       p.updated_at AS updatedAt,
       p.created_at AS createdAt
"""

GET_PROMPT_BY_NAME = """
MATCH (p:PromptConfig {name: $name, version: $version})
RETURN p.id AS id,
       p.name AS name,
       p.version AS version,
       p.system_prompt AS systemPrompt,
       p.output_schema AS outputSchema,
       p.verification AS verification,
       p.few_shot_examples AS fewShotExamples,
       p.updated_at AS updatedAt
"""

CREATE_PROMPT = """
CREATE (p:PromptConfig {
  id: $id,
  name: $name,
  description: $description,
  version: $version,
  system_prompt: $system_prompt,
  output_schema: $output_schema,
  verification: $verification,
  few_shot_examples: $few_shot_examples,
  created_at: datetime(),
  updated_at: datetime(),
  source: $source
})
RETURN p.id AS id
"""

UPDATE_PROMPT = """
MATCH (p:PromptConfig {id: $id})
SET p.name = $name,
    p.description = $description,
    p.system_prompt = $system_prompt,
    p.output_schema = $output_schema,
    p.verification = $verification,
    p.few_shot_examples = $few_shot_examples,
    p.updated_at = datetime()
RETURN p.id AS id
"""

DELETE_PROMPT = """
MATCH (p:PromptConfig {id: $id})
WHERE p.source <> 'seed'
DELETE p
RETURN count(*) AS deleted
"""

UPSERT_SEED_PROMPT = """
MERGE (p:PromptConfig {name: $name, version: $version})
ON CREATE SET
  p.id = $id,
  p.description = $description,
  p.system_prompt = $system_prompt,
  p.output_schema = $output_schema,
  p.verification = $verification,
  p.few_shot_examples = $few_shot_examples,
  p.source = 'seed',
  p.created_at = datetime(),
  p.updated_at = datetime()
ON MATCH SET
  p.description = CASE WHEN p.source = 'seed' THEN $description ELSE p.description END,
  p.system_prompt = CASE WHEN p.source = 'seed' THEN $system_prompt ELSE p.system_prompt END,
  p.output_schema = CASE WHEN p.source = 'seed' THEN $output_schema ELSE p.output_schema END,
  p.few_shot_examples = CASE WHEN p.source = 'seed' THEN $few_shot_examples ELSE p.few_shot_examples END,
  p.updated_at = datetime()
RETURN p.id AS id, p.source AS source
"""
