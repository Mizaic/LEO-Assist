"""LangGraph-based clinical pipeline subgraphs.

Each subgraph is a self-contained StateGraph that can be composed into
larger workflows via the SubgraphRegistry.  Subgraphs are dispatched by
the WorkflowEngine based on FHIR PlanDefinition / ActivityDefinition
configuration stored in Neo4j.
"""
