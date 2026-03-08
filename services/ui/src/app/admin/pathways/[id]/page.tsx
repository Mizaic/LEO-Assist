"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import IconButton from "@mui/material/IconButton";
import Drawer from "@mui/material/Drawer";
import TextField from "@mui/material/TextField";
import Select from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import FormControl from "@mui/material/FormControl";
import FormControlLabel from "@mui/material/FormControlLabel";
import InputLabel from "@mui/material/InputLabel";
import Chip from "@mui/material/Chip";
import Switch from "@mui/material/Switch";
import Stepper from "@mui/material/Stepper";
import Step from "@mui/material/Step";
import StepLabel from "@mui/material/StepLabel";
import Divider from "@mui/material/Divider";
import Alert from "@mui/material/Alert";
import CircularProgress from "@mui/material/CircularProgress";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Paper from "@mui/material/Paper";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import SaveIcon from "@mui/icons-material/Save";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import HistoryIcon from "@mui/icons-material/History";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  addEdge,
  useNodesState,
  useEdgesState,
  Handle,
  Position,
  type Node,
  type Edge,
  type Connection,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { api } from "@/lib/api";
import { nodeTypes as pathwayNodeTypes } from "@/components/pathway/nodes/nodeTypes";
import { PortEdge } from "@/components/pathway/edges/PortEdge";
import { SidePanel } from "@/components/pathway/panel/SidePanel";

