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
  type NodeTypes,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { api } from "@/lib/api";

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

const SUBGRAPH_IO: Record<string, { reads: string[]; writes: string[] }> = {
  extraction: { reads: ["encounter_text"], writes: ["entities", "sentences", "errors"] },
  post_processing: { reads: ["entities", "encounter_text"], writes: ["entities", "errors"] },
  verification: { reads: ["entities", "encounter_text"], writes: ["is_verified", "verification_result", "errors"] },
  terminology: { reads: ["entities"], writes: ["entities", "errors"] },
  tier_classify: { reads: ["entities"], writes: ["entities", "tier_decisions"] },
  persist: { reads: ["entities", "encounter_id", "patient_id", "output_target"], writes: ["documents_written", "training_labels_written"] },
  sbar: { reads: ["entities", "encounter_text", "patient_id"], writes: ["sbar_report"] },
  compliance: { reads: ["entities"], writes: ["compliance_result"] },
  anchor_detect: { reads: ["entities"], writes: ["anchors"] },
  episode_build: { reads: ["entities", "patient_id"], writes: ["episodes"] },
  safety_net: { reads: ["entities", "patient_id"], writes: ["safety_net_alerts"] },
  quality_check: { reads: ["entities"], writes: ["quality_issues"] },
  next_best_action: { reads: ["entities", "patient_id"], writes: ["recommendations"] },
};

const TRIGGER_OPTIONS = [
  { id: "encounter-created", label: "New Encounter Created", description: "Fires when a new GP encounter document is ingested." },
  { id: "referral-received", label: "Referral Received", description: "Fires when a referral letter is uploaded or received via integration." },
  { id: "training-run-requested", label: "Training Run Requested", description: "Manual trigger — used to generate gold-standard NER training data." },
  { id: "results-received", label: "Investigation Results Received", description: "Fires when lab results or diagnostic reports arrive." },
  { id: "safety-net-check", label: "Safety Net Timer", description: "Scheduled check for overdue investigations and follow-ups." },
  { id: "manual", label: "Manual / API Call", description: "Pipeline is invoked manually via the API or admin UI." },
];

const WIZARD_STEPS = ["Subgraph", "Inputs", "Configuration", "Prompt", "Review"];

interface ActionConfig {
  subgraphId: string;
  label: string;
  description: string;
  inputSource: string;
  outputTarget: string;
  enableVerification: boolean;
  maxRetries: number;
  promptConfigId: string;
  modelProvider: string;
  modelName: string;
  temperature: number;
  timeout: number;
}

