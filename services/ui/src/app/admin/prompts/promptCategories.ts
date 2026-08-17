/**
 * Atlas trace:
 *   DO: DO-BCD21209
 *   DI: DI-553F50A2, DI-C5A523A7
 */
import { color } from "@leo/design-system/tokens";

export interface PromptConfig {
  id: string;
  name: string;
  description: string;
  version: number;
  verification: boolean;
  fewShotCount: number;
  updatedAt: string;
}

export type CategoryTone = {
  color: string;
  bg: string;
};

export const CATEGORY_ALL = "All";

const TONE = {
  brand: { color: color.brand.primary, bg: "rgba(13, 70, 214, 0.12)" },
  violet: { color: color.brand.secondary, bg: "rgba(147, 56, 255, 0.12)" },
  warn: { color: color.status.warning, bg: "rgba(180, 83, 9, 0.12)" },
  ok: { color: color.status.success, bg: "rgba(4, 120, 87, 0.12)" },
  navy: { color: color.brand.primaryHover, bg: "rgba(0, 33, 120, 0.1)" },
  mute: { color: color.text.secondary, bg: color.surface.alt },
} as const;

export const SBAR_CONTEXT_GROUP_STYLE: Record<string, CategoryTone> = {
  "Primary care": TONE.brand,
  "Secondary care": TONE.violet,
  "Statutory and social": TONE.navy,
  "Quality assurance": TONE.ok,
};

const SBAR_CONTEXT_GROUP_FALLBACK = TONE.mute;

export type PromptCategory = {
  label: string;
  tone: CategoryTone;
};

export function categorise(name: string, description?: string): PromptCategory {
  if (name.startsWith("sbar_situation_context_")) {
    const match = description?.match(/^\[([^\]]+)\]/);
    const group = match?.[1]?.trim() ?? "Summarisation context";
    const tone = SBAR_CONTEXT_GROUP_STYLE[group] ?? SBAR_CONTEXT_GROUP_FALLBACK;
    return { label: group, tone };
  }
  return categoryFromName(name.toLowerCase());
}

export function categoriseFromPrompt(p: PromptConfig): PromptCategory {
  return categorise(p.name, p.description);
}

export function humanName(raw: string): string {
  return raw.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function categoryFromName(n: string): PromptCategory {
  if (n.includes("extract") || n.includes("relation")) {
    return { label: "Extraction", tone: TONE.brand };
  }
  if (n.includes("classif") || n.includes("detect") || n.includes("exclusion")) {
    return { label: "Classification", tone: TONE.violet };
  }
  if (n.includes("disambig")) return { label: "Disambiguation", tone: TONE.warn };
  if (n.includes("verif") || n.includes("anchor")) {
    return { label: "Verification", tone: TONE.ok };
  }
  if (n.includes("episode") || n.includes("consolid") || n.includes("builder")) {
    return { label: "Episode builder", tone: TONE.navy };
  }
  if (n.includes("label")) return { label: "Labelling", tone: TONE.warn };
  return { label: "General", tone: TONE.mute };
}
