export type RuleSource = "builtin" | "custom";
export type FilterView = "all" | "builtin" | "custom";

export interface ContextRule {
  rule_id: string | null;
  literal: string;
  category: string;
  direction: string;
  max_scope: number | null;
  description: string;
  example: string;
  created_by: string;
  active: boolean;
  created_at: string | null;
  source: RuleSource;
  org_id: string | null;
}

export interface ContextWorkedExample {
  note: string;
  withoutGuard: string;
  withGuard: string;
  dataChange: string;
}