const SUBGRAPH_OPTIONS = [
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

// Sentinel value used to mark pass-through rows in field mappings (not sourced from LLM output).
const PIPELINE_GENERATED_SENTINEL = "__pipeline_passthrough__";

// requiredFields: per state-key, the sub-fields this step MUST find on each item.
// These drive field-level validation when a predecessor provides field_mappings.
const SUBGRAPH_IO: Record<string, {
  reads: string[];
  writes: string[];
  requiredFields?: Record<string, string[]>;
}> = {
  extraction: {
    reads:  ["encounter_text"],
    writes: ["entities", "sentences", "errors"],
    // extraction produces all entity fields — nothing required from upstream entities
  },
  post_processing: {
    reads:  ["entities", "encounter_text"],
    writes: ["entities", "errors"],
    requiredFields: {
      entities: ["text", "semantic_tag", "assertion"],
    },
  },
  verification: {
    reads:  ["entities", "encounter_text"],
    writes: ["is_verified", "verification_result", "errors"],
    requiredFields: {
      entities: ["text", "lookup_term", "semantic_tag", "assertion"],
    },
  },
  terminology: {
    reads:  ["entities"],
    writes: ["entities", "errors"],
    requiredFields: {
      entities: ["text", "lookup_term", "semantic_tag"],
    },
  },
  tier_classify: {
    reads:  ["entities"],
    writes: ["entities", "tier_decisions"],
    requiredFields: {
      entities: ["text", "semantic_tag", "assertion"],
    },
  },
  persist: {
    reads:  ["entities", "encounter_id", "patient_id", "output_target"],
    writes: ["documents_written", "training_labels_written"],
    requiredFields: {
      entities: ["text", "lookup_term", "semantic_tag", "assertion"],
    },
  },
  sbar: {
    reads:  ["entities", "encounter_text", "patient_id"],
    writes: ["sbar_report"],
    requiredFields: {
      entities: ["text", "semantic_tag", "assertion"],
    },
  },
  compliance: {
    reads:  ["entities"],
    writes: ["compliance_result"],
    requiredFields: {
      entities: ["text", "semantic_tag", "assertion"],
    },
  },
  anchor_detect: {
    reads:  ["entities"],
    writes: ["anchors"],
    requiredFields: {
      entities: ["text", "semantic_tag", "assertion"],
    },
  },
  episode_build: {
    reads:  ["entities", "patient_id"],
    writes: ["episodes"],
    requiredFields: {
      entities: ["text", "semantic_tag", "assertion"],
    },
  },
  safety_net: {
    reads:  ["entities", "patient_id"],
    writes: ["safety_net_alerts"],
    requiredFields: {
      entities: ["text", "semantic_tag", "assertion"],
    },
  },
  quality_check: {
    reads:  ["entities"],
    writes: ["quality_issues"],
    requiredFields: {
      entities: ["text", "lookup_term", "semantic_tag", "assertion"],
    },
  },
  next_best_action: {
    reads:  ["entities", "patient_id"],
    writes: ["recommendations"],
    requiredFields: {
      entities: ["text", "semantic_tag", "assertion"],
    },
  },
};

const TRIGGER_OPTIONS = [
  { id: "encounter-created", label: "New Encounter Created", description: "Fires when a new GP encounter document is ingested." },
  { id: "referral-received", label: "Referral Received", description: "Fires when a referral letter is uploaded or received via integration." },
  { id: "training-run-requested", label: "Training Run Requested", description: "Manual trigger — used to generate gold-standard NER training data." },
  { id: "results-received", label: "Investigation Results Received", description: "Fires when lab results or diagnostic reports arrive." },
  { id: "safety-net-check", label: "Safety Net Timer", description: "Scheduled check for overdue investigations and follow-ups." },
  { id: "manual", label: "Manual / API Call", description: "Pipeline is invoked manually via the API or admin UI." },
];

// ── Subgraph categories ───────────────────────────────────────────────────────
// Controls which config panels and wizard steps are shown.
type SubgraphCategory = "llm" | "persist" | "post_process" | "terminology" | "tier_classify" | "generic";

const SUBGRAPH_CATEGORY: Record<string, SubgraphCategory> = {
  extraction:       "llm",
  verification:     "llm",
  sbar:             "llm",
  anchor_detect:    "llm",
  episode_build:    "llm",
  next_best_action: "llm",
  quality_check:    "llm",
  compliance:       "llm",
  persist:          "persist",
  post_processing:  "post_process",
  terminology:      "terminology",
  tier_classify:    "tier_classify",
  safety_net:       "generic",
};

// Wizard steps — step 3 (Prompt) is hidden for non-LLM subgraphs
const WIZARD_STEPS_LLM     = ["Subgraph", "Data flow", "Settings", "Prompt & model", "Review"];
const WIZARD_STEPS_NO_LLM  = ["Subgraph", "Data flow", "Settings", "Review"];

interface ActionConfig {
  subgraphId: string;
  label: string;
  description: string;
  // Data flow
  inputSource: string;
  outputTarget: string;
  // Runtime
  enableVerification: boolean;
  maxRetries: number;
  timeout: number;
  // LLM
  modelPresetId: string;
  modelPresetName: string;
  temperature: number;
  promptConfigId: string;
  promptConfigName: string;
  // Subgraph-specific params (stored as generic map)
  params: Record<string, unknown>;
  nodeType?: "action" | "condition" | "rest_connector" | "queue_publish" | "trigger" | "parallel" | "merge" | "transform";
}

const DEFAULT_CONFIG: ActionConfig = {
  subgraphId: "",
  label: "",
  description: "",
  inputSource: "previous_step",
  outputTarget: "patient_graph",
  enableVerification: false,
  maxRetries: 2,
  timeout: 120,
  modelPresetId: "",
  modelPresetName: "",
  temperature: 0.0,
  promptConfigId: "",
  promptConfigName: "",
  params: {},
  nodeType: "action",
};

interface ActionNodeData {
  label: string;
  subgraphId: string;
  color: string;
  config?: Partial<ActionConfig>;
  onConfigure: () => void;
}

function ActionNode({ data }: { data: ActionNodeData }) {
  return (
    <Box
      sx={{
        px: 2, py: 1.5, borderRadius: 2,
        border: "2px solid", borderColor: data.color,
        bgcolor: "background.paper", minWidth: 180, cursor: "pointer",
      }}
      onClick={data.onConfigure}
    >
      <Handle type="target" position={Position.Top} />
      <Typography variant="body2" fontWeight={600}>{data.label}</Typography>
      <Chip label={data.subgraphId} size="small" sx={{ mt: 0.5, bgcolor: data.color, color: "#fff" }} />
      <Handle type="source" position={Position.Bottom} />
    </Box>
  );
}

const nodeTypes = { action: ActionNode };
const edgeTypes = { portEdge: PortEdge };

interface PlanData {
  id: string;
  name: string;
  status: string;
  description: string;
  actions: Array<{
    id: string;
    subgraphId: string;
    label: string;
    nodeType?: string;
    position?: { x: number; y: number };
    config?: Partial<ActionConfig>;
  }>;
  edges: Array<{ source: string; target: string; sourceHandle?: string; targetHandle?: string }>;
}

// ── Model preset picker ───────────────────────────────────────────────────────
interface ModelPreset {
  preset_id: string;
  name: string;
  description: string;
  color: string;
  extractor: string;       // "llm" | "ner" | "ner+llm"
  primary_model: string;   // "aws:small" | "azure:big" | "ner" etc.
  consensus_mode: boolean;
  is_default: boolean;
  is_system: boolean;
  prompt_config_id: string;
}

function ModelPresetPicker({
  value, onChange,
}: { value: string; onChange: (presetId: string, preset: ModelPreset | null) => void }) {
  const [presets, setPresets] = useState<ModelPreset[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/presets", { credentials: "include", headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then((r) => r.ok ? r.json() : Promise.reject(r.statusText))
      .then((data) => setPresets(Array.isArray(data) ? data : data.presets ?? []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <Alert severity="info" sx={{ fontSize: "0.78rem" }}>Loading model presets…</Alert>;

  if (presets.length === 0) {
    return (
      <Alert severity="warning" sx={{ fontSize: "0.78rem" }}>
        No model presets found. Create presets in{" "}
        <Typography component="a" href="/admin/models" variant="caption" color="primary" sx={{ textDecoration: "underline" }}>
          AI Models
        </Typography>{" "}first.
      </Alert>
    );
  }

  return (
    <Stack spacing={1}>
      {presets.map((p) => {
        const selected = value === p.preset_id;
        return (
          <Paper
            key={p.preset_id}
            variant="outlined"
            onClick={() => onChange(p.preset_id, p)}
            sx={{
              p: 1.5, cursor: "pointer", borderRadius: 2,
              borderColor: selected ? "primary.main" : "divider",
              borderWidth: selected ? 2 : 1,
              bgcolor: selected ? "primary.50" : "transparent",
            }}
          >
            <Stack direction="row" alignItems="flex-start" spacing={1.5}>
              <Box sx={{ width: 10, height: 10, borderRadius: "50%", bgcolor: p.color || "#999", mt: "5px", flexShrink: 0 }} />
              <Box sx={{ flex: 1 }}>
                <Stack direction="row" spacing={0.75} alignItems="center" flexWrap="wrap" useFlexGap>
                  <Typography variant="body2" fontWeight={700}>{p.name}</Typography>
                  {p.is_default && <Chip size="small" label="Default" color="primary" sx={{ height: 16, fontSize: "0.6rem" }} />}
                  {p.is_system && <Chip size="small" label="System" variant="outlined" sx={{ height: 16, fontSize: "0.6rem" }} />}
                  <Chip size="small" label={p.extractor} variant="outlined"
                    sx={{ height: 16, fontSize: "0.6rem", fontFamily: "monospace" }} />
                  <Chip size="small" label={p.primary_model}
                    sx={{ height: 16, fontSize: "0.6rem", fontFamily: "monospace", bgcolor: "grey.100" }} />
                  {p.consensus_mode && <Chip size="small" label="consensus" color="secondary" sx={{ height: 16, fontSize: "0.6rem" }} />}
                </Stack>
                {p.description && (
                  <Typography variant="caption" color="text.secondary" sx={{ mt: 0.25, display: "block" }}>
                    {p.description}
                  </Typography>
                )}
              </Box>
            </Stack>
          </Paper>
        );
      })}
    </Stack>
  );
}

// ── Prompt picker ─────────────────────────────────────────────────────────────
interface PromptOption { id: string; name: string; version: number; description: string; }

function PromptPicker({
  value, onChange,
}: { value: string; onChange: (id: string, name: string) => void }) {
  const [options, setOptions] = useState<PromptOption[]>([]);
  useEffect(() => {
    fetch("/api/prompts", { credentials: "include", headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then((r) => r.ok ? r.json() : Promise.reject(r.statusText))
      .then((data) => setOptions(Array.isArray(data) ? data : data.prompts ?? data.items ?? []))
      .catch(() => {});
  }, []);

  return (
    <FormControl fullWidth size="small">
      <InputLabel>AI instructions (prompt)</InputLabel>
      <Select
        value={value}
        label="AI instructions (prompt)"
        onChange={(e) => {
          const opt = options.find((o) => o.id === e.target.value);
          onChange(e.target.value, opt ? `${opt.name} v${opt.version}` : "");
        }}
      >
        <MenuItem value=""><em>None — step runs without a prompt</em></MenuItem>
        {options.map((o) => (
          <MenuItem key={o.id} value={o.id}>
            <Stack>
              <Typography variant="body2">{o.name} <Typography component="span" variant="caption" color="text.secondary">v{o.version}</Typography></Typography>
              {o.description && <Typography variant="caption" color="text.secondary" noWrap sx={{ maxWidth: 340 }}>{o.description}</Typography>}
            </Stack>
          </MenuItem>
        ))}
      </Select>
    </FormControl>
  );
}

// ── Data-flow summary ─────────────────────────────────────────────────────────

/** Build the set of pipeline state paths produced by a predecessor's field mappings.
 *  e.g. { "entities": Set(["text","lookup_term","semantic_tag"]) }
 */
function buildProducedFields(mappings: FieldMappingRow[]): Record<string, Set<string>> {
  const result: Record<string, Set<string>> = {};
  for (const row of mappings) {
    // statePath is like "entities[].text" or "entities[].lookup_term"
    const match = row.statePath.match(/^(\w+)\[\]\.(.+)$/);
    if (!match) continue;
    const [, key, field] = match;
    if (!result[key]) result[key] = new Set();
    result[key].add(field);
  }
  return result;
}

function DataFlowPanel({
  subgraphId,
  prevStepWrites,
  prevStepFieldMappings,
}: {
  subgraphId: string;
  prevStepWrites: string[] | null;
  prevStepFieldMappings: FieldMappingRow[] | null;
}) {
  const io = SUBGRAPH_IO[subgraphId];
  if (!io) return null;

  const provided      = prevStepWrites ? new Set(prevStepWrites) : null;
  const missingKeys   = provided ? io.reads.filter((k) => !provided.has(k)) : [];
  const satisfiedKeys = provided ? io.reads.filter((k) =>  provided.has(k)) : [];
  const extraKeys     = provided ? prevStepWrites!.filter((k) => !io.reads.includes(k)) : [];

  // Field-level analysis — only meaningful when we have field mappings AND required fields
  const producedFields = prevStepFieldMappings ? buildProducedFields(prevStepFieldMappings) : null;
  const requiredFields = io.requiredFields;

  // For each state key that has both requiredFields and producedFields, classify sub-fields
  const fieldReport = useMemo<Record<string, { ok: string[]; missing: string[] }>>(() => {
    if (!producedFields || !requiredFields) return {};
    const report: Record<string, { ok: string[]; missing: string[] }> = {};
    for (const [stateKey, reqFields] of Object.entries(requiredFields)) {
      const produced = producedFields[stateKey];
      const ok      = reqFields.filter((f) => produced?.has(f));
      const missing = reqFields.filter((f) => !produced?.has(f));
      report[stateKey] = { ok, missing };
    }
    return report;
  }, [producedFields, requiredFields]);

  const fieldMismatches = Object.values(fieldReport).some((r) => r.missing.length > 0);
  const allFieldsOk     = producedFields && requiredFields && !fieldMismatches;

  return (
    <Stack spacing={1.5}>

      {/* What this step reads */}
      <Paper variant="outlined" sx={{ p: 1.5, bgcolor: "grey.50" }}>
        <Stack spacing={1.5}>
          <Box>
            <Typography variant="caption" fontWeight={700} color="text.secondary" display="block" sx={{ mb: 0.5 }}>
              NEEDS FROM PREVIOUS STEP
            </Typography>
            <Stack spacing={0.5}>
              {io.reads.map((k) => {
                const ok      = provided && provided.has(k);
                const unknown = provided === null;
                // Expand with field-level detail if the predecessor has mappings for this key
                const fieldsForKey = producedFields?.[k] ? Array.from(producedFields[k]) : null;
                const requiredForKey = requiredFields?.[k] ?? null;
                return (
                  <Box key={k}>
                    <Stack direction="row" alignItems="center" spacing={0.5} sx={{ mb: fieldsForKey ? 0.4 : 0 }}>
                      <Chip
                        size="small"
                        label={k}
                        variant={unknown ? "outlined" : ok ? "filled" : "outlined"}
                        color={unknown ? "default" : ok ? "success" : "error"}
                        sx={{ fontFamily: "monospace", fontSize: "0.68rem" }}
                      />
                      {!unknown && !ok && (
                        <Typography variant="caption" color="error.main" sx={{ fontSize: "0.65rem" }}>
                          — not provided by previous step
                        </Typography>
                      )}
                    </Stack>
                    {/* Field-level drill-down */}
                    {fieldsForKey && (
                      <Stack direction="row" spacing={0.4} flexWrap="wrap" useFlexGap sx={{ pl: 1.5, mt: 0.3 }}>
                        {fieldsForKey.map((f) => {
                          const needed = requiredForKey?.includes(f);
                          return (
                            <Chip key={f} size="small"
                              label={`.${f}${needed ? " *" : ""}`}
                              color={needed ? "success" : "default"}
                              variant={needed ? "filled" : "outlined"}
                              sx={{ fontFamily: "monospace", fontSize: "0.62rem", height: 16 }}
                            />
                          );
                        })}
                        {/* Show required fields that are missing from the mapping */}
                        {requiredForKey?.filter((f) => !producedFields?.[k]?.has(f)).map((f) => (
                          <Chip key={`missing-${f}`} size="small"
                            label={`.${f} ✗`}
                            color="error"
                            variant="outlined"
                            sx={{ fontFamily: "monospace", fontSize: "0.62rem", height: 16 }}
                          />
                        ))}
                      </Stack>
                    )}
                  </Box>
                );
              })}
            </Stack>
          </Box>

          <Box>
            <Typography variant="caption" fontWeight={700} color="text.secondary" display="block" sx={{ mb: 0.5 }}>
              ADDS TO PIPELINE STATE
            </Typography>
            <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
              {io.writes.map((k) => <Chip key={k} size="small" label={k} color="primary" variant="outlined" sx={{ fontFamily: "monospace", fontSize: "0.68rem" }} />)}
            </Stack>
          </Box>
        </Stack>
      </Paper>

      {/* Overall compatibility banner */}
      {provided && (
        missingKeys.length > 0 ? (
          <Alert severity="warning" sx={{ fontSize: "0.78rem" }} icon={false}>
            <strong>Missing data from the previous step.</strong> {missingKeys.join(", ")} {missingKeys.length === 1 ? "is" : "are"} needed but not produced.
            {extraKeys.length > 0 && (
              <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
                The previous step also produces {extraKeys.join(", ")} which this step does not use.
              </Typography>
            )}
          </Alert>
        ) : fieldMismatches ? (
          <Alert severity="warning" sx={{ fontSize: "0.78rem" }} icon={false}>
            <strong>Some required fields are missing.</strong> Go back to the previous step and check its field mappings include all the fields marked ✗ above.
          </Alert>
        ) : allFieldsOk ? (
          <Alert severity="success" sx={{ fontSize: "0.78rem" }} icon={false}>
            All required data and fields are provided by the previous step.
          </Alert>
        ) : (
          <Alert severity="success" sx={{ fontSize: "0.78rem" }} icon={false}>
            All {satisfiedKeys.length} required data block{satisfiedKeys.length > 1 ? "s are" : " is"} provided by the previous step.
            {extraKeys.length > 0 && (
              <Typography variant="caption" color="text.secondary" display="block">
                Also available (not used by this step): {extraKeys.join(", ")}.
              </Typography>
            )}
          </Alert>
        )
      )}

      {provided === null && (
        <Alert severity="info" sx={{ fontSize: "0.78rem" }} icon={false}>
          Set "Where does data come from?" to "Output of the previous step" to see compatibility checks.
        </Alert>
      )}
    </Stack>
  );
}

// ── Per-subgraph settings panel (step 2) ─────────────────────────────────────
function SubgraphSettingsPanel({
  category, config, updateField, updateParam,
}: {
  category: SubgraphCategory;
  config: ActionConfig;
  updateField: <K extends keyof ActionConfig>(k: K, v: ActionConfig[K]) => void;
  updateParam: (k: string, v: unknown) => void;
}) {
  if (category === "persist") {
    return (
      <Stack spacing={2}>
        <Typography variant="subtitle2">Where should results be saved?</Typography>
        {[
          { value: "patient_graph", label: "Patient Graph", desc: "Write coded entities to the live patient record — visible in the clinical audit view." },
          { value: "gold_training", label: "Gold Training Dataset", desc: "Write verified, de-identified labels to the NER training pipeline." },
          { value: "next_step",    label: "Pass to next step only", desc: "Don't persist anything — hand the data to the next action in the pipeline." },
        ].map((opt) => (
          <Paper
            key={opt.value}
            variant="outlined"
            onClick={() => updateField("outputTarget", opt.value)}
            sx={{
              p: 1.5, cursor: "pointer", borderRadius: 2,
              borderColor: config.outputTarget === opt.value ? "primary.main" : "divider",
              bgcolor: config.outputTarget === opt.value ? "primary.50" : "transparent",
            }}
          >
            <Typography variant="body2" fontWeight={600}>{opt.label}</Typography>
            <Typography variant="caption" color="text.secondary">{opt.desc}</Typography>
          </Paper>
        ))}
      </Stack>
    );
  }

  if (category === "post_process") {
    const layers: Array<{ key: string; label: string; desc: string }> = [
      { key: "observable_normalise", label: "Observable normalisation", desc: "Strip value, unit, and interpretation suffix from lab test span text." },
      { key: "scope_guard",          label: "Scope guard", desc: "Remove entities that fall outside the configured clinical domain." },
      { key: "context_detection",    label: "Context detection (ConText)", desc: "Infer assertion from surrounding sentence context (negation, family, hypothetical)." },
      { key: "entity_type_normalise",label: "Entity type normalisation", desc: "Standardise semantic tag labels to canonical SNOMED values." },
      { key: "value_unit_linking",   label: "Value/unit linking", desc: "Link qualifier_value entities back to their parent observable entity." },
    ];
    return (
      <Stack spacing={1.5}>
        <Typography variant="subtitle2">Which processing layers should run?</Typography>
        {layers.map((l) => (
          <FormControlLabel
            key={l.key}
            sx={{ alignItems: "flex-start", m: 0 }}
            control={
              <Switch
                size="small"
                checked={(config.params[l.key] as boolean) !== false}
                onChange={(e) => updateParam(l.key, e.target.checked)}
                sx={{ mt: 0.25 }}
              />
            }
            label={
              <Box sx={{ ml: 0.5 }}>
                <Typography variant="body2">{l.label}</Typography>
                <Typography variant="caption" color="text.secondary">{l.desc}</Typography>
              </Box>
            }
          />
        ))}
      </Stack>
    );
  }

  if (category === "terminology") {
    const threshold = (config.params.confidence_threshold as number) ?? 0.7;
    const maxCandidates = (config.params.max_candidates as number) ?? 5;
    return (
      <Stack spacing={2.5}>
        <Typography variant="subtitle2">SNOMED CT matching settings</Typography>
        <Box>
          <Typography variant="body2" gutterBottom>
            Minimum match confidence: <strong>{threshold.toFixed(2)}</strong>
          </Typography>
          <Box component="input" type="range" min={0.5} max={1.0} step={0.05}
            value={threshold}
            onChange={(e) => updateParam("confidence_threshold", Number(e.currentTarget.value))}
            style={{ width: "100%" }} />
          <Stack direction="row" justifyContent="space-between">
            <Typography variant="caption" color="text.secondary">0.50 (lenient)</Typography>
            <Typography variant="caption" color="text.secondary">1.00 (exact only)</Typography>
          </Stack>
        </Box>
        <TextField label="Max candidates to score" type="number" size="small" fullWidth
          value={maxCandidates}
          onChange={(e) => updateParam("max_candidates", Math.max(1, Math.min(20, Number(e.target.value))))}
          inputProps={{ min: 1, max: 20 }}
          helperText="How many SNOMED concept candidates are considered per surface form (1–20)." />
      </Stack>
    );
  }

  if (category === "tier_classify") {
    const gold   = (config.params.gold_threshold   as number) ?? 0.95;
    const silver = (config.params.silver_threshold as number) ?? 0.80;
    const bronze = (config.params.bronze_threshold as number) ?? 0.60;
    return (
      <Stack spacing={2.5}>
        <Typography variant="subtitle2">Confidence tier thresholds</Typography>
        <Alert severity="info" sx={{ fontSize: "0.78rem" }} icon={false}>
          Entities at or above the <strong>gold</strong> threshold are auto-accepted.
          Below <strong>bronze</strong> they are flagged for manual review.
        </Alert>
        {[
          { key: "gold_threshold",   label: "Gold",   color: "#FFD700", val: gold },
          { key: "silver_threshold", label: "Silver", color: "#C0C0C0", val: silver },
          { key: "bronze_threshold", label: "Bronze", color: "#CD7F32", val: bronze },
        ].map((t) => (
          <Box key={t.key}>
            <Typography variant="body2" gutterBottom>
              <span style={{ color: t.color, fontWeight: 700 }}>●</span> {t.label} threshold: <strong>{t.val.toFixed(2)}</strong>
            </Typography>
            <Box component="input" type="range" min={0.0} max={1.0} step={0.01}
              value={t.val}
              onChange={(e) => updateParam(t.key, Number(e.currentTarget.value))}
              style={{ width: "100%" }} />
          </Box>
        ))}
      </Stack>
    );
  }

  if (category === "generic") {
    return (
      <Alert severity="info" sx={{ fontSize: "0.8rem" }}>
        This step runs automatically with system defaults. No step-specific configuration is required here.
      </Alert>
    );
  }

  // LLM: model preset picker
  return (
    <Stack spacing={2}>
      <Box>
        <Typography variant="subtitle2" gutterBottom>Model preset</Typography>
        <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1.5 }}>
          Choose a preset from your model library. Presets set the AI engine, size, and consensus mode for this step.
          Manage presets in{" "}
          <Typography component="a" href="/admin/models" target="_blank" variant="caption" color="primary" sx={{ textDecoration: "underline" }}>
            AI Models
          </Typography>.
        </Typography>
        <ModelPresetPicker
          value={config.modelPresetId}
          onChange={(presetId, preset) => {
            updateField("modelPresetId", presetId);
            updateField("modelPresetName", preset?.name ?? "");
          }}
        />
      </Box>
    </Stack>
  );
}

// ── Schema alignment panel ────────────────────────────────────────────────────
// Fetches the prompt's output schema and lets the user map schema keys →
// pipeline state write keys, flagging any gaps.
// ── Schema field-level mapping panel ─────────────────────────────────────────
// Maps every field inside the LLM output array (e.g. terms[].text) to a
// pipeline state path (e.g. entities[].text). Users can edit the target path
// and add custom rows for downstream enrichment fields.

interface FieldMappingRow {
  id: string;         // stable React key
  llmField: string;   // e.g. "terms[].sentence_id"
  type: string;       // e.g. "string" or "string | null"
  description: string;
  required: boolean;
  statePath: string;  // editable — where this lands in pipeline state
  custom: boolean;    // user-added row (not derived from schema)
}

function buildDefaultRows(
  topKey: string,
  fields: Array<{ name: string; type: string; description: string; required: boolean }>,
): FieldMappingRow[] {
  // Default target container = first word of topKey pluralised if needed
  // e.g. "terms" → "entities" is conventional but unknowable; default to same name
  return fields.map((f) => ({
    id: `${topKey}.${f.name}`,
    llmField: `${topKey}[].${f.name}`,
    type: f.type,
    description: f.description,
    required: f.required,
    statePath: `${topKey}[].${f.name}`,
    custom: false,
  }));
}

function SchemaAlignmentPanel({
  promptConfigId,
  fieldMappings,
  onFieldMappingsChange,
  prevStepFieldMappings,
}: {
  promptConfigId: string;
  fieldMappings: FieldMappingRow[];
  onFieldMappingsChange: (rows: FieldMappingRow[]) => void;
  prevStepFieldMappings: FieldMappingRow[] | null;
}) {
  const [schemaFields, setSchemaFields] = useState<{
    topKey: string;
    fields: Array<{ name: string; type: string; description: string; required: boolean }>;
  } | null>(null);
  const [loading, setLoading] = useState(false);
  const initialised = fieldMappings.length > 0;

  useEffect(() => {
    if (!promptConfigId) return;
    setLoading(true);
    fetch(`/api/prompts/${promptConfigId}`, {
      credentials: "include",
      headers: { "X-Requested-With": "XMLHttpRequest" },
    })
      .then((r) => r.ok ? r.json() : Promise.reject(r.statusText))
      .then((data) => {
        const raw = data.outputSchema;
        if (!raw) { setSchemaFields(null); return; }
        const parsed = typeof raw === "string" ? JSON.parse(raw) : raw;
        const topProps: Record<string, unknown> = parsed?.properties ?? {};
        for (const [topKey, propDef] of Object.entries(topProps)) {
          const prop = propDef as Record<string, unknown>;
          if (prop?.type !== "array") continue;
          const itemProps = (prop.items as Record<string, unknown>)?.properties as Record<string, unknown> | undefined;
          const required = ((prop.items as Record<string, unknown>)?.required as string[]) ?? [];
          if (!itemProps) continue;
          const fields = Object.entries(itemProps).map(([name, def]) => {
            const d = def as Record<string, unknown>;
            const t = Array.isArray(d.type) ? (d.type as string[]).join(" | ") : String(d.type ?? "");
            return { name, type: t, description: String(d.description ?? ""), required: required.includes(name) };
          });
          setSchemaFields({ topKey, fields });
          if (!initialised) {
            onFieldMappingsChange(buildDefaultRows(topKey, fields));
          }
          return;
        }
        setSchemaFields(null);
      })
      .catch(() => setSchemaFields(null))
      .finally(() => setLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [promptConfigId]);

  const updateRow = (id: string, patch: Partial<FieldMappingRow>) =>
    onFieldMappingsChange(fieldMappings.map((r) => r.id === id ? { ...r, ...patch } : r));

  const removeRow = (id: string) =>
    onFieldMappingsChange(fieldMappings.filter((r) => r.id !== id));

  const addCustomRow = () => {
    onFieldMappingsChange([...fieldMappings, {
      id: `custom_${Date.now()}`,
      llmField: "",
      type: "string",
      description: "",
      required: false,
      statePath: "",
      custom: true,
    }]);
  };

  // Build grouped view of incoming fields from the previous step.
  // MUST be before any early returns to satisfy Rules of Hooks.
  const incomingGroups = useMemo<Record<string, string[]>>(() => {
    if (!prevStepFieldMappings) return {};
    const groups: Record<string, string[]> = {};
    for (const row of prevStepFieldMappings) {
      if (!row.statePath.trim()) continue;
      const match = row.statePath.match(/^(\w+)\[\]\.(.+)$/);
      if (match) {
        const [, key, field] = match;
        if (!groups[key]) groups[key] = [];
        groups[key].push(field);
      } else {
        if (!groups["__flat__"]) groups["__flat__"] = [];
        groups["__flat__"].push(row.statePath);
      }
    }
    return groups;
  }, [prevStepFieldMappings]);

  // Pass-through rows: fields the user wants to carry forward from the previous step unchanged.
  const passthroughPaths = new Set(
    fieldMappings
      .filter((r) => r.llmField === PIPELINE_GENERATED_SENTINEL)
      .map((r) => r.statePath)
  );

  const togglePassthrough = (statePath: string) => {
    if (passthroughPaths.has(statePath)) {
      onFieldMappingsChange(fieldMappings.filter((r) => !(r.llmField === PIPELINE_GENERATED_SENTINEL && r.statePath === statePath)));
    } else {
      onFieldMappingsChange([...fieldMappings, {
        id: `passthrough_${Date.now()}`,
        llmField: PIPELINE_GENERATED_SENTINEL,
        type: "passthrough",
        description: "Carried forward unchanged from the previous step",
        required: false,
        statePath,
        custom: false,
      }]);
    }
  };

  if (loading) return <Alert severity="info" sx={{ fontSize: "0.78rem" }} icon={false}>Loading prompt output fields…</Alert>;

  if (!schemaFields && fieldMappings.length === 0) {
    return (
      <Alert severity="warning" sx={{ fontSize: "0.78rem" }} icon={false}>
        This prompt does not have an output schema yet. Add one in the{" "}
        <Typography component="a" href="/admin/prompts" variant="caption" color="primary" sx={{ textDecoration: "underline" }}>
          Prompt Tuner
        </Typography>.
      </Alert>
    );
  }

  const aiRows          = fieldMappings.filter((r) => r.llmField !== PIPELINE_GENERATED_SENTINEL);
  const unmapped        = aiRows.filter((r) => !r.statePath.trim()).length;
  const missingRequired = aiRows.some((r) => r.required && !r.statePath.trim());
  const hasIncoming     = Object.keys(incomingGroups).length > 0;

  return (
    <Stack spacing={2}>

      {/* ── Part 1: What arrives from the previous step ── */}
      {hasIncoming && (
        <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 2, bgcolor: "grey.50" }}>
          <Typography variant="subtitle2" gutterBottom>What arrives from the previous step</Typography>
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1.5 }}>
            These fields are already in the pipeline. Tick any you want this step to keep and pass on.
            Leave them unticked if this step does not need them further down.
          </Typography>
          {Object.entries(incomingGroups).map(([stateKey, fields]) => (
            <Box key={stateKey} sx={{ mb: 1 }}>
              {stateKey !== "__flat__" && (
                <Typography variant="caption" fontWeight={600} sx={{ fontFamily: "monospace", display: "block", mb: 0.5, color: "text.secondary" }}>
                  {stateKey}[]
                </Typography>
              )}
              <Stack spacing={0.5}>
                {fields.map((field) => {
                  const path = stateKey === "__flat__" ? field : `${stateKey}[].${field}`;
                  const checked = passthroughPaths.has(path);
                  return (
                    <Stack key={path} direction="row" alignItems="center" spacing={1}>
                      <Box
                        component="input"
                        type="checkbox"
                        checked={checked}
                        onChange={() => togglePassthrough(path)}
                        style={{ cursor: "pointer", width: 15, height: 15, flexShrink: 0 }}
                      />
                      <Typography variant="caption" sx={{ fontFamily: "monospace", fontSize: "0.72rem", flex: 1 }}>
                        .{field}
                      </Typography>
                      {checked && (
                        <Chip size="small" label="kept" color="success" variant="outlined"
                          sx={{ height: 16, fontSize: "0.6rem" }} />
                      )}
                    </Stack>
                  );
                })}
              </Stack>
            </Box>
          ))}
        </Paper>
      )}

      {/* ── Part 2: What the AI adds ── */}
      <Box>
        <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 0.5 }}>
          <Typography variant="subtitle2">What the AI adds</Typography>
          {unmapped === 0
            ? <Chip size="small" label="All named ✓" color="success" sx={{ fontSize: "0.65rem", height: 18 }} />
            : <Chip size="small" label={`${unmapped} still need a name`} color="warning" sx={{ fontSize: "0.65rem", height: 18 }} />}
        </Stack>

        <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1.5 }}>
          The AI returns these fields. Give each one a name that the next step will use to find it.
          You can rename a field here — it will not change the prompt itself.
          {schemaFields && (
            <> The AI groups them inside <Box component="span" sx={{ fontFamily: "monospace", fontWeight: 600 }}>{schemaFields.topKey}[]</Box>.</>
          )}
        </Typography>

        {/* Column headers */}
        <Stack direction="row" spacing={1} sx={{ px: 0.5, mb: 0.5 }}>
          <Typography variant="caption" fontWeight={700} color="text.secondary" sx={{ flex: "0 0 160px", fontSize: "0.65rem" }}>AI FIELD NAME</Typography>
          <Typography variant="caption" fontWeight={700} color="text.secondary" sx={{ flex: "0 0 80px", fontSize: "0.65rem" }}>TYPE</Typography>
          <Typography variant="caption" fontWeight={700} color="text.secondary" sx={{ flex: 1, fontSize: "0.65rem" }}>CALL IT IN THE PIPELINE</Typography>
          <Box sx={{ width: 28 }} />
        </Stack>

        <Stack spacing={0.5}>
          {aiRows.map((row) => (
            <Stack key={row.id} direction="row" spacing={1} alignItems="center">
              {/* AI field name — locked for schema rows, editable for custom */}
              <Box sx={{ flex: "0 0 160px" }}>
                {row.custom ? (
                  <TextField
                    size="small"
                    value={row.llmField}
                    onChange={(e) => updateRow(row.id, { llmField: e.target.value })}
                    placeholder="e.g. terms[].fieldName"
                    inputProps={{ style: { fontFamily: "monospace", fontSize: "0.72rem", padding: "3px 6px" } }}
                    sx={{ width: "100%" }}
                  />
                ) : (
                  <Tooltip title={row.description || ""} placement="top-start">
                    <Box sx={{
                      fontFamily: "monospace",
                      fontSize: "0.72rem",
                      color: row.required ? "text.primary" : "text.secondary",
                      fontWeight: row.required ? 600 : 400,
                      whiteSpace: "nowrap",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      cursor: "help",
                    }}>
                      {row.llmField}{row.required ? " *" : ""}
                    </Box>
                  </Tooltip>
                )}
              </Box>

              {/* Type */}
              <Box sx={{ flex: "0 0 80px", fontFamily: "monospace", fontSize: "0.65rem", color: "info.main", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                {row.type || "—"}
              </Box>

              {/* Target pipeline state path */}
              <TextField
                size="small"
                value={row.statePath}
                onChange={(e) => updateRow(row.id, { statePath: e.target.value })}
                placeholder="e.g. entities[].text"
                error={row.required && !row.statePath.trim()}
                helperText={row.required && !row.statePath.trim() ? "Required — give this field a name" : undefined}
                inputProps={{ style: { fontFamily: "monospace", fontSize: "0.72rem", padding: "3px 6px" } }}
                sx={{ flex: 1 }}
              />

              <IconButton
                size="small"
                onClick={() => removeRow(row.id)}
                sx={{ width: 28, height: 28, color: "text.disabled", "&:hover": { color: "error.main" } }}
              >
                <Box component="span" sx={{ fontSize: "0.8rem", lineHeight: 1 }}>✕</Box>
              </IconButton>
            </Stack>
          ))}
        </Stack>

        {missingRequired && (
          <Alert severity="error" sx={{ mt: 1, fontSize: "0.75rem" }} icon={false}>
            Fields marked * are required — give them a name before saving.
          </Alert>
        )}

        <Button
          size="small"
          variant="outlined"
          onClick={addCustomRow}
          sx={{ mt: 1.5, alignSelf: "flex-start", fontSize: "0.75rem", textTransform: "none" }}
        >
          + Add an extra field
        </Button>

        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1, fontSize: "0.67rem" }}>
          * must be named &nbsp;·&nbsp; Hover a locked field name to see what it means
        </Typography>
      </Box>
    </Stack>
  );
}

