import type { PortDefinition } from "./types";

export const SUBGRAPH_OPTIONS = [
  { id: "extraction", label: "Entity Extraction", color: "#4CAF50", description: "Extract clinical entities (findings, conditions, procedures) from encounter text using NER or LLM." },
  { id: "post_processing", label: "Post-Processing", color: "#2196F3", description: "Clean and normalise extracted entities — merge duplicates, fix abbreviations, apply context rules." },
  { id: "terminology", label: "Terminology Resolution", color: "#FF9800", description: "Resolve surface forms to SNOMED CT codes via the Terminology API." },
  { id: "tier_classify", label: "Tier Classification", color: "#9C27B0", description: "Classify each entity into confidence tiers (gold / silver / bronze) for review prioritisation." },
  { id: "verification", label: "Verification", color: "#F44336", description: "Use a larger LLM to verify pipeline output quality before persisting results." },
  { id: "persist", label: "Persist Results", color: "#607D8B", description: "Write final entities to the Patient Graph or Gold Training Dataset." },
  { id: "sbar", label: "SBAR Generation", color: "#00BCD4", description: "Generate a Situation-Background-Assessment-Recommendation summary for the encounter." },
  { id: "compliance", label: "Compliance Check", color: "#795548", description: "Check extracted data against guideline graphs and compliance rules." },
  { id: "anchor_detect", label: "Anchor Detection", color: "#E91E63", description: "Detect clinical anchors (significant findings) that trigger episodes of care." },
  { id: "episode_build", label: "Episode Builder", color: "#3F51B5", description: "Group anchored encounters into episodes of care with timeline tracking." },
  { id: "safety_net", label: "Safety Netting", color: "#FF5722", description: "Monitor for overdue investigations, referral responses, and follow-up actions." },
  { id: "quality_check", label: "Quality Check", color: "#009688", description: "Run data quality checks (completeness, consistency, NHS target compliance)." },
  { id: "next_best_action", label: "Next Best Action", color: "#673AB7", description: "Generate recommended next actions based on clinical context and guidelines." },
];

export const SUBGRAPH_IO: Record<string, {
  reads: string[];
  writes: string[];
  requiredFields?: Record<string, string[]>;
}> = {
  extraction: { reads: ["encounter_text"], writes: ["entities", "sentences", "errors"] },
  post_processing: {
    reads: ["entities", "encounter_text"],
    writes: ["entities", "errors"],
    requiredFields: { entities: ["text", "semantic_tag", "assertion"] },
  },
  verification: {
    reads: ["entities", "encounter_text"],
    writes: ["is_verified", "verification_result", "errors"],
    requiredFields: { entities: ["text", "lookup_term", "semantic_tag", "assertion"] },
  },
  terminology: {
    reads: ["entities"],
    writes: ["entities", "errors"],
    requiredFields: { entities: ["text", "lookup_term", "semantic_tag"] },
  },
  tier_classify: {
    reads: ["entities"],
    writes: ["entities", "tier_decisions"],
    requiredFields: { entities: ["text", "semantic_tag", "assertion"] },
  },
  persist: {
    reads: ["entities", "encounter_id", "patient_id", "output_target"],
    writes: ["documents_written", "training_labels_written"],
    requiredFields: { entities: ["text", "lookup_term", "semantic_tag", "assertion"] },
  },
  sbar: {
    reads: ["entities", "encounter_text", "patient_id"],
    writes: ["sbar_report"],
    requiredFields: { entities: ["text", "semantic_tag", "assertion"] },
  },
  compliance: {
    reads: ["entities"],
    writes: ["compliance_result"],
    requiredFields: { entities: ["text", "semantic_tag", "assertion"] },
  },
  anchor_detect: {
    reads: ["entities"],
    writes: ["anchors"],
    requiredFields: { entities: ["text", "semantic_tag", "assertion"] },
  },
  episode_build: {
    reads: ["entities", "patient_id"],
    writes: ["episodes"],
    requiredFields: { entities: ["text", "semantic_tag", "assertion"] },
  },
  safety_net: {
    reads: ["entities", "patient_id"],
    writes: ["safety_net_alerts"],
    requiredFields: { entities: ["text", "semantic_tag", "assertion"] },
  },
  quality_check: {
    reads: ["entities"],
    writes: ["quality_issues"],
    requiredFields: { entities: ["text", "lookup_term", "semantic_tag", "assertion"] },
  },
  next_best_action: {
    reads: ["entities", "patient_id"],
    writes: ["recommendations"],
    requiredFields: { entities: ["text", "semantic_tag", "assertion"] },
  },
  rest_connector: { reads: ["*"], writes: ["connector_response", "errors"] },
  queue_publish: { reads: ["*"], writes: ["queued", "errors"] },
};

export type SubgraphCategory = "llm" | "persist" | "post_process" | "terminology" | "tier_classify" | "generic";

export const SUBGRAPH_CATEGORY: Record<string, SubgraphCategory> = {
  extraction: "llm",
  verification: "llm",
  sbar: "llm",
  anchor_detect: "llm",
  episode_build: "llm",
  next_best_action: "llm",
  quality_check: "llm",
  compliance: "llm",
  persist: "persist",
  post_processing: "post_process",
  terminology: "terminology",
  tier_classify: "tier_classify",
  safety_net: "generic",
  rest_connector: "generic",
  queue_publish: "generic",
};

export const WIZARD_STEPS_LLM = ["Subgraph", "Data flow", "Settings", "Prompt & model", "Review"];
export const WIZARD_STEPS_NO_LLM = ["Subgraph", "Data flow", "Settings", "Review"];

export function inferDataType(key: string): PortDefinition["dataType"] {
  const arrayKeys = new Set([
    "entities",
    "sentences",
    "errors",
    "tier_decisions",
    "documents_written",
    "training_labels_written",
    "anchors",
    "episodes",
    "safety_net_alerts",
    "quality_issues",
    "recommendations",
  ]);
  if (arrayKeys.has(key)) return "object[]";
  if (key === "is_verified") return "boolean";
  if (["verification_result", "sbar_report", "compliance_result", "connector_response"].includes(key)) return "object";
  return "string";
}

export function getPortsFromDescriptor(
  subgraphId: string,
  requiredFields?: Record<string, string[]>,
): PortDefinition[] {
  const io = SUBGRAPH_IO[subgraphId];
  if (!io) return [];
  const inputs = io.reads.map((key) => ({
    key,
    direction: "input" as const,
    dataType: inferDataType(key),
    required: true,
    fields: requiredFields?.[key] ?? io.requiredFields?.[key],
  }));
  const outputs = io.writes.map((key) => ({
    key,
    direction: "output" as const,
    dataType: inferDataType(key),
    required: false,
  }));
  return [...inputs, ...outputs];
}

