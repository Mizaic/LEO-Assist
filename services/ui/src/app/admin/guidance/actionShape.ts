/**
 * Normalise API / cache action payloads into the nested RuleAction shape
 * the editor and read-only views expect ({ criterion, strength }).
 *
 * The Neo4j actionJson store and older API responses use a flat dict
 * (snomed_concept_id at the top level). Newer API responses and the
 * save payload use nested RuleAction. This helper bridges both.
 *
 * Also carries optional action-group fields (group_id / group_mode /
 * group_rank) for either/or and preferred-then-fallback procedures.
 *
 * Atlas trace:
 *   DO: DO-2C03CA0E
 *   DI: DI-3F771AFB
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C03CA0E")
 */
import type {
  ActionGroupMode,
  LogicCriterion,
  RuleAction,
} from "./EditRuleDialog/types";

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

function normalizeGroupMode(raw: unknown): ActionGroupMode | undefined {
  if (raw === "all" || raw === "any" || raw === "preferred_fallback") {
    return raw;
  }
  return undefined;
}

function normalizeGroupRank(raw: unknown): number | undefined {
  if (typeof raw === "number" && Number.isFinite(raw) && raw >= 0) {
    return Math.floor(raw);
  }
  if (typeof raw === "string" && raw.trim() !== "") {
    const n = Number(raw);
    if (Number.isFinite(n) && n >= 0) return Math.floor(n);
  }
  return undefined;
}

/** Optional OR / preferred-fallback metadata on an action row. */
function normalizeGroupFields(raw: Record<string, unknown>): Partial<RuleAction> {
  const groupId =
    typeof raw.group_id === "string" && raw.group_id.trim()
      ? raw.group_id.trim()
      : undefined;
  if (!groupId) return {};
  const out: Partial<RuleAction> = { group_id: groupId };
  const mode = normalizeGroupMode(raw.group_mode);
  if (mode) out.group_mode = mode;
  const rank = normalizeGroupRank(raw.group_rank);
  if (rank !== undefined) out.group_rank = rank;
  return out;
}

/** Normalise one flat or nested action item into RuleAction. */
export function normalizeRuleAction(raw: unknown): RuleAction {
  if (!isRecord(raw)) {
    return {
      criterion: { snomed_concept_id: "", preferred_term: "" },
      strength: "unspecified",
    };
  }
  const group = normalizeGroupFields(raw);
  if (isRecord(raw.criterion)) {
    return {
      criterion: normalizeCriterion(raw.criterion),
      strength:
        typeof raw.strength === "string" ? raw.strength : "unspecified",
      ...group,
    };
  }
  // Flat API / legacy cache shape: snomed fields at top level.
  return {
    criterion: normalizeCriterion(raw),
    strength:
      typeof raw.strength === "string" ? raw.strength : "unspecified",
    ...group,
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
