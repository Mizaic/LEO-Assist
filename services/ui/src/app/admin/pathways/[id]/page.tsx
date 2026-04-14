"use client";

import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import IconButton from "@mui/material/IconButton";
import TextField from "@mui/material/TextField";
import Select from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import FormControl from "@mui/material/FormControl";
import FormControlLabel from "@mui/material/FormControlLabel";
import Checkbox from "@mui/material/Checkbox";
import InputLabel from "@mui/material/InputLabel";
import Chip from "@mui/material/Chip";
import Switch from "@mui/material/Switch";
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
import CloseIcon from "@mui/icons-material/Close";
import CloudUploadIcon from "@mui/icons-material/CloudUpload";
import HistoryIcon from "@mui/icons-material/History";
import ReplayIcon from "@mui/icons-material/Replay";
import AccountTreeIcon from "@mui/icons-material/AccountTree";
import SearchIcon from "@mui/icons-material/Search";
import StorageIcon from "@mui/icons-material/Storage";
import Drawer from "@mui/material/Drawer";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import DialogActions from "@mui/material/DialogActions";
import LinearProgress from "@mui/material/LinearProgress";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  addEdge,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  type Connection,
  type EdgeChange,
} from "@xyflow/react";
import dagre from "@dagrejs/dagre";
import "@xyflow/react/dist/style.css";
import { api } from "@/lib/api";
import { compareIsoDateTimeDesc } from "@/lib/dateSort";
import { nodeTypes as pathwayNodeTypes } from "@/components/pathway/nodes/nodeTypes";
import { PortEdge } from "@/components/pathway/edges/PortEdge";
import {
  SUBGRAPH_OPTIONS,
  SUBGRAPH_IO,
  SUBGRAPH_CATEGORY,
  WIZARD_STEPS_LLM,
  WIZARD_STEPS_NO_LLM,
  type SubgraphCategory,
} from "@/components/pathway/config/subgraphs";
import { TRIGGER_OPTIONS } from "@/components/pathway/config/triggers";
import { SOURCE_DEFINITIONS, type SourceType } from "@/components/pathway/nodes/SourceNode";
import { OUTPUT_DEFINITIONS, type OutputType } from "@/components/pathway/nodes/OutputNode";
import {
  PipelineTestContext,
  type StepTraceResult,
  type ViewerTraceSnapshot,
} from "@/components/pathway/context/PipelineTestContext";
import {
  PIPELINE_GENERATED_SENTINEL,
  DEFAULT_CONFIG,
  type ActionConfig,
  type ActionNodeData,
  type PlanData,
  type ModelPreset,
} from "@/components/pathway/config/types";

const edgeTypes = { portEdge: PortEdge };

// ── Dagre auto-layout ─────────────────────────────────────────────────────────

const NODE_WIDTH  = 220;
const NODE_HEIGHT = 80;

// -- Layout helpers -----------------------------------------------------------

/** Per-port height in pixels used to estimate the rendered node height. */
const PORT_ROW_PX = 28;

/**
 * Estimate the rendered height of an action node based on how many port
 * handles it will render on each side (input vs output).  Nodes with more
 * ports must be given more vertical space in the Dagre graph so they do not
 * visually overlap their neighbours.
 */
function estimatedNodeHeight(subgraphId: string): number {
  const io = SUBGRAPH_IO[subgraphId];
  if (!io) return NODE_HEIGHT;
  const portCount = Math.max(io.reads.length, io.writes.length);
  return Math.max(NODE_HEIGHT, portCount * PORT_ROW_PX + 40);
}
const CANVAS_ONLY_NODE_TYPES = new Set(["source", "output", "viewer"]);

function isCanvasOnlyNodeType(nodeType: string | null | undefined): boolean {
  return CANVAS_ONLY_NODE_TYPES.has(nodeType ?? "");
}

function filterExecutionNodes(nodes: Node[]): Node[] {
  return nodes.filter((n) => !isCanvasOnlyNodeType(n.type ?? ""));
}

function filterExecutionEdges(edges: Edge[], nodes: Node[]): Edge[] {
  return edges.filter(
    (e) => !nodes.find((n) => n.id === e.source && isCanvasOnlyNodeType(n.type ?? ""))
      && !nodes.find((n) => n.id === e.target && isCanvasOnlyNodeType(n.type ?? "")),
  );
}

type PersistedCanvasEdge = {
  source: string;
  target: string;
  sourceHandle?: string | null;
  targetHandle?: string | null;
  source_handle?: string | null;
  target_handle?: string | null;
};

function applyDagreLayout(nodes: Node[], edges: Edge[]): Node[] {
  const g = new dagre.graphlib.Graph();
  // ranksep: vertical gap between pipeline stages (increased to avoid port overlap)
  // nodesep: horizontal gap between sibling nodes in the same rank
  g.setGraph({ rankdir: "TB", nodesep: 80, ranksep: 120 });
  g.setDefaultEdgeLabel(() => ({}));
  nodes.forEach((n) => {
    const subgraphId = (n.data as Record<string, unknown>)?.subgraphId as string | undefined;
    const h = subgraphId ? estimatedNodeHeight(subgraphId) : NODE_HEIGHT;
    g.setNode(n.id, { width: NODE_WIDTH, height: h });
  });
  edges.forEach((e) => { if (e.source && e.target) g.setEdge(e.source, e.target); });
  dagre.layout(g);
  return nodes.map((n) => {
    const pos = g.node(n.id);
    const subgraphId = (n.data as Record<string, unknown>)?.subgraphId as string | undefined;
    const h = subgraphId ? estimatedNodeHeight(subgraphId) : NODE_HEIGHT;
    return { ...n, position: { x: pos.x - NODE_WIDTH / 2, y: pos.y - h / 2 } };
  });
}

// ── Model preset picker ───────────────────────────────────────────────────────

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
        <Typography component="a" href="/admin/platform?tab=model-config" variant="caption" color="primary" sx={{ textDecoration: "underline" }}>
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

/** Plain-English descriptions for pipeline state keys — shown in the data-flow panel. */
const STATE_KEY_LABELS: Record<string, string> = {
  encounter_text:            "Patient notes text",
  patient_id:                "Patient identifier",
  encounter_id:              "Encounter / document ID",
  entities:                  "Clinical findings (list)",
  sentences:                 "Sentences from the notes (list)",
  errors:                    "Processing errors (list)",
  is_verified:               "Verification passed? (yes/no)",
  verification_result:       "Verification detail",
  tier_decisions:            "Confidence grades (list)",
  documents_written:         "Records saved (list)",
  training_labels_written:   "Training labels saved (list)",
  sbar_report:               "SBAR clinical summary",
  compliance_result:         "Compliance check result",
  anchors:                   "Key clinical anchors (list)",
  episodes:                  "Episodes of care (list)",
  safety_net_alerts:         "Safety-netting alerts (list)",
  quality_issues:            "Quality issues found (list)",
  recommendations:           "Next best action recommendations (list)",
  connector_response:        "API response",
  queued:                    "Queue publish status",
  run_id:                    "Pipeline run ID",
  organization_id:           "Organisation / practice ID",
};

function stateKeyLabel(key: string): string {
  return STATE_KEY_LABELS[key] ?? key;
}

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

function getProducedKeysFromMappings(mappings: FieldMappingRow[] | undefined): string[] {
  if (!mappings || mappings.length === 0) return [];
  const keys = new Set<string>();
  for (const row of mappings) {
    const statePath = row.statePath?.trim();
    if (!statePath) continue;
    const match = statePath.match(/^(\w+)/);
    if (match?.[1]) keys.add(match[1]);
  }
  return Array.from(keys);
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
    <Stack spacing={2}>

      {/* What this step reads */}
      <Paper variant="outlined" sx={{ p: 2, borderRadius: 2 }}>
        <Stack spacing={2}>
          <Box>
            <Typography variant="subtitle2" fontWeight={700} sx={{ mb: 0.5 }}>What this step needs</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1.25 }}>
              This step expects the following data to arrive from earlier in the pipeline.
            </Typography>
            <Stack spacing={0.75}>
              {io.reads.map((k) => {
                const ok      = provided && provided.has(k);
                const unknown = provided === null;
                const fieldsForKey = producedFields?.[k] ? Array.from(producedFields[k]) : null;
                const requiredForKey = requiredFields?.[k] ?? null;
                return (
                  <Box key={k}>
                    <Stack direction="row" alignItems="center" spacing={0.75} sx={{ mb: fieldsForKey ? 0.5 : 0 }}>
                      <Tooltip title={<Box sx={{ fontFamily: "monospace" }}>{k}</Box>} placement="top">
                        <Chip
                          size="small"
                          label={stateKeyLabel(k)}
                          variant={unknown ? "outlined" : ok ? "filled" : "outlined"}
                          color={unknown ? "default" : ok ? "success" : "error"}
                          sx={{ fontSize: "0.8rem", height: 26 }}
                        />
                      </Tooltip>
                      {!unknown && !ok && (
                        <Typography variant="body2" color="error.main" sx={{ fontSize: "0.78rem" }}>
                          — not yet provided by the previous step
                        </Typography>
                      )}
                    </Stack>
                    {fieldsForKey && (
                      <Stack direction="row" spacing={0.4} flexWrap="wrap" useFlexGap sx={{ pl: 2, mt: 0.4 }}>
                        {fieldsForKey.map((f) => {
                          const needed = requiredForKey?.includes(f);
                          return (
                            <Chip key={f} size="small"
                              label={`.${f}${needed ? " *" : ""}`}
                              color={needed ? "success" : "default"}
                              variant={needed ? "filled" : "outlined"}
                              sx={{ fontFamily: "monospace", fontSize: "0.72rem", height: 20 }}
                            />
                          );
                        })}
                        {requiredForKey?.filter((f) => !producedFields?.[k]?.has(f)).map((f) => (
                          <Chip key={`missing-${f}`} size="small"
                            label={`.${f} ✗`}
                            color="error"
                            variant="outlined"
                            sx={{ fontFamily: "monospace", fontSize: "0.72rem", height: 20 }}
                          />
                        ))}
                      </Stack>
                    )}
                  </Box>
                );
              })}
            </Stack>
          </Box>

          <Divider />

          <Box>
            <Typography variant="subtitle2" fontWeight={700} sx={{ mb: 0.5 }}>What gets sent to the next step</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1.25 }}>
              After this step runs, these items are ready for the next step to use.
            </Typography>
            <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
              {io.writes.map((k) => (
                <Tooltip key={k} title={<Box sx={{ fontFamily: "monospace" }}>{k}</Box>} placement="top">
                  <Chip size="small" label={stateKeyLabel(k)} color="primary" variant="outlined" sx={{ fontSize: "0.8rem", height: 26 }} />
                </Tooltip>
              ))}
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
          Wire a data source node or a previous step to this one on the canvas, then come back here to see whether the right data is available.
        </Alert>
      )}
    </Stack>
  );
}

