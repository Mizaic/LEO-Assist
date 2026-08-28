"""Leaf-layer pipeline data contracts.

This package sits at the bottom of the dependency graph.  It must not
import from ``libs.pipeline``, ``libs.ner``, ``libs.pipeline_graph`` or
``libs.workflow`` -- those packages import *from* here.  Keeping this
rule is what lets the contracts be used inside modules that are
currently tangled in import cycles.
"""

from __future__ import annotations
