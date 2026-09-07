"""Cypher queries for the density preference (Wave E Phase 1 / DI-LEO-AI-169).

Atlas trace:
  DO: DO-F8EFEF89
  DI: DI-E47C3FC2
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-F8EFEF89")

These queries read and write the per-practitioner UI density preference:

- ``Practitioner.density_preference`` -- one of compact / comfortable / spacious
- The default at sign-in is ``comfortable`` (touch targets >= 40px). Patient
  reachable routes still force ``spacious`` in the UI regardless of preference.

Keeping density queries in their own module avoids pushing
``libs/cypher/role_queries.py`` past the 500 LOC hard limit and mirrors the
DI-LEO-AI-129 split that introduced the role-state module.
"""

from __future__ import annotations

# Whitelist of accepted density values. Mirrors the DensityTier union in
# services/ui/src/theme/tokens.ts; the API rejects anything else with 400.
ALLOWED_DENSITIES: tuple[str, ...] = ("compact", "comfortable", "spacious")

# Read the current density preference for a practitioner. Returns NULL when
# the practitioner has no preference set so the UI can fall back to the
# comfortable default.
GET_PRACTITIONER_DENSITY = """
MATCH (pr:User {email: $email})
RETURN pr.density_preference AS density_preference
"""

# Write the density preference. Returns the persisted value so the API can
# surface it to the client without a separate read.
SET_PRACTITIONER_DENSITY = """
MATCH (pr:User {email: $email})
SET pr.density_preference = $density
RETURN pr.density_preference AS density_preference
"""
