/**
 * Atlas trace:
 *   DO: DO-83EBEE2C
 *   DI: DI-B954388C
 */
import {
  DEFAULT_MAX_FEW_SHOT,
  type FewShotExample,
  type PromptConfigData,
  type SandboxProvider,
  type SandboxResult,
  type SandboxTier,
} from "./types";

export type PromptForm = {
  name: string;
  description: string;
  systemPrompt: string;
  outputSchema: string;
  verification: boolean;
  fewShotExamples: FewShotExample[];
  maxFewShot: number;
  version: number | null;
};

export type PromptUi = {
  tab: string;
  loaded: boolean;
  loadError: string | null;
  saveError: string | null;
  saveSuccess: boolean;
  saving: boolean;
  improving: boolean;
  aiSuggestion: string | null;
  filterCat: string;
  filterScope: string;
};

export type SandboxUi = {
  text: string;
  presetId: string;
  provider: SandboxProvider;
  tier: SandboxTier;
  dryRun: boolean;
  running: boolean;
  error: string | null;
  result: SandboxResult | null;
};

export const EMPTY_FORM: PromptForm = {
  name: "",
  description: "",
  systemPrompt: "",
  outputSchema: "{}",
  verification: false,
  fewShotExamples: [],
  maxFewShot: DEFAULT_MAX_FEW_SHOT,
  version: null,
};

export const EMPTY_UI: PromptUi = {
  tab: "instructions",
  loaded: false,
  loadError: null,
  saveError: null,
  saveSuccess: false,
  saving: false,
  improving: false,
  aiSuggestion: null,
  filterCat: "",
  filterScope: "",
};

export const EMPTY_SANDBOX: SandboxUi = {
  text: "",
  presetId: "__custom__",
  provider: "aws",
  tier: "small",
  dryRun: true,
  running: false,
  error: null,
  result: null,
};

export function formFromPrompt(data: PromptConfigData): PromptForm {
  return {
    name: data.name,
    description: data.description || "",
    systemPrompt: data.systemPrompt,
    outputSchema: data.outputSchema || "{}",
    verification: data.verification,
    fewShotExamples: (data.fewShotExamples || []).map((ex) => ({
      ...ex,
      category: ex.category ?? "",
      model_scope: ex.model_scope ?? "any",
      description: ex.description ?? "",
      core: Boolean(ex.core),
    })),
    maxFewShot: data.maxFewShot ?? DEFAULT_MAX_FEW_SHOT,
    version: data.version,
  };
}

export function blankExample(): FewShotExample {
  return {
    id: `ex_${Date.now()}`,
    input: "",
    output: "",
    deidentified: false,
    category: "",
    model_scope: "any",
    description: "",
    core: false,
  };
}

export function filterExamples(
  examples: FewShotExample[],
  filterCat: string,
  filterScope: string,
): FewShotExample[] {
  return examples.filter((ex) => {
    if (filterCat && ex.category !== filterCat) return false;
    if (filterScope && ex.model_scope !== filterScope) return false;
    return true;
  });
}

export function exampleCatCounts(
  examples: FewShotExample[],
): Record<string, number> {
  return examples.reduce<Record<string, number>>((acc, ex) => {
    const k = ex.category || "uncategorised";
    acc[k] = (acc[k] ?? 0) + 1;
    return acc;
  }, {});
}
