/**
 * Map Ask LEO coding results onto extraction-review fact tags.
 *
 * Atlas trace:
 *   DO: DO-E7824FED
 *   DI: DI-4A012A59
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-E7824FED")
 */
import { semanticTagKey, TAG_STYLE } from "@/app/admin/validation-lab/letterMarkStyle";
import type { AskLeoSmartResult } from "@/lib/types";

export type AskLeoFactPatch = {
  semantic_tag: string;
  assertion: string;
};

const TAG_ALIASES: Record<string, string> = {
  clinical_finding: "finding",
  finding: "finding",
  disorder: "disorder",
  situation: "situation",
  procedure: "procedure",
  observable_entity: "observable",
  observable: "observable",
  substance: "substance",
  body_structure: "body_structure",
  qualifier_value: "qualifier_value",
};

export function tagFromLeoCandidate(raw?: string): string {
  const key = semanticTagKey(raw);
  if (TAG_STYLE[key]) return key;
  if (TAG_ALIASES[key]) return TAG_ALIASES[key];
  if (key.includes("finding")) return "finding";
  if (key.includes("disorder")) return "disorder";
  if (key.includes("observable")) return "observable";
  if (key.includes("body")) return "body_structure";
  return "";
}

export function applyAskLeoPatch(
  result: AskLeoSmartResult,
): AskLeoFactPatch | null {
  if (result.assertion_warning || result.is_ambiguous) return null;
  const match = result.matched_candidate;
  if (!match) return null;
  const semantic_tag = tagFromLeoCandidate(match.semantic_tag);
  if (!semantic_tag) return null;
  return {
    semantic_tag,
    assertion: result.assertion || "present",
  };
}

export function nextUnsetFact(
  entities: Array<{ text: string; semantic_tag?: string }>,
  currentText: string,
): string {
  const start = entities.findIndex((entity) => entity.text === currentText);
  const rest =
    start < 0
      ? entities
      : [...entities.slice(start + 1), ...entities.slice(0, start)];
  const next = rest.find((entity) => !String(entity.semantic_tag ?? "").trim());
  return next?.text ?? "";
}