// ── Per-subgraph settings panel (step 2) ─────────────────────────────────────
function SubgraphSettingsPanel({
  category, config, updateField, updateParam, onPresetSelected,
}: {
  category: SubgraphCategory;
  config: ActionConfig;
  updateField: <K extends keyof ActionConfig>(k: K, v: ActionConfig[K]) => void;
  updateParam: (k: string, v: unknown) => void;
  /** Called when the user selects a preset, so callers can read supports_temperature. */
  onPresetSelected?: (preset: ModelPreset | null) => void;
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
          <Typography component="a" href="/admin/platform?tab=model-config" target="_blank" variant="caption" color="primary" sx={{ textDecoration: "underline" }}>
            AI Models
          </Typography>.
        </Typography>
        <ModelPresetPicker
          value={config.modelPresetId}
          onChange={(presetId, preset) => {
            updateField("modelPresetId", presetId);
            updateField("modelPresetName", preset?.name ?? "");
            onPresetSelected?.(preset);
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
  return fields.map((f) => ({
    id: `${topKey}.${f.name}`,
    llmField: `${topKey}[].${f.name}`,
    type: f.type,
    description: f.description,
    required: f.required,
    statePath: "",
    custom: false,
  }));
}

// Common AI sub-field names mapped to canonical pipeline sub-field names.
// Used by auto-map to pre-fill the most likely statePath for each AI field.
const AUTO_MAP_SUBFIELD: Record<string, string> = {
  text: "text",
  surface_form: "text",
  raw_text: "text",
  lookup_term: "lookup_term",
  preferred_term: "lookup_term",
  canonical: "lookup_term",
  semantic_tag: "semantic_tag",
  type: "semantic_tag",
  category: "semantic_tag",
  assertion: "assertion",
  negation: "assertion",
  negated: "assertion",
  value: "value",
  numeric_value: "value",
  unit: "unit",
  units: "unit",
  reference_range: "reference_range",
  normal_range: "reference_range",
  sentence_id: "id",
  sent_id: "id",
  sentence: "text",
  id: "id",
};

// For a given AI field name, guess the best (writeKey, subField) pair.
function autoMapField(
  llmField: string,
  writeKeys: string[],
): string {
  // Strip the top-level array prefix, e.g. "terms[].sentence_id" → "sentence_id"
  const bare = llmField.replace(/^[^[]+\[\]\./, "");
  const canonicalSub = AUTO_MAP_SUBFIELD[bare] ?? bare;

  // sentence_id / id → try sentences[] first, fall back to entities[]
  if (["id", "sentence_id", "sent_id"].includes(bare)) {
    if (writeKeys.includes("sentences")) return `sentences[].${canonicalSub}`;
    if (writeKeys.includes("entities")) return `entities[].${canonicalSub}`;
  }

  // Prefer entities[] for clinical-fact fields; if not available pick first array key
  const preferredKey = writeKeys.find((k) => ARRAY_OUTPUT_KEYS.has(k) && k === "entities")
    ?? writeKeys.find((k) => ARRAY_OUTPUT_KEYS.has(k));

  if (preferredKey) return `${preferredKey}[].${canonicalSub}`;
  // Flat key fallback
  if (writeKeys.length > 0) return `${writeKeys[0]}.${canonicalSub}`;
  return "";
}

// Keys whose statePath uses the "key[].subField" object-array format.
const ARRAY_OUTPUT_KEYS = new Set([
  "entities", "sentences", "errors", "tier_decisions", "anchors",
  "episodes", "safety_net_alerts", "quality_issues", "recommendations",
  "documents_written", "training_labels_written",
]);

/** Parse a statePath (e.g. "entities[].text") into { topKey, subField }. */
function parseStatePath(statePath: string): { topKey: string; subField: string } {
  const m = statePath.match(/^(\w+)\[\]\.(.*)$/);
  if (m) return { topKey: m[1], subField: m[2] };
  return { topKey: statePath, subField: "" };
}

/** Build a statePath from topKey + subField for the given key type.
 *  Any key that ends up in object-array form (has a subField) uses the key[].field format.
 */
function buildStatePath(topKey: string, subField: string): string {
  if (!topKey) return "";
  if (subField.trim()) return `${topKey}[].${subField.trim()}`;
  return topKey;
}

function topKeysFromMappings(rows: FieldMappingRow[]): string[] {
  const keys = new Set<string>();
  for (const row of rows) {
    const path = row.statePath?.trim();
    if (!path) continue;
    const match = path.match(/^(\w+)/);
    if (match?.[1]) keys.add(match[1]);
  }
  return Array.from(keys);
}

function hydrateActionConfig(action: {
  subgraphId: string;
  label?: string;
  config?: unknown;
}): ActionConfig {
  const rawConfig = (action.config ?? {}) as Record<string, unknown>;
  const rawParams = (rawConfig.params && typeof rawConfig.params === "object"
    ? (rawConfig.params as Record<string, unknown>)
    : {}) as ActionConfig["params"];

  // Backward compatibility: older saves stored mappings at config.field_mappings.
  if (
    !Array.isArray((rawParams as Record<string, unknown>).field_mappings) &&
    Array.isArray(rawConfig.field_mappings)
  ) {
    (rawParams as Record<string, unknown>).field_mappings = rawConfig.field_mappings;
  }

  return {
    ...DEFAULT_CONFIG,
    subgraphId: action.subgraphId,
    label: action.label || action.subgraphId,
    ...(rawConfig as Partial<ActionConfig>),
    params: rawParams,
  };
}


/** Small inline control to let the user add a new named output group. */
function AddGroupButton({ onAdd }: { onAdd: (name: string) => void }) {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState("");
  if (!open) {
    return (
      <Button size="small" variant="text" sx={{ fontSize: "0.68rem", textTransform: "none", color: "text.secondary", mt: 0.25 }}
        onClick={() => setOpen(true)}>
        + Add output group
      </Button>
    );
  }
  return (
    <Stack direction="row" spacing={0.75} alignItems="center" sx={{ mt: 0.5 }}>
      <TextField
        autoFocus
        size="small"
        value={value}
        onChange={(e) => setValue(e.target.value.replace(/[^a-z0-9_]/gi, "_").toLowerCase())}
        placeholder="group name (e.g. findings)"
        inputProps={{ style: { fontFamily: "monospace", fontSize: "0.75rem", padding: "3px 8px" } }}
        sx={{ flex: 1 }}
        onKeyDown={(e) => {
          if (e.key === "Enter" && value.trim()) { onAdd(value.trim()); setValue(""); setOpen(false); }
          if (e.key === "Escape") { setValue(""); setOpen(false); }
        }}
      />
      <Button size="small" variant="contained" disabled={!value.trim()}
        sx={{ fontSize: "0.72rem", textTransform: "none", py: "2px" }}
        onClick={() => { if (value.trim()) { onAdd(value.trim()); setValue(""); setOpen(false); } }}>
        Add
      </Button>
      <IconButton size="small" onClick={() => { setValue(""); setOpen(false); }}>
        <CloseIcon sx={{ fontSize: "0.9rem" }} />
      </IconButton>
    </Stack>
  );
}

function SchemaAlignmentPanel({
  subgraphId,
  promptConfigId,
  fieldMappings,
  onFieldMappingsChange,
  prevStepFieldMappings,
}: {
  subgraphId: string;
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
  // Extra user-defined output group names (added via the "+ New group" option).
  const [extraWriteKeys, setExtraWriteKeys] = useState<string[]>([]);
  // Auto-fill preview: set to the proposed mappings before the user confirms
  const [autoFillPreview, setAutoFillPreview] = useState<FieldMappingRow[] | null>(null);
  // Undo stack: stores the previous mapping state before auto-fill was applied
  const [undoStack, setUndoStack] = useState<FieldMappingRow[] | null>(null);
  const initialised = fieldMappings.length > 0;

  // Derive output groups from actual mappings and schema (not hardcoded SUBGRAPH_IO writes)
  // so the canvas connectors match what the user/prompt configured.
  const mappedWriteKeys = useMemo(() => topKeysFromMappings(fieldMappings), [fieldMappings]);
  const writeKeys: string[] = useMemo(() => {
    const keys = [...mappedWriteKeys];
    if (schemaFields?.topKey && !keys.includes(schemaFields.topKey)) {
      keys.unshift(schemaFields.topKey);
    }
    for (const k of extraWriteKeys) {
      if (!keys.includes(k)) keys.push(k);
    }
    return keys;
  }, [mappedWriteKeys, schemaFields?.topKey, extraWriteKeys]);

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
        <Typography component="a" href="/admin/knowledge?tab=ai-instructions" variant="caption" color="primary" sx={{ textDecoration: "underline" }}>
          Prompt Tuner
        </Typography>.
      </Alert>
    );
  }

  const aiRows          = fieldMappings.filter((r) => r.llmField !== PIPELINE_GENERATED_SENTINEL);
  const unmapped        = aiRows.filter((r) => !r.statePath.trim()).length;
  const missingRequired = aiRows.some((r) => r.required && !r.statePath.trim());
  const hasIncoming     = Object.keys(incomingGroups).length > 0;

  // Coverage count: how many AI rows map to each write key.
  const coverageByKey: Record<string, number> = {};
  for (const key of writeKeys) coverageByKey[key] = 0;
  for (const row of aiRows) {
    const { topKey } = parseStatePath(row.statePath);
    if (topKey && coverageByKey[topKey] !== undefined) coverageByKey[topKey]++;
  }

  return (
    <Stack spacing={2}>

      {/* ── Part 1: What arrives from the previous step ── */}
      {hasIncoming && (
        <Paper variant="outlined" sx={{ p: 2, borderRadius: 2 }}>
          <Typography variant="subtitle2" fontWeight={700} sx={{ mb: 0.5 }}>Data available from earlier steps</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
            These items were produced by an earlier step. Tick any you also want this step to pass forward to the next one.
          </Typography>
          {Object.entries(incomingGroups).map(([stateKey, fields]) => (
            <Box key={stateKey} sx={{ mb: 1.5 }}>
              {stateKey !== "__flat__" && (
                <Typography variant="body2" fontWeight={600} sx={{ fontFamily: "monospace", display: "block", mb: 0.75, color: "text.secondary" }}>
                  {stateKey}[]
                </Typography>
              )}
              <Stack spacing={0.75}>
                {fields.map((field) => {
                  const path = stateKey === "__flat__" ? field : `${stateKey}[].${field}`;
                  const checked = passthroughPaths.has(path);
                  return (
                    <Stack key={path} direction="row" alignItems="center" spacing={1.5}>
                      <Box
                        component="input"
                        type="checkbox"
                        checked={checked}
                        onChange={() => togglePassthrough(path)}
                        style={{ cursor: "pointer", width: 17, height: 17, flexShrink: 0 }}
                      />
                      <Typography variant="body2" sx={{ fontFamily: "monospace", fontSize: "0.82rem", flex: 1 }}>
                        .{field}
                      </Typography>
                      {checked && (
                        <Chip size="small" label="kept" color="success" variant="outlined"
                          sx={{ height: 22, fontSize: "0.78rem" }} />
                      )}
                    </Stack>
                  );
                })}
              </Stack>
            </Box>
          ))}
        </Paper>
      )}

      {/* ── Output groups — connection points this step will expose on the canvas ── */}
      <Paper variant="outlined" sx={{ p: 2, borderRadius: 2 }}>
        <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 0.75 }}>
          <Typography variant="subtitle2" fontWeight={700} sx={{ flex: 1 }}>
            Connection points on the canvas
          </Typography>
          <Tooltip title="Each group becomes a labelled dot on this step's canvas block. Wire each dot independently to a different next step.">
            <InfoOutlinedIcon sx={{ fontSize: "1rem", color: "text.disabled" }} />
          </Tooltip>
        </Stack>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
          Each group below becomes a dot on this step&apos;s canvas block — you can wire each one to a different next step.
          {schemaFields && (
            <> The AI uses the name <Box component="span" sx={{ fontFamily: "monospace", fontWeight: 600 }}>{schemaFields.topKey}[]</Box> — it has been added as a group for you.</>
          )}
        </Typography>
        <Stack direction="row" flexWrap="wrap" gap={0.75} sx={{ mb: 1 }}>
          {writeKeys.map((key) => {
            const count = coverageByKey[key] ?? 0;
            return (
              <Chip
                key={key}
                size="small"
                label={`${key}[] — ${count > 0 ? `${count} field${count > 1 ? "s" : ""}` : "none yet"}`}
                color={count > 0 ? "success" : "default"}
                variant={count > 0 ? "filled" : "outlined"}
                sx={{ fontFamily: "monospace", fontSize: "0.8rem", height: 28 }}
              />
            );
          })}
        </Stack>
        {/* Allow user to add a new named output group */}
        <AddGroupButton onAdd={(name) => setExtraWriteKeys((prev) => prev.includes(name) ? prev : [...prev, name])} />
      </Paper>

      {/* ── Part 2: What the AI adds ── */}
      <Box>
        <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 0.75 }}>
          <Typography variant="subtitle2" fontWeight={700}>Name what the AI finds</Typography>
          {unmapped === 0
            ? <Chip size="small" label="All named ✓" color="success" sx={{ fontSize: "0.8rem", height: 26 }} />
            : <Chip size="small" label={`${unmapped} still need a name`} color="warning" sx={{ fontSize: "0.8rem", height: 26 }} />}
          <Box sx={{ flex: 1 }} />
          {undoStack && (
            <Button size="small" variant="outlined" color="warning"
              onClick={() => { onFieldMappingsChange(undoStack); setUndoStack(null); setAutoFillPreview(null); }}
              sx={{ fontSize: "0.8rem", textTransform: "none", flexShrink: 0 }}>
              Undo auto-fill
            </Button>
          )}
          {!autoFillPreview && unmapped > 0 && writeKeys.length > 0 && (
            <Button
              size="small"
              variant="outlined"
              onClick={() => {
                const proposed = fieldMappings.map((r) => {
                  if (r.llmField === PIPELINE_GENERATED_SENTINEL) return r;
                  if (r.statePath.trim()) return r;
                  return { ...r, statePath: autoMapField(r.llmField, writeKeys) };
                });
                setAutoFillPreview(proposed);
              }}
              sx={{ fontSize: "0.8rem", textTransform: "none", flexShrink: 0 }}
            >
              Preview auto-fill
            </Button>
          )}
          {autoFillPreview && (
            <Stack direction="row" spacing={0.5}>
              <Button size="small" variant="contained" color="primary"
                onClick={() => { setUndoStack(fieldMappings); onFieldMappingsChange(autoFillPreview); setAutoFillPreview(null); }}
                sx={{ fontSize: "0.72rem", textTransform: "none" }}>
                Apply
              </Button>
              <Button size="small" variant="outlined"
                onClick={() => setAutoFillPreview(null)}
                sx={{ fontSize: "0.72rem", textTransform: "none" }}>
                Cancel
              </Button>
            </Stack>
          )}
        </Stack>

        {autoFillPreview && (
          <Alert severity="info" sx={{ fontSize: "0.8rem", mb: 1 }} icon={false}>
            <strong>Preview:</strong> Names shown below are what auto-fill would apply to unmapped fields. Click <strong>Apply</strong> to use them, or <strong>Cancel</strong> to discard.
          </Alert>
        )}
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
          The AI returns these fields. For each one, choose which group it belongs to and give it a name. Those groups appear as connection points on the canvas.
          {schemaFields && (
            <> The AI calls them <Box component="span" sx={{ fontFamily: "monospace", fontWeight: 600 }}>{schemaFields.topKey}[]</Box> — you can rename them here.</>
          )}
        </Typography>

        {/* Column headers */}
        <Stack direction="row" spacing={1} sx={{ px: 0.5, mb: 0.75 }}>
          <Typography variant="caption" fontWeight={700} color="text.secondary" sx={{ flex: "0 0 150px", fontSize: "0.75rem" }}>The AI finds</Typography>
          <Typography variant="caption" fontWeight={700} color="text.secondary" sx={{ flex: "0 0 70px", fontSize: "0.75rem" }}>Type</Typography>
          <Typography variant="caption" fontWeight={700} color="text.secondary" sx={{ flex: 1, fontSize: "0.75rem" }}>Save as</Typography>
          <Box sx={{ width: 28 }} />
        </Stack>

        <Stack spacing={0.75}>
          {(autoFillPreview ?? fieldMappings).filter((r) => r.llmField !== PIPELINE_GENERATED_SENTINEL).map((row) => {
            const { topKey: rowTopKey, subField: rowSubField } = parseStatePath(row.statePath);
            const isKnownKey = rowTopKey ? writeKeys.includes(rowTopKey) : true;
            const isCustomMode = rowTopKey === "__custom__" || (rowTopKey && !writeKeys.includes(rowTopKey) && writeKeys.length > 0);
            // All output groups use the key[].field format for AI steps
            const needsSubField = Boolean(rowTopKey) && rowTopKey !== "__custom__" && isKnownKey;
            const showUnrecognisedWarning = row.statePath.trim() && !isKnownKey && writeKeys.length > 0;

            return (
              <Stack key={row.id} spacing={0.25}>
                <Stack direction="row" spacing={1} alignItems="flex-start">
                  {/* AI field name — locked for schema rows, editable for custom */}
                  <Box sx={{ flex: "0 0 150px", pt: 0.5 }}>
                    {row.custom ? (
                      <TextField
                        size="small"
                        value={row.llmField}
                        onChange={(e) => updateRow(row.id, { llmField: e.target.value })}
                        placeholder="e.g. terms[].fieldName"
                        inputProps={{ style: { fontFamily: "monospace", fontSize: "0.8rem", padding: "4px 8px" } }}
                        sx={{ width: "100%" }}
                      />
                    ) : (
                      <Tooltip title={row.description || ""} placement="top-start">
                        <Box sx={{
                          fontFamily: "monospace",
                          fontSize: "0.8rem",
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
                  <Box sx={{ flex: "0 0 70px", fontFamily: "monospace", fontSize: "0.78rem", color: "info.main", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", pt: 0.5 }}>
                    {row.type || "—"}
                  </Box>

                  {/* Target pipeline state path — split key dropdown + sub-field input */}
                  <Box sx={{ flex: 1 }}>
                    {writeKeys.length > 0 && !row.custom ? (
                      <Stack direction="row" spacing={0.5} alignItems="center">
                        {/* Output key selector */}
                        <FormControl size="small" sx={{ minWidth: 120 }} error={row.required && !rowTopKey}>
                          <Select
                            value={writeKeys.includes(rowTopKey) ? rowTopKey : (rowTopKey ? "__custom__" : "")}
                            onChange={(e) => {
                              const val = e.target.value as string;
                              if (val === "__custom__") {
                                updateRow(row.id, { statePath: "" });
                              } else {
                                updateRow(row.id, { statePath: buildStatePath(val, rowSubField) });
                              }
                            }}
                            displayEmpty
                            renderValue={(val) => (
                              <Box sx={{ fontFamily: "monospace", fontSize: "0.8rem" }}>
                                {val === "" ? <Box component="span" sx={{ color: "text.disabled" }}>— choose group —</Box> : val === "__custom__" ? "custom…" : val}
                              </Box>
                            )}
                            sx={{ fontSize: "0.8rem", "& .MuiSelect-select": { py: "4px", px: "8px" } }}
                          >
                            <MenuItem value="" disabled sx={{ fontSize: "0.8rem" }}>
                              <em>Choose a group</em>
                            </MenuItem>
                            {writeKeys.map((k) => (
                              <MenuItem key={k} value={k} sx={{ fontFamily: "monospace", fontSize: "0.8rem" }}>
                                {k}[]
                                {schemaFields?.topKey === k && (
                                  <Chip size="small" label="from AI" sx={{ ml: 1, height: 18, fontSize: "0.72rem" }} />
                                )}
                              </MenuItem>
                            ))}
                            <MenuItem value="__custom__" sx={{ fontSize: "0.8rem", color: "text.secondary" }}>
                              Create a new group…
                            </MenuItem>
                          </Select>
                        </FormControl>

                        {/* Sub-field name — shown for object[] keys */}
                        {needsSubField && !isCustomMode && (
                          <>
                            <Typography variant="body2" sx={{ fontFamily: "monospace", color: "text.disabled", flexShrink: 0 }}>[].</Typography>
                            <TextField
                              size="small"
                              value={rowSubField}
                              onChange={(e) => updateRow(row.id, { statePath: buildStatePath(rowTopKey, e.target.value) })}
                              placeholder="field name"
                              error={row.required && !rowSubField.trim()}
                              inputProps={{ style: { fontFamily: "monospace", fontSize: "0.8rem", padding: "4px 8px" } }}
                              sx={{ flex: 1, minWidth: 80 }}
                            />
                          </>
                        )}

                        {/* Custom free-text fallback */}
                        {(isCustomMode || (rowTopKey && !writeKeys.includes(rowTopKey))) && (
                          <TextField
                            size="small"
                            value={row.statePath}
                            onChange={(e) => updateRow(row.id, { statePath: e.target.value })}
                            placeholder="e.g. entities[].text"
                            error={row.required && !row.statePath.trim()}
                            inputProps={{ style: { fontFamily: "monospace", fontSize: "0.8rem", padding: "4px 8px" } }}
                            sx={{ flex: 1, minWidth: 100 }}
                          />
                        )}
                      </Stack>
                    ) : (
                      // Custom row or no writeKeys — single free-text field
                      <TextField
                        size="small"
                        value={row.statePath}
                        onChange={(e) => updateRow(row.id, { statePath: e.target.value })}
                        placeholder="e.g. entities[].text"
                        error={row.required && !row.statePath.trim()}
                        helperText={row.required && !row.statePath.trim() ? "Required — give this field a name" : undefined}
                        inputProps={{ style: { fontFamily: "monospace", fontSize: "0.8rem", padding: "4px 8px" } }}
                        sx={{ width: "100%" }}
                      />
                    )}
                  </Box>

                  <IconButton
                    size="small"
                    onClick={() => removeRow(row.id)}
                    sx={{ width: 28, height: 28, color: "text.disabled", "&:hover": { color: "error.main" }, flexShrink: 0, mt: 0.25 }}
                  >
                    <Box component="span" sx={{ fontSize: "0.8rem", lineHeight: 1 }}>✕</Box>
                  </IconButton>
                </Stack>

                {/* Unrecognised output key warning */}
                {showUnrecognisedWarning && (
                  <Stack direction="row" alignItems="center" spacing={0.5} sx={{ pl: "228px" }}>
                    <WarningAmberIcon sx={{ fontSize: 16, color: "warning.main" }} />
                    <Typography variant="body2" color="warning.main" sx={{ fontSize: "0.78rem" }}>
                      &ldquo;{rowTopKey}&rdquo; is not one of the named outputs — later steps won&apos;t be able to pick it up
                    </Typography>
                  </Stack>
                )}
              </Stack>
            );
          })}
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
          sx={{ mt: 1.5, alignSelf: "flex-start", fontSize: "0.8rem", textTransform: "none" }}
        >
          + Add an extra field
        </Button>

        <Typography variant="body2" color="text.secondary" sx={{ display: "block", mt: 1, fontSize: "0.78rem" }}>
          * Required — must be saved before you can continue. Hover a field name to see its description.
        </Typography>
      </Box>
    </Stack>
  );
}

// ── Action configurator ───────────────────────────────────────────────────────
// ── Parallel / Merge branch configuration ────────────────────────────────────

function BranchConfigPanel({
  nodeType,
  branches,
  onBranchesChange,
}: {
  nodeType: "parallel" | "merge";
  branches: string[];
  onBranchesChange: (branches: string[]) => void;
}) {
  const label = nodeType === "parallel" ? "output branch" : "input branch";
  const addBranch = () => onBranchesChange([...branches, `branch_${String.fromCharCode(97 + branches.length)}`]);
  const removeBranch = (i: number) => { if (branches.length > 2) onBranchesChange(branches.filter((_, idx) => idx !== i)); };
  const renameBranch = (i: number, val: string) => onBranchesChange(branches.map((b, idx) => (idx === i ? val.replace(/[^a-z0-9_]/gi, "_").toLowerCase() : b)));

  return (
    <Stack spacing={2}>
      <Box>
        <Typography variant="subtitle2" fontWeight={700} sx={{ mb: 0.5 }}>
          {nodeType === "parallel" ? "Output branches" : "Input branches"}
        </Typography>
        <Typography variant="caption" color="text.secondary">
          Each branch becomes a separate {label} on this node. Name them to match the canvas wires.
        </Typography>
      </Box>
      <Stack spacing={1}>
        {branches.map((b, i) => (
          <Stack key={i} direction="row" spacing={1} alignItems="center">
            <TextField
              size="small"
              value={b}
              onChange={(e) => renameBranch(i, e.target.value)}
              inputProps={{ style: { fontFamily: "monospace", fontSize: "0.8rem" } }}
              sx={{ flex: 1 }}
            />
            <IconButton size="small" onClick={() => removeBranch(i)} disabled={branches.length <= 2}
              sx={{ color: "text.disabled", "&:hover": { color: "error.main" } }}>
              <CloseIcon sx={{ fontSize: "0.9rem" }} />
            </IconButton>
          </Stack>
        ))}
      </Stack>
      <Button size="small" variant="outlined" onClick={addBranch}
        sx={{ alignSelf: "flex-start", textTransform: "none", fontSize: "0.78rem" }}>
        + Add {label}
      </Button>
      {branches.length < 2 && (
        <Alert severity="warning" sx={{ fontSize: "0.78rem" }}>Minimum 2 branches required.</Alert>
      )}
    </Stack>
  );
}

// ── Transform node operations ─────────────────────────────────────────────────

type TransformOp = "rename" | "filter" | "compute";

interface TransformOperation {
  id: string;
  op: TransformOp;
  sourceField: string;
  targetField: string;
  expression: string;
}

function TransformConfigPanel({
  operations,
  onOperationsChange,
}: {
  operations: TransformOperation[];
  onOperationsChange: (ops: TransformOperation[]) => void;
}) {
  const addOp = (op: TransformOp) => onOperationsChange([
    ...operations,
    { id: `op_${Date.now()}`, op, sourceField: "", targetField: "", expression: "" },
  ]);
  const removeOp = (id: string) => onOperationsChange(operations.filter((o) => o.id !== id));
  const updateOp = (id: string, patch: Partial<TransformOperation>) =>
    onOperationsChange(operations.map((o) => (o.id === id ? { ...o, ...patch } : o)));

  return (
    <Stack spacing={2}>
      <Box>
        <Typography variant="subtitle2" fontWeight={700} sx={{ mb: 0.5 }}>Transform operations</Typography>
        <Typography variant="caption" color="text.secondary">
          Add operations to reshape the data as it passes through this step.
        </Typography>
      </Box>
      {operations.length === 0 && (
        <Alert severity="info" sx={{ fontSize: "0.78rem" }} icon={false}>
          No operations yet. Add one below to start reshaping data.
        </Alert>
      )}
      <Stack spacing={1.5}>
        {operations.map((o) => (
          <Paper key={o.id} variant="outlined" sx={{ p: 1.5, borderRadius: 2 }}>
            <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
              <Select
                size="small"
                value={o.op}
                onChange={(e) => updateOp(o.id, { op: e.target.value as TransformOp })}
                sx={{ fontSize: "0.78rem", minWidth: 110 }}
              >
                <MenuItem value="compute">Compute value</MenuItem>
                <MenuItem value="filter">Filter rows</MenuItem>
                <MenuItem value="rename">Rename field</MenuItem>
              </Select>
              <Box sx={{ flex: 1 }} />
              <IconButton size="small" onClick={() => removeOp(o.id)}
                sx={{ color: "text.disabled", "&:hover": { color: "error.main" } }}>
                <CloseIcon sx={{ fontSize: "0.9rem" }} />
              </IconButton>
            </Stack>
            {o.op === "rename" && (
              <Stack direction="row" spacing={1} alignItems="center">
                <TextField size="small" label="From field" value={o.sourceField}
                  onChange={(e) => updateOp(o.id, { sourceField: e.target.value })}
                  inputProps={{ style: { fontFamily: "monospace", fontSize: "0.75rem" } }} sx={{ flex: 1 }} />
                <Typography variant="caption" color="text.disabled">→</Typography>
                <TextField size="small" label="To field" value={o.targetField}
                  onChange={(e) => updateOp(o.id, { targetField: e.target.value })}
                  inputProps={{ style: { fontFamily: "monospace", fontSize: "0.75rem" } }} sx={{ flex: 1 }} />
              </Stack>
            )}
            {o.op === "filter" && (
              <TextField size="small" fullWidth label="Keep rows where…"
                value={o.expression}
                placeholder='e.g. assertion != "negated"'
                onChange={(e) => updateOp(o.id, { expression: e.target.value })}
                inputProps={{ style: { fontFamily: "monospace", fontSize: "0.75rem" } }} />
            )}
            {o.op === "compute" && (
              <Stack spacing={1}>
                <TextField size="small" fullWidth label="New field name" value={o.targetField}
                  onChange={(e) => updateOp(o.id, { targetField: e.target.value })}
                  inputProps={{ style: { fontFamily: "monospace", fontSize: "0.75rem" } }} />
                <TextField size="small" fullWidth label="Expression" value={o.expression}
                  placeholder='e.g. f"{text} ({semantic_tag})"'
                  onChange={(e) => updateOp(o.id, { expression: e.target.value })}
                  inputProps={{ style: { fontFamily: "monospace", fontSize: "0.75rem" } }} />
              </Stack>
            )}
          </Paper>
        ))}
      </Stack>
      <Stack direction="row" spacing={1}>
        {(["compute", "filter", "rename"] as TransformOp[]).map((op) => (
          <Button key={op} size="small" variant="outlined" onClick={() => addOp(op)}
            sx={{ fontSize: "0.72rem", textTransform: "none" }}>
            + {op === "rename" ? "Rename" : op === "filter" ? "Filter" : "Compute"}
          </Button>
        ))}
      </Stack>
    </Stack>
  );
}

// ── Visual step-type palette — two-level: category cards → task cards ─────────

const CATEGORY_META: Record<string, { description: string; color: string }> = {
  "Clinical AI":  { description: "Use AI to read patient notes and extract clinical facts.",           color: "#4CAF50" },
  "Quality":      { description: "Verify and double-check results before they are saved.",              color: "#F44336" },
  "Data":         { description: "Save the final results to the right place.",                          color: "#607D8B" },
  "Reports":      { description: "Generate clinical summaries, timelines, and episode records.",        color: "#00BCD4" },
  "Safety":       { description: "Flag overdue actions and suggest the next best clinical step.",       color: "#FF5722" },
};

function StepTypePalette({
  selected,
  onSelect,
}: {
  selected: string;
  onSelect: (id: string) => void;
}) {
  const [search, setSearch] = useState("");

  // Group all steps by category (used for both levels)
  const allByCategory = useMemo(() => {
    const groups: Record<string, typeof SUBGRAPH_OPTIONS> = {};
    for (const s of SUBGRAPH_OPTIONS) {
      const cat = (s as typeof s & { category?: string }).category ?? "Other";
      if (!groups[cat]) groups[cat] = [];
      groups[cat].push(s);
    }
    return groups;
  }, []);

  // When a step is already selected, start drilled into its category
  const [browsedCategory, setBrowsedCategory] = useState<string | null>(() => {
    if (!selected) return null;
    const found = SUBGRAPH_OPTIONS.find((s) => s.id === selected);
    return (found as typeof found & { category?: string })?.category ?? null;
  });

  // ── Search mode — flat filtered list across all categories ──
  if (search.trim()) {
    const q = search.toLowerCase();
    const filtered = SUBGRAPH_OPTIONS.filter(
      (s) => s.label.toLowerCase().includes(q) || s.description.toLowerCase().includes(q)
    );
    return (
      <Stack spacing={1.5}>
        <TextField size="small" fullWidth placeholder="Search step types…" value={search}
          onChange={(e) => setSearch(e.target.value)}
          inputProps={{ style: { fontSize: "0.9rem" } }} />
        {filtered.length === 0 ? (
          <Typography variant="body2" color="text.secondary" sx={{ textAlign: "center", py: 3 }}>
            No step types match &ldquo;{search}&rdquo;
          </Typography>
        ) : (
          <Stack spacing={0.75}>
            {filtered.map((s) => <StepCard key={s.id} step={s} selected={selected} onSelect={onSelect} />)}
          </Stack>
        )}
      </Stack>
    );
  }

  // ── Drilled into a category — show task cards + back button ──
  if (browsedCategory) {
    const steps = allByCategory[browsedCategory] ?? [];
    const meta = CATEGORY_META[browsedCategory];
    return (
      <Stack spacing={1.5}>
        <TextField size="small" fullWidth placeholder="Search step types…" value={search}
          onChange={(e) => setSearch(e.target.value)}
          inputProps={{ style: { fontSize: "0.9rem" } }} />
        <Stack direction="row" alignItems="center" spacing={1}>
          <Button
            size="small"
            startIcon={<ArrowBackIcon />}
            onClick={() => setBrowsedCategory(null)}
            sx={{ textTransform: "none", fontSize: "0.85rem", color: "text.secondary", pl: 0, minWidth: 0 }}
          >
            All categories
          </Button>
          <Typography variant="body2" color="text.disabled">›</Typography>
          <Box sx={{ width: 10, height: 10, borderRadius: "50%", bgcolor: meta?.color ?? "grey.400", flexShrink: 0 }} />
          <Typography variant="body2" fontWeight={700}>{browsedCategory}</Typography>
        </Stack>
        <Stack spacing={0.75}>
          {steps.map((s) => <StepCard key={s.id} step={s} selected={selected} onSelect={onSelect} />)}
        </Stack>
      </Stack>
    );
  }

  // ── Top level — category cards grid ──
  return (
    <Stack spacing={1.5}>
      <TextField size="small" fullWidth placeholder="Search all step types…" value={search}
        onChange={(e) => setSearch(e.target.value)}
        inputProps={{ style: { fontSize: "0.9rem" } }} />
      <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 1.5 }}>
        {Object.entries(allByCategory).map(([cat, steps]) => {
          const meta = CATEGORY_META[cat];
          const catColor = meta?.color ?? steps[0]?.color ?? "#607D8B";
          const hasSelected = steps.some((s) => s.id === selected);
          return (
            <Paper
              key={cat}
              variant="outlined"
              onClick={() => setBrowsedCategory(cat)}
              sx={{
                p: 2,
                cursor: "pointer",
                borderRadius: 2,
                borderLeft: `5px solid ${catColor}`,
                borderColor: hasSelected ? catColor : "divider",
                borderWidth: hasSelected ? 2 : 1,
                bgcolor: hasSelected ? `${catColor}0e` : "background.paper",
                transition: "all 0.15s ease",
                "&:hover": { bgcolor: `${catColor}08`, borderColor: catColor },
              }}
            >
              <Typography variant="subtitle2" fontWeight={700} sx={{ mb: 0.5 }}>{cat}</Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5, fontSize: "0.82rem", lineHeight: 1.45 }}>
                {meta?.description ?? ""}
              </Typography>
              {/* Dot row showing each step in the category */}
              <Stack direction="row" spacing={0.75} alignItems="center" flexWrap="wrap" useFlexGap>
                {steps.map((s) => (
                  <Tooltip key={s.id} title={s.label} placement="top">
                    <Box sx={{
                      width: selected === s.id ? 12 : 9,
                      height: selected === s.id ? 12 : 9,
                      borderRadius: "50%",
                      bgcolor: s.color,
                      outline: selected === s.id ? `2px solid ${s.color}` : "none",
                      outlineOffset: 2,
                      transition: "all 0.15s ease",
                      flexShrink: 0,
                    }} />
                  </Tooltip>
                ))}
              </Stack>
              <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
                {steps.length} step type{steps.length !== 1 ? "s" : ""}
                {hasSelected && (
                  <Box component="span" sx={{ ml: 1, color: catColor, fontWeight: 700 }}>· selected</Box>
                )}
              </Typography>
            </Paper>
          );
        })}
      </Box>
    </Stack>
  );
}

function StepCard({
  step,
  selected,
  onSelect,
}: {
  step: typeof SUBGRAPH_OPTIONS[number];
  selected: string;
  onSelect: (id: string) => void;
}) {
  const isSelected = selected === step.id;
  return (
    <Paper
      variant="outlined"
      onClick={() => onSelect(step.id)}
      sx={{
        p: 1.75,
        cursor: "pointer",
        borderRadius: 2,
        borderLeft: `5px solid ${step.color}`,
        borderColor: isSelected ? step.color : "divider",
        borderWidth: isSelected ? 2 : 1,
        bgcolor: isSelected ? `${step.color}12` : "background.paper",
        transition: "all 0.15s ease",
        "&:hover": { bgcolor: `${step.color}08`, borderColor: step.color },
      }}
    >
      <Stack direction="row" alignItems="flex-start" spacing={1.25}>
        <Box sx={{ width: 10, height: 10, borderRadius: "50%", bgcolor: step.color, mt: "5px", flexShrink: 0 }} />
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography variant="body1" fontWeight={isSelected ? 700 : 500}>{step.label}</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ lineHeight: 1.45, display: "block", mt: 0.25 }}>
            {step.description}
          </Typography>
        </Box>
        {isSelected && (
          <Chip size="small" label="Selected ✓" color="primary" sx={{ height: 22, fontSize: "0.75rem", flexShrink: 0, mt: 0.25 }} />
        )}
      </Stack>
    </Paper>
  );
}

// ── Source node configurator ─────────────────────────────────────────────────

type SamplePreview = {
  nodeLabel: string;
  textProperty: string;
  properties: Record<string, unknown>;
};

