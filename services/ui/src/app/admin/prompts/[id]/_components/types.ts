/**
 * Shared types, taxonomy and colour vocabulary for the AI Instructions
 * editor. Extracted from prompts/[id]/page.tsx as part of Wave E Phase 4b
 * (DI-LEO-AI-170 / VT-LEO-AI-169) so the orchestrator drops below the
 * 300 LOC target.
 */

export interface FewShotExample {
  id: string;
  input: string;
  output: string;
  deidentified: boolean;
  category: string;
  model_scope: string;
  description: string;
  core: boolean;
}

export interface PromptConfigData {
  id: string;
  name: string;
  description: string;
  version: number;
  systemPrompt: string;
  outputSchema: string;
  verification: boolean;
  fewShotExamples: FewShotExample[];
  maxFewShot?: number;
}

export type ChipColour =
  | "default"
  | "primary"
  | "secondary"
  | "error"
  | "warning"
  | "info"
  | "success";

export type SandboxProvider = "aws" | "azure";
export type SandboxTier = "small" | "big" | "max";

export type CostBreakdown = {
  totalCost: number;
  inputCost?: number;
  outputCost?: number;
  cachedInputCost?: number;
  uncachedInputCost?: number;
};

export type CostEstimate = {
  role: "primary" | "secondary";
  model: {
    key: string;
    displayName: string;
    modelId: string;
    costPer1mInput: number;
    costPer1mCachedInput: number;
    costPer1mOutput: number;
  };
  systemTokens: number;
  userTokens: number;
  estOutputTokens: number;
  withoutCache: CostBreakdown;
  withCache: CostBreakdown;
  cacheSavingPct: number;
};

export type SandboxResult = {
  presetName: string;
  consensusMode: boolean;
  systemPrompt: string;
  coreExamples: SandboxExample[];
  selectedDynamicExamples: SandboxDynamicExample[];
  userMessage: string;
  tokenEstimate: {
    approxSystemTokens: number;
    approxUserTokens: number;
    estOutputTokens: number;
  };
  costEstimates: CostEstimate[];
  llmResponse: string | null;
  llmTokenUsage: {
    inputTokens: number;
    outputTokens: number;
    cachedInputTokens: number;
  } | null;
  llmActualCostUsd: number | null;
};

export interface SandboxExample {
  category: string;
  description: string;
  input: string;
  output: string;
}

export interface SandboxDynamicExample extends SandboxExample {
  _similarity_score?: number;
}

export interface PresetItem {
  preset_id: string;
  name: string;
  primary_model: string;
  secondary_model: string;
  consensus_mode: boolean;
  color: string;
}

const CATEGORY_OPTIONS_REST = [
  { value: "assertion:absent", label: "Absent / negated" },
  { value: "assertion:possible", label: "Possible / uncertain" },
  { value: "assertion:historical", label: "Historical / resolved" },
  { value: "assertion:hypothetical", label: "Hypothetical / planned" },
  { value: "assertion:family", label: "Family history" },
  { value: "assertion:refuted", label: "Refuted (overridden)" },
  { value: "assertion:declined", label: "Declined by patient" },
  { value: "assertion:cancelled", label: "Cancelled" },
  { value: "negation:compound", label: "Compound negation" },
  { value: "multi-entity", label: "Multiple entities" },
  { value: "observable", label: "Observable / lab result" },
  { value: "vital-signs", label: "Vital signs" },
  { value: "staging", label: "Cancer staging / performance status" },
  { value: "abbreviation", label: "Abbreviation expansion" },
  { value: "brand-name", label: "Brand name -> generic" },
  { value: "situation:allergy", label: "Allergy status" },
  { value: "situation:referral", label: "Referral / planned procedure" },
  { value: "situation:smoking", label: "Smoking status" },
];

export const CATEGORY_OPTIONS = [
  { value: "", label: "All categories" },
  ...[...CATEGORY_OPTIONS_REST].sort((a, b) =>
    a.label.localeCompare(b.label, "en", { sensitivity: "base" }),
  ),
];

export const SCOPE_OPTIONS = [
  { value: "aws", label: "AWS only (Claude / Bedrock)" },
  { value: "azure", label: "Azure only (OpenAI / GPT)" },
  { value: "any", label: "Both providers (AWS + Azure)" },
];

export function categoryLabel(cat: string): string {
  return CATEGORY_OPTIONS.find((o) => o.value === cat)?.label ?? cat;
}

export function categoryColor(cat: string): ChipColour {
  if (cat.startsWith("assertion:absent") || cat.startsWith("negation"))
    return "error";
  if (cat.startsWith("assertion:possible")) return "warning";
  if (cat.startsWith("assertion:historical")) return "secondary";
  if (
    cat.startsWith("assertion:declined") ||
    cat.startsWith("assertion:cancelled")
  )
    return "error";
  if (cat.startsWith("assertion:family")) return "info";
  if (cat.startsWith("staging")) return "secondary";
  if (cat.startsWith("observable") || cat.startsWith("vital")) return "primary";
  if (cat.startsWith("multi")) return "warning";
  return "default";
}

export const TAG_COLORS: Record<string, ChipColour> = {
  disorder: "error",
  finding: "warning",
  "observable entity": "primary",
  procedure: "info",
  substance: "secondary",
  product: "secondary",
  situation: "default",
  "regime/therapy": "info",
  "staging scale": "success",
};

export const ASSERTION_COLORS: Record<string, ChipColour> = {
  present: "success",
  absent: "error",
  refuted: "error",
  possible: "warning",
  historical: "default",
  hypothetical: "info",
  family: "info",
  declined: "warning",
  cancelled: "default",
};

export const DEFAULT_MAX_FEW_SHOT = 20;
