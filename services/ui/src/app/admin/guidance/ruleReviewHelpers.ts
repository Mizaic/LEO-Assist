/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 */
import type { LogicTreeNode } from "./RuleLogicView";
import type { EditableRule } from "./EditRuleDialog";
import type { LogicCriterion, RuleAction } from "./EditRuleDialog/types";
import { normalizeRuleActions } from "./actionShape";
import type {
  ActionConcept,
  Rule,
  RuleReviewIdentity,
  RuleStatusFilter,
} from "./ruleReviewTypes";

export type {
  ActionConcept,
  Rule,
  RuleReviewIdentity,
  RuleStatusFilter,
  PromoteResult,
} from "./ruleReviewTypes";

export function formatApiDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const parts = detail
      .map((d) => {
        if (typeof d === "string") return d;
        if (d && typeof d === "object") {
          const obj = d as Record<string, unknown>;
          const loc = Array.isArray(obj.loc)
            ? (obj.loc as unknown[]).filter((x) => x !== "body" && x !== "updates").join(".")
            : "";
          const msg = typeof obj.msg === "string" ? obj.msg : "";
          if (loc && msg) return `${loc}: ${msg}`;
          if (msg) return msg;
        }
        try {
          return JSON.stringify(d);
        } catch {
          return String(d);
        }
      })
      .filter((s) => s.length > 0);
    return parts.join("; ");
  }
  if (detail && typeof detail === "object") {
    try {
      return JSON.stringify(detail);
    } catch {
      return String(detail);
    }
  }
  return "";
}

export function mergeEditedRuleIntoCache(
  previous: Rule,
  newRuleId: string,
  payload: {
    name: string;
    logic_tree: Record<string, unknown>;
    /** Sanitised save-payload shape (see ``sanitiseActionsForSave``);
     *  each item's ``criterion``/``strength`` line up with ``RuleAction``
     *  but are typed loosely here because they are about to be POSTed
     *  as plain JSON, not consumed as editor state. */
    actions?: Array<Record<string, unknown>>;
  },
): Rule {
  const actions = payload.actions as unknown as RuleAction[] | undefined;
  return {
    ...previous,
    rule_id: newRuleId,
    status: "active",
    name: payload.name || previous.name,
    logic_tree: payload.logic_tree as unknown as LogicTreeNode,
    ...(actions
      ? { actions, strength: actions[0]?.strength ?? previous.strength }
      : {}),
  };
}

function normaliseRecommendationText(value: string | undefined): string {
  return (value || "").toLowerCase().replace(/\s+/g, " ").replace(/[^\w. ]+/g, "").trim();
}

export function ruleReviewKey(rule: RuleReviewIdentity): string {
  const text = normaliseRecommendationText(rule.recommendation_text);
  const recommendationNumber = text.match(/^(\d+(?:\.\d+)+)\b/)?.[1];
  if (recommendationNumber) return `${rule.guideline_id || ""}:${recommendationNumber}`;
  return `${rule.guideline_id || ""}:${text || rule.rule_id}`;
}

export function upsertApprovedRule<T extends RuleReviewIdentity>(current: T[], next: T): T[] {
  const nextKey = ruleReviewKey(next);
  return [
    ...current.filter((rule) => rule.rule_id !== next.rule_id && ruleReviewKey(rule) !== nextKey),
    next,
  ];
}

export function filterRulesForReview<T extends RuleReviewIdentity>(
  rules: T[],
  sessionApproved: RuleReviewIdentity[],
  statusFilter: RuleStatusFilter,
): T[] {
  const approvedKeys = new Set(sessionApproved.map(ruleReviewKey));
  const seen = new Set<string>();
  const out: T[] = [];
  for (const rule of rules) {
    const key = ruleReviewKey(rule);
    if (statusFilter === "pending_review" && approvedKeys.has(key)) continue;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(rule);
  }
  return out;
}

export function sortRulesForStatus<R extends { rule_id: string; updated_at?: string }>(
  rules: R[],
  statusFilter: RuleStatusFilter,
): R[] {
  if (statusFilter !== "active") return rules;
  const epoch = (iso: string | undefined): number => {
    if (!iso) return 0;
    const t = new Date(iso).getTime();
    return Number.isNaN(t) ? 0 : t;
  };
  return [...rules].sort((a, b) => {
    const da = epoch(a.updated_at);
    const db = epoch(b.updated_at);
    if (da !== db) return da - db;
    return a.rule_id.localeCompare(b.rule_id);
  });
}

export function ruleToEditable(rule: Rule): EditableRule {
  let action: LogicCriterion | null = null;
  if (rule.action && rule.action.snomed_concept_id) {
    action = {
      snomed_concept_id: rule.action.snomed_concept_id,
      preferred_term: rule.action.preferred_term,
      semantic_tag: rule.action.semantic_tag,
      term: rule.action.term,
    };
  }
  return {
    rule_id: rule.rule_id,
    name: rule.name,
    strength: rule.strength,
    guideline_id: rule.guideline_id,
    chapter_title: rule.chapter_title,
    recommendation_text: rule.recommendation_text,
    logic_tree: rule.logic_tree,
    actions: normalizeRuleActions(rule.actions as unknown[] | undefined),
    action,
  };
}

export async function fetchRules(status: RuleStatusFilter): Promise<Rule[]> {
  const resp = await fetch(`/api/guidance/rules/review?status=${status}&limit=200`);
  if (!resp.ok) throw new Error(resp.statusText);
  return resp.json();
}