const DEFAULT_CONFIG: ActionConfig = {
  subgraphId: "",
  label: "",
  description: "",
  inputSource: "previous_step",
  outputTarget: "patient_graph",
  enableVerification: false,
  maxRetries: 2,
  promptConfigId: "",
  modelProvider: "auto",
  modelName: "",
  temperature: 0.0,
  timeout: 120,
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

const nodeTypes: NodeTypes = { action: ActionNode };

interface PlanData {
  id: string;
  name: string;
  status: string;
  description: string;
  actions: Array<{
    id: string;
    subgraphId: string;
    label: string;
    position?: { x: number; y: number };
    config?: Partial<ActionConfig>;
  }>;
  edges: Array<{ source: string; target: string }>;
}

function ActionConfigurator({
  nodeId,
  initialConfig,
  onSave,
  onDelete,
  onClose,
}: {
  nodeId: string;
  initialConfig: ActionConfig;
  onSave: (nodeId: string, config: ActionConfig) => void;
  onDelete: (nodeId: string) => void;
  onClose: () => void;
}) {
  const [step, setStep] = useState(0);
  const [config, setConfig] = useState<ActionConfig>(initialConfig);

  const subgraph = SUBGRAPH_OPTIONS.find((s) => s.id === config.subgraphId);
  const canProceed = step === 0 ? !!config.subgraphId && !!config.label : true;

  const updateField = <K extends keyof ActionConfig>(key: K, value: ActionConfig[K]) => {
    setConfig((prev) => ({ ...prev, [key]: value }));
  };

  const handleSubgraphChange = (id: string) => {
    const opt = SUBGRAPH_OPTIONS.find((s) => s.id === id);
    setConfig((prev) => ({
      ...prev,
      subgraphId: id,
      label: prev.label || opt?.label || "",
      description: prev.description || opt?.description || "",
    }));
  };

  const handleSaveAndClose = () => {
    onSave(nodeId, config);
    onClose();
  };

  return (
    <Box sx={{ width: 440, p: 3, display: "flex", flexDirection: "column", height: "100%" }}>
      <Typography variant="h6" fontWeight={600} gutterBottom>Configure Action</Typography>
      <Typography variant="caption" color="text.secondary" sx={{ mb: 2 }}>
        {nodeId}
      </Typography>

      <Stepper activeStep={step} alternativeLabel sx={{ mb: 3 }}>
        {WIZARD_STEPS.map((label) => (
          <Step key={label}>
            <StepLabel>{label}</StepLabel>
          </Step>
        ))}
      </Stepper>

      <Box sx={{ flex: 1, overflowY: "auto", mb: 2 }}>
        {step === 0 && (
          <Stack spacing={2.5}>
            <Typography variant="subtitle2">Which subgraph should this action run?</Typography>
            <FormControl fullWidth size="small">
              <InputLabel>Subgraph</InputLabel>
              <Select
                value={config.subgraphId}
                label="Subgraph"
                onChange={(e) => handleSubgraphChange(e.target.value)}
              >
                {SUBGRAPH_OPTIONS.map((s) => (
                  <MenuItem key={s.id} value={s.id}>
                    <Stack>
                      <Typography variant="body2">{s.label}</Typography>
                      <Typography variant="caption" color="text.secondary">{s.id}</Typography>
                    </Stack>
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            {subgraph && (
              <Alert severity="info" icon={false} sx={{ fontSize: "0.8rem" }}>
                {subgraph.description}
              </Alert>
            )}
            <TextField
              label="Display name"
              size="small"
              fullWidth
              value={config.label}
              onChange={(e) => updateField("label", e.target.value)}
              helperText="A friendly name shown on the pathway canvas."
            />
            <TextField
              label="Description"
              size="small"
              fullWidth
              multiline
              minRows={2}
              value={config.description}
              onChange={(e) => updateField("description", e.target.value)}
              helperText="What does this step do in plain English?"
            />
          </Stack>
        )}

        {step === 1 && (
          <Stack spacing={2.5}>
            <Typography variant="subtitle2">Where does this step get its data?</Typography>
            <FormControl fullWidth size="small">
              <InputLabel>Input source</InputLabel>
              <Select
                value={config.inputSource}
                label="Input source"
                onChange={(e) => updateField("inputSource", e.target.value)}
              >
                <MenuItem value="previous_step">Previous step output</MenuItem>
                <MenuItem value="encounter_text">Raw encounter text</MenuItem>
                <MenuItem value="patient_graph">Patient Graph (Neo4j)</MenuItem>
                <MenuItem value="knowledge_graph">Knowledge Graph (Neo4j)</MenuItem>
              </Select>
            </FormControl>
            <Divider />
            <Typography variant="subtitle2">Where should results be written?</Typography>
            <FormControl fullWidth size="small">
              <InputLabel>Output target</InputLabel>
              <Select
                value={config.outputTarget}
                label="Output target"
                onChange={(e) => updateField("outputTarget", e.target.value)}
              >
                <MenuItem value="patient_graph">Patient Graph</MenuItem>
                <MenuItem value="gold_training">Gold Training Dataset</MenuItem>
                <MenuItem value="next_step">Pass to next step only</MenuItem>
              </Select>
            </FormControl>
          </Stack>
        )}

        {step === 2 && (
          <Stack spacing={2.5}>
            <Typography variant="subtitle2">Runtime settings</Typography>
            <FormControlLabel
              control={
                <Switch
                  checked={config.enableVerification}
                  onChange={(e) => updateField("enableVerification", e.target.checked)}
                />
              }
              label="Enable verification (big model confirms output)"
            />
            <TextField
              label="Max retries on failure"
              type="number"
              size="small"
              fullWidth
              value={config.maxRetries}
              onChange={(e) => updateField("maxRetries", Math.max(0, Math.min(5, Number(e.target.value))))}
              inputProps={{ min: 0, max: 5 }}
              helperText="How many times to retry if this step fails (0–5)."
            />
            <TextField
              label="Timeout (seconds)"
              type="number"
              size="small"
              fullWidth
              value={config.timeout}
              onChange={(e) => updateField("timeout", Math.max(10, Number(e.target.value)))}
              inputProps={{ min: 10 }}
              helperText="Maximum time to wait before timing out."
            />
          </Stack>
        )}

        {step === 3 && (
          <Stack spacing={2.5}>
            <Typography variant="subtitle2">LLM / prompt settings</Typography>
            <Typography variant="body2" color="text.secondary">
              If this action uses an LLM, configure the model and prompt here. Leave blank for
              non-LLM steps (like post-processing or persist).
            </Typography>
            <FormControl fullWidth size="small">
              <InputLabel>Model provider</InputLabel>
              <Select
                value={config.modelProvider}
                label="Model provider"
                onChange={(e) => updateField("modelProvider", e.target.value)}
              >
                <MenuItem value="auto">Auto (platform default)</MenuItem>
                <MenuItem value="aws_bedrock">AWS Bedrock</MenuItem>
                <MenuItem value="azure_openai">Azure OpenAI</MenuItem>
              </Select>
            </FormControl>
            <TextField
              label="Model name (optional)"
              size="small"
              fullWidth
              value={config.modelName}
              onChange={(e) => updateField("modelName", e.target.value)}
              helperText='e.g. "claude-3-haiku" or "gpt-5-mini". Leave blank for platform default.'
            />
            <TextField
              label="Temperature"
              type="number"
              size="small"
              fullWidth
              value={config.temperature}
              onChange={(e) => updateField("temperature", Math.max(0, Math.min(2, Number(e.target.value))))}
              inputProps={{ min: 0, max: 2, step: 0.1 }}
            />
            <Divider />
            <TextField
              label="Prompt Config ID (from Neo4j)"
              size="small"
              fullWidth
              value={config.promptConfigId}
              onChange={(e) => updateField("promptConfigId", e.target.value)}
              helperText={
                <>
                  Link a PromptConfig stored in Neo4j. Manage prompts in{" "}
                  <Typography
                    component="a"
                    href="/admin/prompts"
                    variant="caption"
                    color="primary"
                    sx={{ textDecoration: "underline" }}
                  >
                    Prompt Tuner
                  </Typography>.
                </>
              }
            />
          </Stack>
        )}

        {step === 4 && (
          <Stack spacing={2}>
            <Typography variant="subtitle2">Review your configuration</Typography>
            <Paper variant="outlined" sx={{ p: 2 }}>
              <Stack spacing={1}>
                <ReviewRow label="Subgraph" value={subgraph?.label || config.subgraphId} />
                <ReviewRow label="Display name" value={config.label} />
                <ReviewRow label="Description" value={config.description || "—"} />
                <Divider />
                <ReviewRow label="Input" value={config.inputSource.replace(/_/g, " ")} />
                <ReviewRow label="Output" value={config.outputTarget.replace(/_/g, " ")} />
                <Divider />
                <ReviewRow label="Verification" value={config.enableVerification ? "Enabled" : "Disabled"} />
                <ReviewRow label="Max retries" value={String(config.maxRetries)} />
                <ReviewRow label="Timeout" value={`${config.timeout}s`} />
                <Divider />
                <ReviewRow label="Model" value={config.modelProvider === "auto" ? "Platform default" : `${config.modelProvider} / ${config.modelName || "default"}`} />
                <ReviewRow label="Temperature" value={String(config.temperature)} />
                <ReviewRow label="Prompt config" value={config.promptConfigId || "—"} />
              </Stack>
            </Paper>
          </Stack>
        )}
      </Box>

      <Divider sx={{ mb: 2 }} />

      <Stack direction="row" justifyContent="space-between">
        <Tooltip title="Remove this action from the pathway">
          <IconButton color="error" onClick={() => { onDelete(nodeId); onClose(); }}>
            <DeleteOutlineIcon />
          </IconButton>
        </Tooltip>
        <Stack direction="row" spacing={1}>
          {step > 0 && (
            <Button size="small" onClick={() => setStep((s) => s - 1)}>Back</Button>
          )}
          {step < WIZARD_STEPS.length - 1 ? (
            <Button size="small" variant="contained" disabled={!canProceed} onClick={() => setStep((s) => s + 1)}>
              Next
            </Button>
          ) : (
            <Button size="small" variant="contained" color="success" onClick={handleSaveAndClose}>
              Save action
            </Button>
          )}
        </Stack>
      </Stack>
    </Box>
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
    const availableKeys = new Set(["encounter_text", "patient_id", "encounter_id", "run_id"]);

    for (const node of ordered) {
      const subgraphId = (node.data as ActionNodeData)?.subgraphId || "";
      const io = SUBGRAPH_IO[subgraphId];
      if (!io) continue;
      for (const key of io.reads) {
        if (!availableKeys.has(key) && !["patient_id", "encounter_id", "run_id"].includes(key)) {
          warnings.push({
            severity: "warning",
            message: `"${(node.data as ActionNodeData).label}" reads "${key}" but no upstream step produces it.`,
          });
        }
      }
      for (const wk of io.writes) availableKeys.add(wk);
    }

    const hasVerify = nodes.some(n => (n.data as ActionNodeData)?.subgraphId === "verification");
    const hasPersist = nodes.some(n => (n.data as ActionNodeData)?.subgraphId === "persist");
    const persistGold = nodes.some(n => {
      const cfg = nodeConfigs[n.id];
      return (n.data as ActionNodeData)?.subgraphId === "persist" && cfg?.outputTarget === "gold_training";
    });
    if (hasPersist && persistGold && !hasVerify) {
      warnings.push({
        severity: "error",
        message: "Persisting to Gold Training without a Verification step. Unverified data could corrupt training labels.",
      });
    }
    if (hasVerify && hasPersist) {
      const verifyIdx = ordered.findIndex(n => (n.data as ActionNodeData)?.subgraphId === "verification");
      const persistIdx = ordered.findIndex(n => (n.data as ActionNodeData)?.subgraphId === "persist");
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
        message: `"${(o.data as ActionNodeData).label}" has no incoming edge — it won't receive data from previous steps.`,
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
  const [nodeConfigs, setNodeConfigs] = useState<Record<string, ActionConfig>>({});
  const [saveError, setSaveError] = useState<string | null>(null);

  const validationWarnings = useValidationWarnings(nodes, edges, nodeConfigs, triggerEvent);

  const openConfigurator = useCallback((nodeId: string) => {
    setSelectedNode(nodeId);
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
            const cfg: ActionConfig = { ...DEFAULT_CONFIG, subgraphId: a.subgraphId, label: a.label || a.subgraphId, ...a.config };
            configs[a.id] = cfg;
            return {
              id: a.id,
              type: "action",
              position: a.position || { x: 250, y: 100 + i * 150 },
              data: {
                label: a.label || a.subgraphId,
                subgraphId: a.subgraphId,
                color: SUBGRAPH_OPTIONS.find((s) => s.id === a.subgraphId)?.color || "#999",
                config: a.config,
                onConfigure: () => openConfigurator(a.id),
              },
            };
          });
          setNodeConfigs(configs);
          setNodes(loadedNodes);
          setEdges((data.edges || []).map((e, i) => ({ id: `e${i}`, source: e.source, target: e.target })));
        })
        .catch(() => {});
    }
  }, [planId, isNew, setNodes, setEdges, openConfigurator]);

  const onConnect = useCallback((connection: Connection) => {
    setEdges((eds) => addEdge(connection, eds));
  }, [setEdges]);

  const addAction = useCallback((subgraphId: string) => {
    const option = SUBGRAPH_OPTIONS.find((s) => s.id === subgraphId);
    if (!option) return;
    const id = `action_${Date.now()}`;
    const cfg: ActionConfig = { ...DEFAULT_CONFIG, subgraphId, label: option.label, description: option.description };
    setNodeConfigs((prev) => ({ ...prev, [id]: cfg }));
    const newNode: Node = {
      id,
      type: "action",
      position: { x: 250, y: (nodes.length + 1) * 150 },
      data: {
        label: option.label,
        subgraphId: option.id,
        color: option.color,
        onConfigure: () => openConfigurator(id),
      },
    };
    setNodes((nds) => [...nds, newNode]);
  }, [nodes.length, setNodes, openConfigurator]);

  const handleConfigSave = useCallback((nodeId: string, config: ActionConfig) => {
    setNodeConfigs((prev) => ({ ...prev, [nodeId]: config }));
    const option = SUBGRAPH_OPTIONS.find((s) => s.id === config.subgraphId);
    setNodes((nds) =>
      nds.map((n) =>
        n.id === nodeId
          ? {
              ...n,
              data: {
                ...n.data,
                label: config.label,
                subgraphId: config.subgraphId,
                color: option?.color || "#999",
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

  const handleSave = useCallback(async () => {
    setSaveError(null);
    const payload = {
      name: planName,
      status: planStatus,
      description: planDescription,
      trigger: triggerEvent ? { event: triggerEvent, type: "data-changed" } : undefined,
      actions: nodes.map((n) => ({
        id: n.id,
        subgraphId: (n.data as ActionNodeData).subgraphId,
        label: (n.data as ActionNodeData).label,
        position: n.position,
        config: nodeConfigs[n.id] || {},
      })),
      edges: edges.map((e) => ({ source: e.source, target: e.target })),
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
            {SUBGRAPH_OPTIONS.map((s) => (
              <MenuItem key={s.id} value={s.id}>{s.label}</MenuItem>
            ))}
          </Select>
        </FormControl>
        <Button variant="contained" startIcon={<SaveIcon />} onClick={handleSave}>Save</Button>
      </Box>

      <TriggerContextPanel
        triggerEvent={triggerEvent}
        onTriggerChange={setTriggerEvent}
        planId={planId}
        planDescription={planDescription}
        onDescriptionChange={setPlanDescription}
      />

      <ValidationPanel warnings={validationWarnings} />

      <Box sx={{ flex: 1 }}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
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
      <Drawer anchor="right" open={drawerOpen} onClose={() => setDrawerOpen(false)}>
        {selectedNode && (
          <ActionConfigurator
            nodeId={selectedNode}
            initialConfig={selectedConfig}
            onSave={handleConfigSave}
            onDelete={handleDeleteNode}
            onClose={() => setDrawerOpen(false)}
          />
        )}
      </Drawer>
    </Box>
  );
}
