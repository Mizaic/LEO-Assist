"""Per-stage Haiku agents for the episode engine.

Each module exposes a single ``run(...)`` function that takes the relevant
inputs, calls the LLM with the stage's tool_config, parses the result via
the matching Pydantic schema, and returns the schema instance plus a
``StageTrace`` for provenance.
"""
