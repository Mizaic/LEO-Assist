/**
 * Placeholder helpers for downstream pipeline expectations on a scenario.
 */

import type { ExpectedAnalysis, ExpectedSbar } from "./types";

export const EMPTY_EXPECTED_ANALYSIS: ExpectedAnalysis = {
  matched_rule_ids: [],
  expect_no_rules_fired: false,
  expected_action_priority: null,
  reviewer_notes: "",
};

export const EMPTY_EXPECTED_SBAR: ExpectedSbar = {
  situation_md: "",
  background_md: "",
  recommendation_md: "",
  matched_rule_ids: [],
  required_phrases: [],
  banned_phrases: [],
  expected_action_priority: null,
  reviewer_focus: "",
};

function cleanList(values: unknown): string[] {
  if (!Array.isArray(values)) return [];
  return values
    .map((item) => String(item ?? "").trim())
    .filter(Boolean);
}

export function normaliseExpectedAnalysis(raw: unknown): ExpectedAnalysis {
  if (!raw || typeof raw !== "object") {
    return { ...EMPTY_EXPECTED_ANALYSIS };
  }
  const source = raw as Record<string, unknown>;
  const priority = source.expected_action_priority;
  return {
    matched_rule_ids: cleanList(source.matched_rule_ids),
    expect_no_rules_fired: Boolean(source.expect_no_rules_fired),
    expected_action_priority:
      priority == null || String(priority).trim() === "" ? null : String(priority).trim(),
    reviewer_notes: String(source.reviewer_notes ?? "").trim(),
  };
}

export function normaliseExpectedSbar(raw: unknown): ExpectedSbar {
  if (!raw || typeof raw !== "object") {
    return { ...EMPTY_EXPECTED_SBAR };
  }
  const source = raw as Record<string, unknown>;
  const priority = source.expected_action_priority;
  return {
    situation_md: String(source.situation_md ?? "").trim(),
    background_md: String(source.background_md ?? "").trim(),
    recommendation_md: String(source.recommendation_md ?? "").trim(),
    matched_rule_ids: cleanList(source.matched_rule_ids),
    required_phrases: cleanList(source.required_phrases),
    banned_phrases: cleanList(source.banned_phrases),
    expected_action_priority:
      priority == null || String(priority).trim() === "" ? null : String(priority).trim(),
    reviewer_focus: String(source.reviewer_focus ?? "").trim(),
  };
}

export function hasExpectedAnalysisContent(value: ExpectedAnalysis): boolean {
  return (
    value.matched_rule_ids.length > 0 ||
    value.expect_no_rules_fired ||
    Boolean(value.expected_action_priority) ||
    Boolean(value.reviewer_notes.trim())
  );
}

export function hasExpectedSbarContent(value: ExpectedSbar): boolean {
  return (
    Boolean(value.situation_md.trim()) ||
    Boolean(value.background_md.trim()) ||
    Boolean(value.recommendation_md.trim()) ||
    value.matched_rule_ids.length > 0 ||
    value.required_phrases.length > 0 ||
    value.banned_phrases.length > 0 ||
    Boolean(value.expected_action_priority) ||
    Boolean(value.reviewer_focus.trim())
  );
}

export function serialiseExpectedAnalysis(value: ExpectedAnalysis): ExpectedAnalysis | null {
  const normalised = normaliseExpectedAnalysis(value);
  return hasExpectedAnalysisContent(normalised) ? normalised : null;
}

export function serialiseExpectedSbar(value: ExpectedSbar): ExpectedSbar | null {
  const normalised = normaliseExpectedSbar(value);
  return hasExpectedSbarContent(normalised) ? normalised : null;
}
