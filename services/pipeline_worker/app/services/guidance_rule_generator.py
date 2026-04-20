"""Worker-facing guidance rule generator bridge.

Atlas trace:
  DO: DO-C2F6CA16
  DI: DI-06CB6881
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-C2F6CA16")
"""

from services.api.app.services.guidance_rule_generator import GuidanceRuleGenerator

__all__ = ["GuidanceRuleGenerator"]
