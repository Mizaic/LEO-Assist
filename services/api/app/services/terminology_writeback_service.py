"""Auto-stamped Atlas trace.

Atlas trace:
  DO: DO-92F92EFB
  DI: DI-88C1715A
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-92F92EFB")
"""
from __future__ import annotations

from services.terminology_api.app.services.writeback_service import (
    _extract_surface_form_rows,
    writeback_approved_terms,
)

__all__ = ["_extract_surface_form_rows", "writeback_approved_terms"]