function SourceConfiguratorContent({
  nodeId,
  nodeData,
  onUpdate,
  onClose,
  onRemove,
}: {
  nodeId: string;
  nodeData: Record<string, unknown>;
  onUpdate: (patch: Record<string, unknown>) => void;
  onClose: () => void;
  onRemove: () => void;
}) {
  const currentType: SourceType = (nodeData.sourceType as SourceType) ?? "encounter_text";
  const meta = SOURCE_DEFINITIONS[currentType];
  const nodeLabel = (nodeData.input_node_label as string) || "";
  const textProperty = (nodeData.input_text_property as string) || "text";
  const graph = currentType === "knowledge_graph" ? "knowledge" : "patient";

  const [preview, setPreview] = useState<SamplePreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  // ── PubSub-specific state ─────────────────────────────────────────────────
  const [pubsubSampleText, setPubsubSampleText] = useState(
    (nodeData.pubsub_sample_json as string) || "",
  );
  const [pubsubParseError, setPubsubParseError] = useState<string | null>(null);
  const [pubsubParsedFields, setPubsubParsedFields] = useState<string[]>([]);

  // Parse pubsub sample JSON whenever the text changes
  useEffect(() => {
    if (currentType !== "pubsub_subscribe" || !pubsubSampleText.trim()) {
      setPubsubParsedFields([]);
      setPubsubParseError(null);
      return;
    }
    try {
      const parsed = JSON.parse(pubsubSampleText);
      const keys = typeof parsed === "object" && parsed !== null ? Object.keys(parsed) : [];
      setPubsubParsedFields(keys);
      setPubsubParseError(null);
      // Auto-populate outputs from the parsed fields
      onUpdate({ outputs: keys, pubsub_sample_json: pubsubSampleText });
    } catch {
      setPubsubParseError("Not valid JSON — check the sample above");
      setPubsubParsedFields([]);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pubsubSampleText, currentType]);

  // Auto-fetch a sample record whenever node label or text property changes
  useEffect(() => {
    if (!nodeLabel || !["patient_graph", "knowledge_graph"].includes(currentType)) {
      setPreview(null);
      setPreviewError(null);
      return;
    }
    let cancelled = false;
    setPreviewLoading(true);
    setPreviewError(null);
    const params = new URLSearchParams({ node_label: nodeLabel, graph, text_property: textProperty });
    fetch(`/api/training/schema/sample-node?${params}`)
      .then(async (res) => {
        if (cancelled) return;
        if (res.status === 404) {
          setPreviewError("empty");
          setPreview(null);
        } else if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: res.statusText }));
          setPreviewError(err.detail ?? "Could not load sample");
          setPreview(null);
        } else {
          const data: SamplePreview = await res.json();
          setPreview(data);
          // Auto-populate outputs from actual record fields.
          // For graph sources the test runner aliases the text property → encounter_text
          // so replace the raw text field name with encounter_text in the declared outputs.
          const actualKeys = Object.keys(data.properties);
          const enrichedKeys = isGraphSource
            ? actualKeys.map((k) => (k === textProperty ? "encounter_text" : k))
            : actualKeys;
          onUpdate({ outputs: enrichedKeys });
        }
      })
      .catch((e) => { if (!cancelled) setPreviewError(e.message ?? "Network error"); })
      .finally(() => { if (!cancelled) setPreviewLoading(false); });
    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodeLabel, textProperty, graph, currentType]);

  // Auto-select the first record type when switching to a database source
  useEffect(() => {
    if (currentType === "patient_graph" && !nodeLabel) {
      onUpdate({ input_node_label: "EncounterCandidate", input_text_property: "text" });
    } else if (currentType === "knowledge_graph" && !nodeLabel) {
      onUpdate({ input_node_label: "TrainingCandidate", input_text_property: "text" });
    }
  // Only trigger when source type changes — not on every render
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentType]);

  const PATIENT_RECORD_TYPES = [
    { v: "EncounterCandidate", d: "Encounter text awaiting coding" },
    { v: "Encounter",          d: "Clinical encounter / consultation" },
    { v: "Patient",            d: "Patient root record" },
    { v: "ReviewTask",         d: "Human review task" },
    { v: "EpisodeOfCare",      d: "Grouped episode of care" },
    { v: "SafetyNetAlert",     d: "Overdue investigation alert" },
  ];
  const KNOWLEDGE_RECORD_TYPES = [
    { v: "TrainingCandidate", d: "De-identified text for gold labelling" },
    { v: "GoldLabel",         d: "Verified NER training label" },
    { v: "Concept",           d: "SNOMED CT concept" },
    { v: "CodingDecision",    d: "Recorded coding decision" },
    { v: "PromptConfig",      d: "AI prompt configuration" },
  ];
  const TEXT_FIELDS = [
    { v: "text",              d: "Main text / body" },
    { v: "raw_text",          d: "Unprocessed original text" },
    { v: "deidentified_text", d: "De-identified text" },
    { v: "content",           d: "Document content" },
  ];

  const isGraphSource   = currentType === "patient_graph" || currentType === "knowledge_graph";
  const isPubSubSource  = currentType === "pubsub_subscribe";

  return (
    <>
      <Box sx={{ px: 3, pt: 2.5, pb: 1, overflowY: "auto", maxHeight: "80vh" }}>
        <Typography variant="h6" fontWeight={700} gutterBottom>Data source</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          This node represents where data enters this pathway. Wire its outputs to any steps that need them.
        </Typography>

        {/* Source type picker */}
        <Stack spacing={1.5}>
          {(Object.entries(SOURCE_DEFINITIONS) as [SourceType, typeof SOURCE_DEFINITIONS[SourceType]][]).map(([type, m]) => (
            <Paper
              key={type}
              variant="outlined"
              onClick={() => onUpdate({ sourceType: type, label: m.label, outputs: m.outputs })}
              sx={{
                p: 1.5, cursor: "pointer", borderRadius: 2,
                borderColor: currentType === type ? m.color : "divider",
                borderWidth: currentType === type ? 2 : 1,
                bgcolor: currentType === type ? `${m.color}10` : "transparent",
              }}
            >
              <Typography variant="body2" fontWeight={currentType === type ? 700 : 500}>{m.label}</Typography>
              <Typography variant="caption" color="text.secondary">{m.description}</Typography>
              <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.25, fontFamily: "monospace" }}>
                outputs: {m.outputs.join(", ")}
              </Typography>
            </Paper>
          ))}
        </Stack>

        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 2 }}>
          <strong>Tip:</strong> Add one source node per data source, then wire it to multiple steps that all need the same data.
        </Typography>

        {/* ── PubSub subscribe configuration ──────────────────────────────── */}
        {isPubSubSource && (
          <Paper variant="outlined" sx={{ p: 2, mt: 2, borderRadius: 2 }}>
            <Typography variant="subtitle2" fontWeight={700} sx={{ mb: 0.5 }}>
              Which queue or topic?
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
              This pathway will start whenever a message arrives on the configured topic. Each field in the message becomes an output handle you can wire to your steps.
            </Typography>
            <Stack spacing={1.5}>
              <TextField
                size="small" fullWidth label="Topic name"
                placeholder="e.g. hl7v2.labs.results  or  nhs.clinical.events"
                value={(nodeData.pubsub_topic as string) || ""}
                onChange={(e) => onUpdate({ pubsub_topic: e.target.value })}
              />
              <TextField
                size="small" fullWidth label="Subscription ID (optional)"
                placeholder="e.g. sub-leo-processing"
                value={(nodeData.pubsub_subscription as string) || ""}
                onChange={(e) => onUpdate({ pubsub_subscription: e.target.value })}
              />

              <Box>
                <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                  Paste a sample message (JSON) to discover the fields it carries:
                </Typography>
                <TextField
                  size="small" fullWidth multiline minRows={4}
                  label="Sample message (JSON)"
                  placeholder={'{\n  "patient_id": "abc-123",\n  "encounter_id": "enc-456",\n  "payload": "...\"\n}'}
                  value={pubsubSampleText}
                  onChange={(e) => setPubsubSampleText(e.target.value)}
                  inputProps={{ style: { fontFamily: "monospace", fontSize: "0.78rem" } }}
                />
                {pubsubParseError && (
                  <Alert severity="warning" sx={{ mt: 0.75, fontSize: "0.75rem", py: 0.5 }}>
                    {pubsubParseError}
                  </Alert>
                )}
              </Box>

              {pubsubParsedFields.length > 0 && (
                <Box>
                  <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                    Tick the fields to expose as output handles on the canvas:
                  </Typography>
                  <Box sx={{ borderRadius: 1.5, border: "1px solid", borderColor: "divider", overflow: "hidden" }}>
                    {pubsubParsedFields.map((key, idx) => {
                      const currentOutputs: string[] = (nodeData.outputs as string[]) ?? [];
                      const isChecked = currentOutputs.includes(key);
                      return (
                        <Box
                          key={key}
                          sx={{
                            display: "flex", alignItems: "center", gap: 1,
                            px: 1, py: 0.5,
                            bgcolor: idx % 2 === 0 ? "grey.50" : "background.paper",
                            borderBottom: "1px solid", borderColor: "divider",
                            "&:last-child": { borderBottom: 0 },
                          }}
                        >
                          <Checkbox
                            size="small" checked={isChecked}
                            onChange={(e) => {
                              const updated = e.target.checked
                                ? [...currentOutputs, key]
                                : currentOutputs.filter((k) => k !== key);
                              onUpdate({ outputs: updated });
                            }}
                            sx={{ p: 0.25, flexShrink: 0 }}
                          />
                          <Typography variant="caption" sx={{ fontFamily: "monospace", fontSize: "0.7rem", color: "text.secondary" }}>
                            {key}
                          </Typography>
                        </Box>
                      );
                    })}
                  </Box>
                </Box>
              )}
            </Stack>
          </Paper>
        )}

        {/* Graph picker + live record preview */}
        {isGraphSource && (
          <Paper variant="outlined" sx={{ p: 2, mt: 2, borderRadius: 2 }}>
            <Typography variant="subtitle2" fontWeight={700} sx={{ mb: 0.5 }}>
              {currentType === "patient_graph" ? "Which patient records?" : "Which knowledge records?"}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
              Choose the type of record to read, and which field holds the text.
            </Typography>
            <Stack spacing={1.5}>
              <FormControl fullWidth size="small">
                <InputLabel>Record type</InputLabel>
                <Select
                  value={nodeLabel}
                  label="Record type"
                  onChange={(e) => onUpdate({ input_node_label: e.target.value })}
                >
                  {(currentType === "patient_graph" ? PATIENT_RECORD_TYPES : KNOWLEDGE_RECORD_TYPES).map(({ v, d }) => (
                    <MenuItem key={v} value={v}>
                      <Typography variant="body2">{d}</Typography>
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>

              <FormControl fullWidth size="small">
                <InputLabel>Text field</InputLabel>
                <Select
                  value={textProperty}
                  label="Text field"
                  onChange={(e) => onUpdate({ input_text_property: e.target.value })}
                >
                  {TEXT_FIELDS.map(({ v, d }) => (
                    <MenuItem key={v} value={v}>
                      <Typography variant="body2">{d}</Typography>
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>

              <Stack direction="row" spacing={1}>
                <TextField
                  size="small" label="Filter field (optional)" sx={{ flex: 1 }}
                  placeholder="e.g. status"
                  value={(nodeData.input_filter_property as string) || ""}
                  onChange={(e) => onUpdate({ input_filter_property: e.target.value })}
                />
                <TextField
                  size="small" label="= Value" sx={{ flex: 1 }}
                  placeholder="e.g. pending"
                  value={(nodeData.input_filter_value as string) || ""}
                  onChange={(e) => onUpdate({ input_filter_value: e.target.value })}
                />
              </Stack>
            </Stack>

            {/* ── Record preview ───────────────────────────────────────────── */}
            <Box sx={{ mt: 2 }}>
              <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", mb: 0.75 }}>
                <Typography variant="subtitle2" fontWeight={700}>
                  Sample record preview
                </Typography>
                {previewLoading && <CircularProgress size={14} />}
              </Box>

              {previewError && (
                <Alert severity={previewError === "empty" ? "info" : "warning"} sx={{ fontSize: "0.78rem", borderRadius: 1.5 }}>
                  {previewError === "empty"
                    ? `No sample ${nodeLabel} records available to preview right now — your field choices will still work correctly.`
                    : previewError}
                </Alert>
              )}

              {!previewLoading && !previewError && preview && (
                <>
                  <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.75 }}>
                    Tick the fields you want to expose as output handles on the canvas.
                  </Typography>
                  <Box sx={{ borderRadius: 1.5, border: "1px solid", borderColor: "divider", overflow: "hidden" }}>
                    {Object.entries(preview.properties).map(([key, value], idx) => {
                      const isTextProp = key === preview.textProperty;
                      const strVal = value === null || value === undefined ? "—" : String(value);
                      const currentOutputs: string[] = (nodeData.outputs as string[]) ?? [];
                      const isChecked = currentOutputs.includes(key);
                      return (
                        <Box
                          key={key}
                          sx={{
                            display: "flex",
                            alignItems: "flex-start",
                            gap: 1,
                            px: 1,
                            py: 0.5,
                            bgcolor: isTextProp ? `${meta.color}10` : idx % 2 === 0 ? "grey.50" : "background.paper",
                            borderBottom: "1px solid",
                            borderColor: "divider",
                            "&:last-child": { borderBottom: 0 },
                          }}
                        >
                          <Checkbox
                            size="small"
                            checked={isChecked}
                            onChange={(e) => {
                              const updated = e.target.checked
                                ? [...currentOutputs, key]
                                : currentOutputs.filter((k) => k !== key);
                              onUpdate({ outputs: updated });
                            }}
                            sx={{ p: 0.25, mt: 0.25, flexShrink: 0 }}
                          />
                          <Box sx={{ flex: "0 0 130px", display: "flex", alignItems: "center", gap: 0.5, pt: 0.25 }}>
                            <Typography
                              variant="caption"
                              sx={{ fontFamily: "monospace", fontSize: "0.7rem", color: isTextProp ? meta.color : "text.secondary", fontWeight: isTextProp ? 700 : 400 }}
                            >
                              {key}
                            </Typography>
                            {isTextProp && (
                              <Chip label="text" size="small" sx={{ height: 14, fontSize: "0.58rem", bgcolor: meta.color, color: "#fff" }} />
                            )}
                          </Box>
                          <Typography
                            variant="caption"
                            sx={{
                              flex: 1,
                              fontSize: "0.72rem",
                              color: "text.primary",
                              wordBreak: "break-word",
                              lineHeight: 1.5,
                              fontStyle: strVal === "—" ? "italic" : "normal",
                            }}
                          >
                            {strVal}
                          </Typography>
                        </Box>
                      );
                    })}
                  </Box>
                </>
              )}

              {!previewLoading && !previewError && !preview && nodeLabel && (
                <Typography variant="caption" color="text.disabled" sx={{ display: "block", mt: 0.5 }}>
                  Loading preview…
                </Typography>
              )}
            </Box>
          </Paper>
        )}
      </Box>

      <Box sx={{ px: 3, pb: 2.5, pt: 1.5, display: "flex", justifyContent: "space-between", alignItems: "center", borderTop: 1, borderColor: "divider" }}>
        <Button size="small" color="error" onClick={onRemove} sx={{ textTransform: "none" }}>
          Remove source node
        </Button>
        <Button variant="contained" onClick={onClose} sx={{ textTransform: "none" }}>
          Done
        </Button>
      </Box>
    </>
  );
  // suppress unused nodeId warning — kept for future use
  void nodeId;
}

// ── Step configurator ─────────────────────────────────────────────────────────

function ActionConfigurator({
  nodeId, initialConfig, onSave, onDelete, onClose, onPathwaySave, prevStepWrites, prevStepFieldMappings, prevStepSources, inboundConnections,
}: {
  nodeId: string;
  initialConfig: ActionConfig;
  onSave: (nodeId: string, config: ActionConfig) => void;
  onDelete: (nodeId: string) => void;
  onClose: () => void;
  onPathwaySave: () => Promise<void>;
  prevStepWrites: string[] | null;
  prevStepFieldMappings: FieldMappingRow[] | null;
  prevStepSources: Array<{ label: string; keys: string[] }>;
  inboundConnections: Array<{ sourceLabel: string; sourceHandle: string; targetHandle: string }>;
}) {
  const [step, setStep] = useState(0);
  const [config, setConfig] = useState<ActionConfig>({ ...DEFAULT_CONFIG, ...initialConfig, params: initialConfig.params ?? {} });
  const [presetSupportsTemp, setPresetSupportsTemp] = useState<boolean>(true);
  const isNerOnlyPreset = !presetSupportsTemp;
  // "idle" | "saving" | "saved" | "error"
  const [autoSave, setAutoSave] = useState<"idle" | "saving" | "saved" | "error">("idle");
  // Pending subgraph change — shown in confirmation dialog before wiping config
  const [pendingSubgraphId, setPendingSubgraphId] = useState<string | null>(null);
  // Track which steps the user has visited (enables non-linear navigation)
  const [visitedSteps, setVisitedSteps] = useState<Set<number>>(new Set([0]));
  // Show a banner when temperature support changes due to preset selection
  const [tempSupportChanged, setTempSupportChanged] = useState<boolean | null>(null);

  // Fire a non-blocking draft save to the server (called on each Next click).
  const backgroundSave = useCallback((latestConfig: ActionConfig) => {
    onSave(nodeId, latestConfig);   // sync local state first
    setAutoSave("saving");
    // Let React flush parent node/config state before serializing payload.
    Promise.resolve()
      .then(() => new Promise<void>((resolve) => setTimeout(resolve, 0)))
      .then(() => onPathwaySave())
      .then(() => {
        setAutoSave("saved");
        setTimeout(() => setAutoSave("idle"), 2500);
      })
      .catch(() => {
        setAutoSave("error");
        setTimeout(() => setAutoSave("idle"), 3500);
      });
  }, [nodeId, onSave, onPathwaySave]);

  const category: SubgraphCategory = SUBGRAPH_CATEGORY[config.subgraphId] ?? "generic";
  const isLLM = category === "llm";
  const wizardSteps = isLLM ? WIZARD_STEPS_LLM : WIZARD_STEPS_NO_LLM;
  const lastStep = wizardSteps.length - 1;
  const subgraph = SUBGRAPH_OPTIONS.find((s) => s.id === config.subgraphId);

  const updateField = <K extends keyof ActionConfig>(key: K, value: ActionConfig[K]) =>
    setConfig((prev) => ({ ...prev, [key]: value }));

  const updateParam = (key: string, value: unknown) =>
    setConfig((prev) => ({ ...prev, params: { ...prev.params, [key]: value } }));

  // Keep canvas handles in sync while editing (field mappings / branches / node type),
  // without waiting for "Save step". Server persistence still happens on Next/Save.
  useEffect(() => {
    onSave(nodeId, config);
  }, [onSave, nodeId, config]);

  // Field mappings are high-impact for canvas ports; update local config and
  // let the post-render effect propagate to parent state safely.
  const setFieldMappings = useCallback((rows: FieldMappingRow[]) => {
    setConfig((prev) => ({
      ...prev,
      params: { ...prev.params, field_mappings: rows },
    }));
  }, []);

  const applySubgraphChange = (id: string) => {
    const opt = SUBGRAPH_OPTIONS.find((s) => s.id === id);
    setConfig((prev) => ({
      ...DEFAULT_CONFIG,
      subgraphId: id,
      label: prev.label || opt?.label || "",
      description: prev.description || opt?.description || "",
      params: {},
    }));
  };

  const handleSubgraphChange = (id: string) => {
    if (id === config.subgraphId) return;
    // If there's meaningful config already, ask before wiping it
    const hasMeaningfulConfig = Boolean(
      config.promptConfigId || config.modelPresetId ||
      Object.keys(config.params).length > 0 ||
      config.inputSource !== "previous_step"
    );
    if (hasMeaningfulConfig && config.subgraphId) {
      setPendingSubgraphId(id);
    } else {
      applySubgraphChange(id);
    }
  };

  const confirmSubgraphChange = () => {
    if (pendingSubgraphId) {
      applySubgraphChange(pendingSubgraphId);
      setPendingSubgraphId(null);
    }
  };

  // step indices shift when non-LLM (no Prompt step)
  // LLM:    0=Subgraph  1=DataFlow  2=Settings  3=Prompt  4=Review
  // No-LLM: 0=Subgraph  1=DataFlow  2=Settings  3=Review

  const reviewStep = isLLM ? 4 : 3;
  const promptStep = 3; // only exists in LLM mode

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>

      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <Box sx={{
        px: 4, pt: 2.5, pb: 2, flexShrink: 0,
        borderBottom: 1, borderColor: "divider",
        bgcolor: subgraph ? `${subgraph.color}0d` : "grey.50",
        borderLeft: "4px solid",
        borderLeftColor: subgraph?.color || "primary.main",
      }}>
        <Stack direction="row" alignItems="flex-start" spacing={1}>
          <Box sx={{ flex: 1 }}>
            <Typography sx={{ fontSize: "0.6rem", fontWeight: 700, letterSpacing: 1.4, color: "text.disabled", textTransform: "uppercase", lineHeight: 1 }}>
              Pipeline Step
            </Typography>
            <Typography variant="h6" fontWeight={700} sx={{ mt: 0.4, lineHeight: 1.2 }}>Configure step</Typography>
          </Box>
          {/* Auto-save status indicator */}
          {autoSave !== "idle" && (
            <Stack direction="row" alignItems="center" spacing={0.5} sx={{ mt: 0.75 }}>
              {autoSave === "saving" && <CircularProgress size={10} thickness={5} />}
              <Typography sx={{
                fontSize: "0.62rem",
                color: autoSave === "error" ? "error.main" : autoSave === "saving" ? "text.disabled" : "success.main",
              }}>
                {autoSave === "saving" ? "Saving…" : autoSave === "saved" ? "Draft saved ✓" : "Save failed"}
              </Typography>
            </Stack>
          )}
          <IconButton size="small" onClick={onClose} sx={{ color: "text.secondary", mt: -0.5, mr: -0.75 }}>
            <CloseIcon sx={{ fontSize: "1.1rem" }} />
          </IconButton>
        </Stack>
        {subgraph && (
          <Chip
            size="small"
            label={subgraph.label}
            sx={{ mt: 1.25, bgcolor: subgraph.color, color: "#fff", fontSize: "0.68rem", fontWeight: 600, height: 22, borderRadius: "6px" }}
          />
        )}
      </Box>

      {/* ── Step progress indicator (circles are clickable for visited steps) ── */}
      <Box sx={{ px: 4, pt: 2.25, pb: 1.5, flexShrink: 0, bgcolor: "background.paper" }}>
        <Box sx={{ display: "flex", alignItems: "flex-start" }}>
          {wizardSteps.map((label, idx) => {
            const isVisited = visitedSteps.has(idx);
            const isActive = idx === step;
            const isClickable = isVisited && !isActive;
            return (
              <Fragment key={label}>
                <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", flexShrink: 0 }}>
                  <Box
                    onClick={() => isClickable && setStep(idx)}
                    sx={{
                      width: 28, height: 28, borderRadius: "50%",
                      display: "flex", alignItems: "center", justifyContent: "center",
                      bgcolor: idx < step ? "primary.main" : isActive ? "primary.main" : "grey.100",
                      color: idx <= step ? "#fff" : "text.disabled",
                      fontSize: "0.7rem", fontWeight: 700,
                      border: "2px solid",
                      borderColor: idx <= step ? "primary.main" : "grey.200",
                      boxShadow: isActive ? "0 0 0 4px rgba(25,118,210,0.12)" : "none",
                      transition: "all 0.25s ease",
                      cursor: isClickable ? "pointer" : "default",
                      "&:hover": isClickable ? { opacity: 0.8, boxShadow: "0 0 0 3px rgba(25,118,210,0.2)" } : {},
                    }}
                  >
                    {idx < step ? "✓" : idx + 1}
                  </Box>
                  <Typography sx={{
                    mt: 0.75, fontSize: "0.59rem", textAlign: "center", lineHeight: 1.3,
                    color: isActive ? "primary.main" : idx < step ? "text.secondary" : "text.disabled",
                    fontWeight: isActive ? 700 : 400,
                    cursor: isClickable ? "pointer" : "default",
                  }}
                    onClick={() => isClickable && setStep(idx)}
                  >
                    {label}
                  </Typography>
                </Box>
                {idx < wizardSteps.length - 1 && (
                  <Box sx={{
                    flex: 1, height: 2, mt: "13px", mx: 0.75,
                    bgcolor: idx < step ? "primary.main" : "grey.200",
                    borderRadius: 1, transition: "background-color 0.25s ease",
                  }} />
                )}
              </Fragment>
            );
          })}
        </Box>
      </Box>

      <Box sx={{ flex: 1, overflowY: "auto", px: 4, py: 3 }}>

        {/* ── Step 0: Step type picker (visual card palette) ── */}
        {step === 0 && (
          <Stack direction="row" spacing={3} sx={{ height: "100%", alignItems: "flex-start" }}>

            {/* Left column — name and description */}
            <Box sx={{ flex: "0 0 340px", display: "flex", flexDirection: "column", gap: 2 }}>
              <Paper variant="outlined" sx={{ p: 2.5, borderRadius: 2 }}>
                <Typography variant="subtitle2" fontWeight={700} sx={{ mb: 0.5 }}>Name this step</Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 2.5 }}>
                  Give this step a short name so you can spot it on the canvas, and say in plain English what it does.
                </Typography>
                <Stack spacing={2.5}>
                  <TextField
                    label="Step name"
                    size="small"
                    fullWidth
                    value={config.label}
                    onChange={(e) => updateField("label", e.target.value)}
                    helperText="Shown on the canvas block."
                  />
                  <TextField
                    label="What does this step do?"
                    size="small"
                    fullWidth
                    multiline
                    minRows={4}
                    value={config.description}
                    onChange={(e) => updateField("description", e.target.value)}
                    helperText="Plain English — shown in the pathway summary."
                  />
                </Stack>
              </Paper>
            </Box>

            {/* Right column — step type palette */}
            <Box sx={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 1.5 }}>
              <Box>
                <Typography variant="subtitle2" fontWeight={700} sx={{ mb: 0.5 }}>Choose the step type</Typography>
                <Typography variant="body2" color="text.secondary">
                  Pick the kind of task this step carries out. Tap a card to select it.
                </Typography>
              </Box>
              <StepTypePalette selected={config.subgraphId} onSelect={handleSubgraphChange} />
            </Box>

          </Stack>
        )}

        {/* ── Step 1: Data flow ── */}
        {step === 1 && (
          <Stack direction="row" spacing={3} sx={{ alignItems: "flex-start" }}>

            {/* Left column — configurable controls */}
            <Box sx={{ flex: "0 0 340px", display: "flex", flexDirection: "column", gap: 2 }}>

              {/* Canvas connections card — shows which source / upstream nodes are wired in */}
              <Paper variant="outlined" sx={{ p: 2.5, borderRadius: 2 }}>
                <Typography variant="subtitle2" fontWeight={700} sx={{ mb: 0.5 }}>How data arrives</Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                  Data flows into this step from nodes wired to it on the canvas. Use the <strong>Add a data source</strong> button on the toolbar to add a source node, then drag a wire from it to this step.
                </Typography>
                {prevStepSources.length > 0 ? (
                  <Stack spacing={1.5}>
                    {prevStepSources.map((src) => (
                      <Box key={src.label}>
                        <Stack direction="row" alignItems="center" spacing={0.75} sx={{ mb: 0.75 }}>
                          <Box sx={{ width: 8, height: 8, borderRadius: "50%", bgcolor: "success.main", flexShrink: 0 }} />
                          <Typography variant="caption" fontWeight={700} color="success.dark">
                            {src.label}
                          </Typography>
                        </Stack>
                        <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5, pl: 2 }}>
                          {src.keys.map((k) => (
                            <Chip key={k} label={k} size="small" variant="outlined"
                              sx={{ fontFamily: "monospace", fontSize: "0.72rem", height: 22, color: "success.main", borderColor: "success.light" }} />
                          ))}
                        </Box>
                      </Box>
                    ))}
                    {inboundConnections.length > 0 && (
                      <Box sx={{ pl: 2 }}>
                        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                          Wired ports
                        </Typography>
                        <Stack spacing={0.5}>
                          {inboundConnections.map((conn, idx) => (
                            <Typography key={`${conn.sourceLabel}-${idx}`} variant="caption" sx={{ fontFamily: "monospace", color: "text.secondary" }}>
                              {`${conn.sourceLabel}.${conn.sourceHandle} -> this.${conn.targetHandle}`}
                            </Typography>
                          ))}
                        </Stack>
                      </Box>
                    )}
                  </Stack>
                ) : (
                  <Alert severity="info" icon={false} sx={{ fontSize: "0.8rem", borderRadius: 1.5 }}>
                    No nodes connected yet. Close this window, wire a data source or previous step to this node on the canvas, then come back here.
                  </Alert>
                )}
              </Paper>

              {/* Failure handling card */}
              <Paper variant="outlined" sx={{ p: 2.5, borderRadius: 2 }}>
                <Typography variant="subtitle2" fontWeight={700} sx={{ mb: 0.5 }}>If something goes wrong</Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                  How many times should this step try again before giving up?
                </Typography>
                <FormControl fullWidth size="small">
                  <InputLabel>Retries on failure</InputLabel>
                  <Select value={String(config.maxRetries)} label="Retries on failure"
                    onChange={(e) => updateField("maxRetries", Number(e.target.value))}>
                    {[0, 1, 2, 3, 5].map((n) => (
                      <MenuItem key={n} value={String(n)}>
                        {n === 0 ? "Don't retry — fail straight away" : `Try again ${n} time${n > 1 ? "s" : ""}`}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
              </Paper>

            </Box>

            {/* Right column — data flow panel (informational) */}
            <Box sx={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 2 }}>
              <Box>
                <Typography variant="subtitle2" fontWeight={700} sx={{ mb: 0.5 }}>Data flow</Typography>
                <Typography variant="body2" color="text.secondary">
                  What this step needs from the pipeline, and what it sends on when it finishes.
                </Typography>
              </Box>
              <DataFlowPanel
                subgraphId={config.subgraphId}
                prevStepWrites={prevStepWrites}
                prevStepFieldMappings={prevStepFieldMappings}
              />
            </Box>

          </Stack>
        )}

        {/* ── Step 2: Per-subgraph settings ── */}
        {step === 2 && (config.nodeType === "parallel" || config.nodeType === "merge") && (
          <BranchConfigPanel
            nodeType={config.nodeType}
            branches={(config.params.branches as string[]) ?? ["branch_a", "branch_b"]}
            onBranchesChange={(branches) => updateParam("branches", branches)}
          />
        )}
        {step === 2 && config.nodeType === "transform" && (
          <TransformConfigPanel
            operations={(config.params.operations as TransformOperation[]) ?? []}
            onOperationsChange={(ops) => updateParam("operations", ops)}
          />
        )}
        {step === 2 && config.nodeType !== "parallel" && config.nodeType !== "merge" && config.nodeType !== "transform" && (
          <Stack spacing={2.5}>
            <SubgraphSettingsPanel
              category={category}
              config={config}
              updateField={updateField}
              updateParam={updateParam}
              onPresetSelected={(preset) => {
                const supportsTemp = preset?.supports_temperature ?? true;
                if (preset && supportsTemp !== presetSupportsTemp) {
                  setTempSupportChanged(supportsTemp);
                  setTimeout(() => setTempSupportChanged(null), 5000);
                }
                setPresetSupportsTemp(supportsTemp);
              }}
            />
            <Divider />
            <Box>
              <Typography variant="subtitle2" fontWeight={700} sx={{ mb: 0.5 }}>Advanced options</Typography>
              <Typography variant="caption" color="text.secondary">
                These settings apply to all step types.
              </Typography>
            </Box>
            <FormControl fullWidth size="small">
              <InputLabel>Step timeout</InputLabel>
              <Select
                value={String(config.timeout ?? 120)}
                label="Step timeout"
                onChange={(e) => updateField("timeout", Number(e.target.value))}
              >
                {[30, 60, 120, 300, 600].map((n) => (
                  <MenuItem key={n} value={String(n)}>{n < 60 ? `${n} seconds` : `${n / 60} minute${n / 60 > 1 ? "s" : ""}`}</MenuItem>
                ))}
              </Select>
            </FormControl>
            {category === "llm" && (
              <FormControlLabel
                control={
                  <Switch
                    checked={config.enableVerification}
                    onChange={(e) => updateField("enableVerification", e.target.checked)}
                    size="small"
                  />
                }
                label={
                  <Box>
                    <Typography variant="body2">Enable verification gate</Typography>
                    <Typography variant="caption" color="text.secondary" display="block">
                      Halt the pipeline if AI confidence is too low — sends for human review instead of proceeding.
                    </Typography>
                  </Box>
                }
              />
            )}
          </Stack>
        )}

        {/* ── Step 3 (LLM only): Prompt & model ── */}
        {isLLM && step === promptStep && (
          <Stack direction="row" spacing={3} sx={{ alignItems: "flex-start" }}>

            {/* Left column — AI instructions + temperature */}
            <Box sx={{ flex: "0 0 340px", display: "flex", flexDirection: "column", gap: 2.5 }}>
              {tempSupportChanged !== null && (
                <Alert severity="info" sx={{ fontSize: "0.8rem" }} icon={false}>
                  {tempSupportChanged
                    ? "Temperature slider is now visible — this model supports it."
                    : "Temperature slider hidden — this model does not support it."}
                </Alert>
              )}
              <Paper variant="outlined" sx={{ p: 2.5, borderRadius: 2 }}>
                <Typography variant="subtitle2" fontWeight={700} sx={{ mb: 0.5 }}>AI instructions</Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                  Choose which set of AI instructions this step follows.
                </Typography>
                <PromptPicker
                  value={config.promptConfigId}
                  onChange={(id, name) => { updateField("promptConfigId", id); updateField("promptConfigName", name); }}
                />
                {config.promptConfigId && (
                  <Typography variant="body2" color="text.secondary" sx={{ mt: 1.5 }}>
                    <Typography component="a" href="/admin/knowledge?tab=ai-instructions" variant="body2" color="primary"
                      sx={{ textDecoration: "underline" }}>
                      Open in Prompt Tuner
                    </Typography>{" "}to edit the instructions, output schema, or teaching examples.
                  </Typography>
                )}
              </Paper>

              {/* Temperature */}
              {!isNerOnlyPreset ? (
                <Paper variant="outlined" sx={{ p: 2.5, borderRadius: 2 }}>
                  <Typography variant="subtitle2" fontWeight={700} sx={{ mb: 0.5 }}>Temperature</Typography>
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                    Keep at <strong>0.0</strong> for clinical work — the AI always gives the same answer.
                    Higher values make it more creative but less predictable.
                  </Typography>
                  <Typography variant="body2" gutterBottom>
                    Current: <strong>{config.temperature.toFixed(1)}</strong>
                    {config.temperature === 0 && " — deterministic (recommended)"}
                    {config.temperature > 0.5 && " — creative (not recommended for clinical tasks)"}
                  </Typography>
                  <Box component="input" type="range" min={0} max={1} step={0.1}
                    value={config.temperature}
                    onChange={(e) => updateField("temperature", Number(e.currentTarget.value))}
                    style={{ width: "100%" }} />
                  <Stack direction="row" justifyContent="space-between" sx={{ mt: 0.5 }}>
                    <Typography variant="caption" color="text.secondary">0.0 — always the same</Typography>
                    <Typography variant="caption" color="text.secondary">1.0 — varied / creative</Typography>
                  </Stack>
                </Paper>
              ) : (
                <Alert severity="info" sx={{ fontSize: "0.8rem" }} icon={false}>
                  Temperature is not used by this model preset. To change it, go to <strong>AI Models → Edit preset</strong>.
                </Alert>
              )}
            </Box>

            {/* Right column — output groups + field mapping */}
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Box sx={{ mb: 1.5 }}>
                <Typography variant="subtitle2" fontWeight={700} sx={{ mb: 0.5 }}>Name the AI outputs</Typography>
                <Typography variant="body2" color="text.secondary">
                  Tell the pipeline what to call each thing the AI finds, and which canvas connection point it belongs to.
                </Typography>
              </Box>
              {config.promptConfigId ? (
                <SchemaAlignmentPanel
                  subgraphId={config.subgraphId}
                  promptConfigId={config.promptConfigId}
                  fieldMappings={(config.params.field_mappings as FieldMappingRow[]) ?? []}
                  onFieldMappingsChange={setFieldMappings}
                  prevStepFieldMappings={prevStepFieldMappings}
                />
              ) : (
                <Paper variant="outlined" sx={{ p: 3, borderRadius: 2, textAlign: "center" }}>
                  <Typography variant="body2" color="text.secondary">
                    Select AI instructions on the left to configure outputs.
                  </Typography>
                </Paper>
              )}
            </Box>

          </Stack>
        )}

        {/* ── Review step ── */}
        {step === reviewStep && (
          <Stack direction="row" spacing={3} sx={{ alignItems: "flex-start" }}>

            {/* Left — configuration summary */}
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Typography variant="subtitle2" fontWeight={700} sx={{ mb: 1.5 }}>Configuration summary</Typography>
              <Paper variant="outlined" sx={{ p: 2.5, borderRadius: 2 }}>
                <Stack spacing={1.25}>
                  <ReviewRow label="Step type" value={subgraph?.label || config.subgraphId} />
                  <ReviewRow label="Display name" value={config.label} />
                  <Divider />
                  <ReviewRow
                    label="Data connections"
                    value={prevStepWrites && prevStepWrites.length > 0
                      ? prevStepWrites.join(", ")
                      : "No nodes connected yet"}
                  />
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
            </Box>

            {/* Right — issues and guidance */}
            <Box sx={{ flex: "0 0 320px", display: "flex", flexDirection: "column", gap: 2 }}>
              <Typography variant="subtitle2" fontWeight={700}>Checks</Typography>
              {isLLM && !config.promptConfigId && (
                <Alert severity="warning" sx={{ fontSize: "0.82rem" }}>
                  No prompt selected. This step will use the system default instructions.
                  Go back to <strong>AI &amp; outputs</strong> to choose one.
                </Alert>
              )}
              {(() => {
                const io = SUBGRAPH_IO[config.subgraphId];
                if (!io || !prevStepWrites) return null;
                const provided = new Set(prevStepWrites);
                const missing = io.reads.filter((k) => !provided.has(k));
                if (missing.length === 0) return null;
                return (
                  <Alert severity="error" sx={{ fontSize: "0.82rem" }}>
                    <Typography variant="body2" fontWeight={700} display="block" gutterBottom>
                      Data mismatch — step may fail
                    </Typography>
                    <Typography variant="body2">
                      This step needs{" "}
                      {missing.map((k) => (
                        <Box key={k} component="span" sx={{ fontFamily: "monospace", bgcolor: "error.50", px: 0.5, borderRadius: 0.5, mr: 0.5 }}>{k}</Box>
                      ))}
                      but the connected nodes do not produce {missing.length > 1 ? "them" : "it"}.
                      Close this window and wire the correct data source or step to this one on the canvas.
                    </Typography>
                  </Alert>
                );
              })()}
              {!isLLM || config.promptConfigId ? (
                <Alert severity="success" sx={{ fontSize: "0.82rem" }}>
                  Looking good — tap <strong>Save step</strong> to apply this configuration.
                </Alert>
              ) : null}
            </Box>

          </Stack>
        )}
      </Box>

      {/* ── Footer ─────────────────────────────────────────────────────────── */}
      <Box sx={{ px: 4, py: 2, borderTop: 1, borderColor: "divider", bgcolor: "grey.50", flexShrink: 0 }}>
        <Stack direction="row" justifyContent="space-between" alignItems="center">
          <Tooltip title="Remove this step from the pathway">
            <IconButton
              color="error"
              size="small"
              onClick={() => { onDelete(nodeId); onClose(); }}
              sx={{ border: "1px solid", borderColor: "error.200", borderRadius: 1.5, "&:hover": { bgcolor: "error.50" } }}
            >
              <DeleteOutlineIcon sx={{ fontSize: "1.15rem" }} />
            </IconButton>
          </Tooltip>
          <Stack direction="row" spacing={1} alignItems="center">
            {step > 0 && (
              <Button
                variant="outlined"
                size="small"
                onClick={() => setStep((s) => s - 1)}
                sx={{ textTransform: "none", minWidth: 80, borderRadius: 2 }}
              >
                Back
              </Button>
            )}
            {step < lastStep ? (
              <Button
                variant="contained"
                size="small"
                disabled={step === 0 && (!config.subgraphId || !config.label)}
                onClick={() => {
                  backgroundSave(config);
                  setStep((s) => {
                    const next = s + 1;
                    setVisitedSteps((v) => new Set([...v, next]));
                    return next;
                  });
                }}
                sx={{ textTransform: "none", minWidth: 80, borderRadius: 2, px: 3 }}
              >
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

      {/* ── Step type change confirmation dialog ── */}
      <Dialog open={Boolean(pendingSubgraphId)} onClose={() => setPendingSubgraphId(null)} maxWidth="xs" fullWidth
        PaperProps={{ sx: { borderRadius: 3 } }}>
        <Box sx={{ px: 3, pt: 2.5, pb: 1 }}>
          <Typography variant="h6" fontWeight={700} gutterBottom>Change step type?</Typography>
          <Typography variant="body2" color="text.secondary">
            Changing the step type will reset all current settings — your prompt, model, and field mappings will be cleared. This cannot be undone.
          </Typography>
        </Box>
        <Box sx={{ px: 3, pb: 2.5, pt: 1.5, display: "flex", justifyContent: "flex-end", gap: 1 }}>
          <Button onClick={() => setPendingSubgraphId(null)} sx={{ textTransform: "none" }}>Keep current</Button>
          <Button variant="contained" color="warning" onClick={confirmSubgraphChange} sx={{ textTransform: "none" }}>
            Yes, change type
          </Button>
        </Box>
      </Dialog>
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
      // Ensure parent state is committed before pathway serialization.
      await new Promise<void>((resolve) => setTimeout(resolve, 0));
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
        <Button size="small" variant="contained" color="error" onClick={handleClick}
          sx={{ textTransform: "none", minWidth: 100, borderRadius: 2, px: 3 }}>
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
      sx={{ textTransform: "none", minWidth: 100, borderRadius: 2, px: 3 }}
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

    // Build a full transitive-ancestor write set for each node via BFS.
    // Includes outputs from source nodes (fan-in data sources) and action nodes.
    function getAllAncestorWrites(startId: string): Set<string> {
      const result = new Set<string>([...GLOBAL_KEYS]);
      const visited = new Set<string>();
      const queue = [startId];
      while (queue.length) {
        const id = queue.shift()!;
        if (visited.has(id)) continue;
        visited.add(id);
        for (const edge of edges) {
          if (edge.target === id) {
            const predNode = nodes.find((n) => n.id === edge.source);
            // Source nodes inject their declared outputs into the available key set
            if (predNode?.type === "source") {
              const srcOutputs = (predNode.data as { outputs?: string[] }).outputs ?? [];
              srcOutputs.forEach((k) => result.add(k));
            }
            const predSubId = (predNode?.data as unknown as ActionNodeData | undefined)?.subgraphId;
            if (predSubId) SUBGRAPH_IO[predSubId]?.writes.forEach((w) => result.add(w));
            queue.push(edge.source);
          }
        }
      }
      return result;
    }

    // Edge-aware key alignment: for each action node, check that every key it reads
    // is either a global key or produced by any upstream ancestor (full DAG traversal).
    // Source nodes themselves are always valid — they don't consume keys.
    for (const node of nodes) {
      if (node.type === "source") continue; // source nodes provide, never consume
      const cfg = nodeConfigs[node.id];
      const inputSource = cfg?.inputSource ?? "previous_step";
      if (inputSource !== "previous_step") continue;

      const subgraphId = (node.data as unknown as ActionNodeData)?.subgraphId || "";
      const io = SUBGRAPH_IO[subgraphId];
      if (!io) continue;

      const predecessorIds = edges.filter((e) => e.target === node.id).map((e) => e.source);
      // Full DAG ancestor writes (not just direct parent)
      const predecessorWrites = getAllAncestorWrites(node.id);

      const missingKeys = io.reads.filter((k) => !predecessorWrites.has(k));
      for (const key of missingKeys) {
        warnings.push({
          severity: predecessorIds.length === 0 ? "warning" : "error",
          message: `"${(node.data as unknown as ActionNodeData).label}" needs "${stateKeyLabel(key)}" (${key}) but ${predecessorIds.length === 0 ? "has no connected predecessor" : "no upstream step produces it"}.`,
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
            // Only validate sub-fields when the predecessor explicitly maps this key at
            // sub-field level (e.g. "entities[].text"). If produced is undefined the
            // predecessor passes the key through as a whole block — no false positive.
            if (!produced) continue;
            const missingFields = reqFields.filter((f) => !produced.has(f));
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
      const isFirst = ordered[0]?.id === n.id;
      // Source nodes are data providers — they don't need an incoming edge.
      const isSource = n.type === "source";
      return !hasIncoming && !isFirst && !isSource;
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

interface VersionEntry {
  versionId: number;
  publishedAt: string;
  versionNotes: string;
  status: string;
  name?: string;
}

function formatSaveTime(date: Date): string {
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function isSeededPlanRecord(plan: Pick<PlanData, "meta" | "source">): boolean {
  return Boolean(plan.meta?.seeded || plan.source === "seed");
}

function formatVersionDate(iso: string): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) +
      " " + d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return iso;
  }
}

// ── TestRunDialog ──────────────────────────────────────────────────────────
type GraphSampleState = {
  loading: boolean;
  error: string | null;
  data: Record<string, unknown> | null;
};

function TestRunDialog({
  open, onClose, onRun, isRunning, sourceNodes,
}: {
  open: boolean;
  onClose: () => void;
  onRun: (initialState: Record<string, unknown>) => void;
  isRunning: boolean;
  sourceNodes: Node[];
}) {
  const [manualText, setManualText] = useState("");
  const [sampleMap, setSampleMap] = useState<Record<string, GraphSampleState>>({});
  // PubSub: one JSON text area per subscribe source node
  const [pubsubPayloads, setPubsubPayloads] = useState<Record<string, string>>({});

  // Categorise sources by how the test run gets their data:
  //   graph   → auto-fetched from DB (no user input needed)
  //   pubsub  → user pastes a JSON message payload
  //   live    → user pastes plain encounter text (encounter_text type, or fallback)
  const graphSources  = sourceNodes.filter((n) => {
    const t = (n.data as { sourceType?: string }).sourceType;
    return t === "knowledge_graph" || t === "patient_graph";
  });
  const pubsubSources = sourceNodes.filter((n) =>
    (n.data as { sourceType?: string }).sourceType === "pubsub_subscribe",
  );
  const hasLiveInput  = sourceNodes.length === 0 || sourceNodes.some(
    (n) => ((n.data as { sourceType?: string }).sourceType ?? "encounter_text") === "encounter_text",
  );

  // Auto-fetch sample records for each graph source when the dialog opens
  useEffect(() => {
    if (!open) return;
    for (const node of graphSources) {
      const d = node.data as { sourceType?: string; input_node_label?: string; input_text_property?: string };
      const nodeLabel = d.input_node_label ?? "";
      const textProp  = d.input_text_property ?? "text";
      const graph     = d.sourceType === "knowledge_graph" ? "knowledge" : "patient";
      if (!nodeLabel) {
        setSampleMap((prev) => ({ ...prev, [node.id]: { loading: false, error: "Source not configured — double-click it to set a record type.", data: null } }));
        continue;
      }
      setSampleMap((prev) => ({ ...prev, [node.id]: { loading: true, error: null, data: null } }));
      const params = new URLSearchParams({ node_label: nodeLabel, graph, text_property: textProp });
      fetch(`/api/training/schema/sample-node?${params}`)
        .then(async (res) => {
          if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: res.statusText }));
            setSampleMap((prev) => ({ ...prev, [node.id]: { loading: false, error: err.detail ?? "Could not load record", data: null } }));
          } else {
            const payload = await res.json();
            setSampleMap((prev) => ({ ...prev, [node.id]: { loading: false, error: null, data: payload.properties ?? {} } }));
          }
        })
        .catch((e) => setSampleMap((prev) => ({ ...prev, [node.id]: { loading: false, error: e.message, data: null } })));
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // Run is ready when:
  //   • every graph source has loaded (or errored)
  //   • every pubsub source has a non-empty JSON payload
  //   • live text is supplied when required
  const allGraphReady = graphSources.every((n) => { const s = sampleMap[n.id]; return s && !s.loading; });
  const allPubsubReady = pubsubSources.every((n) => (pubsubPayloads[n.id] ?? "").trim().length > 0);
  const canRun = allGraphReady && allPubsubReady
    && (!hasLiveInput || manualText.trim().length > 0 || graphSources.length > 0 || pubsubSources.length > 0);

  const handleRun = () => {
    const initialState: Record<string, unknown> = {
      patient_id: "test-patient",
      encounter_id: "test-encounter",
    };
    // Inject each graph source's record properties directly into pipeline state
    for (const node of graphSources) {
      const d = node.data as { input_text_property?: string };
      const textProp = d.input_text_property ?? "text";
      const sample = sampleMap[node.id];
      if (sample?.data) {
        Object.assign(initialState, sample.data);
        // Alias the text field as encounter_text so existing subgraphs find it
        if (sample.data[textProp] !== undefined) {
          initialState["encounter_text"] = sample.data[textProp];
        }
      }
    }
    // Inject each pubsub source's pasted JSON payload
    for (const node of pubsubSources) {
      const raw = (pubsubPayloads[node.id] ?? "").trim();
      if (raw) {
        try {
          const parsed = JSON.parse(raw);
          if (typeof parsed === "object" && parsed !== null) Object.assign(initialState, parsed);
          else initialState["message"] = parsed;
        } catch {
          initialState["message"] = raw; // treat as plain string if not valid JSON
        }
      }
    }
    // Manual/live text (encounter_text source or fallback when no graph/pubsub sources)
    if (hasLiveInput && manualText.trim()) {
      initialState["encounter_text"] = manualText.trim();
    }
    onRun(initialState);
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth PaperProps={{ sx: { borderRadius: 3 } }}>
      <Box sx={{ px: 3, pt: 2.5, pb: 0 }}>
        <Typography variant="h6" fontWeight={700} gutterBottom>Test run</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2.5 }}>
          Dry-run your pipeline. Nothing will be written to any database.
        </Typography>

        <Stack spacing={2}>
          {/* ── Graph-backed source previews ────────────────────────────────── */}
          {graphSources.map((node) => {
            const d = node.data as { label?: string; sourceType?: string; input_node_label?: string };
            const sample = sampleMap[node.id];
            const sourceLabel = d.label ?? (d.sourceType === "knowledge_graph" ? "Knowledge Base" : "Patient Records");
            const nodeLabel = d.input_node_label ?? "record";
            return (
              <Paper key={node.id} variant="outlined" sx={{ p: 2, borderRadius: 2, borderColor: "success.light" }}>
                <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1.5 }}>
                  <StorageIcon sx={{ fontSize: "1rem", color: "success.main" }} />
                  <Typography variant="subtitle2" fontWeight={600}>{sourceLabel}</Typography>
                  <Chip label="Database" size="small" color="success" variant="outlined" sx={{ fontSize: "0.65rem", height: 18, ml: "auto !important" }} />
                </Stack>
                {(!sample || sample.loading) ? (
                  <Stack direction="row" spacing={1} alignItems="center">
                    <CircularProgress size={13} color="success" />
                    <Typography variant="caption" color="text.secondary">Loading a sample {nodeLabel} record…</Typography>
                  </Stack>
                ) : sample.error ? (
                  <Alert severity="warning" sx={{ fontSize: "0.75rem", py: 0.5 }}>{sample.error}</Alert>
                ) : (
                  <Stack spacing={0.75}>
                    <Typography variant="caption" sx={{ color: "success.dark", fontWeight: 600 }}>
                      1 record ready — this data will be injected into the pipeline
                    </Typography>
                    <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 1, maxHeight: 160, overflow: "auto", bgcolor: "grey.50" }}>
                      {Object.entries(sample.data ?? {}).slice(0, 7).map(([k, v]) => (
                        <Box key={k} sx={{ display: "flex", gap: 1, mb: 0.3 }}>
                          <Typography variant="caption" sx={{ fontFamily: "monospace", color: "text.secondary", minWidth: 110, flexShrink: 0 }}>
                            {k}:
                          </Typography>
                          <Typography variant="caption" sx={{ fontFamily: "monospace", color: "text.primary", wordBreak: "break-all" }}>
                            {String(v).slice(0, 140)}{String(v).length > 140 ? "…" : ""}
                          </Typography>
                        </Box>
                      ))}
                      {Object.keys(sample.data ?? {}).length > 7 && (
                        <Typography variant="caption" color="text.secondary">
                          …and {Object.keys(sample.data ?? {}).length - 7} more fields
                        </Typography>
                      )}
                    </Paper>
                  </Stack>
                )}
              </Paper>
            );
          })}

          {/* ── PubSub subscribe: paste a message payload ───────────────────── */}
          {pubsubSources.map((node) => {
            const d = node.data as { label?: string; pubsub_topic?: string };
            const topic = d.pubsub_topic ? ` · ${d.pubsub_topic}` : "";
            return (
              <Paper key={node.id} variant="outlined" sx={{ p: 2, borderRadius: 2, borderColor: "#E65100" }}>
                <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1.5 }}>
                  <StorageIcon sx={{ fontSize: "1rem", color: "#E65100" }} />
                  <Typography variant="subtitle2" fontWeight={600}>{d.label ?? "Message Queue"}{topic}</Typography>
                  <Chip label="Pub/Sub" size="small" sx={{ fontSize: "0.65rem", height: 18, ml: "auto !important", bgcolor: "#E65100", color: "#fff" }} />
                </Stack>
                <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.75 }}>
                  Paste a sample message JSON to test how this pathway handles it:
                </Typography>
                <TextField
                  size="small" fullWidth multiline minRows={3}
                  placeholder={'{\n  "patient_id": "abc-123",\n  "payload": "..."\n}'}
                  value={pubsubPayloads[node.id] ?? ""}
                  onChange={(e) => setPubsubPayloads((prev) => ({ ...prev, [node.id]: e.target.value }))}
                  inputProps={{ style: { fontFamily: "monospace", fontSize: "0.78rem" } }}
                />
              </Paper>
            );
          })}

          {/* ── Live / event-feed text input ─────────────────────────────────── */}
          {hasLiveInput && (
            <Stack spacing={1}>
              {graphSources.length > 0 && (
                <Typography variant="body2" color="text.secondary">
                  This pipeline also reads from a live notes feed — paste some text to test it:
                </Typography>
              )}
              <TextField
                label="Clinical notes text"
                multiline
                minRows={4}
                fullWidth
                size="small"
                placeholder="Paste encounter text here…"
                value={manualText}
                onChange={(e) => setManualText(e.target.value)}
              />
            </Stack>
          )}
        </Stack>
      </Box>

      <Box sx={{ px: 3, py: 2.5, display: "flex", justifyContent: "flex-end", gap: 1 }}>
        <Button onClick={onClose} sx={{ textTransform: "none" }}>Cancel</Button>
        <Button
          variant="contained"
          color="success"
          disabled={isRunning || !canRun}
          startIcon={isRunning ? <CircularProgress size={13} color="inherit" /> : <PlayArrowIcon />}
          onClick={handleRun}
          sx={{ textTransform: "none" }}
        >
          {isRunning ? "Running…" : "Run test"}
        </Button>
      </Box>
    </Dialog>
  );
}

