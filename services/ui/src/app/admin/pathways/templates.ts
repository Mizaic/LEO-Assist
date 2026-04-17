/**
 * Pathway templates -- starter payloads for new clinical pathways.
 *
 * Used by the New Pathway dialog (NewPathwayDialog.tsx).
 *
 * Design Controls: DI-LEO-AI-150, DO-LEO-AI-146.
 */

export interface PathwayTemplate {
  id: string;
  name: string;
  description: string;
  stepCount: number;
  payload: Record<string, unknown>;
}

const baseConfig = (label: string, description: string, opts: Record<string, unknown> = {}) => ({
  label,
  description,
  inputSource: "encounter_text",
  outputTarget: "patient_graph",
  enableVerification: false,
  maxRetries: 2,
  timeout: 120,
  modelPresetId: "",
  modelPresetName: "",
  temperature: 0,
  promptConfigId: "",
  promptConfigName: "",
  params: {},
  ...opts,
});

// LONG FUNCTION: PATHWAY_TEMPLATES is a static data declaration; templates
// are deliberately verbose so they round-trip cleanly to the FHIR PlanDefinition
// API and produce a workable canvas without further editing.
export const PATHWAY_TEMPLATES: PathwayTemplate[] = [
  {
    id: "blank",
    name: "Start from scratch",
    description: "Empty canvas - add and connect steps yourself.",
    stepCount: 0,
    payload: { name: "New pathway", status: "draft", description: "", actions: [], edges: [] },
  },
  {
    id: "extraction-only",
    name: "Find clinical facts",
    description: "Read patient notes, extract clinical facts with AI, and save them to the patient record.",
    stepCount: 2,
    payload: {
      name: "Find Clinical Facts",
      status: "draft",
      description: "Extract clinical facts from patient encounter notes and save them.",
      trigger: { event: "encounter-created", type: "data-changed" },
      actions: [
        {
          id: "step_extract",
          subgraphId: "extraction",
          label: "Find Clinical Facts",
          nodeType: "action",
          position: { x: 200, y: 200 },
          config: { subgraphId: "extraction", ...baseConfig("Find Clinical Facts", "Read patient notes and pull out clinical facts.") },
        },
        {
          id: "step_persist",
          subgraphId: "persist",
          label: "Save Results",
          nodeType: "action",
          position: { x: 520, y: 200 },
          config: { subgraphId: "persist", ...baseConfig("Save Results", "Write extracted facts to the patient record.", { inputSource: "previous_step" }) },
        },
      ],
      edges: [{ source: "step_extract", target: "step_persist" }],
    },
  },
  {
    id: "extraction-verify-persist",
    name: "Find, double-check, then save",
    description: "Extract clinical facts, run a second AI pass to check for errors, then save to the patient record.",
    stepCount: 3,
    payload: {
      name: "Find, Verify and Save",
      status: "draft",
      description: "Extract clinical facts, verify them with a second AI, then save.",
      trigger: { event: "encounter-created", type: "data-changed" },
      actions: [
        {
          id: "step_extract",
          subgraphId: "extraction",
          label: "Find Clinical Facts",
          nodeType: "action",
          position: { x: 160, y: 200 },
          config: { subgraphId: "extraction", ...baseConfig("Find Clinical Facts", "Read patient notes and pull out clinical facts.") },
        },
        {
          id: "step_verify",
          subgraphId: "verification",
          label: "Double-Check with AI",
          nodeType: "action",
          position: { x: 460, y: 200 },
          config: { subgraphId: "verification", ...baseConfig("Double-Check with AI", "Run a second AI to catch any errors before saving.", { inputSource: "previous_step", maxRetries: 1 }) },
        },
        {
          id: "step_persist",
          subgraphId: "persist",
          label: "Save Results",
          nodeType: "action",
          position: { x: 760, y: 200 },
          config: { subgraphId: "persist", ...baseConfig("Save Results", "Write verified facts to the patient record.", { inputSource: "previous_step" }) },
        },
      ],
      edges: [
        { source: "step_extract", target: "step_verify" },
        { source: "step_verify", target: "step_persist" },
      ],
    },
  },
  {
    id: "training-audit",
    name: "Training data audit",
    description: "Extract facts from de-identified notes, verify them, and store as gold-labelled training data.",
    stepCount: 3,
    payload: {
      name: "Training Data Audit",
      status: "draft",
      description: "Extract and verify clinical facts from de-identified notes for gold-standard training labels.",
      trigger: { event: "training-candidate-ready", type: "data-changed" },
      actions: [
        {
          id: "step_extract",
          subgraphId: "extraction",
          label: "Find Clinical Facts",
          nodeType: "action",
          position: { x: 160, y: 200 },
          config: {
            subgraphId: "extraction",
            ...baseConfig("Find Clinical Facts", "Extract clinical facts from de-identified notes.", {
              inputSource: "knowledge_graph",
              outputTarget: "gold_training",
              params: { input_node_label: "TrainingCandidate", input_text_property: "text" },
            }),
          },
        },
        {
          id: "step_verify",
          subgraphId: "verification",
          label: "Double-Check with AI",
          nodeType: "action",
          position: { x: 460, y: 200 },
          config: {
            subgraphId: "verification",
            ...baseConfig("Double-Check with AI", "Verify extracted facts against the source text.", {
              inputSource: "previous_step",
              outputTarget: "gold_training",
              maxRetries: 1,
            }),
          },
        },
        {
          id: "step_persist",
          subgraphId: "persist",
          label: "Save as Training Labels",
          nodeType: "action",
          position: { x: 760, y: 200 },
          config: {
            subgraphId: "persist",
            ...baseConfig("Save as Training Labels", "Write gold-labelled facts to the training dataset.", {
              inputSource: "previous_step",
              outputTarget: "gold_training",
            }),
          },
        },
      ],
      edges: [
        { source: "step_extract", target: "step_verify" },
        { source: "step_verify", target: "step_persist" },
      ],
    },
  },
];
