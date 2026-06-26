/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-E647765A
 *   DI: DI-0C8FBAF7
 */
import type {
  CriterionResult,
  LogicTreeNode,
  RuleCriterion as Criterion,
} from "./RuleLogicView";

export interface ActionConcept {
  snomed_concept_id: string | null;
  preferred_term: string;
  semantic_tag?: string;
  term?: string;
}

export interface Rule {
  rule_id: string;
  name: string;
  status: string;
  strength: string;
  schema_version?: number;
  guideline_id: string;
  guideline_version?: number;
  chapter_title?: string;
  recommendation_text: string;
  plain_english: string;
  present_criteria: Criterion[];
  absent_criteria: Criterion[];
  logic_tree?: LogicTreeNode | null;
  criteria_concepts?: CriterionResult[];
  action?: ActionConcept | null;
  has_predecessor: boolean;
  predecessor_id?: string;
  created_at?: string;
  updated_at?: string;
  reviewed_at?: string;
  reviewed_by?: string;
  generation_outcome?: string | null;
  needs_human_review?: boolean;
  generation_errors?: string[];
}

export interface PromoteResult {
  domain_id: string;
  domain_name: string;
  concepts_added: number;
}

export interface RuleReviewIdentity {
  rule_id: string;
  guideline_id?: string;
  recommendation_text?: string;
}

export type RuleStatusFilter = "pending_review" | "active" | "superseded";
