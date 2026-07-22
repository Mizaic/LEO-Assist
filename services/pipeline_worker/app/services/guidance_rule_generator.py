"""Worker-facing guidance rule generator bridge.

Atlas trace:
  DO: DO-CE65B1F2
  DI: DI-36F80B95
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-CE65B1F2")
"""

from services.api.app.services.guidance_rule_generator import GuidanceRuleGenerator

__all__ = ["GuidanceRuleGenerator"]
