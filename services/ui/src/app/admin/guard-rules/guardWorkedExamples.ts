/**
 * Worked examples for Pipeline Guards.
 *
 * Notes come from the automated tests that already prove each guard.
 */
import catalog from "./guard_worked_examples.json";

export interface GuardWorkedExample {
  note: string;
  withoutGuard: string;
  withGuard: string;
  dataChange: string;
  sourceTest?: string;
}

interface RawExample {
  note: string;
  without_guard: string;
  with_guard: string;
  data_change: string;
  source_test?: string;
}

function toExample(raw: RawExample): GuardWorkedExample {
  return {
    note: raw.note,
    withoutGuard: raw.without_guard,
    withGuard: raw.with_guard,
    dataChange: raw.data_change,
    sourceTest: raw.source_test,
  };
}

function looksLikeRegex(pattern: string): boolean {
  return /[\\|()^$]|\[\^|\(\?:/.test(pattern);
}

function namedTestExample(pattern: string, fallback: GuardWorkedExample): GuardWorkedExample {
  const token = pattern.trim();
  if (!token || looksLikeRegex(token)) return fallback;
  return {
    ...fallback,
    note: `2WW referral for ${token}`,
    withGuard: `Kept because this span names ${token}, a real test.`,
  };
}

export function resolveWorkedExample(
  family: string,
  ruleType?: string,
  rulePattern?: string,
  _summary?: string,
  ruleId?: string,
): GuardWorkedExample {
  const families = catalog.families as Record<string, RawExample>;
  const types = catalog.types as Record<string, RawExample>;
  const rules = catalog.rules as Record<string, RawExample>;
  if (ruleId && rules[ruleId]) return toExample(rules[ruleId]);
  const typeKey = ruleType ? `${family}:${ruleType}` : "";
  const raw = (typeKey && types[typeKey]) || families[family] || families.scope_guard;
  const base = toExample(raw);
  if (family === "referral_routing_guard" && ruleType === "named_test") {
    return namedTestExample(rulePattern ?? "", base);
  }
  return base;
}