// ── Action configurator ───────────────────────────────────────────────────────
function ActionConfigurator({
  nodeId, initialConfig, onSave, onDelete, onClose, onPathwaySave, prevStepWrites, prevStepFieldMappings,
}: {
  nodeId: string;
  initialConfig: ActionConfig;
  onSave: (nodeId: string, config: ActionConfig) => void;
  onDelete: (nodeId: string) => void;
  onClose: () => void;
  onPathwaySave: () => Promise<void>;
  prevStepWrites: string[] | null;
  prevStepFieldMappings: FieldMappingRow[] | null;
}) {
  const [step, setStep] = useState(0);
  const [config, setConfig] = useState<ActionConfig>({ ...DEFAULT_CONFIG, ...initialConfig, params: initialConfig.params ?? {} });

  const category: SubgraphCategory = SUBGRAPH_CATEGORY[config.subgraphId] ?? "generic";
  const isLLM = category === "llm";
  const wizardSteps = isLLM ? WIZARD_STEPS_LLM : WIZARD_STEPS_NO_LLM;
  const lastStep = wizardSteps.length - 1;
  const subgraph = SUBGRAPH_OPTIONS.find((s) => s.id === config.subgraphId);

  const updateField = <K extends keyof ActionConfig>(key: K, value: ActionConfig[K]) =>
    setConfig((prev) => ({ ...prev, [key]: value }));

  const updateParam = (key: string, value: unknown) =>
    setConfig((prev) => ({ ...prev, params: { ...prev.params, [key]: value } }));

  const handleSubgraphChange = (id: string) => {
    const opt = SUBGRAPH_OPTIONS.find((s) => s.id === id);
    setConfig((prev) => ({
      ...DEFAULT_CONFIG,
      subgraphId: id,
      label: prev.label || opt?.label || "",
      description: prev.description || opt?.description || "",
      params: {},
    }));
  };

  // step indices shift when non-LLM (no Prompt step)
  // LLM:    0=Subgraph  1=DataFlow  2=Settings  3=Prompt  4=Review
  // No-LLM: 0=Subgraph  1=DataFlow  2=Settings  3=Review

  const reviewStep = isLLM ? 4 : 3;
  const promptStep = 3; // only exists in LLM mode

  return (
    <Box sx={{ width: 460, p: 3, display: "flex", flexDirection: "column", height: "100%" }}>
      <Typography variant="h6" fontWeight={600} gutterBottom>Configure step</Typography>
      {subgraph && (
        <Chip size="small" label={subgraph.label}
          sx={{ mb: 1.5, alignSelf: "flex-start", bgcolor: subgraph.color, color: "#fff", fontSize: "0.7rem" }} />
      )}

      <Stepper activeStep={step} alternativeLabel sx={{ mb: 3 }}>
        {wizardSteps.map((label) => (
          <Step key={label}><StepLabel sx={{ "& .MuiStepLabel-label": { fontSize: "0.68rem" } }}>{label}</StepLabel></Step>
        ))}
      </Stepper>

      <Box sx={{ flex: 1, overflowY: "auto", mb: 2 }}>

        {/* ── Step 0: Subgraph ── */}
        {step === 0 && (
          <Stack spacing={2.5}>
            <Typography variant="subtitle2">Which step should this action run?</Typography>
            <FormControl fullWidth size="small">
              <InputLabel>Step type</InputLabel>
              <Select value={config.subgraphId} label="Step type"
                onChange={(e) => handleSubgraphChange(e.target.value)}>
                {SUBGRAPH_OPTIONS.map((s) => (
                  <MenuItem key={s.id} value={s.id}>
                    <Stack>
                      <Typography variant="body2">{s.label}</Typography>
                      <Typography variant="caption" color="text.secondary">{s.description}</Typography>
                    </Stack>
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <TextField label="Display name" size="small" fullWidth value={config.label}
              onChange={(e) => updateField("label", e.target.value)}
              helperText="A friendly name shown on the canvas." />
            <TextField label="What does this step do?" size="small" fullWidth multiline minRows={2}
              value={config.description}
              onChange={(e) => updateField("description", e.target.value)}
              helperText="Plain English — shown in the pathway summary." />
          </Stack>
        )}

        {/* ── Step 1: Data flow ── */}
        {step === 1 && (
          <Stack spacing={2.5}>
            <Typography variant="subtitle2">Data this step reads and writes</Typography>
            <DataFlowPanel
              subgraphId={config.subgraphId}
              prevStepWrites={config.inputSource === "previous_step" ? prevStepWrites : null}
              prevStepFieldMappings={config.inputSource === "previous_step" ? prevStepFieldMappings : null}
            />
            <Divider />

            <FormControl fullWidth size="small">
              <InputLabel>Where does data come from?</InputLabel>
              <Select value={config.inputSource} label="Where does data come from?"
                onChange={(e) => {
                  updateField("inputSource", e.target.value);
                  // clear Neo4j node config when switching away
                  if (!["patient_graph", "knowledge_graph"].includes(e.target.value)) {
                    updateParam("input_node_label", "");
                    updateParam("input_text_property", "text");
                    updateParam("input_filter_property", "");
                    updateParam("input_filter_value", "");
                  }
                }}>
                <MenuItem value="previous_step">Output of the previous step</MenuItem>
                <MenuItem value="encounter_text">Raw encounter text (pipeline start)</MenuItem>
                <MenuItem value="patient_graph">Patient Graph Neo4j — pick a node type</MenuItem>
                <MenuItem value="knowledge_graph">Knowledge Graph Neo4j — pick a node type</MenuItem>
              </Select>
            </FormControl>

            {/* Neo4j node + property picker — shown when reading from either graph */}
            {(config.inputSource === "patient_graph" || config.inputSource === "knowledge_graph") && (
              <Paper variant="outlined" sx={{ p: 2, borderRadius: 2 }}>
                <Typography variant="caption" fontWeight={700} color="text.secondary" sx={{ display: "block", mb: 1.5 }}>
                  {config.inputSource === "patient_graph" ? "PATIENT GRAPH" : "KNOWLEDGE GRAPH"} — NODE QUERY
                </Typography>
                <Stack spacing={1.5}>
                  <FormControl fullWidth size="small">
                    <InputLabel>Node label</InputLabel>
                    <Select
                      value={(config.params.input_node_label as string) || ""}
                      label="Node label"
                      onChange={(e) => updateParam("input_node_label", e.target.value)}
                    >
                      {config.inputSource === "patient_graph" ? (
                        // Patient Graph — contains PII-linked clinical records
                        [
                          { v: "EncounterCandidate", d: "Raw encounter text candidate for coding (linked to patient)" },
                          { v: "Encounter",          d: "A clinical encounter / consultation record" },
                          { v: "Patient",            d: "Patient root node" },
                          { v: "ReviewTask",         d: "A HITL coding review task awaiting clinician" },
                          { v: "EpisodeOfCare",      d: "A grouped episode of care across encounters" },
                          { v: "SafetyNetAlert",     d: "An overdue investigation or follow-up alert" },
                        ].map(({ v, d }) => (
                          <MenuItem key={v} value={v}>
                            <Stack>
                              <Typography variant="body2" sx={{ fontFamily: "monospace" }}>{v}</Typography>
                              <Typography variant="caption" color="text.secondary">{d}</Typography>
                            </Stack>
                          </MenuItem>
                        ))
                      ) : (
                        // Knowledge Graph — de-identified / anonymous clinical knowledge
                        [
                          { v: "TrainingCandidate",  d: "De-identified text awaiting gold labelling — GDPR-isolated, no patient IDs" },
                          { v: "GoldLabel",          d: "Verified NER training label linked to a TrainingCandidate" },
                          { v: "SurfaceFormTask",    d: "A surface form validation task for HITL review" },
                          { v: "SurfaceForm",        d: "A clinical surface form / alias for a SNOMED concept" },
                          { v: "Concept",            d: "A SNOMED CT concept node" },
                          { v: "CodingDecision",     d: "A recorded coding decision for a surface form" },
                          { v: "PromptConfig",       d: "An AI prompt configuration" },
                          { v: "PipelineConfig",     d: "A pipeline configuration node" },
                        ].map(({ v, d }) => (
                          <MenuItem key={v} value={v}>
                            <Stack>
                              <Typography variant="body2" sx={{ fontFamily: "monospace" }}>{v}</Typography>
                              <Typography variant="caption" color="text.secondary">{d}</Typography>
                            </Stack>
                          </MenuItem>
                        ))
                      )}
                    </Select>
                  </FormControl>

                  <FormControl fullWidth size="small">
                    <InputLabel>Property to use as encounter text</InputLabel>
                    <Select
                      value={(config.params.input_text_property as string) || "text"}
                      label="Property to use as encounter text"
                      onChange={(e) => updateParam("input_text_property", e.target.value)}
                    >
                      {[
                        { v: "text",              d: "The main text/body of the node" },
                        { v: "raw_text",          d: "Unprocessed original text" },
                        { v: "deidentified_text", d: "De-identified version of the text" },
                        { v: "content",           d: "Document content field" },
                      ].map(({ v, d }) => (
                        <MenuItem key={v} value={v}>
                          <Typography variant="body2" sx={{ fontFamily: "monospace" }}>{v}</Typography>
                          <Typography variant="caption" color="text.secondary" sx={{ ml: 1 }}>{d}</Typography>
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>

                  <Divider />
                  <Typography variant="caption" color="text.secondary" fontWeight={600}>
                    FILTER (optional — only process nodes matching this condition)
                  </Typography>
                  <Stack direction="row" spacing={1}>
                    <TextField size="small" label="Property" sx={{ flex: 1 }}
                      placeholder="e.g. status"
                      value={(config.params.input_filter_property as string) || ""}
                      onChange={(e) => updateParam("input_filter_property", e.target.value)}
                      inputProps={{ style: { fontFamily: "monospace" } }} />
                    <TextField size="small" label="= Value" sx={{ flex: 1 }}
                      placeholder='e.g. "pending"'
                      value={(config.params.input_filter_value as string) || ""}
                      onChange={(e) => updateParam("input_filter_value", e.target.value)}
                      inputProps={{ style: { fontFamily: "monospace" } }} />
                  </Stack>

                  {Boolean(config.params.input_node_label) && (
                    <Paper sx={{ p: 1, bgcolor: "grey.50", borderRadius: 1 }}>
                      <Typography variant="caption" sx={{ fontFamily: "monospace", color: "text.secondary" }}>
                        MATCH (n:{config.params.input_node_label as string}
                        {config.params.input_filter_property
                          ? ` {${config.params.input_filter_property as string}: "${config.params.input_filter_value as string || "..."}"}`
                          : ""})
                        {"\n"}RETURN n.{(config.params.input_text_property as string) || "text"} AS encounter_text
                      </Typography>
                    </Paper>
                  )}
                </Stack>
              </Paper>
            )}

            <FormControl fullWidth size="small">
              <InputLabel>Runtime retries on failure</InputLabel>
              <Select value={String(config.maxRetries)} label="Runtime retries on failure"
                onChange={(e) => updateField("maxRetries", Number(e.target.value))}>
                {[0, 1, 2, 3, 5].map((n) => (
                  <MenuItem key={n} value={String(n)}>{n === 0 ? "None — fail immediately" : `${n} retr${n === 1 ? "y" : "ies"}`}</MenuItem>
                ))}
              </Select>
            </FormControl>
          </Stack>
        )}

        {/* ── Step 2: Per-subgraph settings ── */}
        {step === 2 && (
          <SubgraphSettingsPanel
            category={category}
            config={config}
            updateField={updateField}
            updateParam={updateParam}
          />
        )}

        {/* ── Step 3 (LLM only): Prompt & model ── */}
        {isLLM && step === promptStep && (
          <Stack spacing={2.5}>
            <Typography variant="subtitle2">Which AI instructions should this step use?</Typography>
            <PromptPicker
              value={config.promptConfigId}
              onChange={(id, name) => { updateField("promptConfigId", id); updateField("promptConfigName", name); }}
            />
            {config.promptConfigId && (
              <>
                <Typography variant="caption" color="text.secondary">
                  <Typography component="a" href="/admin/prompts" variant="caption" color="primary"
                    sx={{ textDecoration: "underline" }}>
                    Open in Prompt Tuner
                  </Typography>{" "}to edit the instructions, output schema, or teaching examples.
                </Typography>
                <SchemaAlignmentPanel
                  promptConfigId={config.promptConfigId}
                  fieldMappings={(config.params.field_mappings as FieldMappingRow[]) ?? []}
                  onFieldMappingsChange={(rows) => updateParam("field_mappings", rows)}
                  prevStepFieldMappings={prevStepFieldMappings}
                />
              </>
            )}
            <Divider />
            <Typography variant="subtitle2">Temperature</Typography>
            <Alert severity="info" sx={{ fontSize: "0.78rem" }} icon={false}>
              For clinical extraction, keep this at <strong>0.0</strong> — the AI should give the same answer every time, not be creative.
            </Alert>
            <Box>
              <Typography variant="body2" gutterBottom>
                Temperature: <strong>{config.temperature.toFixed(1)}</strong>
                {config.temperature === 0 && " (deterministic — recommended)"}
                {config.temperature > 0.5 && " (creative — not recommended for clinical tasks)"}
              </Typography>
              <Box component="input" type="range" min={0} max={1} step={0.1}
                value={config.temperature}
                onChange={(e) => updateField("temperature", Number(e.currentTarget.value))}
                style={{ width: "100%" }} />
              <Stack direction="row" justifyContent="space-between">
                <Typography variant="caption" color="text.secondary">0.0 — always same answer</Typography>
                <Typography variant="caption" color="text.secondary">1.0 — creative / varied</Typography>
              </Stack>
            </Box>
          </Stack>
        )}

        {/* ── Review step ── */}
        {step === reviewStep && (
          <Stack spacing={2}>
            <Typography variant="subtitle2">Review your configuration</Typography>
            <Paper variant="outlined" sx={{ p: 2 }}>
              <Stack spacing={1}>
                <ReviewRow label="Step type" value={subgraph?.label || config.subgraphId} />
                <ReviewRow label="Display name" value={config.label} />
                <Divider />
                <ReviewRow label="Input source" value={config.inputSource.replace(/_/g, " ")} />
                {(config.inputSource === "patient_graph" || config.inputSource === "knowledge_graph") && Boolean(config.params.input_node_label) && (
                  <>
                    <ReviewRow label="Node label" value={config.params.input_node_label as string} />
                    <ReviewRow label="Text property" value={(config.params.input_text_property as string) || "text"} />
                    {config.params.input_filter_property && (
                      <ReviewRow label="Filter" value={`${config.params.input_filter_property} = "${config.params.input_filter_value}"`} />
                    )}
                  </>
                )}
                <ReviewRow label="Max retries" value={config.maxRetries === 0 ? "None" : `${config.maxRetries}`} />
                {category === "persist" && <ReviewRow label="Save to" value={config.outputTarget.replace(/_/g, " ")} />}
                {category === "terminology" && (
                  <>
                    <ReviewRow label="Min confidence" value={String((config.params.confidence_threshold as number) ?? 0.7)} />
                    <ReviewRow label="Max candidates" value={String((config.params.max_candidates as number) ?? 5)} />
                  </>
                )}
                {isLLM && (
                  <>
                    <Divider />
                    <ReviewRow label="Model preset" value={config.modelPresetName || config.modelPresetId || "Not set"} />
                    <ReviewRow label="Temperature" value={config.temperature.toFixed(1)} />
                    <ReviewRow label="Prompt" value={config.promptConfigName || config.promptConfigId || "None"} />
                    {Array.isArray(config.params.field_mappings) && (config.params.field_mappings as FieldMappingRow[]).length > 0 && (
                      <ReviewRow
                        label="Field mappings"
                        value={`${(config.params.field_mappings as FieldMappingRow[]).filter((r) => r.statePath).length} of ${(config.params.field_mappings as FieldMappingRow[]).length} mapped`}
                      />
                    )}
                  </>
                )}
              </Stack>
            </Paper>
            {isLLM && !config.promptConfigId && (
              <Alert severity="warning" sx={{ fontSize: "0.78rem" }}>
                No prompt selected. This LLM step will use the system default instructions.
              </Alert>
            )}
            {(() => {
              if (config.inputSource !== "previous_step" || !prevStepWrites) return null;
              const io = SUBGRAPH_IO[config.subgraphId];
              if (!io) return null;
              const provided = new Set(prevStepWrites);
              const missing = io.reads.filter((k) => !provided.has(k));
              if (missing.length === 0) return null;
              return (
                <Alert severity="error" sx={{ fontSize: "0.78rem" }}>
                  <Typography variant="caption" fontWeight={700} display="block">
                    Pipeline key mismatch — step will likely fail
                  </Typography>
                  <Typography variant="caption">
                    This step needs{" "}
                    {missing.map((k) => (
                      <Box key={k} component="span" sx={{ fontFamily: "monospace", bgcolor: "error.50", px: 0.5, borderRadius: 0.5, mr: 0.5 }}>{k}</Box>
                    ))}
                    but the previous step does not produce {missing.length > 1 ? "them" : "it"}.
                    Go back to Data flow to change the input source.
                  </Typography>
                </Alert>
              );
            })()}
          </Stack>
        )}
      </Box>

      <Divider sx={{ mb: 2 }} />
      <Stack direction="row" justifyContent="space-between">
        <Tooltip title="Remove this step from the pathway">
          <IconButton color="error" onClick={() => { onDelete(nodeId); onClose(); }}>
            <DeleteOutlineIcon />
          </IconButton>
        </Tooltip>
        <Stack direction="row" spacing={1}>
          {step > 0 && <Button size="small" onClick={() => setStep((s) => s - 1)}>Back</Button>}
          {step < lastStep ? (
            <Button size="small" variant="contained"
              disabled={step === 0 && (!config.subgraphId || !config.label)}
              onClick={() => { onSave(nodeId, config); setStep((s) => s + 1); }}>
              Next
            </Button>
          ) : (
            <SaveStepButton
              onSave={() => onSave(nodeId, config)}
              onPathwaySave={onPathwaySave}
              onClose={onClose}
            />
          )}
        </Stack>
      </Stack>
    </Box>
  );
}

function SaveStepButton({
  onSave, onPathwaySave, onClose,
}: {
  onSave: () => void;
  onPathwaySave: () => Promise<void>;
  onClose: () => void;
}) {
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleClick = async () => {
    setSaving(true);
    setError(null);
    try {
      onSave();               // update local nodeConfigs state
      await onPathwaySave();  // persist to server
      setSaved(true);
      setTimeout(() => { setSaved(false); onClose(); }, 800);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
      setSaving(false);
    }
  };

  if (error) {
    return (
      <Tooltip title={error}>
        <Button size="small" variant="contained" color="error" onClick={handleClick}>
          Retry save
        </Button>
      </Tooltip>
    );
  }

  return (
    <Button
      size="small"
      variant="contained"
      color={saved ? "success" : "primary"}
      disabled={saving}
      onClick={handleClick}
      startIcon={saving ? <CircularProgress size={14} color="inherit" /> : undefined}
    >
      {saving ? "Saving…" : saved ? "Saved ✓" : "Save step"}
    </Button>
  );
}

function ReviewRow({ label, value }: { label: string; value: string }) {
  return (
    <Box sx={{ display: "flex", justifyContent: "space-between", gap: 2 }}>
      <Typography variant="caption" color="text.secondary">{label}</Typography>
      <Typography variant="caption" fontWeight={500} sx={{ textAlign: "right" }}>{value}</Typography>
    </Box>
  );
}

function TriggerContextPanel({
  triggerEvent,
  onTriggerChange,
  planId,
  planDescription,
  onDescriptionChange,
}: {
  triggerEvent: string;
  onTriggerChange: (v: string) => void;
  planId: string;
  planDescription: string;
  onDescriptionChange: (v: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const selected = TRIGGER_OPTIONS.find((t) => t.id === triggerEvent);

  return (
    <Paper variant="outlined" sx={{ mx: 2, mt: 1 }}>
      <Box
        sx={{ px: 2, py: 1, display: "flex", alignItems: "center", gap: 1, cursor: "pointer" }}
        onClick={() => setExpanded((e) => !e)}
      >
        <InfoOutlinedIcon fontSize="small" color="primary" />
        <Typography variant="subtitle2" sx={{ flex: 1 }}>
          Pipeline Context &amp; Trigger
        </Typography>
        <Chip
          size="small"
          icon={<PlayArrowIcon />}
          label={selected?.label || triggerEvent || "No trigger set"}
          color={triggerEvent ? "primary" : "default"}
          variant="outlined"
        />
        {expanded ? <ExpandLessIcon fontSize="small" /> : <ExpandMoreIcon fontSize="small" />}
      </Box>

      {expanded && (
        <Box sx={{ px: 2, pb: 2 }}>
          <Divider sx={{ mb: 2 }} />
          <Stack spacing={2}>
            <Typography variant="body2" color="text.secondary">
              Configure what event triggers this pipeline and what context it requires at runtime.
            </Typography>

            <FormControl fullWidth size="small">
              <InputLabel>Trigger Event</InputLabel>
              <Select
                value={triggerEvent}
                label="Trigger Event"
                onChange={(e) => onTriggerChange(e.target.value)}
              >
                {TRIGGER_OPTIONS.map((t) => (
                  <MenuItem key={t.id} value={t.id}>
                    <Stack>
                      <Typography variant="body2">{t.label}</Typography>
                      <Typography variant="caption" color="text.secondary">{t.description}</Typography>
                    </Stack>
                  </MenuItem>
                ))}
              </Select>
            </FormControl>

            {selected && (
              <Alert severity="info" icon={false} sx={{ fontSize: "0.8rem" }}>
                <strong>How it works:</strong> {selected.description}
              </Alert>
            )}

            <TextField
              label="Pipeline description"
              size="small"
              fullWidth
              multiline
              minRows={2}
              value={planDescription}
              onChange={(e) => onDescriptionChange(e.target.value)}
              helperText="Describe what this pipeline does in plain English. Shown to users on the pathways list."
            />

            <Paper variant="outlined" sx={{ p: 1.5, bgcolor: "grey.50" }}>
              <Typography variant="caption" fontWeight={600} gutterBottom>
                Runtime context required
              </Typography>
              <Stack spacing={0.5} sx={{ mt: 1 }}>
                <Typography variant="caption" color="text.secondary">
                  When this pipeline is triggered, the runtime automatically provides:
                </Typography>
                <Box component="ul" sx={{ m: 0, pl: 2.5, "& li": { fontSize: "0.75rem", color: "text.secondary" } }}>
                  <li><strong>patient_id</strong> — The patient whose data triggered the event</li>
                  <li><strong>encounter_id</strong> — The encounter or document being processed</li>
                  <li><strong>encounter_text</strong> — The raw clinical text from the encounter</li>
                  <li><strong>organization_id</strong> — The tenant / practice organisation</li>
                  {triggerEvent === "training-run-requested" && (
                    <li><strong>training_batch_id</strong> — The batch ID for grouping gold labels</li>
                  )}
                  {triggerEvent === "referral-received" && (
                    <li><strong>referral_document</strong> — The full referral letter text</li>
                  )}
                  {triggerEvent === "results-received" && (
                    <li><strong>diagnostic_report</strong> — The investigation results (lab, imaging, etc.)</li>
                  )}
                </Box>
              </Stack>
            </Paper>

            <Paper variant="outlined" sx={{ p: 1.5, bgcolor: "grey.50" }}>
              <Typography variant="caption" fontWeight={600} gutterBottom>
                API invocation
              </Typography>
              <Box sx={{ mt: 1, fontFamily: "monospace", fontSize: "0.7rem", bgcolor: "grey.100", p: 1, borderRadius: 1, overflowX: "auto" }}>
                POST /fhir/PlanDefinition/{planId}/$apply<br />
                {`{ "event_type": "${triggerEvent || "..."}", "patient_id": "..." }`}
              </Box>
            </Paper>
          </Stack>
        </Box>
      )}
    </Paper>
  );
}

interface ValidationWarning {
  severity: "error" | "warning" | "info";
  message: string;
}

function useValidationWarnings(
  nodes: Node[],
  edges: Edge[],
  nodeConfigs: Record<string, ActionConfig>,
  triggerEvent: string,
): ValidationWarning[] {
  return useMemo(() => {
    const warnings: ValidationWarning[] = [];
    if (nodes.length === 0) {
      warnings.push({ severity: "warning", message: "Pipeline has no action steps. Add at least one action." });
      return warnings;
    }
    if (!triggerEvent) {
      warnings.push({ severity: "error", message: "No trigger event configured. The pipeline cannot be invoked without a trigger." });
    }

    const ordered = [...nodes].sort((a, b) => (a.position?.y ?? 0) - (b.position?.y ?? 0));

    // Global keys always available at pipeline start
    const GLOBAL_KEYS = new Set(["encounter_text", "patient_id", "encounter_id", "run_id"]);

    // Edge-aware key alignment: for each node, check that every key it reads
    // is either a global key or produced by one of its direct predecessors.
    for (const node of nodes) {
      const cfg = nodeConfigs[node.id];
      const inputSource = cfg?.inputSource ?? "previous_step";
      // Only check alignment when reading from previous pipeline step
      if (inputSource !== "previous_step") continue;

      const subgraphId = (node.data as unknown as ActionNodeData)?.subgraphId || "";
      const io = SUBGRAPH_IO[subgraphId];
      if (!io) continue;

      const predecessorIds = edges.filter((e) => e.target === node.id).map((e) => e.source);
      const predecessorWrites = new Set<string>([...GLOBAL_KEYS]);
      for (const predId of predecessorIds) {
        const predNode = nodes.find((n) => n.id === predId);
        const predSubgraphId = (predNode?.data as unknown as ActionNodeData | undefined)?.subgraphId;
        if (predSubgraphId) SUBGRAPH_IO[predSubgraphId]?.writes.forEach((w) => predecessorWrites.add(w));
      }

      const missingKeys = io.reads.filter((k) => !predecessorWrites.has(k));
      for (const key of missingKeys) {
        warnings.push({
          severity: predecessorIds.length === 0 ? "warning" : "error",
          message: `"${(node.data as unknown as ActionNodeData).label}" needs key "${key}" but ${predecessorIds.length === 0 ? "has no connected predecessor" : "the previous step does not produce it"}.`,
        });
      }

      // Field-level validation: if this step has requiredFields and any predecessor
      // has configured field_mappings, check that all required sub-fields are covered.
      if (io.requiredFields) {
        for (const predId of predecessorIds) {
          const predCfg = nodeConfigs[predId];
          const mappings = predCfg?.params?.field_mappings as FieldMappingRow[] | undefined;
          if (!mappings || mappings.length === 0) continue;

          const producedFields = buildProducedFields(mappings);
          for (const [stateKey, reqFields] of Object.entries(io.requiredFields)) {
            const produced = producedFields[stateKey];
            const missingFields = reqFields.filter((f) => !produced?.has(f));
            if (missingFields.length > 0) {
              const label = (node.data as unknown as ActionNodeData).label;
              warnings.push({
                severity: "error",
                message: `"${label}" needs ${stateKey}[].${missingFields.join(", " + stateKey + "[].") } but the previous step's field mappings do not include ${missingFields.length === 1 ? "it" : "them"}. Update the previous step's Schema Alignment.`,
              });
            }
          }
        }
      }
    }

    const hasVerify = nodes.some(n => (n.data as unknown as ActionNodeData)?.subgraphId === "verification");
    const hasPersist = nodes.some(n => (n.data as unknown as ActionNodeData)?.subgraphId === "persist");
    const persistGold = nodes.some(n => {
      const cfg = nodeConfigs[n.id];
      return (n.data as unknown as ActionNodeData)?.subgraphId === "persist" && cfg?.outputTarget === "gold_training";
    });
    if (hasPersist && persistGold && !hasVerify) {
      warnings.push({
        severity: "error",
        message: "Persisting to Gold Training without a Verification step. Unverified data could corrupt training labels.",
      });
    }
    if (hasVerify && hasPersist) {
      const verifyIdx = ordered.findIndex(n => (n.data as unknown as ActionNodeData)?.subgraphId === "verification");
      const persistIdx = ordered.findIndex(n => (n.data as unknown as ActionNodeData)?.subgraphId === "persist");
      if (verifyIdx > persistIdx) {
        warnings.push({
          severity: "error",
          message: "Verification runs AFTER persist. Move Verification before Persist so it can gate the output.",
        });
      }
    }

    const orphaned = nodes.filter(n => {
      const hasIncoming = edges.some(e => e.target === n.id);
      const hasOutgoing = edges.some(e => e.source === n.id);
      const isFirst = ordered[0]?.id === n.id;
      return !hasIncoming && !isFirst;
    });
    for (const o of orphaned) {
      warnings.push({
        severity: "warning",
        message: `"${(o.data as unknown as ActionNodeData).label}" has no incoming edge — it won't receive data from previous steps.`,
      });
    }

    if (warnings.length === 0) {
      warnings.push({ severity: "info", message: "Pipeline looks good. All steps are connected and I/O keys are consistent." });
    }
    return warnings;
  }, [nodes, edges, nodeConfigs, triggerEvent]);
}

function ValidationPanel({ warnings }: { warnings: ValidationWarning[] }) {
  const [expanded, setExpanded] = useState(false);
  const errorCount = warnings.filter(w => w.severity === "error").length;
  const warnCount = warnings.filter(w => w.severity === "warning").length;
  const allGood = errorCount === 0 && warnCount === 0;

  return (
    <Paper variant="outlined" sx={{ mx: 2, mt: 1 }}>
      <Box
        sx={{ px: 2, py: 1, display: "flex", alignItems: "center", gap: 1, cursor: "pointer" }}
        onClick={() => setExpanded(e => !e)}
      >
        {allGood ? (
          <CheckCircleOutlineIcon fontSize="small" color="success" />
        ) : (
          <WarningAmberIcon fontSize="small" color={errorCount > 0 ? "error" : "warning"} />
        )}
        <Typography variant="subtitle2" sx={{ flex: 1 }}>
          Pipeline Validation
        </Typography>
        {errorCount > 0 && <Chip size="small" label={`${errorCount} error${errorCount > 1 ? "s" : ""}`} color="error" variant="outlined" />}
        {warnCount > 0 && <Chip size="small" label={`${warnCount} warning${warnCount > 1 ? "s" : ""}`} color="warning" variant="outlined" sx={{ ml: 0.5 }} />}
        {allGood && <Chip size="small" label="Valid" color="success" variant="outlined" />}
        {expanded ? <ExpandLessIcon fontSize="small" /> : <ExpandMoreIcon fontSize="small" />}
      </Box>
      {expanded && (
        <Box sx={{ px: 2, pb: 2 }}>
          <Divider sx={{ mb: 1 }} />
          <Stack spacing={0.5}>
            {warnings.map((w, i) => (
              <Alert
                key={i}
                severity={w.severity}
                sx={{ py: 0, fontSize: "0.78rem", "& .MuiAlert-message": { py: 0.5 } }}
              >
                {w.message}
              </Alert>
            ))}
          </Stack>
        </Box>
      )}
    </Paper>
  );
}

export default function PathwayBuilderPage() {
  const params = useParams();
  const router = useRouter();
  const planId = params.id as string;
  const isNew = planId === "new";

  const [planName, setPlanName] = useState("");
  const [planDescription, setPlanDescription] = useState("");
  const [planStatus, setPlanStatus] = useState("draft");
  const [triggerEvent, setTriggerEvent] = useState("");
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerKey, setDrawerKey] = useState(0);
  const [nodeConfigs, setNodeConfigs] = useState<Record<string, ActionConfig>>({});
  const [saveError, setSaveError] = useState<string | null>(null);

  const validationWarnings = useValidationWarnings(nodes, edges, nodeConfigs, triggerEvent);

  const openConfigurator = useCallback((nodeId: string) => {
    setSelectedNode(nodeId);
    setDrawerKey((k) => k + 1); // force remount so step resets to 0 and initialConfig re-applies
    setDrawerOpen(true);
  }, []);

  useEffect(() => {
    if (!isNew) {
      api.get<PlanData>(`/fhir/PlanDefinition/${planId}`)
        .then((data) => {
          setPlanName(data.name || "");
          setPlanDescription(data.description || "");
          setPlanStatus(data.status || "draft");
          const trig = (data as any).trigger;
          if (trig?.event) setTriggerEvent(trig.event);
          const configs: Record<string, ActionConfig> = {};
          const loadedNodes: Node[] = (data.actions || []).map((a, i) => {
            const cfg: ActionConfig = { ...DEFAULT_CONFIG, subgraphId: a.subgraphId, label: a.label || a.subgraphId, ...a.config, params: (a.config as ActionConfig)?.params ?? {} };
            configs[a.id] = cfg;
            return {
              id: a.id,
              type: a.nodeType || cfg.nodeType || "action",
              position: a.position || { x: 250, y: 100 + i * 150 },
              data: {
                label: a.label || a.subgraphId,
                subgraphId: a.subgraphId,
                color: SUBGRAPH_OPTIONS.find((s) => s.id === a.subgraphId)?.color || "#999",
                nodeType: a.nodeType || cfg.nodeType || "action",
                config: a.config,
                onConfigure: () => openConfigurator(a.id),
              },
            };
          });
          setNodeConfigs(configs);
          setNodes(loadedNodes);
          setEdges((data.edges || []).map((e, i) => ({
            id: `e${i}`,
            source: e.source,
            target: e.target,
            sourceHandle: e.sourceHandle,
            targetHandle: e.targetHandle,
            type: "portEdge",
            data: { label: e.sourceHandle || e.targetHandle || "" },
          })));
        })
        .catch(() => {});
    }
  }, [planId, isNew, setNodes, setEdges, openConfigurator]);

  const onConnect = useCallback((connection: Connection) => {
    const edgeId = `${connection.source}:${connection.sourceHandle ?? "_"}->${connection.target}:${connection.targetHandle ?? "_"}`;
    setEdges((eds) => addEdge({ ...connection, id: edgeId, type: "portEdge", data: { label: connection.sourceHandle || connection.targetHandle || "" } }, eds));
  }, [setEdges]);

  const addAction = useCallback((subgraphId: string) => {
    if (subgraphId === "condition") {
      const id = `condition_${Date.now()}`;
      const cfg: ActionConfig = {
        ...DEFAULT_CONFIG,
        subgraphId: "condition",
        label: "Condition",
        description: "Route based on rule conditions",
        nodeType: "condition",
        params: {
          rules: [
            { id: `rule_${Date.now()}`, field: "is_verified", operator: "==", value: "true", outputPort: "verified" },
          ],
          defaultPort: "failed",
        },
      };
      setNodeConfigs((prev) => ({ ...prev, [id]: cfg }));
      setNodes((nds) => [...nds, {
        id,
        type: "condition",
        position: { x: 250, y: (nodes.length + 1) * 150 },
        data: { label: cfg.label, subgraphId: cfg.subgraphId, color: "#E91E63", onConfigure: () => openConfigurator(id), rules: cfg.params.rules, defaultPort: cfg.params.defaultPort },
      } as Node]);
      return;
    }
    if (subgraphId === "rest_connector" || subgraphId === "queue_publish") {
      const id = `${subgraphId}_${Date.now()}`;
      const cfg: ActionConfig = {
        ...DEFAULT_CONFIG,
        subgraphId,
        label: subgraphId === "rest_connector" ? "REST API Call" : "Queue Publish",
        description: subgraphId === "rest_connector" ? "Call an internal or external API" : "Publish message to queue",
        nodeType: subgraphId as ActionConfig["nodeType"],
        params: subgraphId === "queue_publish"
          ? { queue_name: "pipeline-jobs", schedule_after_seconds: 0, message_body: {} }
          : { method: "GET", url: "", headers: {}, response_mapping: [] },
      };
      setNodeConfigs((prev) => ({ ...prev, [id]: cfg }));
      setNodes((nds) => [...nds, {
        id,
        type: subgraphId,
        position: { x: 250, y: (nodes.length + 1) * 150 },
        data: {
          label: cfg.label,
          subgraphId,
          color: subgraphId === "rest_connector" ? "#3F51B5" : "#795548",
          connectorType: subgraphId,
          onConfigure: () => openConfigurator(id),
        },
      } as Node]);
      return;
    }
    if (subgraphId === "trigger") {
      const id = `trigger_${Date.now()}`;
      const cfg: ActionConfig = { ...DEFAULT_CONFIG, subgraphId: "trigger", label: "Trigger", description: "Pipeline entry point", nodeType: "trigger", params: {} };
      setNodeConfigs((prev) => ({ ...prev, [id]: cfg }));
      setNodes((nds) => [...nds, {
        id,
        type: "trigger",
        position: { x: 80, y: 80 },
        data: { label: "Trigger", subgraphId: "trigger", color: "#FFC107", triggerEvent, outputPorts: ["patient_id", "encounter_id", "encounter_text"], onConfigure: () => openConfigurator(id) },
      } as Node]);
      return;
    }
    if (subgraphId === "parallel" || subgraphId === "merge" || subgraphId === "transform") {
      const id = `${subgraphId}_${Date.now()}`;
      const cfg: ActionConfig = { ...DEFAULT_CONFIG, subgraphId, label: subgraphId.replace("_", " "), description: "Flow control node", nodeType: subgraphId as ActionConfig["nodeType"], params: {} };
      setNodeConfigs((prev) => ({ ...prev, [id]: cfg }));
      setNodes((nds) => [...nds, {
        id,
        type: subgraphId,
        position: { x: 250, y: (nodes.length + 1) * 150 },
        data: { label: cfg.label, subgraphId, color: "#999", onConfigure: () => openConfigurator(id) },
      } as Node]);
      return;
    }

    const option = SUBGRAPH_OPTIONS.find((s) => s.id === subgraphId);
    if (!option) return;
    const id = `${subgraphId}_${Date.now()}`;
    const cfg: ActionConfig = { ...DEFAULT_CONFIG, subgraphId, label: option.label, description: option.description, nodeType: "action" };
    setNodeConfigs((prev) => ({ ...prev, [id]: cfg }));
    const newNode: Node = {
      id,
      type: "action",
      position: { x: 250, y: (nodes.length + 1) * 150 },
      data: {
        label: option.label,
        subgraphId: option.id,
        color: option.color,
        nodeType: "action",
        onConfigure: () => openConfigurator(id),
      },
    };
    setNodes((nds) => [...nds, newNode]);
  }, [nodes.length, setNodes, openConfigurator, triggerEvent]);

  const handleConfigSave = useCallback((nodeId: string, config: ActionConfig) => {
    setNodeConfigs((prev) => ({ ...prev, [nodeId]: config }));
    const option = SUBGRAPH_OPTIONS.find((s) => s.id === config.subgraphId);
    setNodes((nds) =>
      nds.map((n) =>
        n.id === nodeId
          ? {
              ...n,
              type: config.nodeType || n.type || "action",
              data: {
                ...n.data,
                label: config.label,
                subgraphId: config.subgraphId,
                color: option?.color || "#999",
                nodeType: config.nodeType || "action",
                rules: config.params.rules,
                defaultPort: config.params.defaultPort,
                connectorType: config.nodeType,
              },
            }
          : n
      )
    );
  }, [setNodes]);

  const handleDeleteNode = useCallback((nodeId: string) => {
    setNodes((nds) => nds.filter((n) => n.id !== nodeId));
    setEdges((eds) => eds.filter((e) => e.source !== nodeId && e.target !== nodeId));
    setNodeConfigs((prev) => {
      const next = { ...prev };
      delete next[nodeId];
      return next;
    });
  }, [setNodes, setEdges]);

  const selectedConfig = useMemo(() => {
    if (!selectedNode) return DEFAULT_CONFIG;
    return nodeConfigs[selectedNode] || DEFAULT_CONFIG;
  }, [selectedNode, nodeConfigs]);

  // Compute what all predecessor steps write into the pipeline state.
  // Used to validate key alignment when inputSource === "previous_step".
  const prevStepWrites = useMemo<string[] | null>(() => {
    if (!selectedNode) return null;
    const predecessorIds = edges
      .filter((e) => e.target === selectedNode)
      .map((e) => e.source);
    if (predecessorIds.length === 0) return null;
    const allWrites = new Set<string>();
    for (const predId of predecessorIds) {
      const predNode = nodes.find((n) => n.id === predId);
      const predSubgraphId = (predNode?.data as unknown as ActionNodeData | undefined)?.subgraphId;
      if (predSubgraphId) {
        SUBGRAPH_IO[predSubgraphId]?.writes.forEach((w) => allWrites.add(w));
      }
    }
    return allWrites.size > 0 ? Array.from(allWrites) : null;
  }, [selectedNode, edges, nodes]);

  // Collect field-level mappings from DIRECT predecessors (first predecessor wins per key).
  // Only direct predecessors matter — each step reads from the immediately preceding step.
  const prevStepFieldMappings = useMemo<FieldMappingRow[] | null>(() => {
    if (!selectedNode) return null;
    const predecessorIds = edges
      .filter((e) => e.target === selectedNode)
      .map((e) => e.source);
    if (predecessorIds.length === 0) return null;
    for (const predId of predecessorIds) {
      const predCfg = nodeConfigs[predId];
      const mappings = predCfg?.params?.field_mappings as FieldMappingRow[] | undefined;
      if (mappings && mappings.length > 0) return mappings;
    }
    return null;
  }, [selectedNode, edges, nodeConfigs]);

  const handleSave = useCallback(async () => {
    setSaveError(null);
    const payload = {
      name: planName,
      status: planStatus,
      description: planDescription,
      trigger: triggerEvent ? { event: triggerEvent, type: "data-changed" } : undefined,
      actions: nodes.map((n) => ({
        id: n.id,
        subgraphId: (n.data as unknown as ActionNodeData).subgraphId,
        label: (n.data as unknown as ActionNodeData).label,
        nodeType: (nodeConfigs[n.id]?.nodeType || n.type || "action"),
        position: n.position,
        config: nodeConfigs[n.id] || {},
      })),
      edges: edges.map((e) => ({
        source: e.source,
        target: e.target,
        sourceHandle: e.sourceHandle,
        targetHandle: e.targetHandle,
      })),
    };
    try {
      if (isNew) {
        const result = await api.post<{ id: string }>("/fhir/PlanDefinition", payload);
        router.push(`/admin/pathways/${result.id}`);
      } else {
        await api.put(`/fhir/PlanDefinition/${planId}`, payload);
      }
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "Failed to save pathway");
    }
  }, [planName, planStatus, planDescription, triggerEvent, nodes, edges, nodeConfigs, isNew, planId, router]);

  return (
    <Box sx={{ height: "100vh", display: "flex", flexDirection: "column" }}>
      <Box sx={{ p: 2, display: "flex", alignItems: "center", gap: 2, borderBottom: 1, borderColor: "divider" }}>
        <IconButton onClick={() => router.push("/admin/pathways")}><ArrowBackIcon /></IconButton>
        <TextField
          size="small" placeholder="Pathway name" value={planName}
          onChange={(e) => setPlanName(e.target.value)} sx={{ width: 300 }}
        />
        <FormControl size="small" sx={{ minWidth: 120 }}>
          <InputLabel>Status</InputLabel>
          <Select value={planStatus} label="Status" onChange={(e) => setPlanStatus(e.target.value)}>
            <MenuItem value="draft">Draft</MenuItem>
            <MenuItem value="active">Active</MenuItem>
            <MenuItem value="retired">Retired</MenuItem>
          </Select>
        </FormControl>
        <Box sx={{ flex: 1 }} />
        {saveError && (
          <Alert severity="error" sx={{ py: 0, fontSize: "0.75rem" }} onClose={() => setSaveError(null)}>
            {saveError}
          </Alert>
        )}
        <FormControl size="small" sx={{ minWidth: 200 }}>
          <InputLabel>Add Action</InputLabel>
          <Select label="Add Action" value="" onChange={(e) => addAction(e.target.value)}>
            <MenuItem value="">Add action...</MenuItem>
            <MenuItem disabled sx={{ fontWeight: 700, opacity: 1 }}>Pipeline Steps</MenuItem>
            {SUBGRAPH_OPTIONS.map((s) => (
              <MenuItem key={s.id} value={s.id}>{s.label}</MenuItem>
            ))}
            <MenuItem disabled sx={{ fontWeight: 700, opacity: 1 }}>Flow Control</MenuItem>
            <MenuItem value="condition">Condition</MenuItem>
            <MenuItem value="parallel">Parallel</MenuItem>
            <MenuItem value="merge">Merge</MenuItem>
            <MenuItem value="transform">Transform</MenuItem>
            <MenuItem value="trigger">Trigger</MenuItem>
            <MenuItem disabled sx={{ fontWeight: 700, opacity: 1 }}>Connectors</MenuItem>
            <MenuItem value="rest_connector">REST API Call</MenuItem>
            <MenuItem value="queue_publish">Queue Publish</MenuItem>
          </Select>
        </FormControl>
        <Button variant="contained" startIcon={<SaveIcon />} onClick={handleSave}>Save pathway</Button>
      </Box>

      <TriggerContextPanel
        triggerEvent={triggerEvent}
        onTriggerChange={setTriggerEvent}
        planId={planId}
        planDescription={planDescription}
        onDescriptionChange={setPlanDescription}
      />

      <ValidationPanel warnings={validationWarnings} />

      <Box sx={{ flex: 1, display: "flex", minHeight: 0 }}>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={pathwayNodeTypes}
            edgeTypes={edgeTypes}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            fitView
          >
            <Background />
            <Controls />
            <MiniMap />
          </ReactFlow>
        </Box>
        {drawerOpen && selectedNode && (
          <SidePanel
            key={`${selectedNode}-${drawerKey}`}
            nodeId={selectedNode}
            config={selectedConfig}
            prevStepWrites={prevStepWrites}
            onConfigChange={handleConfigSave}
            onDelete={(nodeId) => {
              handleDeleteNode(nodeId);
              setDrawerOpen(false);
            }}
            onClose={() => setDrawerOpen(false)}
          />
        )}
      </Box>
    </Box>
  );
}
