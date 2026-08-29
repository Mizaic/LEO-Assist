"""Cypher for the admin workflow builder graph."""

LIST_WORKFLOWS = """
MATCH (w:Workflow)
OPTIONAL MATCH (s:Service)-[:HAS_WORKFLOW]->(w)
OPTIONAL MATCH (w)-[:STARTS_AT|NEXT_STEP*0..]->(step)
  WHERE step:Step OR step:HumanInTheLoop
WITH w, s, count(DISTINCT step) AS total_steps,
     count(DISTINCT CASE WHEN step:HumanInTheLoop THEN step END) AS human_count
RETURN
  w.id          AS id,
  w.name        AS name,
  coalesce(s.id, '')   AS service_id,
  coalesce(s.name, '') AS service_name,
  toString(w.created_at) AS created_at,
  total_steps   AS step_count,
  human_count   AS human_count
ORDER BY w.created_at DESC
"""

CREATE_WORKFLOW = """
CREATE (w:Workflow {
  id:         $id,
  name:       $name,
  created_at: datetime()
})
RETURN w.id AS id, w.name AS name, toString(w.created_at) AS created_at
"""

LINK_WORKFLOW_TO_SERVICE = """
MATCH (w:Workflow {id: $workflow_id})
MATCH (s:Service {id: $service_id})
CREATE (s)-[:HAS_WORKFLOW]->(w)
"""

DELETE_WORKFLOW = """
MATCH (w:Workflow {id: $id})
OPTIONAL MATCH (w)-[:STARTS_AT|NEXT_STEP*0..]->(n)
  WHERE n:Step OR n:HumanInTheLoop
DETACH DELETE n
WITH w
DETACH DELETE w
"""

GET_WORKFLOW_META = """
MATCH (w:Workflow {id: $id})
OPTIONAL MATCH (s:Service)-[:HAS_WORKFLOW]->(w)
RETURN w.id AS id, w.name AS name,
       coalesce(s.id, '') AS service_id,
       toString(w.created_at) AS created_at
"""

GET_GRAPH_NODES = """
MATCH (w:Workflow {id: $id})
OPTIONAL MATCH (w)-[:STARTS_AT|NEXT_STEP*0..]->(n)
  WHERE n:Step OR n:HumanInTheLoop
WITH DISTINCT n
RETURN n,
       labels(n) AS node_labels,
       CASE
         WHEN n:HumanInTheLoop THEN 'human'
         WHEN n:AmbientAgent THEN 'ambient'
         ELSE 'agent'
       END AS kind,
       coalesce(n.canvas_x, 200.0) AS pos_x,
       coalesce(n.canvas_y, 200.0) AS pos_y
"""

GET_GRAPH_EDGES = """
MATCH (w:Workflow {id: $id})
OPTIONAL MATCH (w)-[:STARTS_AT|NEXT_STEP*0..]->(src)-[r:NEXT_STEP]->(tgt)
  WHERE (src:Step OR src:HumanInTheLoop)
    AND (tgt:Step OR tgt:HumanInTheLoop)
WITH DISTINCT src, tgt, r
RETURN src.id AS source, tgt.id AS target,
       coalesce(r.condition, '') AS condition,
       elementId(r) AS rel_id
"""

GET_START_EDGE = """
MATCH (w:Workflow {id: $id})-[r:STARTS_AT]->(n)
  WHERE n:Step OR n:HumanInTheLoop
RETURN n.id AS target_id, coalesce(r.condition, '') AS condition
"""

GET_GRAPH_CONTEXT = """
MATCH (w:Workflow {id: $id})
OPTIONAL MATCH (s:Service)-[:HAS_WORKFLOW]->(w)
OPTIONAL MATCH (s)-[:PROVIDES_SERVICE_FOR]->(o:Organization)
OPTIONAL MATCH (o2)-[:PROVIDES_SERVICE]->(s)
OPTIONAL MATCH (s)<-[:PROVIDES_SERVICE]-(o3)
WITH w, s, coalesce(o, o2, o3) AS org
OPTIONAL MATCH (w)-[:STARTS_AT|NEXT_STEP*0..]->(a)
  WHERE a:AmbientAgent
OPTIONAL MATCH (a2:AmbientAgent)-[:CREATES_DATA_FOR]->(w)
WITH s, org,
     [x IN collect(DISTINCT a) + collect(DISTINCT a2) WHERE x IS NOT NULL]
     AS ambients
RETURN s, org, ambients
"""

REPLACE_GRAPH = """
MATCH (w:Workflow {id: $workflow_id})
OPTIONAL MATCH (w)-[:STARTS_AT|NEXT_STEP*0..]->(old)
  WHERE old:Step OR old:HumanInTheLoop
DETACH DELETE old
WITH w
SET w.updated_at = datetime()
RETURN w
"""

SAVE_STEP = """
CREATE (n:Step {
  id: $id,
  type: $type,
  name: $name,
  interval: $interval,
  alwaysTrigger: $alwaysTrigger,
  statusOnReady: $statusOnReady,
  defaultOnHitl: $defaultOnHitl,
  description: $description,
  enabled: $enabled,
  status: $status,
  canvas_x: $canvas_x,
  canvas_y: $canvas_y,
  created_at: datetime()
})
"""

SAVE_HUMAN = """
CREATE (n:HumanInTheLoop {
  id: $id,
  type: $type,
  name: $name,
  interval: $interval,
  alwaysTrigger: $alwaysTrigger,
  statusOnReady: $statusOnReady,
  defaultOnHitl: $defaultOnHitl,
  description: $description,
  enabled: $enabled,
  status: $status,
  canvas_x: $canvas_x,
  canvas_y: $canvas_y,
  created_at: datetime()
})
"""

LINK_STARTS_AT = """
MATCH (w:Workflow {id: $workflow_id})
MATCH (n {id: $node_id})
  WHERE n:Step OR n:HumanInTheLoop
MERGE (w)-[r:STARTS_AT]->(n)
SET r.condition = $condition
"""

SET_AGENT_LABELS = """
MATCH (n {id: $id})
SET n:Agent
"""

SET_AMBIENT_LABELS = """
MATCH (n {id: $id})
SET n:Agent:AmbientAgent
"""

LINK_NEXT_STEP = """
MATCH (src {id: $source_id}) WHERE src:Step OR src:HumanInTheLoop
MATCH (tgt {id: $target_id}) WHERE tgt:Step OR tgt:HumanInTheLoop
CREATE (src)-[:NEXT_STEP {condition: $condition}]->(tgt)
"""
