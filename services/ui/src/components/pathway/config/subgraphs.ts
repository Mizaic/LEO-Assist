import type { FieldMappingRow, PortDefinition } from "./types";

export const SUBGRAPH_OPTIONS = [
  { id: "encounter_loader",  label: "Load Encounter Text",     color: "#607D8B", category: "Data",            description: "Load encounter clinical text from Neo4j using encounter_id." },
  { id: "extraction",        label: "Find Clinical Facts",    color: "#4CAF50", category: "Clinical AI",     description: "Read patient notes and pull out clinical facts — symptoms, conditions, procedures, test results." },
  { id: "post_processing",   label: "Clean Up Results",       color: "#2196F3", category: "Clinical AI",     description: "Tidy the found facts — remove duplicates, expand abbreviations, and apply context rules." },
  { id: "extraction_check",  label: "Extraction Quality Check", color: "#616161", category: "Quality",        description: "Run a lightweight AI pass to catch extraction-level issues before terminology coding." },
  { id: "terminology",       label: "Code to SNOMED CT",      color: "#FF9800", category: "Clinical AI",     description: "Match each clinical fact to an official SNOMED CT medical code." },
  { id: "coding_check",      label: "Coding Quality Check",   color: "#424242", category: "Quality",          description: "Run a lightweight AI plausibility check on coded entities before confidence grading." },
  { id: "tier_classify",     label: "Grade Confidence",       color: "#9C27B0", category: "Clinical AI",     description: "Rate each clinical fact as gold, silver, or bronze based on how confident the AI is." },
  { id: "verification",      label: "Double-Check with AI",   color: "#F44336", category: "Quality",         description: "Run a second, more capable AI over the results to spot errors before saving." },
  { id: "surface_form_validation", label: "Validate Surface Forms", color: "#8BC34A", category: "Quality",  description: "Check resolved codes against the extracted wording and flag mapping mismatches." },
  { id: "compliance",        label: "Check Compliance",       color: "#795548", category: "Quality",         description: "Compare the results against clinical guidelines and flag any gaps." },
  { id: "quality_check",     label: "Quality Check",          color: "#009688", category: "Quality",         description: "Check for missing data, inconsistencies, and NHS target compliance." },
  { id: "persist",           label: "Save Results",           color: "#607D8B", category: "Data",            description: "Write the final clinical facts to the patient record or gold training dataset." },
  { id: "sbar",              label: "Write SBAR Summary",     color: "#00BCD4", category: "Reports",         description: "Generate a Situation-Background-Assessment-Recommendation clinical summary." },
  { id: "anchor_detect",     label: "Detect Key Findings",    color: "#E91E63", category: "Reports",         description: "Identify the significant clinical findings that start a new episode of care." },
  { id: "episode_build",     label: "Build Episode",          color: "#3F51B5", category: "Reports",         description: "Group related encounters together into a timeline episode of care." },
  { id: "safety_net",        label: "Safety Netting",         color: "#FF5722", category: "Safety",          description: "Flag overdue tests, missing referral replies, or follow-up actions that are past due." },
  { id: "next_best_action",  label: "Next Best Action",       color: "#673AB7", category: "Safety",          description: "Suggest the most appropriate next clinical action based on the patient context." },
  { id: "rest_connector",    label: "Call REST API",          color: "#607D8B", category: "Integration",     description: "Send runtime state to an external REST API and map the response back into the pipeline." },
  { id: "queue_publish",     label: "Publish Queue Message",  color: "#455A64", category: "Integration",     description: "Publish a message to the configured queue or topic for asynchronous downstream work." },
  { id: "guidance_rule_extraction", label: "Extract Guidance Rule", color: "#6A1B9A", category: "Clinical AI", description: "Turn a guideline recommendation into a structured logic tree and a coded action." },
];

