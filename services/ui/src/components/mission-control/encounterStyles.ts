/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-5312F884
 *   DI: DI-AA1F5F5B
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-5312F884")
 */
import type { CodedLink } from "@/lib/types";

// Semantic tag colour palette for SNOMED CT parenthetical suffixes.
// Shared by the EncounterCodesPanel chips and any other surface that
// needs to colour-code coded concepts. See DI-LEO-AI-179 / DO-LEO-AI-178.

export interface TagStyle {
  borderColor: string;
  bgcolor: string;
  color: string;
  label: string;
}

export const TAG_STYLE_MAP: Record<string, TagStyle> = {
  // Disorders: red -- highest clinical urgency
  disorder:            { borderColor: "#ef4444", bgcolor: "#fef2f2", color: "#991b1b", label: "Disorder" },
  disease:             { borderColor: "#ef4444", bgcolor: "#fef2f2", color: "#991b1b", label: "Disorder" },
  // Findings: fuchsia -- clearly distinct from amber observable and red disorder
  "clinical finding":  { borderColor: "#d946ef", bgcolor: "#fdf4ff", color: "#701a75", label: "Finding" },
  finding:             { borderColor: "#d946ef", bgcolor: "#fdf4ff", color: "#701a75", label: "Finding" },
  // Procedures: blue
  procedure:           { borderColor: "#3b82f6", bgcolor: "#eff6ff", color: "#1d4ed8", label: "Procedure" },
  "regime/therapy":    { borderColor: "#3b82f6", bgcolor: "#eff6ff", color: "#1d4ed8", label: "Procedure" },
  regime_therapy:      { borderColor: "#3b82f6", bgcolor: "#eff6ff", color: "#1d4ed8", label: "Procedure" },
  // Observables: amber/gold -- lab measurements
  "observable entity": { borderColor: "#b45309", bgcolor: "#fffbeb", color: "#78350f", label: "Observable" },
  observable_entity:   { borderColor: "#b45309", bgcolor: "#fffbeb", color: "#78350f", label: "Observable" },
  observable:          { borderColor: "#b45309", bgcolor: "#fffbeb", color: "#78350f", label: "Observable" },
  // Situations: violet
  situation:           { borderColor: "#8b5cf6", bgcolor: "#f5f3ff", color: "#5b21b6", label: "Situation" },
  // Substances and medications: emerald green
  substance:           { borderColor: "#10b981", bgcolor: "#ecfdf5", color: "#065f46", label: "Substance" },
  "medicinal product": { borderColor: "#10b981", bgcolor: "#ecfdf5", color: "#065f46", label: "Medication" },
  product:             { borderColor: "#10b981", bgcolor: "#ecfdf5", color: "#065f46", label: "Medication" },
  // Body structures: cyan
  "body structure":    { borderColor: "#06b6d4", bgcolor: "#ecfeff", color: "#155e75", label: "Body struct." },
  // Qualifier values: slate grey
  "qualifier value":   { borderColor: "#64748b", bgcolor: "#f8fafc", color: "#334155", label: "Qualifier" },
  qualifier_value:     { borderColor: "#64748b", bgcolor: "#f8fafc", color: "#334155", label: "Qualifier" },
  // Events: rose
  event:               { borderColor: "#f43f5e", bgcolor: "#fff1f2", color: "#9f1239", label: "Event" },
  // Organisms: lime green
  organism:            { borderColor: "#84cc16", bgcolor: "#f7fee7", color: "#3f6212", label: "Organism" },
  // Environments: teal
  environment:         { borderColor: "#0d9488", bgcolor: "#f0fdfa", color: "#134e4a", label: "Environment" },
};

export const DEFAULT_TAG_STYLE: TagStyle = {
  borderColor: "#94a3b8",
  bgcolor: "#f8fafc",
  color: "#334155",
  label: "Other",
};

export function getTagStyle(semanticTag: string | null | undefined): TagStyle {
  if (!semanticTag) return DEFAULT_TAG_STYLE;
  return TAG_STYLE_MAP[semanticTag.toLowerCase().trim()] ?? DEFAULT_TAG_STYLE;
}

export function getLinkAssertion(link: CodedLink): string | null {
  const explicit = (link.assertion ?? "").toString().trim().toLowerCase();
  if (explicit) return explicit;
  const context = (link.context ?? {}) as Record<string, unknown>;
  const fromContext = (context.assertion ?? "").toString().trim().toLowerCase();
  return fromContext || null;
}

export function isNegatedOrAbsent(link: CodedLink): boolean {
  const assertion = getLinkAssertion(link);
  if (assertion === "absent" || assertion === "negated" || assertion === "refuted") {
    return true;
  }
  const context = (link.context ?? {}) as Record<string, unknown>;
  return context.negated === true;
}
