"""NCDA cancer detector (text-driven, four-anchor).

Atlas trace:
  See DO-NCDA-DETECTOR (created 2026-04-28) for the design output that
  governs this package; per-stage VTs to be linked as each stage ships.

This package replaces the SNOMED-anchor episode_detector_v2 cancer paths
with a text + EMR-flags + Bio_ClinicalBERT-vector pipeline. See
.cursor/plans/ncda_cancer_detector_ml_*.plan.md for the architecture.
"""
