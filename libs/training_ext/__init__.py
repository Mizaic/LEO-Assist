"""Shared training extensions (splits, suggesters, architectures).

This package is imported by both the training worker and the inference loader
so any spaCy registry side effects must be idempotent.
"""
