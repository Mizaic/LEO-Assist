/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-7E9AD55B
 *   DI: DI-DA60AC55
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-7E9AD55B")
 */
export interface NerGuardRule {
  rule_id: string;
  family: string;
  rule_type: string;
  pattern: string;
  active: boolean;
  org_id?: string | null;
  source?: "builtin" | "custom";
  readonly?: boolean;
  summary?: string;
}