export const SUBGRAPH_IO: Record<string, {
  reads: string[];
  writes: string[];
  requiredFields?: Record<string, string[]>;
}> = {
  encounter_loader: { reads: ["encounter_id"], writes: ["encounter_text"] },
  extraction: { reads: ["encounter_text"], writes: ["entities", "sentences", "errors"] },
  post_processing: {
    reads: ["entities", "encounter_text"],
    writes: ["entities", "errors"],
    requiredFields: { entities: ["text", "semantic_tag", "assertion"] },
  },
  extraction_check: {
    reads: ["entities", "encounter_text"],
    writes: ["entities", "llm_check_result", "llm_check_changes", "errors"],
    requiredFields: { entities: ["text", "semantic_tag", "assertion"] },
  },
  verification: {
    reads: ["entities", "encounter_text"],
    writes: ["is_verified", "verification_result", "errors"],
    requiredFields: { entities: ["text", "lookup_term", "semantic_tag", "assertion"] },
  },
  surface_form_validation: {
    reads: ["entities"],
    writes: ["entities", "errors"],
    requiredFields: { entities: ["text", "lookup_term", "semantic_tag"] },
  },
  terminology: {
    reads: ["entities"],
    writes: ["entities", "errors"],
    requiredFields: { entities: ["text", "lookup_term", "semantic_tag"] },
  },
  coding_check: {
    reads: ["entities", "encounter_text"],
    writes: ["entities", "llm_check_result", "llm_check_changes", "errors"],
    requiredFields: { entities: ["text", "lookup_term", "semantic_tag", "assertion"] },
  },
  tier_classify: {
    reads: ["entities"],
    writes: ["entities", "tier_decisions"],
    requiredFields: { entities: ["text", "semantic_tag", "assertion"] },
  },
  persist: {
    reads: ["entities", "encounter_id", "patient_id"],
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
  guidance_rule_extraction: {
    reads: ["recommendation", "guideline_id"],
    writes: ["coded_criteria", "errors"],
  },
};

export type SubgraphCategory = "llm" | "persist" | "post_process" | "terminology" | "tier_classify" | "generic";

export const SUBGRAPH_CATEGORY: Record<string, SubgraphCategory> = {
  extraction: "llm",
  extraction_check: "llm",
  verification: "llm",
  coding_check: "llm",
  sbar: "llm",
  anchor_detect: "llm",
  episode_build: "llm",
  next_best_action: "llm",
  quality_check: "llm",
  compliance: "llm",
  guidance_rule_extraction: "llm",
  encounter_loader: "generic",
  persist: "persist",
  post_processing: "post_process",
  terminology: "terminology",
  tier_classify: "tier_classify",
  surface_form_validation: "generic",
  safety_net: "generic",
  rest_connector: "generic",
  queue_publish: "generic",
};

export const WIZARD_STEPS_LLM    = ["Step type", "Data connections", "Settings", "AI & outputs", "Review"];
export const WIZARD_STEPS_NO_LLM = ["Step type", "Data connections", "Settings", "Review"];

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
  if (["verification_result", "sbar_report", "compliance_result", "connector_response", "coded_criteria", "anchor_result"].includes(key)) return "object";
  return "string";
}

/**
 * Derive output port handles from the user's saved field mappings.
 * Extracts unique top-level state keys from statePath values
 * (e.g. "entities[].text" → port key "entities").
 * Falls back to an empty array when no mappings have a resolved statePath.
 */
export function getPortsFromFieldMappings(fieldMappings: FieldMappingRow[]): PortDefinition[] {
  const seen = new Set<string>();
  for (const row of fieldMappings) {
    const path = row.statePath?.trim();
    if (!path) continue;
    // passthrough rows still produce an output port
    const match = path.match(/^(\w+)/);
    if (match) seen.add(match[1]);
  }
  return Array.from(seen).map((key) => ({
    key,
    direction: "output" as const,
    dataType: inferDataType(key),
    required: false,
  }));
}

export function getPortsFromDescriptor(
  subgraphId: string,
  fieldMappings?: FieldMappingRow[],
): PortDefinition[] {
  const io = SUBGRAPH_IO[subgraphId];
  if (!io) return [];

  const inputs = io.reads.map((key) => ({
    key,
    direction: "input" as const,
    dataType: inferDataType(key),
    required: true,
    fields: io.requiredFields?.[key],
  }));

  // When the user has explicitly configured field mappings, derive output ports
  // from those mappings instead of the static SUBGRAPH_IO writes. This makes
  // the canvas ports reflect what was actually wired up in the wizard (n8n style).
  const dynamicOutputs =
    fieldMappings && fieldMappings.length > 0
      ? getPortsFromFieldMappings(fieldMappings)
      : [];

  const outputs =
    dynamicOutputs.length > 0
      ? dynamicOutputs
      : io.writes.map((key) => ({
          key,
          direction: "output" as const,
          dataType: inferDataType(key),
          required: false,
        }));

  return [...inputs, ...outputs];
}


