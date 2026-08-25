/**
 * Map Ask LEO coding results onto extraction-review fact tags.
 *
 * Atlas: DI-4A012A59 / DO-E7824FED
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
