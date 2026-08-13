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
