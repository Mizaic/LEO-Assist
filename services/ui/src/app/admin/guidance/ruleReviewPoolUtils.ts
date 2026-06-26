/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-E647765A
 *   DI: DI-0C8FBAF7
 */
import type { RuleReviewIdentity } from "./ruleReviewTypes";

export const DEFAULT_RULE_PAGE_SIZE = 10;

export type RuleSearchFields = RuleReviewIdentity & {
  name?: string;
  plain_english?: string;
  chapter_title?: string;
  strength?: string;
  guideline_id?: string;
  rule_id?: string;
};

export function ruleMatchesSearch(rule: RuleSearchFields, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  const haystack = [
    rule.name,
    rule.recommendation_text,
    rule.plain_english,
    rule.chapter_title,
    rule.guideline_id,
    rule.rule_id,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return haystack.includes(q);
}

export function filterRulesByGuideline<T extends { guideline_id?: string }>(
  rules: T[],
  guidelineId: string,
): T[] {
  if (!guidelineId || guidelineId === "all") return rules;
  return rules.filter((rule) => rule.guideline_id === guidelineId);
}

export function filterRulesByStrength<T extends { strength?: string }>(
  rules: T[],
  strength: string,
): T[] {
  if (!strength || strength === "all") return rules;
  return rules.filter((rule) => rule.strength === strength);
}

export function collectGuidelineIds<T extends { guideline_id?: string }>(rules: T[]): string[] {
  return [...new Set(rules.map((rule) => rule.guideline_id).filter(Boolean) as string[])].sort();
}

export function collectStrengths<T extends { strength?: string }>(rules: T[]): string[] {
  return [...new Set(rules.map((rule) => rule.strength).filter(Boolean) as string[])].sort();
}

export function paginateRules<T>(
  rules: T[],
  page: number,
  pageSize: number,
): {
  pageRules: T[];
  totalPages: number;
  total: number;
  from: number;
  to: number;
  page: number;
} {
  const total = rules.length;
  const totalPages = Math.max(1, Math.ceil(total / pageSize) || 1);
  const safePage = Math.min(Math.max(1, page), totalPages);
  const start = (safePage - 1) * pageSize;
  const pageRules = rules.slice(start, start + pageSize);
  const from = total === 0 ? 0 : start + 1;
  const to = Math.min(start + pageSize, total);
  return { pageRules, totalPages, total, from, to, page: safePage };
}
