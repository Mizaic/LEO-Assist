"""Episode Detector v2 -- defence-in-depth episode detector.

Atlas trace:
  DI: DI-8A5FCF4F (Defence-in-depth episode detector with coverage fail-safe)
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-8A5FCF4F")

The v2 detector replaces both the rule-based ``episode_builder`` and
the LLM-based ``episode_engine`` with a 12-component pipeline:

    1. Timeline normaliser
    2. Five independent signal extractors
       (code, text, pathway, result, treatment)
    3. Five candidate generators
       (referral-anchored, diagnosis-anchored, treatment-anchored,
        symptom-cluster-anchored, site-cohort-anchored)
    4. Evidence aggregator + per-site scorer + case-based corroborator
    5. Hungarian-assignment conflict resolver
    6. Boundary detector with benign-closure inference
    7. Voting + coverage-check + confidence-tier arbitration
    8. Provenance store

Day-one stub behaviour: returns zero auto-episodes for any site that
does not have a real implementation in this version. Mission Control
manual curation is the only source of episodes during cold start.
Breast is the only site with a real end-to-end implementation in v1
of the v2 system.
"""

from .runner import build_episodes  # noqa: F401
