/**
 * Normalise API / cache action payloads into the nested RuleAction shape
 * the editor and read-only views expect ({ criterion, strength }).
 *
 * The Neo4j actionJson store and older API responses use a flat dict
 * (snomed_concept_id at the top level). Newer API responses and the
 * save payload use nested RuleAction. This helper bridges both.
 */
import type { LogicCriterion, RuleAction } from "./EditRuleDialog/types";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function normalizeCriterion(raw: unknown): LogicCriterion {
  if (!isRecord(raw)) {
    return { snomed_concept_id: "", preferred_term: "" };
  }
  const snomed = raw.snomed_concept_id;
  const preferred =
    typeof raw.preferred_term === "string"
      ? raw.preferred_term
      : typeof raw.term === "string"
        ? raw.term
        : "";
  return {
    snomed_concept_id: snomed != null ? String(snomed) : "",
    preferred_term: preferred,
    semantic_tag:
      typeof raw.semantic_tag === "string" ? raw.semantic_tag : undefined,
    term: typeof raw.term === "string" ? raw.term : undefined,
  };
}

/** Normalise one flat or nested action item into RuleAction. */
export function normalizeRuleAction(raw: unknown): RuleAction {
  if (!isRecord(raw)) {
    return {
      criterion: { snomed_concept_id: "", preferred_term: "" },
      strength: "unspecified",
    };
  }
  if (isRecord(raw.criterion)) {
    return {
      criterion: normalizeCriterion(raw.criterion),
      strength:
        typeof raw.strength === "string" ? raw.strength : "unspecified",
    };
  }
  // Flat API / legacy cache shape: snomed fields at top level.
  return {
    criterion: normalizeCriterion(raw),
    strength:
      typeof raw.strength === "string" ? raw.strength : "unspecified",
  };
}

/** Normalise an actions array; returns undefined when input is absent. */
export function normalizeRuleActions(
  raw: unknown[] | undefined,
): RuleAction[] | undefined {
  if (raw == null) return undefined;
  if (!Array.isArray(raw)) return undefined;
  return raw.map(normalizeRuleAction);
}
