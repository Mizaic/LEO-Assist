/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 */
import type {
  CriterionResult,
  LogicTreeNode,
  RuleCriterion as Criterion,
} from "./RuleLogicView";
import type { RuleAction } from "./EditRuleDialog/types";
import type { RecommendationStructure } from "./EditRuleDialog/SentenceEditor/pathwayTextSplit";
import type { CompanionPanel } from "./EditRuleDialog/HighlightWizard/weightedChecklist";

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
  /** NICE HTML list tree (lead text + <li> items with offsets) when the
   *  recommendation is a list rather than a plain sentence. Null for
   *  plain-sentence recommendations -- see nice_list_parser.py. */
  recommendation_structure?: RecommendationStructure | null;
  /** Sibling NICE panel boxes (e.g. weighted 7-point checklist). */
  companion_panels?: CompanionPanel[] | null;
  plain_english: string;
  present_criteria: Criterion[];
  absent_criteria: Criterion[];
  logic_tree?: LogicTreeNode | null;
  criteria_concepts?: CriterionResult[];
  /** One or more recommended procedures, each with its own strength. */
  actions?: RuleAction[];
  /** Deprecated: legacy single recommended procedure, kept for rules
   *  and callers not yet migrated to ``actions``. */
  action?: ActionConcept | null;
  /** Rule-level clinical priority from HAS_ACTION edges. */
  action_priority?:
    | "immediate"
    | "very_urgent"
    | "2ww"
    | "urgent"
    | "routine"
    | null;
  /** Due-days paired with action_priority (null for routine). */
  action_due_days?: number | null;
  has_predecessor: boolean;
  predecessor_id?: string;
  previous_recommendation_text?: string | null;
  previous_recommendation_number?: string | null;
  /** True when this APPROVED rule's guideline text changed underneath it
   *  during a re-ingest. The rule stays active (still enforced) -- a
   *  guideline update never silently retires an approval -- but a
   *  reviewer should double check it still reflects current guidance. */
  guideline_text_changed?: boolean;
  created_at?: string;
  updated_at?: string;
  reviewed_at?: string;
  reviewed_by?: string;
  generation_outcome?: string | null;
  needs_human_review?: boolean;
  generation_errors?: string[];
  /** When true this rule fires only if no other rule in the guideline matched. */
  is_default?: boolean;
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

export type RuleStatusFilter =
  | "pending_review"
  | "active"
  | "superseded"
  /** Confirmed "no coded rule" or rejected -- not compiled live. */
  | "rejected";
