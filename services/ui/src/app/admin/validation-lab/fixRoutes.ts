/**
 * Route a Validation Lab finding to the matching Knowledge tool.
 *
 * Atlas: DI-562F2C9E / DO-4FD76836
 *
 * Atlas trace:
 *   DO: DO-158BE606
 *   DI: DI-2289D095
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-158BE606")
 */
import type { FindingCategory } from "./findingTypes";

export interface FixRouteInput {
  category: FindingCategory | string;
  target?: string;
  promptName?: string;
  firedRuleId?: string;
  sourceSentence?: string;
  guidelineRuleId?: string;
}

export function fixHref(input: FixRouteInput): string {
  const target = (input.target || "").trim();
  if (input.category === "extraction" || input.category === "semantic_tag") {
    const params = new URLSearchParams({ tab: "ai-instructions" });
    if (input.promptName) params.set("prompt_name", input.promptName);
    else if (target) params.set("prompt_name", target);
    return `/admin/knowledge?${params.toString()}`;
  }
  if (input.category === "context") {
    const params = new URLSearchParams({ tab: "context-rules" });
    if (target) params.set("term", target);
    return `/admin/knowledge?${params.toString()}`;
  }
  if (input.category === "guard") {
    const params = new URLSearchParams({ tab: "guard-rules" });
    if (input.firedRuleId) params.set("fired_rule_id", input.firedRuleId);
    if (input.sourceSentence || target) {
      params.set("source_sentence", input.sourceSentence || target);
    }
    return `/admin/knowledge?${params.toString()}`;
  }
  if (input.category === "phrase_mapping") {
    const params = new URLSearchParams({ tab: "surface-forms" });
    if (target) {
      params.set("q", target);
      params.set("phrase_key", target);
    }
    return `/admin/knowledge?${params.toString()}`;
  }
  const params = new URLSearchParams({ tab: "clinical-guidelines" });
  if (input.guidelineRuleId || target) {
    params.set("rule_id", input.guidelineRuleId || target);
  }
  return `/admin/knowledge?${params.toString()}`;
}

export function isInlineFix(category: string): boolean {
  return category === "phrase_mapping" || category === "guard";
}
