/**
 * Episode card accent colours. Presentation only -- Neo4j does not own
 * UI colour. Condition type still comes from the episode graph row.
 *
 * Atlas trace:
 *   DO: DO-5D3EA371
 *   DI: DI-357A7468
 */

import { color } from "@leo/design-system";

const CONDITION_ACCENT: Record<string, string> = {
  lung: color.brand.primaryHover,
  breast: "#9D174D",
  prostate: color.brand.secondaryHover,
  colorectal: color.status.warning,
  lower_gi: color.status.warning,
  upper_gi: "#7C3AED",
  skin: color.status.success,
  haematology: "#0369A1",
  gynaecology: "#BE185D",
  head_and_neck: color.brand.primary,
  urology: "#4338CA",
};

export function accentFor(type: string | null): string {
  const key = (type ?? "").toLowerCase().replace(/ /g, "_");
  return CONDITION_ACCENT[key] ?? color.status.neutral;
}

export function outcomeColor(outcome: string | null): string {
  const o = (outcome ?? "").toLowerCase();
  if (o === "cancer") return color.status.danger;
  if (o === "benign") return color.status.success;
  return color.status.neutral;
}

export function outcomeLabel(outcome: string | null): string {
  if (!outcome) return "";
  const o = outcome.toLowerCase();
  if (o === "cancer") return "Cancer confirmed";
  if (o === "benign") return "Benign";
  if (o.includes("watch")) return "Watchful waiting";
  return outcome.replace(/_/g, " ");
}
