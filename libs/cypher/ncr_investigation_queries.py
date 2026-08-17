"""Patient-graph store for NCR investigation cases.

Atlas: DI-ED5A9AC3
"""

LOAD_INVESTIGATION = """
MATCH (i:NcrInvestigation {nc_id: $nc_id})
RETURN i.nc_id AS nc_id, i.title AS title, i.cases_json AS cases_json
"""

SAVE_CASES = """
MERGE (i:NcrInvestigation {nc_id: $nc_id})
ON CREATE SET i.created_at = datetime()
SET i.updated_at = datetime(),
    i.title = $title,
    i.cases_json = $cases_json
RETURN i.nc_id AS nc_id, i.cases_json AS cases_json
"""

ADD_EVENT = """
MERGE (i:NcrInvestigation {nc_id: $nc_id})
ON CREATE SET i.created_at = datetime()
CREATE (e:NcrInvestigationEvent {
  event_id: randomUUID(),
  nc_id: $nc_id,
  kind: $kind,
  local_text: $local_text,
  atlas_text: $atlas_text,
  atlas_ok: $atlas_ok,
  created_at: datetime()
})
MERGE (i)-[:HAS_EVENT]->(e)
RETURN e.event_id AS event_id,
       e.atlas_ok AS atlas_ok,
       e.atlas_text AS atlas_text
"""

LIST_EVENTS = """
MATCH (i:NcrInvestigation {nc_id: $nc_id})-[:HAS_EVENT]->(e:NcrInvestigationEvent)
RETURN e.event_id AS event_id,
       e.kind AS kind,
       e.local_text AS local_text,
       e.atlas_text AS atlas_text,
       e.atlas_ok AS atlas_ok,
       toString(e.created_at) AS created_at
ORDER BY e.created_at DESC
LIMIT 100
"""