// ── PeekPanel (kept for reference — replaced by inline ProbeMonitor on edges) ─
// eslint-disable-next-line @typescript-eslint/no-unused-vars
function _PeekPanel_unused({
  open, onClose, sourceId, targetId, testTrace, nodes, rawJson, onToggleRaw,
}: {
  open: boolean;
  onClose: () => void;
  sourceId: string | null;
  targetId: string | null;
  testTrace: Record<string, StepTraceResult> | null;
  nodes: Node[];
  rawJson: boolean;
  onToggleRaw: () => void;
}) {
  const stepResult = sourceId ? testTrace?.[sourceId] ?? null : null;
  const sourceNode = nodes.find((n) => n.id === sourceId);
  const targetNode = nodes.find((n) => n.id === targetId);
  const sourceLabel = (sourceNode?.data as Record<string, unknown>)?.label as string ?? sourceId ?? "Source";
  const targetLabel = (targetNode?.data as Record<string, unknown>)?.label as string ?? targetId ?? "Target";

  const stateData = stepResult?.output_state ?? {};
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const PRIORITY_KEYS = ["encounter_text", "entities", "sentences", "errors", "is_verified"];
  const sortedKeys = Object.keys(stateData).sort((a, b) => {
    const ai = PRIORITY_KEYS.indexOf(a);
    const bi = PRIORITY_KEYS.indexOf(b);
    if (ai !== -1 && bi !== -1) return ai - bi;
    if (ai !== -1) return -1;
    if (bi !== -1) return 1;
    return a.localeCompare(b);
  });

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      PaperProps={{ sx: { width: 440, display: "flex", flexDirection: "column" } }}
    >
      <Box sx={{ px: 2.5, py: 2, borderBottom: 1, borderColor: "divider", flexShrink: 0 }}>
        <Stack direction="row" alignItems="center" spacing={1}>
          <SearchIcon sx={{ color: "primary.main", fontSize: "1.1rem" }} />
          <Box sx={{ flex: 1 }}>
            <Typography variant="subtitle2" fontWeight={700}>Peek</Typography>
            <Typography variant="caption" color="text.secondary">
              {sourceLabel} → {targetLabel}
            </Typography>
          </Box>
          <Switch checked={rawJson} onChange={onToggleRaw} size="small" />
          <Typography variant="caption" color="text.secondary">Raw JSON</Typography>
          <IconButton size="small" onClick={onClose}><CloseIcon fontSize="small" /></IconButton>
        </Stack>
        {stepResult && (
          <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
            <Chip
              size="small"
              label={stepResult.status === "completed" ? "Passed" : "Failed"}
              color={stepResult.status === "completed" ? "success" : "error"}
              sx={{ fontSize: "0.7rem", height: 20 }}
            />
            <Chip
              size="small"
              label={stepResult.duration_ms < 1000 ? `${stepResult.duration_ms}ms` : `${(stepResult.duration_ms / 1000).toFixed(2)}s`}
              variant="outlined"
              sx={{ fontSize: "0.7rem", height: 20 }}
            />
          </Stack>
        )}
        {stepResult?.error && (
          <Alert severity="error" sx={{ mt: 1, fontSize: "0.75rem" }}>{stepResult.error}</Alert>
        )}
      </Box>

      <Box sx={{ flex: 1, overflowY: "auto", p: 2 }}>
        {!stepResult ? (
          <Typography variant="body2" color="text.secondary">No trace data for this connection.</Typography>
        ) : rawJson ? (
          <Box component="pre" sx={{ fontFamily: "monospace", fontSize: "0.72rem", color: "text.primary", whiteSpace: "pre-wrap", wordBreak: "break-word", m: 0 }}>
            {JSON.stringify(stateData, null, 2)}
          </Box>
        ) : (
          <Stack spacing={0.5}>
            {sortedKeys.map((key) => {
              const val = stateData[key];
              const strVal = val === null || val === undefined
                ? "—"
                : typeof val === "string"
                  ? val
                  : JSON.stringify(val, null, 2);
              const isLong = strVal.length > 120;
              const isExpanded = expanded.has(key);
              const displayVal = isLong && !isExpanded ? strVal.slice(0, 120) + "…" : strVal;
              const isPriority = PRIORITY_KEYS.includes(key);

              return (
                <Paper
                  key={key}
                  variant="outlined"
                  sx={{ p: 1.25, borderRadius: 1.5, bgcolor: isPriority ? "primary.50" : "transparent" }}
                >
                  <Typography variant="caption" sx={{ fontFamily: "monospace", fontWeight: 700, color: "primary.main", fontSize: "0.7rem" }}>
                    {key}
                  </Typography>
                  <Typography
                    component="pre"
                    variant="caption"
                    sx={{ display: "block", mt: 0.25, fontFamily: "monospace", fontSize: "0.7rem", color: "text.primary", whiteSpace: "pre-wrap", wordBreak: "break-word", m: 0 }}
                  >
                    {displayVal}
                  </Typography>
                  {isLong && (
                    <Button
                      size="small"
                      variant="text"
                      sx={{ mt: 0.25, p: 0, fontSize: "0.65rem", textTransform: "none", minWidth: 0 }}
                      onClick={() => setExpanded((s) => {
                        const ns = new Set(s);
                        isExpanded ? ns.delete(key) : ns.add(key);
                        return ns;
                      })}
                    >
                      {isExpanded ? "Show less" : "Show more"}
                    </Button>
                  )}
                </Paper>
              );
            })}
          </Stack>
        )}
      </Box>
    </Drawer>
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
  const nodesRef = useRef<Node[]>([]);
  const edgesRef = useRef<Edge[]>([]);
  const nodeConfigsRef = useRef<Record<string, ActionConfig>>({});
  const [saveError, setSaveError] = useState<string | null>(null);
  const [lastSaved, setLastSaved] = useState<Date | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [publishDialogOpen, setPublishDialogOpen] = useState(false);
  const [versionNotes, setVersionNotes] = useState("");
  const [historyOpen, setHistoryOpen] = useState(false);
  const [versions, setVersions] = useState<VersionEntry[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [restoringVid, setRestoringVid] = useState<number | null>(null);
  const [isSeededPathway, setIsSeededPathway] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deleteConfirmText, setDeleteConfirmText] = useState("");
  const [isDeletingPathway, setIsDeletingPathway] = useState(false);
  // Edge deletion confirmation: holds edges pending removal until confirmed
  const [pendingDeleteEdges, setPendingDeleteEdges] = useState<Edge[] | null>(null);

  useEffect(() => {
    nodesRef.current = nodes;
  }, [nodes]);

  useEffect(() => {
    edgesRef.current = edges;
  }, [edges]);

  useEffect(() => {
    nodeConfigsRef.current = nodeConfigs;
  }, [nodeConfigs]);

  // ── Test-run state ────────────────────────────────────────────────────────
  const [testRunOpen, setTestRunOpen] = useState(false);
  const [isTestRunning, setIsTestRunning] = useState(false);
  const [testRunError, setTestRunError] = useState<string | null>(null);

  // ── Batch dry-run state ───────────────────────────────────────────────────
  type ViewerMode = "auto" | "entities" | "verification" | "surface_forms" | "json";
  const [batchPanelOpen, setBatchPanelOpen] = useState(false);
  const [isBatchRunning, setIsBatchRunning] = useState(false);
  const [batchLimit, setBatchLimit] = useState(20);
  const [batchStatusFilter, setBatchStatusFilter] = useState<string>("pending");
  type BatchCandidateResult = {
    batch_run_id: string | null;
    candidate_id: string;
    text_preview: string;
    encounter_text?: string | null;
    status: "completed" | "halted" | "error" | "running";
    halted_at: string | null;
    halted_at_subgraph: string | null;
    halt_reason?: string | null;
    verification_is_accurate?: boolean | null;
    verification_confidence?: number | null;
    verification_threshold?: number | null;
    verification_issues?: string[] | null;
    error: string | null;
    duration_ms: number;
    index: number;
    trace_saved?: boolean;
  };
  type BatchStepStat = { label: string; ran: number; halted: number };
  type BatchSummary = { total: number; passed: number; halted: number; errored: number; by_step_stats: Record<string, BatchStepStat> };
  const [batchResults, setBatchResults] = useState<BatchCandidateResult[]>([]);
  const [batchSummary, setBatchSummary] = useState<BatchSummary | null>(null);
  const [batchRunId, setBatchRunId] = useState<string | null>(null);
  const [batchTraceLoadingId, setBatchTraceLoadingId] = useState<string | null>(null);
  const [selectedBatchCandidateId, setSelectedBatchCandidateId] = useState<string | null>(null);
  const [selectedBatchTrace, setSelectedBatchTrace] = useState<Record<string, StepTraceResult> | null>(null);
  // Live per-step counts while running: subgraph_id → { label, ran, halted }
  const [batchStepCounts, setBatchStepCounts] = useState<Record<string, BatchStepStat>>({});
  const [batchConcurrency, setBatchConcurrency] = useState(3);
  const [testTrace, setTestTrace] = useState<Record<string, StepTraceResult> | null>(null);
  /** ID of the step currently executing (null when between steps) */
  const [runningStepId, setRunningStepId] = useState<string | null>(null);
  /** ID of the node that caused the pipeline to halt (null = completed normally) */
  const [haltedNodeId, setHaltedNodeId] = useState<string | null>(null);
  const deleteConfirmTarget = planName.trim() || planId;
  /** Set of edge keys ("sourceId|targetId") the user has clamped a probe onto */
  const [probedEdges, setProbedEdges] = useState<Set<string>>(new Set());
  const toggleProbe = useCallback((srcId: string, tgtId: string) => {
    const key = `${srcId}|${tgtId}`;
    setProbedEdges((prev) => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });
  }, []);
  const testInputRef = useRef<{ initialState: Record<string, unknown> }>({
    initialState: {},
  });

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
          setIsSeededPathway(isSeededPlanRecord(data));
          setPlanName(data.name || "");
          setPlanDescription(data.description || "");
          setPlanStatus(data.status || "draft");
          const trig = (data as any).trigger;
          if (trig?.event) setTriggerEvent(trig.event);
          const configs: Record<string, ActionConfig> = {};
          const loadedActionNodes: Node[] = (data.actions || [])
            .filter((a) => !isCanvasOnlyNodeType(a.nodeType)) // legacy guard: skip old canvas-only nodes saved as actions
            .map((a, i) => {
              const cfg = hydrateActionConfig(a);
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
                  config: cfg,
                  // Restore saved field mappings so output port handles appear immediately on load.
                  fieldMappings: (cfg.params.field_mappings as FieldMappingRow[]) ?? [],
                  onConfigure: () => openConfigurator(a.id),
                },
              };
            });
          const savedSourceNodes = ((data as unknown as Record<string, unknown>).sourceNodes as Array<{ id: string; position: { x: number; y: number }; data: Record<string, unknown> }>) || [];
          const savedOutputNodes = ((data as unknown as Record<string, unknown>).outputNodes as Array<{ id: string; position: { x: number; y: number }; data: Record<string, unknown> }>) || [];
          const savedViewerNodes = ((data as unknown as Record<string, unknown>).viewerNodes as Array<{ id: string; position: { x: number; y: number }; data: Record<string, unknown> }>) || [];
          const loadedSourceNodes: Node[] = savedSourceNodes.map((sn) => ({
            id: sn.id,
            type: "source",
            position: sn.position,
            data: { ...sn.data, onConfigure: () => setSourceConfigOpen(sn.id) },
          }));
          const loadedOutputNodes: Node[] = savedOutputNodes.map((on) => ({
            id: on.id,
            type: "output",
            position: on.position,
            data: { ...on.data, onConfigure: () => setOutputConfigOpen(on.id) },
          }));
          const loadedViewerNodes: Node[] = savedViewerNodes.map((vn) => ({
            id: vn.id,
            type: "viewer",
            position: vn.position,
            data: { ...vn.data, onConfigure: () => setViewerConfigOpen(vn.id) },
          }));
          nodeConfigsRef.current = configs;
          // Auto-layout when the pathway still carries seed-default positions
          // (all action nodes share the same x=250 column).  This fires once
          // on first open of a freshly seeded plan; user-saved positions are
          // preserved because they spread across multiple x values.
          const allActionX = loadedActionNodes.map((n) => n.position.x);
          const allAtSeedDefault =
            loadedActionNodes.length > 1 &&
            allActionX.every((x) => x === allActionX[0]);
          const allNodes = [...loadedActionNodes, ...loadedSourceNodes, ...loadedOutputNodes, ...loadedViewerNodes];
          const allEdgesForLayout = (data.edges || []).map((e, i) => ({
            id: `e${i}-${e.source}-${e.target}`,
            source: e.source,
            target: e.target,
            sourceHandle: e.sourceHandle ?? null,
            targetHandle: e.targetHandle ?? null,
            type: "portEdge",
            data: {},
          }));
          const finalNodes = allAtSeedDefault
            ? applyDagreLayout(allNodes, allEdgesForLayout)
            : allNodes;
          nodesRef.current = finalNodes;
          setNodeConfigs(configs);
          setNodes(finalNodes);
          const legacySourceEdges = ((data as unknown as Record<string, unknown>).sourceEdges as PersistedCanvasEdge[]) || [];
          const canvasEdges = ((data as unknown as Record<string, unknown>).canvasEdges as PersistedCanvasEdge[]) || [];
          const allEdges: PersistedCanvasEdge[] = [
            ...(data.edges || []),
            ...(canvasEdges.length > 0 ? canvasEdges : legacySourceEdges),   // canvas-only wires
          ];
          const loadedEdges = allEdges.map((e, i) => ({
            id: `e${i}-${e.source}-${e.target}`,
            source: e.source,
            target: e.target,
            sourceHandle: e.sourceHandle ?? e.source_handle ?? null,
            targetHandle: e.targetHandle ?? e.target_handle ?? null,
            type: "portEdge",
            data: { label: e.sourceHandle || e.source_handle || e.targetHandle || e.target_handle || "" },
          }));
          edgesRef.current = loadedEdges;
          setEdges(loadedEdges);
        })
        .catch(() => {});
    }
  }, [planId, isNew, setNodes, setEdges, openConfigurator]);

  const onConnect = useCallback((connection: Connection) => {
    const edgeId = `${connection.source}:${connection.sourceHandle ?? "_"}->${connection.target}:${connection.targetHandle ?? "_"}`;
    setEdges((eds) => addEdge({ ...connection, id: edgeId, type: "portEdge", data: { label: connection.sourceHandle || connection.targetHandle || "" } }, eds));
  }, [setEdges]);

  // Intercept edge removal events to show a confirmation before deleting wires.
  const handleEdgesChange = useCallback((changes: EdgeChange[]) => {
    const removals = changes.filter((c) => c.type === "remove");
    const others   = changes.filter((c) => c.type !== "remove");
    if (others.length) onEdgesChange(others);
    if (removals.length) {
      const edgesToRemove = removals
        .map((c) => edges.find((e) => e.id === (c as { type: "remove"; id: string }).id))
        .filter(Boolean) as Edge[];
      setPendingDeleteEdges(edgesToRemove);
    }
  }, [edges, onEdgesChange]);

  const confirmEdgeDeletion = useCallback(() => {
    if (pendingDeleteEdges) {
      const ids = new Set(pendingDeleteEdges.map((e) => e.id));
      setEdges((eds) => eds.filter((e) => !ids.has(e.id)));
      setPendingDeleteEdges(null);
    }
  }, [pendingDeleteEdges, setEdges]);

  const autoLayout = useCallback(() => {
    setNodes((nds) => applyDagreLayout(nds, edges));
  }, [edges, setNodes]);

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
      const defaultBranches = ["branch_a", "branch_b"];
      const labelMap: Record<string, string> = { parallel: "Parallel", merge: "Merge", transform: "Transform" };
      const colorMap: Record<string, string> = { parallel: "#00ACC1", merge: "#8E24AA", transform: "#43A047" };
      const cfg: ActionConfig = {
        ...DEFAULT_CONFIG,
        subgraphId,
        label: labelMap[subgraphId] ?? subgraphId,
        description: "Flow control node",
        nodeType: subgraphId as ActionConfig["nodeType"],
        params: subgraphId !== "transform" ? { branches: defaultBranches } : { operations: [] },
      };
      setNodeConfigs((prev) => ({ ...prev, [id]: cfg }));
      setNodes((nds) => [...nds, {
        id,
        type: subgraphId,
        position: { x: 250, y: (nodes.length + 1) * 150 },
        data: {
          label: cfg.label,
          subgraphId,
          color: colorMap[subgraphId] ?? "#999",
          branches: subgraphId !== "transform" ? defaultBranches : undefined,
          inputs: subgraphId === "merge" ? defaultBranches : undefined,
          operations: subgraphId === "transform" ? [] : undefined,
          onConfigure: () => openConfigurator(id),
        },
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

  // ── Source node ─────────────────────────────────────────────────────────────
  const [sourceConfigOpen, setSourceConfigOpen] = useState<string | null>(null); // nodeId being configured

  const addSourceNode = useCallback((sourceType: SourceType) => {
    const meta = SOURCE_DEFINITIONS[sourceType];
    const id = `source_${Date.now()}`;
    setNodes((nds) => {
      // Place to the left of the leftmost node, vertically centred on existing content
      const existingSourceNodes = nds.filter((n) => n.type === "source");
      const minX = nds.reduce((m, n) => Math.min(m, n.position?.x ?? 9999), 9999);
      const midY = nds.length > 0
        ? nds.reduce((sum, n) => sum + (n.position?.y ?? 0), 0) / nds.length
        : 200;
      const x = existingSourceNodes.length > 0 ? minX : Math.min(minX - 240, 60);
      const y = Math.max(80, midY + existingSourceNodes.length * 180);
      return [...nds, {
        id,
        type: "source",
        position: { x: Math.max(20, x), y },
        data: {
          label: meta.label,
          sourceType,
          outputs: meta.outputs,
          onConfigure: () => setSourceConfigOpen(id),
        },
      } as Node];
    });
  }, [setNodes]);

  // ── Output node (sink) ───────────────────────────────────────────────────────
  const [outputConfigOpen, setOutputConfigOpen] = useState<string | null>(null);

  const addOutputNode = useCallback((outputType: OutputType) => {
    const meta = OUTPUT_DEFINITIONS[outputType];
    const id = `output_${Date.now()}`;
    setNodes((nds) => {
      // Place to the right of the rightmost node, vertically centred on existing content
      const existingOutputNodes = nds.filter((n) => n.type === "output");
      const maxX = nds.reduce((m, n) => Math.max(m, (n.position?.x ?? 0) + 260), 400);
      const midY = nds.length > 0
        ? nds.reduce((sum, n) => sum + (n.position?.y ?? 0), 0) / nds.length
        : 200;
      const y = Math.max(80, midY + existingOutputNodes.length * 180);
      return [...nds, {
        id,
        type: "output",
        position: { x: maxX + 80, y },
        data: {
          label: meta.label,
          outputType,
          inputs: meta.inputs,
          onConfigure: () => setOutputConfigOpen(id),
        },
      } as Node];
    });
  }, [setNodes]);

  // ── Mini HITL viewer node ───────────────────────────────────────────────────
  const [viewerConfigOpen, setViewerConfigOpen] = useState<string | null>(null);

  const addViewerNode = useCallback(() => {
    const id = `viewer_${Date.now()}`;
    setNodes((nds) => {
      const maxX = nds.reduce((m, n) => Math.max(m, (n.position?.x ?? 0) + 260), 400);
      const midY = nds.length > 0
        ? nds.reduce((sum, n) => sum + (n.position?.y ?? 0), 0) / nds.length
        : 220;
      return [
        ...nds,
        {
          id,
          type: "viewer",
          position: { x: maxX + 120, y: Math.max(80, midY) },
          data: {
            label: "Mini HITL",
            mode: "auto" as ViewerMode,
            onConfigure: () => setViewerConfigOpen(id),
          },
        } as Node,
      ];
    });
  }, [setNodes]);

  const handleConfigSave = useCallback((nodeId: string, config: ActionConfig) => {
    setNodeConfigs((prev) => {
      const next = { ...prev, [nodeId]: config };
      nodeConfigsRef.current = next;
      return next;
    });
    const option = SUBGRAPH_OPTIONS.find((s) => s.id === config.subgraphId);
    setNodes((nds) =>
      {
        const nextNodes = nds.map((n) =>
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
                // Propagate field mappings so the canvas node renders live output port handles.
                fieldMappings: (config.params.field_mappings as FieldMappingRow[]) ?? [],
                // Propagate branch/input arrays so Parallel/Merge nodes render the right handles.
                branches: (config.params.branches as string[]) ?? undefined,
                inputs: (config.params.branches as string[]) ?? undefined,
                // Propagate transform operations so TransformNode shows the correct count.
                operations: (config.params.operations as unknown[]) ?? undefined,
              },
            }
          : n
      );
        nodesRef.current = nextNodes;
        return nextNodes;
      }
    );
  }, [setNodes]);

  const handleDeleteNode = useCallback((nodeId: string) => {
    setNodes((nds) => {
      const next = nds.filter((n) => n.id !== nodeId);
      nodesRef.current = next;
      return next;
    });
    setEdges((eds) => {
      const next = eds.filter((e) => e.source !== nodeId && e.target !== nodeId);
      edgesRef.current = next;
      return next;
    });
    setNodeConfigs((prev) => {
      const next = { ...prev };
      delete next[nodeId];
      nodeConfigsRef.current = next;
      return next;
    });
  }, [setNodes, setEdges]);

  const selectedConfig = useMemo(() => {
    if (!selectedNode) return DEFAULT_CONFIG;
    return nodeConfigs[selectedNode] || DEFAULT_CONFIG;
  }, [selectedNode, nodeConfigs]);

  // Compute what all predecessor steps/source nodes write into the pipeline state.
  // Source nodes contribute their declared outputs; action nodes contribute SUBGRAPH_IO writes.
  const prevStepWrites = useMemo<string[] | null>(() => {
    if (!selectedNode) return null;
    const predecessorIds = edges
      .filter((e) => e.target === selectedNode)
      .map((e) => e.source);
    if (predecessorIds.length === 0) return null;
    // Global keys are always present in every pipeline run — injected at startup by
    // the trigger / test runner regardless of canvas wiring.
    const GLOBAL_PIPELINE_KEYS = ["encounter_text", "patient_id", "encounter_id", "run_id"];
    const allWrites = new Set<string>(GLOBAL_PIPELINE_KEYS);
    for (const predId of predecessorIds) {
      const predNode = nodes.find((n) => n.id === predId);
      if (predNode?.type === "source") {
        const srcOutputs = (predNode.data as { outputs?: string[] }).outputs ?? [];
        srcOutputs.forEach((k) => allWrites.add(k));
      } else {
        const predData = predNode?.data as unknown as ActionNodeData | undefined;
        const predCfg = nodeConfigs[predId];
        const mappedKeys = getProducedKeysFromMappings(
          (predCfg?.params?.field_mappings as FieldMappingRow[] | undefined)
            ?? predData?.fieldMappings,
        );
        if (mappedKeys.length > 0) {
          mappedKeys.forEach((k) => allWrites.add(k));
        } else if (predData?.subgraphId) {
          SUBGRAPH_IO[predData.subgraphId]?.writes.forEach((w) => allWrites.add(w));
        }
      }
    }
    return allWrites.size > 0 ? Array.from(allWrites) : null;
  }, [selectedNode, edges, nodes, nodeConfigs]);

  // Named upstream nodes: [{label, keys[]}] — used to show "Knowledge Base → encounter_text" in Data connections step
  const prevStepSources = useMemo<Array<{ label: string; keys: string[] }>>(() => {
    if (!selectedNode) return [];
    const predecessorIds = edges
      .filter((e) => e.target === selectedNode)
      .map((e) => e.source);
    return predecessorIds.flatMap((predId) => {
      const predNode = nodes.find((n) => n.id === predId);
      if (!predNode) return [];
      if (predNode.type === "source") {
        const label = (predNode.data as { label?: string }).label ?? "Data source";
        const keys = (predNode.data as { outputs?: string[] }).outputs ?? [];
        return [{ label, keys }];
      } else {
        const data = predNode.data as unknown as ActionNodeData | undefined;
        const label = data?.label ?? "Previous step";
        const predCfg = nodeConfigs[predId];
        const mappedKeys = getProducedKeysFromMappings(
          (predCfg?.params?.field_mappings as FieldMappingRow[] | undefined)
            ?? data?.fieldMappings,
        );
        const keys = mappedKeys.length > 0
          ? mappedKeys
          : (data?.subgraphId ? (SUBGRAPH_IO[data.subgraphId]?.writes ?? []) : []);
        return keys.length > 0 ? [{ label, keys }] : [];
      }
    });
  }, [selectedNode, edges, nodes, nodeConfigs]);

  const inboundConnections = useMemo<Array<{
    sourceLabel: string;
    sourceHandle: string;
    targetHandle: string;
  }>>(() => {
    if (!selectedNode) return [];
    return edges
      .filter((e) => e.target === selectedNode)
      .map((e) => {
        const predNode = nodes.find((n) => n.id === e.source);
        const sourceLabel = predNode
          ? (predNode.type === "source"
            ? ((predNode.data as { label?: string }).label ?? "Data source")
            : ((predNode.data as { label?: string }).label ?? "Previous step"))
          : e.source;
        return {
          sourceLabel,
          sourceHandle: String(e.sourceHandle ?? "default"),
          targetHandle: String(e.targetHandle ?? "default"),
        };
      });
  }, [selectedNode, edges, nodes]);

  const outboundConnections = useMemo<Array<{
    targetLabel: string;
    sourceHandle: string;
    targetHandle: string;
  }>>(() => {
    if (!selectedNode) return [];
    return edges
      .filter((e) => e.source === selectedNode)
      .map((e) => {
        const targetNode = nodes.find((n) => n.id === e.target);
        const targetLabel = targetNode
          ? (targetNode.type === "output"
            ? ((targetNode.data as { label?: string }).label ?? "Output")
            : ((targetNode.data as { label?: string }).label ?? "Next step"))
          : e.target;
        return {
          targetLabel,
          sourceHandle: String(e.sourceHandle ?? "default"),
          targetHandle: String(e.targetHandle ?? "default"),
        };
      });
  }, [selectedNode, edges, nodes]);

  const selectedNodeLabel = useMemo(() => {
    if (!selectedNode) return "";
    const n = nodes.find((node) => node.id === selectedNode);
    if (!n) return selectedNode;
    const data = n.data as { label?: string; subgraphId?: string };
    return data.label ?? data.subgraphId ?? selectedNode;
  }, [selectedNode, nodes]);

  // Collect field-level mappings from DIRECT predecessors.
  // If multiple predecessors exist, merge all mappings so pass-through hydration
  // reflects the actual wired graph rather than only the first incoming edge.
  const prevStepFieldMappings = useMemo<FieldMappingRow[] | null>(() => {
    if (!selectedNode) return null;
    const predecessorIds = edges
      .filter((e) => e.target === selectedNode)
      .map((e) => e.source);
    if (predecessorIds.length === 0) return null;
    const merged: FieldMappingRow[] = [];
    const seen = new Set<string>();
    for (const predId of predecessorIds) {
      const predCfg = nodeConfigs[predId];
      const mappings = predCfg?.params?.field_mappings as FieldMappingRow[] | undefined;
      if (!mappings || mappings.length === 0) continue;
      for (const row of mappings) {
        const dedupeKey = `${row.llmField}::${row.statePath}`;
        if (seen.has(dedupeKey)) continue;
        seen.add(dedupeKey);
        merged.push(row);
      }
    }
    return merged.length > 0 ? merged : null;
  }, [selectedNode, edges, nodeConfigs]);

  // Derive output_target for a persist node from whichever output node(s) it is
  // wired to on the canvas.  This means the user connects Persist → Knowledge Base
  // (or Persist → Patient Records) and the wiring IS the config — no separate
  // input field needed on the Persist node.
  const resolveOutputTarget = useCallback((persistNodeId: string, allNodes: typeof nodes, allEdges: typeof edges): string => {
    const OUTPUT_TYPE_MAP: Record<string, string> = {
      knowledge_graph: "gold_training",
      patient_graph:   "patient_graph",
    };
    const connectedOutputTypes = new Set<string>(
      allEdges
        .filter((e) => e.source === persistNodeId)
        .map((e) => allNodes.find((n) => n.id === e.target))
        .filter((n): n is typeof allNodes[number] => n?.type === "output")
        .map((n) => OUTPUT_TYPE_MAP[(n.data as Record<string, unknown>)?.outputType as string] ?? "gold_training"),
    );
    if (connectedOutputTypes.has("patient_graph") && connectedOutputTypes.has("gold_training")) return "both";
    if (connectedOutputTypes.has("patient_graph")) return "patient_graph";
    return "gold_training"; // default when connected to Knowledge Base or unspecified
  }, []);

  // Core streaming runner — accepts an optional pre-filtered node/edge subset
  // so both "full run" and "run to here" share the same SSE logic.
  const runTestStream = useCallback(async (
    initialState: Record<string, unknown>,
    overrideNodes?: typeof nodes,
    overrideEdges?: typeof edges,
  ) => {
    setTestRunError(null);
    setIsTestRunning(true);
    setTestTrace(null);
    setRunningStepId(null);
    setHaltedNodeId(null);
    setTestRunOpen(false);
    setSelectedBatchCandidateId(null);
    setSelectedBatchTrace(null);
    // Remember last input so "run to here" can reuse it without re-opening the dialog
    testInputRef.current = { initialState };

    const actionNodes = overrideNodes ?? filterExecutionNodes(nodes);
    const testEdges = overrideEdges ?? filterExecutionEdges(edges, nodes);

    // All nodes/edges (not just the filtered subset) are needed for output-node topology
    const allNodesForTopology = overrideNodes ?? nodes;
    const allEdgesForTopology = overrideEdges ?? edges;

    const body = {
      plan_id: planId,
      actions: actionNodes.map((n) => {
        const subgraphId = (n.data as unknown as ActionNodeData).subgraphId ?? n.type ?? "action";
        const cfg = { ...(nodeConfigs[n.id] ?? {}) };
        // Persist nodes derive their output_target from which output node they are wired to.
        // The engine maps camelCase outputTarget → snake_case output_target before running.
        if (subgraphId === "persist" && !cfg.outputTarget) {
          (cfg as Record<string, unknown>).outputTarget = resolveOutputTarget(n.id, allNodesForTopology, allEdgesForTopology);
        }
        return {
          id: n.id,
          subgraph_id: subgraphId,
          label: (n.data as unknown as ActionNodeData).label ?? n.id,
          node_type: (n.data as unknown as ActionNodeData).nodeType ?? n.type ?? "action",
          config: cfg,
        };
      }),
      edges: testEdges.map((e) => ({
        source: e.source,
        target: e.target,
        source_handle: e.sourceHandle ?? null,
        target_handle: e.targetHandle ?? null,
      })),
      input: {
        // Ensure baseline keys are always present so subgraphs that expect them don't fail
        patient_id: "test-patient",
        encounter_id: "test-encounter",
        ...initialState,
      },
    };

    try {
      const res = await fetch("/api/pipeline/test-run/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok || !res.body) {
        const errText = await res.text().catch(() => res.statusText);
        let detail = errText;
        try { detail = JSON.parse(errText)?.detail ?? errText; } catch { /* raw text is fine */ }
        setTestRunError(detail ?? "Test run failed");
        return;
      }

      // ── Consume the SSE stream incrementally ─────────────────────────────
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      const traceMap: Record<string, StepTraceResult> = {};
      let sseBuffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        sseBuffer += decoder.decode(value, { stream: true });

        // SSE events are separated by a blank line; support LF and CRLF framing.
        const parts = sseBuffer.split(/\r?\n\r?\n/);
        sseBuffer = parts.pop() ?? "";   // keep incomplete trailing fragment

        for (const part of parts) {
          let eventType = "message";
          let dataLine = "";
          for (const line of part.split(/\r?\n/)) {
            const trimmed = line.trimStart();
            if (trimmed.startsWith("event: ")) eventType = trimmed.slice(7).trim();
            if (trimmed.startsWith("data: "))  dataLine  = trimmed.slice(6).trim();
          }
          if (!dataLine) continue;

          let event: Record<string, unknown>;
          try { event = JSON.parse(dataLine); } catch { continue; }

          if (eventType === "step_start") {
            setRunningStepId(event.step_id as string);
          } else if (eventType === "step_done") {
            const step = event.step_trace as StepTraceResult;
            traceMap[step.step_id] = step;
            setTestTrace({ ...traceMap });
            setRunningStepId(null);
            // "halted" = the step ran but its quality gate stopped the pipeline
            if (step.status === "halted") {
              setHaltedNodeId(step.step_id);
            }
          } else if (eventType === "pipeline_done") {
            setRunningStepId(null);
            // Sync halted_step_id from the final event in case we missed the step_done
            if (event.halted_step_id) setHaltedNodeId(event.halted_step_id as string);
          } else if (eventType === "error") {
            setTestRunError((event.message as string) ?? "Pipeline error");
          }
        }
      }
      // Ensure final state is committed after reader closes
      setTestTrace({ ...traceMap });
    } catch (e: unknown) {
      setTestRunError(e instanceof Error ? e.message : "Network error");
    } finally {
      setIsTestRunning(false);
      setRunningStepId(null);
    }
  }, [nodes, edges, nodeConfigs, planId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Public entry point for full pipeline runs
  const runTest = useCallback((initialState: Record<string, unknown>) => {
    runTestStream(initialState);
  }, [runTestStream]);

  // Must be declared before any callback that reads or sets it.
  const [runToStepPending, setRunToStepPending] = useState<string | null>(null);

  const handleTestRunDialogRun = useCallback((initialState: Record<string, unknown>) => {
    if (runToStepPending) {
      // User opened dialog via "run to here" — build the partial graph then stream
      const upToNodeId = runToStepPending;
      setRunToStepPending(null);
      const actionNodes = filterExecutionNodes(nodes);
      const actionEdges = filterExecutionEdges(edges, nodes);
      const ancestors = new Set<string>([upToNodeId]);
      let changed = true;
      while (changed) {
        changed = false;
        for (const e of actionEdges) {
          if (ancestors.has(e.target) && !ancestors.has(e.source)) {
            ancestors.add(e.source);
            changed = true;
          }
        }
      }
      runTestStream(
        initialState,
        actionNodes.filter((n) => ancestors.has(n.id)),
        actionEdges.filter((e) => ancestors.has(e.source) && ancestors.has(e.target)),
      );
    } else {
      runTestStream(initialState);
    }
  }, [runTestStream, runToStepPending, nodes, edges]);

  // ── Run every step in one dry-run (reuse last test input, skip dialog) ───
  const handleRunAllSteps = useCallback(() => {
    if (testInputRef.current) {
      // Re-use last input so the user doesn't have to re-enter it every iteration
      runTestStream(testInputRef.current.initialState);
    } else {
      // No previous run — open dialog to collect input first
      setTestRunOpen(true);
    }
  }, [runTestStream]);

  // ── Batch dry-run against real TrainingCandidates ────────────────────────
  const handleBatchRun = useCallback(async () => {
    setBatchResults([]);
    setBatchSummary(null);
    setBatchStepCounts({});
    setBatchRunId(null);
    setSelectedBatchCandidateId(null);
    setSelectedBatchTrace(null);
    setIsBatchRunning(true);
    setBatchPanelOpen(true);

    const allNodes = nodesRef.current;
    const allEdges = edgesRef.current;

    const serialisedActions = allNodes
      .filter((n) => !isCanvasOnlyNodeType(n.type ?? ""))
      .map((n) => {
        const subgraphId = (n.data as unknown as ActionNodeData).subgraphId ?? n.type ?? "action";
        const cfg = { ...(nodeConfigsRef.current[n.id] ?? {}) };
        if (subgraphId === "persist" && !(cfg as Record<string, unknown>).outputTarget) {
          (cfg as Record<string, unknown>).outputTarget = resolveOutputTarget(n.id, allNodes, allEdges);
        }
        return {
          id: n.id,
          subgraph_id: subgraphId,
          label: (n.data as unknown as ActionNodeData).label ?? n.id,
          node_type: (n.data as unknown as ActionNodeData).nodeType ?? n.type ?? "action",
          config: cfg,
        };
      });

    const serialisedEdges = filterExecutionEdges(allEdges, allNodes)
      .map((e) => ({
        source: e.source, target: e.target, source_handle: e.sourceHandle ?? null, target_handle: e.targetHandle ?? null,
      }));

    try {
      const res = await fetch("/api/pipeline/test-run/batch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ actions: serialisedActions, edges: serialisedEdges, limit: batchLimit, status_filter: batchStatusFilter || null, concurrency: batchConcurrency }),
      });
      if (!res.ok || !res.body) throw new Error(`Server error ${res.status}`);

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const blocks = buf.split(/\r?\n\r?\n/);
        buf = blocks.pop() ?? "";
        for (const block of blocks) {
          const dataLine = block
            .split(/\r?\n/)
            .find((l) => l.trimStart().startsWith("data:"));
          if (!dataLine) continue;
          try {
            const evt = JSON.parse(dataLine.trimStart().slice(5).trim());
            if (evt.type === "candidate_start") {
              if (typeof evt.batch_run_id === "string") setBatchRunId(evt.batch_run_id);
              setBatchResults((prev) => [...prev, {
                batch_run_id: typeof evt.batch_run_id === "string" ? evt.batch_run_id : null,
                candidate_id: evt.candidate_id,
                text_preview: evt.text_preview,
                encounter_text: typeof evt.encounter_text === "string" ? evt.encounter_text : null,
                status: "running",
                halted_at: null,
                halted_at_subgraph: null,
                halt_reason: null,
                verification_is_accurate: null,
                verification_confidence: null,
                verification_threshold: null,
                verification_issues: null,
                error: null,
                duration_ms: 0,
                index: evt.index,
                trace_saved: false,
              }]);
            } else if (evt.type === "candidate_done") {
              if (typeof evt.batch_run_id === "string") setBatchRunId(evt.batch_run_id);
              setBatchResults((prev) => prev.map((r) => r.candidate_id === evt.candidate_id
                ? {
                    ...r,
                    batch_run_id: typeof evt.batch_run_id === "string" ? evt.batch_run_id : r.batch_run_id,
                    status: evt.status,
                    encounter_text: typeof evt.encounter_text === "string" ? evt.encounter_text : r.encounter_text,
                    halted_at: evt.halted_at,
                    halted_at_subgraph: evt.halted_at_subgraph,
                    halt_reason: evt.halt_reason ?? null,
                    verification_is_accurate: evt.verification_is_accurate ?? null,
                    verification_confidence: typeof evt.verification_confidence === "number" ? evt.verification_confidence : null,
                    verification_threshold: typeof evt.verification_threshold === "number" ? evt.verification_threshold : null,
                    verification_issues: Array.isArray(evt.verification_issues) ? evt.verification_issues.map((x: unknown) => String(x)) : null,
                    error: evt.error,
                    duration_ms: evt.duration_ms,
                    trace_saved: Boolean(evt.trace_saved),
                  }
                : r));
            } else if (evt.type === "step_progress") {
              // Live per-step funnel update
              setBatchStepCounts((prev) => ({
                ...prev,
                [evt.subgraph_id]: { label: evt.label, ran: evt.ran, halted: evt.halted },
              }));
            } else if (evt.type === "batch_done") {
              if (typeof evt.batch_run_id === "string") setBatchRunId(evt.batch_run_id);
              setBatchSummary({ total: evt.total, passed: evt.passed, halted: evt.halted, errored: evt.errored, by_step_stats: evt.by_step_stats ?? {} });
            }
          } catch { /* ignore malformed event */ }
        }
      }
    } catch (err) {
      setBatchSummary({ total: 0, passed: 0, halted: 0, errored: 1, by_step_stats: {} });
    } finally {
      setIsBatchRunning(false);
    }
  }, [batchLimit, batchStatusFilter, batchConcurrency]);

  const inspectBatchCandidate = useCallback(async (candidate: BatchCandidateResult) => {
    const runId = candidate.batch_run_id ?? batchRunId;
    if (candidate.trace_saved && runId) {
      setBatchTraceLoadingId(candidate.candidate_id);
      try {
        const params = new URLSearchParams({
          batch_run_id: runId,
          candidate_id: candidate.candidate_id,
        });
        const res = await fetch(`/api/pipeline/test-run/batch?${params.toString()}`);
        if (!res.ok) throw new Error(`Trace fetch failed (${res.status})`);
        const payload = await res.json() as { step_traces?: StepTraceResult[] };
        const traces = Array.isArray(payload.step_traces) ? payload.step_traces : [];
        const map: Record<string, StepTraceResult> = {};
        traces.forEach((step) => { map[step.step_id] = step; });
        setSelectedBatchCandidateId(candidate.candidate_id);
        setSelectedBatchTrace(map);
        setTestTrace(null);
        setTestRunError(null);
      } catch (err) {
        setTestRunError(err instanceof Error ? err.message : "Failed to load batch trace");
      } finally {
        setBatchTraceLoadingId(null);
      }
      return;
    }

    // Fallback: replay this candidate through the single-run path.
    runTestStream({
      encounter_text: candidate.encounter_text || candidate.text_preview,
      patient_id: "batch-dry-run",
      encounter_id: candidate.candidate_id,
      candidate_id: candidate.candidate_id,
    });
  }, [batchRunId, runTestStream]);

  // ── Run to a specific step (probe "test to this point") ───────────────────
  const runToStep = useCallback((upToNodeId: string) => {
    const canvasOnly = CANVAS_ONLY_NODE_TYPES;

    // If the caller passed a canvas-only node (e.g. a source node), resolve to its first
    // downstream action so the user actually sees something run.
    let resolvedId = upToNodeId;
    const selfNode = nodes.find((n) => n.id === upToNodeId);
    if (selfNode && canvasOnly.has(selfNode.type ?? "")) {
      // Viewer-like canvas nodes usually terminate the graph, so resolve to their first
      // upstream action. Source-like nodes resolve to first downstream action.
      const firstUpstreamEdge = edges.find(
        (e) => e.target === upToNodeId
             && !canvasOnly.has(nodes.find((n) => n.id === e.source)?.type ?? ""),
      );
      if (firstUpstreamEdge) {
        resolvedId = firstUpstreamEdge.source;
      } else {
        const firstDownstreamEdge = edges.find(
          (e) => e.source === upToNodeId
               && !canvasOnly.has(nodes.find((n) => n.id === e.target)?.type ?? ""),
        );
        if (!firstDownstreamEdge) return; // no action connected, nothing to run
        resolvedId = firstDownstreamEdge.target;
      }
    }

    // Compute the ancestor set of resolvedId in the action-only graph (BFS backwards)
    const actionNodes = filterExecutionNodes(nodes);
    const actionEdges = filterExecutionEdges(edges, nodes);

    const ancestors = new Set<string>([resolvedId]);
    let changed = true;
    while (changed) {
      changed = false;
      for (const e of actionEdges) {
        if (ancestors.has(e.target) && !ancestors.has(e.source)) {
          ancestors.add(e.source);
          changed = true;
        }
      }
    }

    const partialNodes = actionNodes.filter((n) => ancestors.has(n.id));
    const partialEdges = actionEdges.filter(
      (e) => ancestors.has(e.source) && ancestors.has(e.target),
    );

    // Launch using the last test input; if none yet, open the dialog first
    const { initialState } = testInputRef.current;
    if (Object.keys(initialState).length === 0) {
      // Queue the partial run after the dialog completes by storing intent
      setRunToStepPending(resolvedId);
      setTestRunOpen(true);
      return;
    }
    runTestStream(initialState, partialNodes, partialEdges);
  }, [nodes, edges, nodeConfigs]); // eslint-disable-line react-hooks/exhaustive-deps

  // Helper: what fields does a node expect to receive from pipeline_state?
  const getNodeExpectedInputs = useCallback((nodeId: string): string[] => {
    const cfg = nodeConfigs[nodeId];
    if (!cfg) return [];
    const fieldMappings = (cfg.params?.field_mappings as FieldMappingRow[] | undefined) ?? [];
    const fromMapping = fieldMappings
      .map((fm) => fm.statePath?.trim() ?? "")
      .filter(Boolean)
      .map((path) => path.match(/^(\w+)/)?.[1] ?? path);
    const fromPorts = SUBGRAPH_IO[cfg.subgraphId]?.reads ?? [];
    return [...new Set([...fromMapping, ...fromPorts])];
  }, [nodeConfigs]);

  const getViewerTraceSnapshot = useCallback((viewerNodeId: string): ViewerTraceSnapshot => {
    const activeTrace = selectedBatchTrace ?? testTrace;
    if (!activeTrace) return { step: null, source: null, candidateId: null };
    const sourceType: "batch" | "single" = selectedBatchTrace ? "batch" : "single";
    const allNodes = nodesRef.current;
    const allEdges = edgesRef.current.filter((e) => e.target === viewerNodeId);
    for (const edge of allEdges) {
      const sourceNode = allNodes.find((n) => n.id === edge.source);
      if (!sourceNode || isCanvasOnlyNodeType(sourceNode.type ?? "")) continue;
      const step = activeTrace[sourceNode.id] ?? null;
      if (step) {
        return {
          step,
          source: sourceType,
          candidateId: selectedBatchCandidateId,
        };
      }
    }
    return {
      step: null,
      source: sourceType,
      candidateId: selectedBatchCandidateId,
    };
  }, [selectedBatchTrace, selectedBatchCandidateId, testTrace]);

  const handleSave = useCallback(async (statusOverride?: string) => {
    setSaveError(null);
    setIsSaving(true);
    const effectiveStatus = statusOverride ?? planStatus;
    const liveNodes = nodesRef.current;
    const liveEdges = edgesRef.current;
    const liveNodeConfigs = nodeConfigsRef.current;
    const payload: Record<string, unknown> = {
      name: planName,
      status: effectiveStatus,
      description: planDescription,
      // Include version notes when publishing so the backend can snapshot them.
      ...(effectiveStatus === "active" && versionNotes ? { versionNotes } : {}),
      trigger: triggerEvent ? { event: triggerEvent, type: "data-changed" } : undefined,
      // Source + output nodes are canvas-only — saved separately so they survive
      // save/reload without confusing the backend execution engine.
      sourceNodes: liveNodes.filter((n) => n.type === "source").map((n) => ({
        id: n.id,
        position: n.position,
        data: { ...(n.data as Record<string, unknown>), onConfigure: undefined },
      })),
      outputNodes: liveNodes.filter((n) => n.type === "output").map((n) => ({
        id: n.id,
        position: n.position,
        data: { ...(n.data as Record<string, unknown>), onConfigure: undefined },
      })),
      viewerNodes: liveNodes.filter((n) => n.type === "viewer").map((n) => ({
        id: n.id,
        position: n.position,
        data: { ...(n.data as Record<string, unknown>), onConfigure: undefined },
      })),
      actions: liveNodes.filter((n) => !isCanvasOnlyNodeType(n.type ?? "")).map((n) => {
        const subgraphId = (n.data as unknown as ActionNodeData).subgraphId;
        const cfg = { ...(liveNodeConfigs[n.id] ?? {}) };
        // Derive output_target for persist nodes from connected output nodes so that
        // the canvas wiring (not a separate config field) controls write destination.
        if (subgraphId === "persist" && !cfg.outputTarget) {
          (cfg as Record<string, unknown>).outputTarget = resolveOutputTarget(n.id, liveNodes, liveEdges);
        }
        return {
          id: n.id,
          subgraphId,
          label: (n.data as unknown as ActionNodeData).label,
          nodeType: (cfg.nodeType || n.type || "action"),
          position: n.position,
          config: cfg,
        };
      }),
      // Action-to-action edges — the backend uses these for execution ordering.
      edges: liveEdges
        .filter((e) => {
          const srcNode = liveNodes.find((n) => n.id === e.source);
          const tgtNode = liveNodes.find((n) => n.id === e.target);
          return !isCanvasOnlyNodeType(srcNode?.type ?? "")
              && !isCanvasOnlyNodeType(tgtNode?.type ?? "");
        })
        .map((e) => ({
          source: e.source,
          target: e.target,
          sourceHandle: e.sourceHandle,
          targetHandle: e.targetHandle,
        })),
      // Canvas-only edges (source/output/viewer connections) — persisted for UI restore.
      canvasEdges: liveEdges
        .filter((e) => {
          const srcNode = liveNodes.find((n) => n.id === e.source);
          const tgtNode = liveNodes.find((n) => n.id === e.target);
          return isCanvasOnlyNodeType(srcNode?.type ?? "")
              || isCanvasOnlyNodeType(tgtNode?.type ?? "");
        })
        .map((e) => ({
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
        if (statusOverride) setPlanStatus(statusOverride);
        setLastSaved(new Date());
      }
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "Failed to save pathway");
    } finally {
      setIsSaving(false);
    }
  }, [planName, planStatus, planDescription, triggerEvent, versionNotes, isNew, planId, router]);

  const handlePublish = useCallback(() => {
    const errCount = validationWarnings.filter((w) => w.severity === "error").length;
    if (errCount > 0) {
      setSaveError(`Fix ${errCount} validation error${errCount > 1 ? "s" : ""} before publishing to live.`);
      return;
    }
    setVersionNotes("");
    setPublishDialogOpen(true);
  }, [validationWarnings]);

  const confirmPublish = useCallback(async () => {
    await handleSave("active");
    setPublishDialogOpen(false);
  }, [handleSave]);

  const handleDeletePathway = useCallback(async () => {
    setIsDeletingPathway(true);
    setSaveError(null);
    try {
      await api.delete(`/fhir/PlanDefinition/${planId}`);
      router.push("/admin/clinical?tab=pathways");
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "Failed to delete pathway");
    } finally {
      setIsDeletingPathway(false);
    }
  }, [planId, router]);

  const loadHistory = useCallback(() => {
    if (isNew) return;
    setHistoryLoading(true);
    api.get<{ entry: Array<{ resource: { meta: { versionId: string; lastUpdated: string; versionNotes: string }; status: string; name: string } }> }>(
      `/fhir/PlanDefinition/${planId}/_history`,
    )
      .then((data) => {
        const mapped = (data.entry || []).map((e) => ({
          versionId: Number(e.resource.meta.versionId),
          publishedAt: e.resource.meta.lastUpdated,
          versionNotes: e.resource.meta.versionNotes,
          status: e.resource.status,
          name: e.resource.name,
        }));
        mapped.sort((a, b) => {
          const byDate = compareIsoDateTimeDesc(a.publishedAt, b.publishedAt);
          if (byDate !== 0) return byDate;
          return b.versionId - a.versionId;
        });
        setVersions(mapped);
      })
      .catch(() => setVersions([]))
      .finally(() => setHistoryLoading(false));
  }, [isNew, planId]);

  const openHistory = useCallback(() => {
    setHistoryOpen(true);
    loadHistory();
  }, [loadHistory]);

  const handleRestore = useCallback(async (vid: number) => {
    setRestoringVid(vid);
    try {
      await api.post(`/fhir/PlanDefinition/${planId}/_restore/${vid}`, {});
      // Re-fetch the plan from the server instead of doing a hard reload
      const data = await api.get<PlanData>(`/fhir/PlanDefinition/${planId}`);
      setPlanName(data.name || "");
      setPlanDescription(data.description || "");
      setPlanStatus(data.status || "active");
      const trig = (data as any).trigger;
      if (trig?.event) setTriggerEvent(trig.event);
      const configs: Record<string, ActionConfig> = {};
      const restoredNodes: Node[] = (data.actions || [])
        .filter((a) => !isCanvasOnlyNodeType(a.nodeType))
        .map((a, i) => {
        const cfg = hydrateActionConfig(a);
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
            config: cfg,
            fieldMappings: (cfg.params.field_mappings as FieldMappingRow[]) ?? [],
            onConfigure: () => openConfigurator(a.id),
          },
        };
      });
      // Restore source nodes
      const versionSourceNodes = ((data as unknown as Record<string, unknown>).sourceNodes as Array<{ id: string; position: { x: number; y: number }; data: Record<string, unknown> }>) || [];
      const versionOutputNodes = ((data as unknown as Record<string, unknown>).outputNodes as Array<{ id: string; position: { x: number; y: number }; data: Record<string, unknown> }>) || [];
      const versionViewerNodes = ((data as unknown as Record<string, unknown>).viewerNodes as Array<{ id: string; position: { x: number; y: number }; data: Record<string, unknown> }>) || [];
      const restoredCanvasNodes = [
        ...restoredNodes,
        ...versionSourceNodes.map((sn) => ({
          id: sn.id, type: "source" as const, position: sn.position,
          data: { ...sn.data, onConfigure: () => setSourceConfigOpen(sn.id) },
        })),
        ...versionOutputNodes.map((on) => ({
          id: on.id, type: "output" as const, position: on.position,
          data: { ...on.data, onConfigure: () => setOutputConfigOpen(on.id) },
        })),
        ...versionViewerNodes.map((vn) => ({
          id: vn.id, type: "viewer" as const, position: vn.position,
          data: { ...vn.data, onConfigure: () => setViewerConfigOpen(vn.id) },
        })),
      ];
      nodeConfigsRef.current = configs;
      nodesRef.current = restoredCanvasNodes;
      setNodeConfigs(configs);
      setNodes(restoredCanvasNodes);
      const restoredLegacySourceEdges = ((data as unknown as Record<string, unknown>).sourceEdges as PersistedCanvasEdge[]) || [];
      const restoredCanvasEdgePayload = ((data as unknown as Record<string, unknown>).canvasEdges as PersistedCanvasEdge[]) || [];
      const allRestoredEdges: PersistedCanvasEdge[] = [
        ...(data.edges || []),
        ...(restoredCanvasEdgePayload.length > 0 ? restoredCanvasEdgePayload : restoredLegacySourceEdges),
      ];
      const restoredCanvasEdges = allRestoredEdges.map((e, i) => ({
        id: `e${i}-${e.source}-${e.target}`,
        source: e.source,
        target: e.target,
        sourceHandle: e.sourceHandle ?? e.source_handle ?? null,
        targetHandle: e.targetHandle ?? e.target_handle ?? null,
        type: "portEdge",
        data: { label: e.sourceHandle || e.source_handle || e.targetHandle || e.target_handle || "" },
      }));
      edgesRef.current = restoredCanvasEdges;
      setEdges(restoredCanvasEdges);
      setLastSaved(new Date());
      setHistoryOpen(false);
    } catch {
      setSaveError(`Failed to restore version v${vid}. Please try again.`);
    } finally {
      setRestoringVid(null);
    }
  }, [planId, openConfigurator, setNodes, setEdges]);

  const executionNodeCount = useMemo(
    () => filterExecutionNodes(nodes).length,
    [nodes],
  );

  return (
    <Box sx={{ height: "100vh", display: "flex", flexDirection: "column" }}>
      <Box sx={{ px: 2, py: 1.25, display: "flex", alignItems: "center", gap: 1.5, borderBottom: 1, borderColor: "divider", overflowX: "auto", flexShrink: 0 }}>
        <IconButton size="small" onClick={() => router.push("/admin/clinical?tab=pathways")} sx={{ flexShrink: 0 }}><ArrowBackIcon /></IconButton>
        <TextField
          size="small" placeholder="Pathway name" value={planName}
          onChange={(e) => setPlanName(e.target.value)} sx={{ width: 200, flexShrink: 0 }}
        />
        {/* Status badge — read-only display; changed via Publish / Retire */}
        <Chip
          size="small"
          label={planStatus.charAt(0).toUpperCase() + planStatus.slice(1)}
          color={planStatus === "active" ? "success" : planStatus === "retired" ? "default" : "warning"}
          variant="outlined"
          sx={{ fontWeight: 600, fontSize: "0.72rem", flexShrink: 0 }}
        />
        {/* Retire action */}
        {planStatus !== "retired" && (
          <Tooltip title="Mark this pathway as retired (no longer in use)">
            <Button size="small" variant="text" color="inherit"
              sx={{ textTransform: "none", fontSize: "0.72rem", color: "text.disabled", minWidth: 0, px: 1, flexShrink: 0 }}
              onClick={() => handleSave("retired")}
            >
              Retire
            </Button>
          </Tooltip>
        )}
        <Box sx={{ flex: 1, minWidth: 8 }} />
        {/* Save draft — always safe, never changes live status */}
        <Button
          variant="outlined"
          size="small"
          startIcon={isSaving ? <CircularProgress size={13} color="inherit" /> : <SaveIcon />}
          disabled={isSaving}
          onClick={() => handleSave()}
          sx={{ textTransform: "none", minWidth: 100, flexShrink: 0 }}
        >
          {isSaving ? "Saving…" : "Save draft"}
        </Button>
        {/* Publish — validates first, sets status=active */}
        <Tooltip title={planStatus === "active" ? "Re-publish to apply latest draft changes to live" : "Validate and publish this pathway to live"}>
          <span style={{ flexShrink: 0 }}>
            <Button
              variant="contained"
              size="small"
              color="success"
              startIcon={<CloudUploadIcon />}
              disabled={isSaving}
              onClick={handlePublish}
              sx={{ textTransform: "none", minWidth: 90 }}
            >
              Publish
            </Button>
          </span>
        </Tooltip>
        <Divider orientation="vertical" flexItem sx={{ mx: 0.5 }} />
        {/* Last-saved indicator */}
        {!isSaving && lastSaved && (
          <Typography variant="caption" color="text.disabled" sx={{ fontSize: "0.7rem", flexShrink: 0, whiteSpace: "nowrap" }}>
            Saved {formatSaveTime(lastSaved)}
          </Typography>
        )}
        {saveError && (
          <Alert severity="error" sx={{ py: 0, fontSize: "0.72rem", flexShrink: 0 }} onClose={() => setSaveError(null)}>
            {saveError}
          </Alert>
        )}
        {/* Add data source — creates a fan-out source node on the canvas */}
        <FormControl size="small" sx={{ minWidth: 160, flexShrink: 0 }}>
          <InputLabel>Add a data source</InputLabel>
          <Select label="Add a data source" value="" onChange={(e) => { if (e.target.value) addSourceNode(e.target.value as SourceType); }}>
            <MenuItem value="">Add a data source…</MenuItem>
            {(Object.entries(SOURCE_DEFINITIONS) as [SourceType, typeof SOURCE_DEFINITIONS[SourceType]][]).map(([type, meta]) => (
              <MenuItem key={type} value={type}>
                <Box>
                  <Typography variant="body2">{meta.label}</Typography>
                  <Typography variant="caption" color="text.secondary">{meta.description}</Typography>
                </Box>
              </MenuItem>
            ))}
          </Select>
        </FormControl>

        {/* Add output destination — creates a sink node on the canvas; includes canvas-only viewer */}
        <FormControl size="small" sx={{ minWidth: 160, flexShrink: 0 }}>
          <InputLabel>Add an output</InputLabel>
          <Select
            label="Add an output"
            value=""
            onChange={(e) => {
              const val = e.target.value;
              if (!val) return;
              if (val === "__viewer__") { addViewerNode(); return; }
              addOutputNode(val as OutputType);
            }}
          >
            <MenuItem value="">Add an output…</MenuItem>
            {(Object.entries(OUTPUT_DEFINITIONS) as [OutputType, typeof OUTPUT_DEFINITIONS[OutputType]][]).map(([type, meta]) => (
              <MenuItem key={type} value={type}>
                <Box>
                  <Typography variant="body2">{meta.label}</Typography>
                  <Typography variant="caption" color="text.secondary">{meta.description}</Typography>
                </Box>
              </MenuItem>
            ))}
            <Divider />
            <MenuItem value="__viewer__">
              <Box>
                <Typography variant="body2">Mini HITL viewer</Typography>
                <Typography variant="caption" color="text.secondary">Canvas-only preview node — inspect step output in context</Typography>
              </Box>
            </MenuItem>
          </Select>
        </FormControl>

        <FormControl size="small" sx={{ minWidth: 170, flexShrink: 0 }}>
          <InputLabel>Add a step</InputLabel>
          <Select label="Add a step" value="" onChange={(e) => addAction(e.target.value)}>
            <MenuItem value="">Add a step…</MenuItem>
            <MenuItem disabled sx={{ fontWeight: 700, opacity: 1 }}>Clinical Steps</MenuItem>
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
        {/* Auto-layout */}
        <Tooltip title="Auto-layout — rearrange steps into a tidy flow (top to bottom)">
          <IconButton size="small" onClick={autoLayout} sx={{ border: "1px solid", borderColor: "divider", borderRadius: 1.5, flexShrink: 0 }}>
            <AccountTreeIcon sx={{ fontSize: "1.1rem" }} />
          </IconButton>
        </Tooltip>
        {/* Test run */}
        {testTrace && (
          <Tooltip title="Clear test results">
              <IconButton size="small" onClick={() => { setTestTrace(null); setSelectedBatchTrace(null); setSelectedBatchCandidateId(null); setTestRunError(null); setProbedEdges(new Set()); }}
              sx={{ border: "1px solid", borderColor: "success.light", borderRadius: 1.5, color: "success.main", flexShrink: 0 }}>
              <CloseIcon sx={{ fontSize: "1rem" }} />
            </IconButton>
          </Tooltip>
        )}
        <Tooltip title="Dry-run the pipeline with sample data — opens the input dialog">
          <span style={{ flexShrink: 0 }}>
            <Button
              size="small"
              variant="outlined"
              color="success"
              startIcon={isTestRunning ? <CircularProgress size={13} color="inherit" /> : <PlayArrowIcon />}
              disabled={isTestRunning || executionNodeCount === 0}
              onClick={() => setTestRunOpen(true)}
              sx={{ textTransform: "none", minWidth: 85 }}
            >
              {isTestRunning ? "Running…" : "Test run"}
            </Button>
          </span>
        </Tooltip>
        <Tooltip title={
          testInputRef.current
            ? "Re-run every step with the same test input — stops at the first failure"
            : "Run all steps — opens the input dialog (no previous run yet)"
        }>
          <span style={{ flexShrink: 0 }}>
            <Button
              size="small"
              variant={testInputRef.current ? "contained" : "outlined"}
              color="success"
              startIcon={isTestRunning ? <CircularProgress size={13} color="inherit" /> : <PlayArrowIcon />}
              disabled={isTestRunning || executionNodeCount === 0}
              onClick={handleRunAllSteps}
              sx={{ textTransform: "none", minWidth: 100 }}
            >
              {isTestRunning ? "Running…" : "Run all steps"}
            </Button>
          </span>
        </Tooltip>
        <Tooltip title="Batch dry-run — run the draft pathway against real Training Candidates from the Knowledge Graph">
          <span style={{ flexShrink: 0 }}>
            <Button
              size="small"
              variant="outlined"
              color="secondary"
              startIcon={isBatchRunning ? <CircularProgress size={13} color="inherit" /> : <PlayArrowIcon />}
              disabled={isBatchRunning || isTestRunning || executionNodeCount === 0}
              onClick={() => setBatchPanelOpen(true)}
              sx={{ textTransform: "none", minWidth: 100 }}
            >
              {isBatchRunning ? "Running…" : "Batch dry run"}
            </Button>
          </span>
        </Tooltip>
        {/* Version history */}
        {!isNew && (
          <Tooltip title="Version history — view and restore previous published versions">
            <IconButton size="small" onClick={openHistory} sx={{ border: "1px solid", borderColor: "divider", borderRadius: 1.5, flexShrink: 0 }}>
              <HistoryIcon sx={{ fontSize: "1.1rem" }} />
            </IconButton>
          </Tooltip>
        )}
        {!isNew && (
          <Tooltip title={isSeededPathway ? "Seeded pathways cannot be deleted from the UI" : "Delete this pathway permanently"}>
            <span style={{ flexShrink: 0 }}>
              <Button
                variant="outlined"
                size="small"
                color="error"
                startIcon={<DeleteOutlineIcon />}
                disabled={isSaving || isDeletingPathway || isSeededPathway}
                onClick={() => { setDeleteConfirmText(""); setDeleteDialogOpen(true); }}
                sx={{ textTransform: "none", minWidth: 90 }}
              >
                Delete
              </Button>
            </span>
          </Tooltip>
        )}
      </Box>

      <TriggerContextPanel
        triggerEvent={triggerEvent}
        onTriggerChange={setTriggerEvent}
        planId={planId}
        planDescription={planDescription}
        onDescriptionChange={setPlanDescription}
      />

      <ValidationPanel warnings={validationWarnings} />

      {selectedNode && (
        <Paper variant="outlined" sx={{ mx: 2, mt: 1, p: 1.5, borderRadius: 2 }}>
          <Stack direction="row" spacing={2} alignItems="flex-start" sx={{ flexWrap: "wrap" }}>
            <Box sx={{ minWidth: 220 }}>
              <Typography variant="caption" color="text.secondary">Selected step</Typography>
              <Typography variant="body2" fontWeight={700}>{selectedNodeLabel}</Typography>
            </Box>
            <Box sx={{ minWidth: 280 }}>
              <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                Incoming wires
              </Typography>
              {inboundConnections.length === 0 ? (
                <Typography variant="caption" color="text.disabled">None</Typography>
              ) : (
                <Stack spacing={0.25}>
                  {inboundConnections.map((conn, idx) => (
                    <Typography key={`in-${idx}`} variant="caption" sx={{ fontFamily: "monospace" }}>
                      {`${conn.sourceLabel}.${conn.sourceHandle} -> this.${conn.targetHandle}`}
                    </Typography>
                  ))}
                </Stack>
              )}
            </Box>
            <Box sx={{ minWidth: 280 }}>
              <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                Outgoing wires
              </Typography>
              {outboundConnections.length === 0 ? (
                <Typography variant="caption" color="text.disabled">None</Typography>
              ) : (
                <Stack spacing={0.25}>
                  {outboundConnections.map((conn, idx) => (
                    <Typography key={`out-${idx}`} variant="caption" sx={{ fontFamily: "monospace" }}>
                      {`this.${conn.sourceHandle} -> ${conn.targetLabel}.${conn.targetHandle}`}
                    </Typography>
                  ))}
                </Stack>
              )}
            </Box>
          </Stack>
        </Paper>
      )}

      <Box sx={{ flex: 1, minHeight: 0 }}>
        <PipelineTestContext.Provider value={{
          testTrace,
          runningStepId,
          isTestRunning,
          haltedNodeId,
          probedEdges,
          toggleProbe,
          runToStep,
          getNodeExpectedInputs,
          getViewerTraceSnapshot,
        }}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={pathwayNodeTypes}
            edgeTypes={edgeTypes}
            onNodesChange={onNodesChange}
            onEdgesChange={handleEdgesChange}
            onConnect={onConnect}
            fitView
          >
            <Background />
            <Controls />
            <MiniMap />
          </ReactFlow>
        </PipelineTestContext.Provider>
      </Box>

      {/* Node configuration dialog — wizard stays open while canvas is visible behind */}
      <Dialog
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        maxWidth={false}
        PaperProps={{ sx: { width: "min(1100px, 96vw)", height: "94vh", display: "flex", flexDirection: "column", borderRadius: 3, overflow: "hidden" } }}
      >
        {selectedNode && (
          <ActionConfigurator
            key={`${selectedNode}-${drawerKey}`}
            nodeId={selectedNode}
            initialConfig={selectedConfig}
            onSave={handleConfigSave}
            onDelete={handleDeleteNode}
            onClose={() => setDrawerOpen(false)}
            onPathwaySave={handleSave}
            prevStepWrites={prevStepWrites}
            prevStepFieldMappings={prevStepFieldMappings}
            prevStepSources={prevStepSources}
            inboundConnections={inboundConnections}
          />
        )}
      </Dialog>

      {/* ── Version history drawer ───────────────────────────────────────── */}
      <Drawer
        anchor="right"
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
        PaperProps={{ sx: { width: 380, display: "flex", flexDirection: "column" } }}
      >
        {/* Header */}
        <Box sx={{ px: 2.5, py: 2, borderBottom: 1, borderColor: "divider", flexShrink: 0 }}>
          <Stack direction="row" alignItems="center" spacing={1}>
            <HistoryIcon color="action" />
            <Box sx={{ flex: 1 }}>
              <Typography variant="subtitle1" fontWeight={700}>Version history</Typography>
              <Typography variant="caption" color="text.secondary">{planName}</Typography>
            </Box>
            <IconButton size="small" onClick={() => setHistoryOpen(false)}><CloseIcon fontSize="small" /></IconButton>
          </Stack>
        </Box>

        {/* Version list */}
        <Box sx={{ flex: 1, overflowY: "auto", py: 1 }}>
          {historyLoading ? (
            <Stack alignItems="center" sx={{ pt: 4, gap: 1 }}>
              <CircularProgress size={24} />
              <Typography variant="caption" color="text.secondary">Loading versions…</Typography>
            </Stack>
          ) : versions.length === 0 ? (
            <Box sx={{ px: 2.5, pt: 4, textAlign: "center" }}>
              <Typography color="text.secondary" variant="body2">No published versions yet.</Typography>
              <Typography variant="caption" color="text.disabled" sx={{ mt: 0.5, display: "block" }}>
                Click "Publish" to create the first live version.
              </Typography>
            </Box>
          ) : (
            <List disablePadding>
              {versions.map((v, i) => (
                <ListItem
                  key={v.versionId}
                  disableGutters
                  sx={{ px: 2.5, py: 1.25, borderBottom: "1px solid", borderColor: "divider", alignItems: "flex-start" }}
                >
                  <Box sx={{ flex: 1 }}>
                    <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 0.4 }}>
                      {/* Version badge */}
                      <Chip
                        label={`v${v.versionId}`}
                        size="small"
                        color={i === 0 ? "success" : "default"}
                        sx={{ height: 20, fontSize: "0.65rem", fontWeight: 700 }}
                      />
                      {i === 0 && (
                        <Typography sx={{ fontSize: "0.62rem", color: "success.main", fontWeight: 700 }}>
                          ● Live
                        </Typography>
                      )}
                    </Stack>
                    <Typography variant="caption" color="text.secondary" sx={{ display: "block", fontSize: "0.68rem" }}>
                      {formatVersionDate(v.publishedAt)}
                    </Typography>
                    {v.versionNotes && (
                      <Typography variant="caption" sx={{ display: "block", mt: 0.5, color: "text.primary", fontSize: "0.72rem", fontStyle: "italic" }}>
                        "{v.versionNotes}"
                      </Typography>
                    )}
                  </Box>
                  {/* Restore button — only for non-current versions */}
                  {i > 0 && (
                    <Tooltip title={`Restore v${v.versionId} to live — creates a new version entry`}>
                      <span>
                        <Button
                          size="small"
                          variant="outlined"
                          color="warning"
                          startIcon={restoringVid === v.versionId ? <CircularProgress size={11} color="inherit" /> : <ReplayIcon sx={{ fontSize: "0.9rem !important" }} />}
                          disabled={restoringVid !== null}
                          onClick={() => handleRestore(v.versionId)}
                          sx={{ textTransform: "none", fontSize: "0.7rem", mt: 0.5 }}
                        >
                          Restore
                        </Button>
                      </span>
                    </Tooltip>
                  )}
                </ListItem>
              ))}
            </List>
          )}
        </Box>

        {/* Footer note */}
        <Box sx={{ px: 2.5, py: 1.5, borderTop: 1, borderColor: "divider", bgcolor: "grey.50", flexShrink: 0 }}>
          <Typography variant="caption" color="text.disabled" sx={{ fontSize: "0.67rem" }}>
            Restoring creates a new v{(versions[0]?.versionId ?? 0) + 1} entry — history is never deleted.
          </Typography>
        </Box>
      </Drawer>

      {/* ── Source node configurator dialog ──────────────────────────────── */}
      <Dialog
        open={Boolean(sourceConfigOpen)}
        onClose={() => setSourceConfigOpen(null)}
        maxWidth="xs"
        fullWidth
        PaperProps={{ sx: { borderRadius: 3 } }}
      >
        {sourceConfigOpen && (() => {
          const sourceNode = nodes.find((n) => n.id === sourceConfigOpen);
          if (!sourceNode) return null;
          return (
            <SourceConfiguratorContent
              nodeId={sourceConfigOpen}
              nodeData={sourceNode.data as Record<string, unknown>}
              onUpdate={(patch) =>
                setNodes((nds) => nds.map((n) =>
                  n.id === sourceConfigOpen ? { ...n, data: { ...n.data, ...patch } } : n
                ))
              }
              onClose={() => setSourceConfigOpen(null)}
              onRemove={() => {
                setNodes((nds) => nds.filter((n) => n.id !== sourceConfigOpen));
                setEdges((eds) => eds.filter((e) => e.source !== sourceConfigOpen));
                setSourceConfigOpen(null);
              }}
            />
          );
        })()}
      </Dialog>

      {/* ── Output node configurator dialog ──────────────────────────────── */}
      <Dialog
        open={Boolean(outputConfigOpen)}
        onClose={() => setOutputConfigOpen(null)}
        maxWidth="xs"
        fullWidth
        PaperProps={{ sx: { borderRadius: 3 } }}
      >
        {outputConfigOpen && (() => {
          const outputNode = nodes.find((n) => n.id === outputConfigOpen);
          if (!outputNode) return null;
          const d = outputNode.data as {
            outputType?: OutputType;
            label?: string;
            pubsub_topic?: string;
            pubsub_routing_key?: string;
            webhook_url?: string;
            inputs?: string[];
          };
          const outputType: OutputType = d.outputType ?? "pubsub_publish";
          const meta = OUTPUT_DEFINITIONS[outputType];
          return (
            <>
              <Box sx={{ px: 3, pt: 2.5, pb: 1, overflowY: "auto", maxHeight: "80vh" }}>
                <Typography variant="h6" fontWeight={700} gutterBottom>Output destination</Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                  This node represents where data leaves this pathway. Wire outputs from upstream steps to its input handle.
                </Typography>

                {/* Output type picker */}
                <Stack spacing={1.5} sx={{ mb: 2 }}>
                  {(Object.entries(OUTPUT_DEFINITIONS) as [OutputType, typeof OUTPUT_DEFINITIONS[OutputType]][]).map(([type, m]) => (
                    <Paper
                      key={type}
                      variant="outlined"
                      onClick={() =>
                        setNodes((nds) => nds.map((n) =>
                          n.id === outputConfigOpen
                            ? { ...n, data: { ...n.data, outputType: type, label: m.label, inputs: m.inputs } }
                            : n
                        ))
                      }
                      sx={{
                        p: 1.5, cursor: "pointer", borderRadius: 2,
                        borderColor: outputType === type ? m.color : "divider",
                        borderWidth: outputType === type ? 2 : 1,
                        bgcolor: outputType === type ? `${m.color}10` : "transparent",
                      }}
                    >
                      <Typography variant="body2" fontWeight={outputType === type ? 700 : 500}>{m.label}</Typography>
                      <Typography variant="caption" color="text.secondary">{m.description}</Typography>
                    </Paper>
                  ))}
                </Stack>

                <Paper variant="outlined" sx={{ p: 2, borderRadius: 2 }}>
                  {outputType === "pubsub_publish" && (
                    <Stack spacing={1.5}>
                      <Typography variant="subtitle2" fontWeight={700}>Topic / queue settings</Typography>
                      <TextField
                        size="small" fullWidth label="Topic name"
                        placeholder="e.g. hl7v2.coded.results  or  nhs.clinical.processed"
                        value={d.pubsub_topic || ""}
                        onChange={(e) =>
                          setNodes((nds) => nds.map((n) =>
                            n.id === outputConfigOpen ? { ...n, data: { ...n.data, pubsub_topic: e.target.value } } : n
                          ))
                        }
                      />
                      <TextField
                        size="small" fullWidth label="Routing key (optional)"
                        placeholder="e.g. coded.encounter"
                        value={d.pubsub_routing_key || ""}
                        onChange={(e) =>
                          setNodes((nds) => nds.map((n) =>
                            n.id === outputConfigOpen ? { ...n, data: { ...n.data, pubsub_routing_key: e.target.value } } : n
                          ))
                        }
                      />
                    </Stack>
                  )}
                  {outputType === "webhook" && (
                    <Stack spacing={1.5}>
                      <Typography variant="subtitle2" fontWeight={700}>Endpoint settings</Typography>
                      <TextField
                        size="small" fullWidth label="Webhook URL"
                        placeholder="https://your-service.example.com/webhook"
                        value={d.webhook_url || ""}
                        onChange={(e) =>
                          setNodes((nds) => nds.map((n) =>
                            n.id === outputConfigOpen ? { ...n, data: { ...n.data, webhook_url: e.target.value } } : n
                          ))
                        }
                      />
                    </Stack>
                  )}
                </Paper>
              </Box>
              <Box sx={{ px: 3, pb: 2.5, pt: 1.5, display: "flex", justifyContent: "space-between", alignItems: "center", borderTop: 1, borderColor: "divider" }}>
                <Button size="small" color="error" sx={{ textTransform: "none" }}
                  onClick={() => {
                    setNodes((nds) => nds.filter((n) => n.id !== outputConfigOpen));
                    setEdges((eds) => eds.filter((e) => e.target !== outputConfigOpen));
                    setOutputConfigOpen(null);
                  }}
                >
                  Remove output node
                </Button>
                <Button variant="contained" onClick={() => setOutputConfigOpen(null)} sx={{ textTransform: "none" }}>
                  Done
                </Button>
              </Box>
            </>
          );
        })()}
      </Dialog>

      {/* ── Mini HITL viewer configurator dialog ─────────────────────────── */}
      <Dialog
        open={Boolean(viewerConfigOpen)}
        onClose={() => setViewerConfigOpen(null)}
        maxWidth="xs"
        fullWidth
        PaperProps={{ sx: { borderRadius: 3 } }}
      >
        {viewerConfigOpen && (() => {
          const viewerNode = nodes.find((n) => n.id === viewerConfigOpen);
          if (!viewerNode) return null;
          const d = viewerNode.data as { label?: string; mode?: ViewerMode };
          return (
            <>
              <Box sx={{ px: 3, pt: 2.5, pb: 1, overflowY: "auto", maxHeight: "80vh" }}>
                <Typography variant="h6" fontWeight={700} gutterBottom>Mini HITL viewer</Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                  Canvas-only preview node for inspecting upstream outputs in a familiar HITL-style view.
                </Typography>
                <Stack spacing={1.5}>
                  <TextField
                    size="small"
                    label="Title"
                    value={d.label || "Mini HITL"}
                    onChange={(e) =>
                      setNodes((nds) => nds.map((n) =>
                        n.id === viewerConfigOpen ? { ...n, data: { ...n.data, label: e.target.value } } : n
                      ))
                    }
                  />
                  <TextField
                    select
                    size="small"
                    label="Display mode"
                    value={d.mode || "auto"}
                    onChange={(e) =>
                      setNodes((nds) => nds.map((n) =>
                        n.id === viewerConfigOpen ? { ...n, data: { ...n.data, mode: e.target.value as ViewerMode } } : n
                      ))
                    }
                    SelectProps={{ native: true }}
                  >
                    <option value="auto">Auto</option>
                    <option value="entities">Entities focus</option>
                    <option value="verification">Verification focus</option>
                    <option value="surface_forms">Surface forms focus</option>
                    <option value="json">Raw JSON</option>
                  </TextField>
                </Stack>
              </Box>
              <Box sx={{ px: 3, pb: 2.5, pt: 1.5, display: "flex", justifyContent: "space-between", alignItems: "center", borderTop: 1, borderColor: "divider" }}>
                <Button size="small" color="error" sx={{ textTransform: "none" }}
                  onClick={() => {
                    setNodes((nds) => nds.filter((n) => n.id !== viewerConfigOpen));
                    setEdges((eds) => eds.filter((e) => e.source !== viewerConfigOpen && e.target !== viewerConfigOpen));
                    setViewerConfigOpen(null);
                  }}
                >
                  Remove viewer node
                </Button>
                <Button variant="contained" onClick={() => setViewerConfigOpen(null)} sx={{ textTransform: "none" }}>
                  Done
                </Button>
              </Box>
            </>
          );
        })()}
      </Dialog>

      {/* ── Edge deletion confirmation dialog ────────────────────────────── */}
      <Dialog open={Boolean(pendingDeleteEdges)} onClose={() => setPendingDeleteEdges(null)} maxWidth="xs" fullWidth
        PaperProps={{ sx: { borderRadius: 3 } }}>
        <Box sx={{ px: 3, pt: 2.5, pb: 1 }}>
          <Typography variant="h6" fontWeight={700} gutterBottom>Remove connection?</Typography>
          <Typography variant="body2" color="text.secondary">
            Disconnecting this wire means the next step will no longer receive data from this one. You can reconnect it on the canvas at any time.
          </Typography>
        </Box>
        <Box sx={{ px: 3, pb: 2.5, pt: 1.5, display: "flex", justifyContent: "flex-end", gap: 1 }}>
          <Button onClick={() => setPendingDeleteEdges(null)} sx={{ textTransform: "none" }}>Keep connected</Button>
          <Button variant="contained" color="error" onClick={confirmEdgeDeletion} sx={{ textTransform: "none" }}>
            Remove connection
          </Button>
        </Box>
      </Dialog>

      {/* ── Publish confirmation dialog ───────────────────────────────────── */}
      {(() => {
        const errCount  = validationWarnings.filter((w) => w.severity === "error").length;
        const warnCount = validationWarnings.filter((w) => w.severity === "warning").length;
        const stepCount = nodes.length;
        return (
          <Dialog
            open={publishDialogOpen}
            onClose={() => !isSaving && setPublishDialogOpen(false)}
            maxWidth="xs"
            fullWidth
            PaperProps={{ sx: { borderRadius: 3 } }}
          >
            <Box sx={{ px: 3, pt: 2.5, pb: 1, borderBottom: 1, borderColor: "divider" }}>
              <Stack direction="row" alignItems="center" spacing={1}>
                <CloudUploadIcon color="success" />
                <Typography variant="h6" fontWeight={700}>Publish to live</Typography>
              </Stack>
              <Typography variant="caption" color="text.secondary">
                {planName || "This pathway"} will immediately be used by the runtime for new executions.
              </Typography>
            </Box>

            <Box sx={{ px: 3, py: 2 }}>
              {/* Validation summary */}
              <Stack spacing={0.75} sx={{ mb: 2 }}>
                <Stack direction="row" justifyContent="space-between">
                  <Typography variant="caption" color="text.secondary">Pipeline steps</Typography>
                  <Typography variant="caption" fontWeight={600}>{stepCount}</Typography>
                </Stack>
                <Stack direction="row" justifyContent="space-between">
                  <Typography variant="caption" color="text.secondary">Validation errors</Typography>
                  <Typography variant="caption" fontWeight={600} color={errCount > 0 ? "error.main" : "success.main"}>
                    {errCount === 0 ? "None ✓" : `${errCount} error${errCount > 1 ? "s" : ""}`}
                  </Typography>
                </Stack>
                {warnCount > 0 && (
                  <Stack direction="row" justifyContent="space-between">
                    <Typography variant="caption" color="text.secondary">Warnings</Typography>
                    <Typography variant="caption" fontWeight={600} color="warning.main">{warnCount}</Typography>
                  </Stack>
                )}
              </Stack>

              <Alert severity="info" icon={false} sx={{ mb: 2, fontSize: "0.75rem" }}>
                To roll back: edit the pathway, adjust the steps, and publish again.
                For a clean rollback, duplicate a known-good version as a new draft and publish that.
              </Alert>

              <TextField
                label="Version notes (optional)"
                placeholder="e.g. Added verification step before persist; updated extraction prompt to v3"
                multiline
                minRows={2}
                fullWidth
                size="small"
                value={versionNotes}
                onChange={(e) => setVersionNotes(e.target.value)}
              />
            </Box>

            <Box sx={{ px: 3, pb: 2.5, display: "flex", justifyContent: "flex-end", gap: 1 }}>
              <Button onClick={() => setPublishDialogOpen(false)} disabled={isSaving} sx={{ textTransform: "none" }}>
                Cancel
              </Button>
              <Button
                variant="contained"
                color="success"
                disabled={isSaving}
                startIcon={isSaving ? <CircularProgress size={13} color="inherit" /> : <CloudUploadIcon />}
                onClick={confirmPublish}
                sx={{ textTransform: "none" }}
              >
                {isSaving ? "Publishing…" : "Publish to live"}
              </Button>
            </Box>
          </Dialog>
        );
      })()}

      <Dialog
        open={deleteDialogOpen}
        onClose={() => !isDeletingPathway && setDeleteDialogOpen(false)}
        maxWidth="sm"
        fullWidth
        PaperProps={{ sx: { borderRadius: 3 } }}
      >
        <Box sx={{ px: 3, pt: 2.5, pb: 1, borderBottom: 1, borderColor: "divider" }}>
          <Stack direction="row" alignItems="center" spacing={1}>
            <DeleteOutlineIcon color="error" />
            <Typography variant="h6" fontWeight={700}>Delete pathway permanently?</Typography>
          </Stack>
          <Typography variant="caption" color="text.secondary">
            {deleteConfirmTarget} will be removed from the admin UI and deleted from Neo4j.
          </Typography>
        </Box>

        <Box sx={{ px: 3, py: 2 }}>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            This deletes the pathway definition, its linked actions, and its saved version history from Neo4j.
            This cannot be undone.
          </Typography>
          {planStatus === "active" && (
            <Alert severity="warning" sx={{ mb: 2 }}>
              This pathway is currently live. Deleting it may stop future runtime processing that depends on it.
            </Alert>
          )}
          <Alert severity="error" icon={false} sx={{ mb: 2, fontSize: "0.78rem" }}>
            Type the pathway name exactly to unlock permanent deletion.
          </Alert>
          <TextField
            label="Confirm pathway name"
            fullWidth
            size="small"
            autoFocus
            value={deleteConfirmText}
            onChange={(e) => setDeleteConfirmText(e.target.value)}
            disabled={isDeletingPathway}
            helperText={`Type "${deleteConfirmTarget}" to confirm.`}
          />
        </Box>

        <Box sx={{ px: 3, pb: 2.5, display: "flex", justifyContent: "flex-end", gap: 1 }}>
          <Button onClick={() => setDeleteDialogOpen(false)} disabled={isDeletingPathway} sx={{ textTransform: "none" }}>
            Cancel
          </Button>
          <Button
            variant="contained"
            color="error"
            disabled={isDeletingPathway || deleteConfirmText.trim() !== deleteConfirmTarget}
            startIcon={isDeletingPathway ? <CircularProgress size={13} color="inherit" /> : <DeleteOutlineIcon />}
            onClick={handleDeletePathway}
            sx={{ textTransform: "none" }}
          >
            {isDeletingPathway ? "Deleting…" : "Delete pathway permanently"}
          </Button>
        </Box>
      </Dialog>

      {/* ── Test-run dialog ──────────────────────────────────────────────── */}
      <TestRunDialog
        open={testRunOpen}
        onClose={() => setTestRunOpen(false)}
        onRun={handleTestRunDialogRun}
        isRunning={isTestRunning}
        sourceNodes={nodes.filter((n) => n.type === "source")}
      />

      {/* ── Batch dry-run panel ───────────────────────────────────────────── */}
      <Dialog
        open={batchPanelOpen}
        onClose={() => { if (!isBatchRunning) setBatchPanelOpen(false); }}
        maxWidth="md"
        fullWidth
        PaperProps={{ sx: { maxHeight: "80vh" } }}
      >
        <DialogTitle sx={{ pb: 1, display: "flex", alignItems: "center", gap: 1 }}>
          <PlayArrowIcon sx={{ color: "secondary.main" }} />
          Batch dry run — Training Candidates
          <Box sx={{ flexGrow: 1 }} />
          {!isBatchRunning && (
            <IconButton size="small" onClick={() => setBatchPanelOpen(false)}>
              <CloseIcon fontSize="small" />
            </IconButton>
          )}
        </DialogTitle>

        <DialogContent dividers sx={{ p: 2 }}>
          {/* Controls */}
          {!isBatchRunning && batchResults.length === 0 && (
            <Box sx={{ display: "flex", gap: 2, alignItems: "flex-end", mb: 2, flexWrap: "wrap" }}>
              <TextField
                label="Max candidates"
                type="number"
                size="small"
                value={batchLimit}
                onChange={(e) => setBatchLimit(Math.max(1, Math.min(100, Number(e.target.value))))}
                inputProps={{ min: 1, max: 100 }}
                sx={{ width: 140 }}
              />
              <TextField
                label="Status filter"
                select
                size="small"
                value={batchStatusFilter}
                onChange={(e) => setBatchStatusFilter(e.target.value)}
                sx={{ width: 160 }}
                SelectProps={{ native: true }}
              >
                <option value="pending">Pending</option>
                <option value="completed">Completed</option>
                <option value="failed">Failed</option>
                <option value="">All</option>
              </TextField>
              <TextField
                label="Concurrency"
                type="number"
                size="small"
                value={batchConcurrency}
                onChange={(e) => setBatchConcurrency(Math.max(1, Math.min(10, Number(e.target.value))))}
                inputProps={{ min: 1, max: 10 }}
                sx={{ width: 120 }}
                helperText="1–10 in parallel"
              />
              <Typography variant="caption" color="text.secondary" sx={{ maxWidth: 260 }}>
                Runs the draft pathway against real candidates in dry-run mode — nothing will be saved. Higher concurrency tests throughput but may hit LLM rate limits.
              </Typography>
            </Box>
          )}

          {/* Summary bar */}
          {batchSummary && (
            <Box sx={{ display: "flex", gap: 1, mb: 2, flexWrap: "wrap", alignItems: "center" }}>
              <Chip label={`${batchSummary.total} total`} size="small" />
              <Chip label={`✓ ${batchSummary.passed} passed`} size="small" color="success" />
              {batchSummary.halted > 0 && <Chip label={`🛑 ${batchSummary.halted} halted`} size="small" color="error" />}
              {batchSummary.errored > 0 && <Chip label={`✗ ${batchSummary.errored} errored`} size="small" color="warning" />}
              {batchRunId && <Chip label={`Run ${batchRunId.slice(0, 8)}`} size="small" variant="outlined" />}
            </Box>
          )}
          {selectedBatchCandidateId && (
            <Alert severity="info" sx={{ mb: 2, fontSize: "0.78rem" }}>
              Inspecting batch candidate <strong>{selectedBatchCandidateId}</strong> on the canvas mini HITL node.
            </Alert>
          )}

          {/* Live per-step funnel */}
          {(isBatchRunning || batchSummary) && Object.keys(batchStepCounts).length > 0 && (
            <Box sx={{ mb: 2 }}>
              <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600, mb: 0.5, display: "block" }}>
                Pipeline steps — live counts
              </Typography>
              <Box component="table" sx={{ width: "100%", borderCollapse: "collapse", fontSize: "0.78rem" }}>
                <Box component="thead">
                  <Box component="tr" sx={{ "& th": { p: "3px 8px", textAlign: "left", color: "text.secondary", fontWeight: 600, borderBottom: "1px solid", borderColor: "divider" } }}>
                    <Box component="th">Step</Box>
                    <Box component="th" sx={{ textAlign: "right" }}>Ran</Box>
                    <Box component="th" sx={{ textAlign: "right" }}>Passed through</Box>
                    <Box component="th" sx={{ textAlign: "right" }}>Halted here</Box>
                  </Box>
                </Box>
                <Box component="tbody">
                  {Object.entries(batchStepCounts).map(([sgId, stat]) => {
                    const passedThrough = stat.ran - stat.halted;
                    const haltPct = stat.ran > 0 ? (stat.halted / stat.ran) * 100 : 0;
                    return (
                      <Box component="tr" key={sgId} sx={{ "& td": { p: "3px 8px", borderBottom: "1px solid", borderColor: "divider" } }}>
                        <Box component="td">{stat.label}</Box>
                        <Box component="td" sx={{ textAlign: "right", color: "text.secondary" }}>{stat.ran}</Box>
                        <Box component="td" sx={{ textAlign: "right", color: "success.main" }}>{passedThrough}</Box>
                        <Box component="td" sx={{ textAlign: "right", color: stat.halted > 0 ? "error.main" : "text.disabled", fontWeight: stat.halted > 0 ? 700 : 400 }}>
                          {stat.halted > 0 ? `🛑 ${stat.halted} (${haltPct.toFixed(0)}%)` : "—"}
                        </Box>
                      </Box>
                    );
                  })}
                </Box>
              </Box>
            </Box>
          )}

          {/* Progress bar */}
          {isBatchRunning && (
            <LinearProgress
              variant={batchResults.length === 0 ? "indeterminate" : "determinate"}
              value={batchResults.filter((r) => r.status !== "running").length / Math.max(1, batchResults.length) * 100}
              sx={{ mb: 1, borderRadius: 1 }}
            />
          )}

          {/* Results table */}
          {batchResults.length > 0 && (
            <Box sx={{ overflowY: "auto", maxHeight: 420 }}>
              <Box component="table" sx={{ width: "100%", borderCollapse: "collapse", fontSize: "0.82rem" }}>
                <Box component="thead">
                  <Box component="tr" sx={{ borderBottom: "2px solid", borderColor: "divider", "& th": { p: "6px 8px", textAlign: "left", color: "text.secondary", fontWeight: 600 } }}>
                    <Box component="th">#</Box>
                    <Box component="th">Text preview</Box>
                    <Box component="th">Result</Box>
                    <Box component="th">Stopped at</Box>
                    <Box component="th">Why halted</Box>
                    <Box component="th" sx={{ textAlign: "right" }}>Time</Box>
                    <Box component="th" sx={{ textAlign: "right" }}>Inspect</Box>
                  </Box>
                </Box>
                <Box component="tbody">
                  {batchResults.map((r) => (
                    <Box
                      component="tr"
                      key={r.candidate_id}
                      sx={{
                        borderBottom: "1px solid",
                        borderColor: "divider",
                        bgcolor: r.status === "completed" ? "success.50" : r.status === "halted" ? "error.50" : r.status === "running" ? "action.hover" : "warning.50",
                        "& td": { p: "6px 8px", verticalAlign: "middle" },
                      }}
                    >
                      <Box component="td" sx={{ color: "text.secondary" }}>{r.index}</Box>
                      <Box component="td" sx={{ maxWidth: 280, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        <Tooltip title={r.text_preview}><span>{r.text_preview}</span></Tooltip>
                      </Box>
                      <Box component="td">
                        {r.status === "running" && <CircularProgress size={12} />}
                        {r.status === "completed" && <Typography variant="caption" color="success.main" fontWeight={700}>✓ Passed</Typography>}
                        {r.status === "halted" && <Typography variant="caption" color="error.main" fontWeight={700}>🛑 Halted</Typography>}
                        {r.status === "error" && <Typography variant="caption" color="warning.main" fontWeight={700}>✗ Error</Typography>}
                      </Box>
                      <Box component="td" sx={{ color: "text.secondary" }}>
                        {r.halted_at ?? (r.error ? r.error.slice(0, 60) : "—")}
                      </Box>
                      <Box component="td" sx={{ color: "text.secondary", maxWidth: 260 }}>
                        {r.status === "halted" ? (
                          (() => {
                            const details: string[] = [];
                            if (typeof r.verification_confidence === "number") {
                              const thresholdText = typeof r.verification_threshold === "number"
                                ? ` / ${r.verification_threshold.toFixed(2)}`
                                : "";
                              details.push(`confidence ${r.verification_confidence.toFixed(2)}${thresholdText}`);
                            }
                            if (r.verification_is_accurate === false) details.push("is_accurate=false");
                            if (r.halt_reason) details.push(r.halt_reason);
                            const issueText = (r.verification_issues ?? []).slice(0, 2).join("; ");
                            const text = [details.join(", "), issueText].filter(Boolean).join(" — ");
                            if (!text) return "Verification gate failed";
                            return (
                              <Tooltip title={text}>
                                <span style={{ display: "inline-block", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 240 }}>
                                  {text}
                                </span>
                              </Tooltip>
                            );
                          })()
                        ) : "—"}
                      </Box>
                      <Box component="td" sx={{ textAlign: "right", color: "text.secondary", whiteSpace: "nowrap" }}>
                        {r.duration_ms > 0 ? `${(r.duration_ms / 1000).toFixed(1)}s` : "—"}
                      </Box>
                      <Box component="td" sx={{ textAlign: "right" }}>
                        <Button
                          size="small"
                          variant={selectedBatchCandidateId === r.candidate_id ? "contained" : "outlined"}
                          disabled={batchTraceLoadingId === r.candidate_id || r.status === "running"}
                          onClick={() => inspectBatchCandidate(r)}
                          sx={{ textTransform: "none", minWidth: 90, fontSize: "0.7rem" }}
                        >
                          {batchTraceLoadingId === r.candidate_id ? "Loading..." : (r.trace_saved ? "Inspect" : "Replay")}
                        </Button>
                      </Box>
                    </Box>
                  ))}
                </Box>
              </Box>
            </Box>
          )}

          {batchResults.length === 0 && !isBatchRunning && !batchSummary && (
            <Typography variant="body2" color="text.secondary">
              Configure the options above and click <strong>Run batch</strong> to start.
            </Typography>
          )}
        </DialogContent>

        <DialogActions sx={{ p: 2, gap: 1 }}>
          {!isBatchRunning && (
            <Button
              variant="contained"
              color="secondary"
              startIcon={<PlayArrowIcon />}
              onClick={handleBatchRun}
              disabled={executionNodeCount === 0}
            >
              {batchResults.length > 0 ? "Run again" : "Run batch"}
            </Button>
          )}
          {isBatchRunning && (
            <Typography variant="caption" color="text.secondary">
              Running {batchResults.filter((r) => r.status !== "running").length} / {batchResults.length} …
            </Typography>
          )}
          <Box sx={{ flexGrow: 1 }} />
          <Button onClick={() => { if (!isBatchRunning) setBatchPanelOpen(false); }} disabled={isBatchRunning}>
            Close
          </Button>
        </DialogActions>
      </Dialog>

      {/* Test-run error banner */}
      {testRunError && (
        <Box sx={{ position: "fixed", bottom: 24, left: "50%", transform: "translateX(-50%)", zIndex: 2000 }}>
          <Alert severity="error" onClose={() => setTestRunError(null)} sx={{ minWidth: 340 }}>
            {testRunError}
          </Alert>
        </Box>
      )}

      {/* Probe monitors are rendered inline on edges via PortEdge/EdgeLabelRenderer */}
    </Box>
  );
}
