/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2C03CA0E
 *   DI: DI-3F771AFB
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C03CA0E")
 */
"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import Accordion from "@mui/material/Accordion";
import AccordionDetails from "@mui/material/AccordionDetails";
import AccordionSummary from "@mui/material/AccordionSummary";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Divider from "@mui/material/Divider";
import FormControlLabel from "@mui/material/FormControlLabel";
import IconButton from "@mui/material/IconButton";
import LinearProgress from "@mui/material/LinearProgress";
import Paper from "@mui/material/Paper";
import Radio from "@mui/material/Radio";
import RadioGroup from "@mui/material/RadioGroup";
import Stack from "@mui/material/Stack";
import Step from "@mui/material/Step";
import StepLabel from "@mui/material/StepLabel";
import Stepper from "@mui/material/Stepper";
import Switch from "@mui/material/Switch";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import Collapse from "@mui/material/Collapse";
import AddIcon from "@mui/icons-material/Add";
import BoltIcon from "@mui/icons-material/Bolt";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutline";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import GroupsIcon from "@mui/icons-material/Groups";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import PersonIcon from "@mui/icons-material/Person";
import RefreshIcon from "@mui/icons-material/Refresh";
import RocketLaunchIcon from "@mui/icons-material/RocketLaunch";
import SaveIcon from "@mui/icons-material/Save";
import SmartToyOutlinedIcon from "@mui/icons-material/SmartToyOutlined";
import StarIcon from "@mui/icons-material/Star";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";

// =============================================================================
// Types
// =============================================================================

// "provider:tier" e.g. "aws:small" | "azure:big" | "ner"
type ModelKey = string;

interface ModelPreset {
  preset_id: string;
  name: string;
  description: string;
  consensus_mode: boolean;
  primary_model: ModelKey;    // single: the model; dual: first model
  secondary_model: ModelKey;  // dual only: second model
  tiebreaker_model: ModelKey; // dual only: arbitrator
  extractor: string;          // "llm" | "ner" | "ner+llm"
  strict: boolean;
  prompt_config_id: string;
  color: string;
  /** Whether the model behind this preset honours the temperature parameter.
   *  GPT-5 and NER models do not. Claude on Bedrock does.
   *  Defaults to true for backwards compatibility with existing presets. */
  supports_temperature: boolean;
  is_default: boolean;
  is_system: boolean;
  created_at: string;
  updated_at: string;
}

interface Device {
  device_id: string;
  name: string;
  provider: string;
  device_type: "llm" | "ner" | "ml";
  role: string;
  status: "active" | "inactive";
  env_var: string;
  default_model_id: string;
  resolved_model_id: string;
  env_var_set: boolean;
  notes: string;
}

interface PipelineConfig {
  provider: string;
  tier: string;
  extractor_backend: string;
  strict: boolean;
  consensus_mode: boolean;
  source?: string;
}

interface ServiceConfig {
  key: string;
  category: string;
  displayName: string;
  description: string;
  config: Record<string, number>;
  source: string;
  updatedAt: string;
}

interface InferenceVersion {
  version: string;
  model_name: string;
  blob_path: string;
  schema_version: string;
  deid_version: string;
  size_bytes: number;
  uploaded_at: string;
  notes: string;
}

interface InferenceHealth {
  status: string;
  loaded: boolean;
  active_version: string | null;
  available_versions?: InferenceVersion[];
}

interface RegistryStatus {
  active_model: ModelVersionDetail | null;
  inference_service: InferenceHealth;
  total_versions: number;
}

interface ModelVersionDetail {
  model_name: string;
  model_version: string;
  model_path: string;
  artifact_uri: string;
  training_dataset_version: string;
  schema_version: string;
  deid_version: string;
  status: string;
  offline_precision: number | null;
  offline_recall: number | null;
  canary_precision: number | null;
  canary_recall: number | null;
  canary_cohort: string | null;
  rollback_target_version: string | null;
  registered_at: string;
  promoted_at: string | null;
  notes: string;
}

interface CanaryJob {
  job_id: string;
  version: string;
  status: "accepted" | "running" | "completed" | "failed";
  phase: string;
  message: string;
  progress?: number;
  processed_candidates?: number;
  total_candidates?: number;
  metrics?: {
    overall: { precision: number; recall: number; f1: number; tp: number; fp: number; fn: number };
    per_label: Array<{ label: string; precision: number; recall: number; f1: number; tp: number; fp: number; fn: number }>;
  };
  sentences_scored?: number;
}

// =============================================================================
// Constants
// =============================================================================

const TIER_OPTIONS = [
  { value: "small", label: "Fast",         desc: "Quick and cost-effective — best for most tasks." },
  { value: "big",   label: "Accurate",     desc: "More careful — better for complex records." },
  { value: "max",   label: "Most careful", desc: "Highest quality — used for checking and tuning." },
];

const PROVIDER_OPTIONS = [
  { value: "aws",   label: "Amazon (Claude)", desc: "AWS Bedrock — Claude models." },
  { value: "azure", label: "Microsoft (GPT)", desc: "Azure OpenAI — GPT models." },
];

const BACKEND_OPTIONS = [
  { value: "llm",   label: "AI assistant only",            desc: "The AI reads and labels text." },
  { value: "model", label: "Medical coder only",           desc: "The trained medical coder labels text." },
  { value: "auto",  label: "AI assistant + medical coder", desc: "Try the medical coder first, fall back to AI." },
];

// Maps registry status → plain label + stepper index
const LIFECYCLE_STAGES = [
  { key: "registered",        label: "Registered",     stepIdx: 0 },
  { key: "offline_validated", label: "Tests passed",   stepIdx: 1 },
  { key: "canary",            label: "Trial run",      stepIdx: 2 },
  { key: "promoted",          label: "Live",           stepIdx: 3 },
];
const LIFECYCLE_STEP_LABELS = ["Registered", "Tests passed", "Trial run", "Live"];

const VERSION_STATUS_CHIPS: Record<string, { label: string; color: "default" | "primary" | "warning" | "success" | "error" | "info" }> = {
  registered:        { label: "Waiting to be tested", color: "default" },
  offline_validated: { label: "Tests passed",         color: "info" },
  canary:            { label: "Trial run",             color: "warning" },
  promoted:          { label: "Live",                  color: "success" },
  rollback:          { label: "Rolled back",           color: "default" },
  deprecated:        { label: "Retired",               color: "error" },
};

// =============================================================================
// Helpers
// =============================================================================

async function apiFetch<T>(path: string, opts?: RequestInit): Promise<T> {
  const r = await fetch(path, {
    credentials: "include",
    headers: { "X-Requested-With": "XMLHttpRequest", "Content-Type": "application/json" },
    ...opts,
  });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

function pct(v: number | null | undefined) {
  return v == null ? "—" : `${Math.round(v * 100)}%`;
}

function f1(p: number | null, r: number | null): string {
  if (p == null || r == null) return "—";
  const denom = p + r;
  return denom <= 0 ? "0%" : pct((2 * p * r) / denom);
}

function fmtDate(iso: string | null | undefined) {
  if (!iso) return "—";
  try { return new Date(iso).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" }); } catch { return iso; }
}

function stepIdx(status: string): number {
  return LIFECYCLE_STAGES.find((s) => s.key === status)?.stepIdx ?? -1;
}

// =============================================================================
// SectionCard — collapsible card wrapping each top-level zone
// =============================================================================

function SectionCard({
  icon, title, description, action, children, defaultOpen = true,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
  action?: React.ReactNode;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <Card variant="outlined" sx={{ mb: 2.5, borderRadius: 2 }}>
      {/* Clickable header */}
      <Box
        onClick={() => setOpen((o) => !o)}
        sx={{ px: 2.5, pt: 2, pb: open ? 1 : 2, cursor: "pointer", "&:hover": { bgcolor: "action.hover" }, transition: "background-color 0.15s" }}
      >
        <Stack direction="row" alignItems="center" justifyContent="space-between">
          <Stack direction="row" alignItems="center" spacing={1.5}>
            {icon}
            <Box>
              <Typography variant="subtitle1" fontWeight={700} lineHeight={1.3}>{title}</Typography>
              {!open && (
                <Typography variant="caption" color="text.secondary">{description}</Typography>
              )}
            </Box>
          </Stack>
          <Stack direction="row" alignItems="center" spacing={1}>
            {/* action (e.g. button) — stop propagation so click doesn't toggle collapse */}
            {action && open && (
              <Box onClick={(e) => e.stopPropagation()}>{action}</Box>
            )}
            <IconButton size="small" sx={{ color: "text.secondary" }}>
              {open ? <ExpandLessIcon fontSize="small" /> : <ExpandMoreIcon fontSize="small" />}
            </IconButton>
          </Stack>
        </Stack>
        {open && (
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            {description}
          </Typography>
        )}
      </Box>
      <Collapse in={open}>
        <Divider />
        <Box sx={{ px: 2.5, pt: 2, pb: 2.5 }}>
          {children}
        </Box>
      </Collapse>
    </Card>
  );
}

// =============================================================================
// OptionCard — selectable tile used in routing config
// =============================================================================

function OptionCard({
  selected, onClick, icon, title, description, badge,
}: {
  selected: boolean; onClick: () => void; icon: React.ReactNode;
  title: string; description: string; badge?: string;
}) {
  return (
    <Paper
      variant="outlined"
      onClick={onClick}
      sx={{
        p: 2, flex: 1, cursor: "pointer", position: "relative",
        borderColor: selected ? "primary.main" : "divider",
        borderWidth: selected ? 2 : 1,
        bgcolor: selected ? "primary.50" : "background.paper",
        transition: "border-color 0.15s, background-color 0.15s",
        "&:hover": { borderColor: selected ? "primary.main" : "primary.light" },
      }}
    >
      {badge && (
        <Chip label={badge} size="small" color="success"
          sx={{ position: "absolute", top: 8, right: 8, height: 18, fontSize: "0.65rem", fontWeight: 700 }} />
      )}
      <Stack direction="row" spacing={1.5} alignItems="flex-start">
        <Box sx={{ mt: 0.25 }}>{icon}</Box>
        <Box>
          <Typography variant="body2" fontWeight={700}>{title}</Typography>
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.25 }}>
            {description}
          </Typography>
        </Box>
      </Stack>
    </Paper>
  );
}

// =============================================================================
// InferenceDeployPanel — live deployment control using inference service API
// =============================================================================

function InferenceDeployPanel({
  health, onReloaded,
}: {
  health: InferenceHealth | null;
  onReloaded: () => void;
}) {
  const [selectedVersion, setSelectedVersion] = useState("");
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const ok      = health?.status === "ok" && health?.loaded;
  const warn    = health?.status === "ok" && !health?.loaded;
  const offline = !health || health.status !== "ok";
  const active  = health?.active_version ?? null;
  const available = health?.available_versions ?? [];

  const handleLoad = async () => {
    if (!selectedVersion) return;
    setLoading(true); setMsg(null); setErr(null);
    try {
      const resp = await apiFetch<{ active_version: string; elapsed_ms: number }>(
        "/api/model-registry/inference/reload",
        { method: "POST", body: JSON.stringify({ version: selectedVersion }) },
      );
      setMsg(`Loaded version ${resp.active_version} in ${Math.round((resp.elapsed_ms ?? 0) / 1000)}s.`);
      setSelectedVersion("");
      onReloaded();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not load — check the inference service.");
    } finally { setLoading(false); }
  };

  return (
    <Card variant="outlined" sx={{
      mb: 1.5,
      borderColor: ok ? "success.main" : warn ? "warning.main" : "divider",
      borderWidth: ok || warn ? 1.5 : 1,
    }}>
      <CardContent sx={{ py: 1.5, "&:last-child": { pb: 2 } }}>
        {/* Status row */}
        <Stack direction="row" alignItems="center" spacing={2} sx={{ mb: ok || warn ? 1.5 : 0 }}>
          {offline ? <ErrorOutlineIcon color="disabled" /> :
           ok      ? <CheckCircleIcon color="success" /> :
                     <WarningAmberIcon color="warning" />}
          <Box sx={{ flex: 1 }}>
            <Typography variant="subtitle2">Medical coding model (NER service)</Typography>
            <Typography variant="body2" color="text.secondary">
              {offline
                ? "Not running — start the NER inference service to use it"
                : ok
                ? `Running — version ${active} is loaded and ready`
                : "Service running but no model loaded yet"}
            </Typography>
          </Box>
          <Chip
            label={offline ? "Offline" : ok ? "Online" : "No model loaded"}
            color={offline ? "default" : ok ? "success" : "warning"}
            size="small" variant={ok ? "filled" : "outlined"}
          />
        </Stack>

        {/* Deploy controls — only when service is reachable */}
        {!offline && available.length > 0 && (
          <>
            <Divider sx={{ mb: 1.5 }} />
            <Typography variant="body2" fontWeight={600} sx={{ mb: 0.5 }}>
              Load a version
            </Typography>
            <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
              Choose a version from the blob store and load it into the running service immediately.
              The currently loaded version will be replaced.
            </Typography>
            <Stack direction="row" spacing={1.5} alignItems="center">
              <RadioGroup
                row
                value={selectedVersion}
                onChange={(e) => setSelectedVersion(e.target.value)}
              >
                {available.map((v) => (
                  <Paper key={v.version} variant="outlined" onClick={() => setSelectedVersion(v.version)}
                    sx={{
                      px: 1.5, py: 1, mr: 1, cursor: "pointer",
                      borderColor: selectedVersion === v.version ? "primary.main" : "divider",
                      borderWidth: selectedVersion === v.version ? 2 : 1,
                      bgcolor: selectedVersion === v.version ? "primary.50" : "background.paper",
                    }}>
                    <FormControlLabel value={v.version} control={<Radio size="small" />}
                      label={
                        <Box>
                          <Stack direction="row" spacing={0.5} alignItems="center">
                            <Typography variant="body2" fontWeight={600} sx={{ fontFamily: "monospace" }}>
                              {v.version}
                            </Typography>
                            {v.version === active && (
                              <Chip label="Loaded now" color="success" size="small" sx={{ height: 16, fontSize: "0.6rem" }} />
                            )}
                          </Stack>
                          <Typography variant="caption" color="text.secondary">
                            {v.model_name}
                            {v.size_bytes ? ` · ${(v.size_bytes / 1024 / 1024).toFixed(0)} MB` : ""}
                          </Typography>
                        </Box>
                      }
                      sx={{ m: 0, alignItems: "flex-start" }} />
                  </Paper>
                ))}
              </RadioGroup>
              <Button
                variant="contained"
                size="small"
                startIcon={loading ? <CircularProgress size={14} /> : <RocketLaunchIcon />}
                disabled={!selectedVersion || loading || selectedVersion === active}
                onClick={handleLoad}
              >
                {selectedVersion === active ? "Already loaded" : "Load now"}
              </Button>
            </Stack>
          </>
        )}

        {msg && <Alert severity="success" sx={{ mt: 1.5 }} onClose={() => setMsg(null)}>{msg}</Alert>}
        {err && <Alert severity="error" sx={{ mt: 1.5 }} onClose={() => setErr(null)}>{err}</Alert>}
      </CardContent>
    </Card>
  );
}

// =============================================================================
// LLM Model card — enable/disable
// =============================================================================

function LLMModelCard({
  device, inUse, onToggle,
}: {
  device: Device; inUse: boolean;
  onToggle: (id: string, next: "active" | "inactive") => Promise<void>;
}) {
  const [toggling, setToggling] = useState(false);
  const isOn = device.status === "active";

  const tierLabels: Record<string, string> = { small: "Fast", big: "Accurate", max: "Most careful" };
  const tierLabel = tierLabels[device.role] ?? device.role;

  return (
    <Card variant="outlined" sx={{ mb: 1.5, borderColor: inUse ? "primary.main" : "divider", borderWidth: inUse ? 2 : 1, opacity: isOn ? 1 : 0.55 }}>
      <CardContent sx={{ py: 1.5, "&:last-child": { pb: 1.5 } }}>
        <Stack direction="row" alignItems="center" spacing={2}>
          <SmartToyOutlinedIcon color={isOn ? "primary" : "disabled"} />
          <Box sx={{ flex: 1 }}>
            <Stack direction="row" alignItems="center" spacing={1}>
              <Typography variant="body2" fontWeight={600}>{device.name}</Typography>
              {inUse && <Chip label="In use by default" color="primary" size="small" sx={{ height: 18, fontSize: "0.68rem" }} />}
            </Stack>
            <Typography variant="caption" color="text.secondary">
              {device.provider === "aws" ? "Amazon" : device.provider === "azure" ? "Microsoft" : device.provider} · {tierLabel}
            </Typography>
            {!device.env_var_set && (
              <Typography variant="caption" color="warning.main" display="block">
                Not configured — set the <code>{device.env_var}</code> environment variable to activate
              </Typography>
            )}
          </Box>
          <Stack alignItems="flex-end" spacing={0.5}>
            <Tooltip title={isOn ? "Switch off" : "Switch on"}>
              <Switch checked={isOn} size="small" color="success" disabled={toggling}
                onChange={async () => {
                  setToggling(true);
                  await onToggle(device.device_id, isOn ? "inactive" : "active");
                  setToggling(false);
                }} />
            </Tooltip>
          </Stack>
        </Stack>
        <Stack direction="row" alignItems="center" spacing={0.5} sx={{ mt: 0.5, ml: "36px" }}>
          <InfoOutlinedIcon sx={{ fontSize: 12, color: "text.disabled" }} />
          <Tooltip title={device.resolved_model_id || device.default_model_id}>
            <Typography variant="caption" sx={{ color: "text.disabled", fontFamily: "monospace", fontSize: "0.68rem", maxWidth: 480, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", cursor: "default" }}>
              {device.resolved_model_id || device.default_model_id}
            </Typography>
          </Tooltip>
        </Stack>
      </CardContent>
    </Card>
  );
}

// =============================================================================
// Model catalogue — built from real Device nodes, not hardcoded
// =============================================================================

interface ModelOption {
  key: ModelKey;   // device_id e.g. "device-aws-small"
  label: string;
  provider: string;
  tier: string;
  desc: string;
  chipColor: "warning" | "primary" | "secondary" | "success";
  isNer: boolean;
}

/** Derive a display tier from the device name/role hints. */
function _inferTier(d: Device): { tier: string; chipColor: ModelOption["chipColor"] } {
  const n = (d.name + " " + (d.role ?? "")).toLowerCase();
  if (n.includes("haiku") || n.includes("mini") || n.includes("small") || n.includes("fast"))
    return { tier: "Fast",         chipColor: "warning" };
  if (n.includes("opus") || n.includes("max") || n.includes("most careful"))
    return { tier: "Most careful", chipColor: "secondary" };
  return { tier: "Accurate", chipColor: "primary" };
}

function devicesToModelOptions(devices: Device[]): ModelOption[] {
  return devices
    .filter((d) => d.status === "active" && (d.device_type === "llm" || d.device_type === "ner"))
    .map((d) => {
      if (d.device_type === "ner") {
        return {
          key:       d.device_id,
          label:     "Medical coder (NER)",
          provider:  "NER",
          tier:      "Specialist",
          desc:      "Trained model — finds and labels clinical terms automatically",
          chipColor: "success" as const,
          isNer:     true,
        };
      }
      const { tier, chipColor } = _inferTier(d);
      const providerLabel = d.provider === "aws" ? "Amazon" : d.provider === "azure" ? "Microsoft" : d.provider;
      return {
        key:       d.device_id,
        label:     d.name,
        provider:  providerLabel,
        tier,
        desc:      d.notes || d.default_model_id || "",
        chipColor,
        isNer:     false,
      };
    });
}

/** Derive extractor value from model selections — not exposed as a user choice. */
function deriveExtractor(primaryIsNer: boolean, hasBackup: boolean): string {
  if (primaryIsNer) return hasBackup ? "ner+llm" : "ner";
  return "llm";
}

// =============================================================================
// ModelPicker — radio card grid for selecting a single model
// =============================================================================

function ModelPicker({
  value, onChange, options = [], label,
}: {
  value: ModelKey;
  onChange: (k: ModelKey) => void;
  options?: ModelOption[];
  label?: string;
}) {
  return (
    <Box>
      {label && <Typography variant="caption" fontWeight={600} display="block" sx={{ mb: 0.75 }}>{label}</Typography>}
      <Stack direction="row" flexWrap="wrap" spacing={1} useFlexGap>
        {options.map((opt) => {
          const selected = value === opt.key;
          return (
            <Paper key={opt.key} variant="outlined" onClick={() => onChange(opt.key)}
              sx={{
                px: 1.5, py: 1, cursor: "pointer", minWidth: 155,
                borderColor: selected ? "primary.main" : "divider",
                borderWidth: selected ? 2 : 1,
                bgcolor: selected ? "primary.50" : "background.paper",
              }}>
              <Typography variant="body2" fontWeight={700} sx={{ mb: 0.25 }}>{opt.label}</Typography>
              <Stack direction="row" spacing={0.5}>
                <Chip label={opt.provider} size="small" variant="outlined" sx={{ height: 16, fontSize: "0.62rem" }} />
                <Chip label={opt.tier} size="small" color={opt.chipColor} variant="outlined" sx={{ height: 16, fontSize: "0.62rem" }} />
              </Stack>
              <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>{opt.desc}</Typography>
            </Paper>
          );
        })}
      </Stack>
    </Box>
  );
}

// =============================================================================
// PresetCard — single named configuration preset
// =============================================================================

const EXTRACTOR_CHIPS: Record<string, string> = {
  llm:       "AI finds terms",
  ner:       "Medical coder finds terms",
  "ner+llm": "Medical coder + AI backup",
};

function modelLabel(key: ModelKey, devices: Device[]): string {
  const opts = devicesToModelOptions(devices);
  return opts.find((m) => m.key === key)?.label ?? key;
}

const CARD_COLORS: Record<string, string> = {
  primary:   "#1976d2",
  success:   "#2e7d32",
  warning:   "#ed6c02",
  error:     "#d32f2f",
  info:      "#0288d1",
  secondary: "#9c27b0",
};

function PresetCard({
  preset,
  devices,
  onSetDefault,
  onEdit,
  onDelete,
}: {
  preset: ModelPreset;
  devices: Device[];
  onSetDefault: (id: string) => Promise<void>;
  onEdit: (preset: ModelPreset) => void;
  onDelete: (id: string) => Promise<void>;
}) {
  const [acting, setActing] = useState<string | null>(null);
  const accentColor = CARD_COLORS[preset.color] ?? CARD_COLORS.primary;

  return (
    <Card
      variant="outlined"
      sx={{
        flex: "1 1 260px",
        minWidth: 240,
        maxWidth: 340,
        borderTop: `4px solid ${accentColor}`,
        display: "flex",
        flexDirection: "column",
        position: "relative",
      }}
    >
      {preset.is_default && (
        <Chip
          label="System default"
          size="small"
          color="primary"
          sx={{ position: "absolute", top: 12, right: 12, height: 20, fontSize: "0.65rem", fontWeight: 700 }}
        />
      )}
      <CardContent sx={{ flex: 1, pb: 1 }}>
        <Typography variant="subtitle1" fontWeight={700} sx={{ mb: 0.5, pr: preset.is_default ? 11 : 0 }}>
          {preset.name}
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5, fontSize: "0.82rem" }}>
          {preset.description}
        </Typography>
        <Stack direction="row" flexWrap="wrap" spacing={0.5} useFlexGap>
          {preset.consensus_mode
            ? <Chip label="Dual check" size="small" icon={<GroupsIcon />} color="primary" variant="outlined" />
            : <Chip label="Single AI"  size="small" icon={<PersonIcon />} variant="outlined" />}
          <Chip label={modelLabel(preset.primary_model, devices)} size="small" variant="outlined" />
          {preset.consensus_mode && (
            <Chip label={`+ ${modelLabel(preset.secondary_model, devices)}`} size="small" variant="outlined" />
          )}
          <Chip label={EXTRACTOR_CHIPS[preset.extractor] ?? preset.extractor} size="small" variant="outlined" />
        </Stack>
      </CardContent>
      <Divider />
      <Stack direction="row" spacing={0.5} sx={{ px: 1.5, py: 1 }}>
        {!preset.is_default && (
          <Button size="small" disabled={!!acting} onClick={async () => {
            setActing("default");
            await onSetDefault(preset.preset_id);
            setActing(null);
          }}>
            {acting === "default" ? <CircularProgress size={14} /> : "Set as default"}
          </Button>
        )}
        <Button size="small" onClick={() => onEdit(preset)}>Edit</Button>
        {!preset.is_system && (
          <Button size="small" color="error" disabled={!!acting} onClick={async () => {
            setActing("delete");
            await onDelete(preset.preset_id);
            setActing(null);
          }}>
            {acting === "delete" ? <CircularProgress size={14} /> : "Delete"}
          </Button>
        )}
      </Stack>
    </Card>
  );
}

// =============================================================================
// PresetDialog — create or edit a preset
// =============================================================================

function PresetDialog({
  open, initial, devices, onClose, onSaved,
}: {
  open: boolean;
  initial: ModelPreset | null;
  devices: Device[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const allOptions = devicesToModelOptions(devices);
  const llmOptions = allOptions.filter((o) => !o.isNer);
  const nerOption  = allOptions.find((o) => o.isNer) ?? null;

  const firstLlm  = llmOptions[0]?.key ?? "";
  const secondLlm = llmOptions[1]?.key ?? firstLlm;

  const [name,               setName]               = useState("");
  const [desc,               setDesc]               = useState("");
  const [consensus,          setConsensus]          = useState(false);
  const [primary,            setPrimary]            = useState<ModelKey>(firstLlm);
  // single NER: llm backup device_id or "" for none; dual: second AI device_id
  const [secondary,          setSecondary]          = useState<ModelKey>(secondLlm);
  const [tiebreaker,         setTiebreaker]         = useState<ModelKey>(firstLlm);
  const [nerBackup,          setNerBackup]          = useState(false); // single NER only
  const [color,              setColor]              = useState("primary");
  const [supportsTemp,       setSupportsTemp]       = useState(true);
  const [saving,             setSaving]             = useState(false);
  const [err,                setErr]                = useState<string | null>(null);

  const primaryIsNer = allOptions.find((o) => o.key === primary)?.isNer ?? false;

  useEffect(() => {
    if (!open) return;
    const p = initial?.primary_model ?? firstLlm;
    const s = initial?.secondary_model ?? secondLlm;
    const pIsNer = allOptions.find((o) => o.key === p)?.isNer ?? false;
    setName(initial?.name ?? "");
    setDesc(initial?.description ?? "");
    setConsensus(initial?.consensus_mode ?? false);
    setPrimary(p);
    setSecondary(s);
    setTiebreaker(initial?.tiebreaker_model ?? firstLlm);
    // Infer nerBackup from stored extractor or secondary being set
    setNerBackup(pIsNer && !!s && s !== "");
    setColor(initial?.color ?? "primary");
    // Default to true for existing presets that predate this field
    setSupportsTemp(initial?.supports_temperature ?? true);
    setErr(null);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, initial]);

  const submit = async () => {
    if (!name.trim()) { setErr("Name is required."); return; }
    setSaving(true); setErr(null);
    try {
      // Derive extractor from model choices — not exposed as a separate question
      const extractor = deriveExtractor(primaryIsNer, nerBackup);
      const body = {
        preset_id:             initial?.preset_id ?? "",
        name:                  name.trim(),
        description:           desc.trim(),
        consensus_mode:        consensus,
        primary_model:         primary,
        // single NER: backup LLM or ""; dual: second AI
        secondary_model:       consensus ? secondary : (primaryIsNer && nerBackup ? secondary : ""),
        tiebreaker_model:      consensus ? tiebreaker : "",
        extractor,
        strict:                initial?.strict ?? false,
        prompt_config_id:      initial?.prompt_config_id ?? "",
        color,
        supports_temperature:  supportsTemp,
      };
      await fetch("/api/presets", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest" },
        body: JSON.stringify(body),
      });
      onSaved(); onClose();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not save — try again.");
    } finally { setSaving(false); }
  };

  const COLOR_LIST = ["primary", "success", "warning", "error", "info", "secondary"] as const;

  const noModels    = allOptions.length === 0;
  const noLlmModels = llmOptions.length === 0;

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth scroll="paper">
      <DialogTitle>{initial ? `Edit preset — ${initial.name}` : "New preset"}</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={3} sx={{ mt: 0.5 }}>
          {err && <Alert severity="error">{err}</Alert>}
          {noModels && (
            <Alert severity="warning">
              No AI models are configured. Add credentials to your environment first.
            </Alert>
          )}

          {/* Name & description */}
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
            <TextField label="Name *" value={name} onChange={(e) => setName(e.target.value)}
              size="small" sx={{ flex: 1 }} placeholder="e.g. Quality check" />
            <TextField label="Description" value={desc} onChange={(e) => setDesc(e.target.value)}
              size="small" sx={{ flex: 2 }} multiline rows={1} placeholder="When would someone choose this?" />
          </Stack>

          {/* ── Step 1: Single or Dual ──────────────────────────────── */}
          <Box>
            <Typography variant="subtitle2" fontWeight={700} gutterBottom>
              Step 1 — Single AI or two AIs?
            </Typography>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5}>
              {([
                { val: false, icon: <PersonIcon />, title: "Single AI",
                  desc: "One model reads and labels the text. Faster and cheaper." },
                { val: true, icon: <GroupsIcon />, title: "Two AIs check each other",
                  desc: "Two models work independently and compare. A third model breaks any tie. More reliable." },
              ] as const).map(({ val, icon, title, desc: d }) => (
                <Paper key={String(val)} variant="outlined" onClick={() => setConsensus(val)}
                  sx={{
                    p: 1.5, cursor: "pointer", flex: 1,
                    borderColor: consensus === val ? "primary.main" : "divider",
                    borderWidth: consensus === val ? 2 : 1,
                    bgcolor: consensus === val ? "primary.50" : "background.paper",
                  }}>
                  <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 0.5 }}>
                    {icon}<Typography variant="body2" fontWeight={700}>{title}</Typography>
                  </Stack>
                  <Typography variant="caption" color="text.secondary">{d}</Typography>
                </Paper>
              ))}
            </Stack>
          </Box>

          {/* ── SINGLE mode ─────────────────────────────────────────── */}
          {!consensus && (
            <>
              <Box>
                <Typography variant="subtitle2" fontWeight={700} gutterBottom>
                  Step 2 — Which model should do the work?
                </Typography>
                <ModelPicker value={primary} onChange={(k) => {
                  setPrimary(k);
                  const isNer = allOptions.find((o) => o.key === k)?.isNer ?? false;
                  if (!isNer) setNerBackup(false);
                  if (isNer && !secondary) setSecondary(firstLlm);
                }} options={allOptions} />
              </Box>

              {/* NER chosen → offer optional LLM backup */}
              {primaryIsNer && (
                <Box>
                  <Typography variant="subtitle2" fontWeight={700} gutterBottom>
                    Step 3 — Add an AI backup?
                  </Typography>
                  <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1.5 }}>
                    If the trained medical coder can&apos;t find anything, an AI can step in as a fallback.
                  </Typography>
                  <Stack direction="row" spacing={1.5} sx={{ mb: nerBackup ? 2 : 0 }}>
                    {([
                      { val: false, label: "No — medical coder only", desc: "If it finds nothing, the result is empty." },
                      { val: true,  label: "Yes — add an AI fallback", desc: "If the medical coder finds nothing, an AI reads the text instead." },
                    ] as const).map(({ val, label, desc: d }) => (
                      <Paper key={String(val)} variant="outlined" onClick={() => setNerBackup(val)}
                        sx={{
                          p: 1.5, cursor: "pointer", flex: 1,
                          borderColor: nerBackup === val ? "primary.main" : "divider",
                          borderWidth: nerBackup === val ? 2 : 1,
                          bgcolor: nerBackup === val ? "primary.50" : "background.paper",
                        }}>
                        <Typography variant="body2" fontWeight={700}>{label}</Typography>
                        <Typography variant="caption" color="text.secondary">{d}</Typography>
                      </Paper>
                    ))}
                  </Stack>
                  {nerBackup && (
                    <Box sx={{ mt: 2 }}>
                      <Typography variant="caption" fontWeight={600} display="block" sx={{ mb: 1 }}>
                        Which AI should be the backup?
                      </Typography>
                      {noLlmModels
                        ? <Alert severity="warning">No LLM models are configured.</Alert>
                        : <ModelPicker value={secondary} onChange={setSecondary} options={llmOptions} />
                      }
                    </Box>
                  )}
                </Box>
              )}
            </>
          )}

          {/* ── DUAL mode ───────────────────────────────────────────── */}
          {consensus && (
            <>
              <Box>
                <Typography variant="subtitle2" fontWeight={700} gutterBottom>
                  Step 2 — Choose the two models
                </Typography>
                <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1.5 }}>
                  They each read the text independently. If they agree, that&apos;s the answer.
                </Typography>
                {noLlmModels
                  ? <Alert severity="warning">No LLM models are configured.</Alert>
                  : <Stack spacing={2}>
                      <ModelPicker value={primary} onChange={setPrimary}
                        options={nerOption ? allOptions : llmOptions}
                        label="First model" />
                      <ModelPicker value={secondary} onChange={setSecondary}
                        options={llmOptions}
                        label={`Second model${primaryIsNer ? " (must be an AI — NER cannot compare with itself)" : ""}`} />
                    </Stack>
                }
              </Box>

              <Box>
                <Typography variant="subtitle2" fontWeight={700} gutterBottom>
                  Step 3 — If they disagree, which model decides?
                </Typography>
                <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
                  This model is only called when the two above give different answers.
                </Typography>
                {noLlmModels
                  ? <Alert severity="warning">No LLM models are configured.</Alert>
                  : <ModelPicker value={tiebreaker} onChange={setTiebreaker} options={llmOptions} />
                }
              </Box>
            </>
          )}

          {/* ── Temperature support ─────────────────────────────────── */}
          <Box>
            <Typography variant="subtitle2" fontWeight={700} gutterBottom>
              Temperature control
            </Typography>
            <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1.5 }}>
              Does the model behind this preset honour the <code>temperature</code> parameter?
              Turn this <strong>off</strong> for GPT-5 family models (Azure OpenAI GPT-5, GPT-5-mini) —
              they ignore temperature and use a fixed internal reasoning approach.
              Leave it <strong>on</strong> for Bedrock Claude models (3.x / 3.5 / Sonnet) which do
              support it. NER-only presets should also have this turned off.
            </Typography>
            <FormControlLabel
              control={
                <Switch
                  checked={supportsTemp}
                  onChange={(e) => setSupportsTemp(e.target.checked)}
                  color="primary"
                />
              }
              label={
                <Typography variant="body2">
                  {supportsTemp
                    ? "Temperature supported — slider will appear in the pathway wizard"
                    : "Temperature not supported — slider will be hidden in the pathway wizard"}
                </Typography>
              }
            />
          </Box>

          {/* ── Card colour ─────────────────────────────────────────── */}
          <Box>
            <Typography variant="caption" fontWeight={600} display="block" sx={{ mb: 0.75 }}>Card colour</Typography>
            <Stack direction="row" spacing={1}>
              {COLOR_LIST.map((c) => (
                <Tooltip key={c} title={c}>
                  <Box onClick={() => setColor(c)} sx={{
                    width: 26, height: 26, borderRadius: "50%", cursor: "pointer",
                    bgcolor: CARD_COLORS[c],
                    border: color === c ? "3px solid #000" : "2px solid transparent",
                    outline: color === c ? "2px solid #fff" : "none",
                    outlineOffset: "-3px",
                  }} />
                </Tooltip>
              ))}
            </Stack>
          </Box>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={saving}>Cancel</Button>
        <Button variant="contained" onClick={submit} disabled={saving || noModels}
          startIcon={saving ? <CircularProgress size={14} /> : <SaveIcon />}>
          {initial ? "Save changes" : "Create preset"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

// =============================================================================
// RoutingCard — default pipeline configuration
// =============================================================================

function RoutingCard({ config, onSave }: { config: PipelineConfig; onSave: (c: PipelineConfig) => Promise<void> }) {
  const [draft, setDraft] = useState<PipelineConfig>(config);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const dirty = JSON.stringify(draft) !== JSON.stringify(config);

  const set = <K extends keyof PipelineConfig>(key: K, val: PipelineConfig[K]) =>
    setDraft((prev) => ({ ...prev, [key]: val }));

  const save = async () => {
    setSaving(true); setMsg(null);
    try {
      await onSave(draft);
      setMsg("Saved. New pipelines will use these settings unless they set their own.");
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Could not save — try again.");
    } finally { setSaving(false); }
  };

  return (
    <Paper variant="outlined" sx={{ p: 2.5, mb: 2 }}>
      {/* Checking mode */}
      <Typography variant="body2" fontWeight={600} sx={{ mb: 1 }}>Checking mode</Typography>
      <Stack direction="row" spacing={1.5} sx={{ mb: 3 }}>
        <OptionCard selected={draft.consensus_mode} onClick={() => set("consensus_mode", true)}
          icon={<GroupsIcon color={draft.consensus_mode ? "primary" : "disabled"} />}
          title="Dual check"
          description="Two AI assistants read the same text independently. If they agree, that's the answer. If they disagree, a third steps in to decide."
          badge="Recommended" />
        <OptionCard selected={!draft.consensus_mode} onClick={() => set("consensus_mode", false)}
          icon={<PersonIcon color={!draft.consensus_mode ? "primary" : "disabled"} />}
          title="Single AI"
          description="One AI assistant reads and codes the text. Faster and cheaper — no cross-check." />
      </Stack>

      {/* Tier */}
      <Typography variant="body2" fontWeight={600} sx={{ mb: 0.5 }}>
        {draft.consensus_mode ? "If the two AIs disagree, which tiebreaker?" : "How careful should the AI be?"}
      </Typography>
      {draft.consensus_mode && (
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
          In dual check mode, both fast models run first (Amazon Claude Haiku + Microsoft GPT-5 mini).
          If they agree — done. If they disagree, the tiebreaker below decides.
        </Typography>
      )}
      <Stack direction="row" spacing={1.5} sx={{ mb: 3 }} flexWrap="wrap" useFlexGap>
        {TIER_OPTIONS.map((opt) => (
          <OptionCard key={opt.value} selected={draft.tier === opt.value} onClick={() => set("tier", opt.value)}
            icon={opt.value === "small" ? <BoltIcon color={draft.tier === opt.value ? "warning" : "disabled"} /> : <StarIcon color={draft.tier === opt.value ? "primary" : "disabled"} />}
            title={opt.label} description={opt.desc}
            badge={draft.consensus_mode && opt.value === "big" ? "Default tiebreaker" : undefined} />
        ))}
      </Stack>

      {/* Provider — single mode only */}
      {!draft.consensus_mode && (
        <>
          <Typography variant="body2" fontWeight={600} sx={{ mb: 1 }}>Which AI company to use</Typography>
          <Stack direction="row" spacing={1.5} sx={{ mb: 3 }}>
            {PROVIDER_OPTIONS.map((opt) => (
              <OptionCard key={opt.value} selected={draft.provider === opt.value} onClick={() => set("provider", opt.value)}
                icon={<SmartToyOutlinedIcon color={draft.provider === opt.value ? "primary" : "disabled"} />}
                title={opt.label} description={opt.desc} />
            ))}
          </Stack>
        </>
      )}

      <Divider sx={{ mb: 2.5 }} />

      {/* Extractor backend */}
      <Typography variant="body2" fontWeight={600} sx={{ mb: 1 }}>How to read and label medical text</Typography>
      <RadioGroup value={draft.extractor_backend} onChange={(e) => set("extractor_backend", e.target.value)}>
        {BACKEND_OPTIONS.map((opt) => (
          <Paper key={opt.value} variant="outlined" onClick={() => set("extractor_backend", opt.value)}
            sx={{ p: 1.5, mb: 1, maxWidth: 560, cursor: "pointer",
              borderColor: draft.extractor_backend === opt.value ? "primary.main" : "divider",
              borderWidth: draft.extractor_backend === opt.value ? 2 : 1,
              bgcolor: draft.extractor_backend === opt.value ? "primary.50" : "background.paper" }}>
            <FormControlLabel value={opt.value} control={<Radio size="small" />}
              label={<Box><Typography variant="body2" fontWeight={600}>{opt.label}</Typography>
                <Typography variant="caption" color="text.secondary">{opt.desc}</Typography></Box>}
              sx={{ m: 0, alignItems: "flex-start" }} />
          </Paper>
        ))}
      </RadioGroup>

      <Stack direction="row" alignItems="center" spacing={2} sx={{ mt: 2.5 }}>
        <Button variant="contained" size="small" startIcon={saving ? <CircularProgress size={14} /> : <SaveIcon />}
          disabled={!dirty || saving} onClick={save}>Save changes</Button>
        {dirty && <Typography variant="caption" color="warning.main" fontWeight={600}>Unsaved changes</Typography>}
      </Stack>
      {msg && <Alert severity={msg.startsWith("Saved") ? "success" : "error"} sx={{ mt: 1.5 }} onClose={() => setMsg(null)}>{msg}</Alert>}
    </Paper>
  );
}

function TerminologyRuntimeCard({
  config,
  onSave,
}: {
  config: ServiceConfig | null;
  onSave: (next: ServiceConfig) => Promise<void>;
}) {
  const [draft, setDraft] = useState<ServiceConfig | null>(config);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    setDraft(config);
  }, [config]);

  if (!draft) {
    return <Alert severity="warning">Terminology runtime settings are not available yet.</Alert>;
  }

  const setNumber = (key: string, value: string) => {
    const next = Number(value);
    setDraft((prev) => prev ? {
      ...prev,
      config: { ...prev.config, [key]: Number.isFinite(next) ? next : 0 },
    } : prev);
  };

  const dirty = JSON.stringify(draft) !== JSON.stringify(config);

  const save = async () => {
    setSaving(true);
    setMsg(null);
    try {
      await onSave(draft);
      setMsg("Saved. All API replicas will pick this up automatically.");
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Could not save runtime settings.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Paper variant="outlined" sx={{ p: 2.5 }}>
      <Typography variant="body2" fontWeight={600} sx={{ mb: 0.75 }}>
        Terminology resolve runtime
      </Typography>
      <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 2 }}>
        Shared controls for timeout, retries, cooldown, per-replica concurrency, and request batch size.
        Use this to tune live behaviour without redeploying when you scale replicas.
      </Typography>
      <Stack spacing={2}>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
          <TextField
            label="Timeout (seconds)"
            type="number"
            size="small"
            value={draft.config.timeout_seconds ?? 15}
            onChange={(e) => setNumber("timeout_seconds", e.target.value)}
            inputProps={{ min: 1, step: 1 }}
            sx={{ flex: 1 }}
          />
          <TextField
            label="Retries"
            type="number"
            size="small"
            value={draft.config.max_retries ?? 3}
            onChange={(e) => setNumber("max_retries", e.target.value)}
            inputProps={{ min: 0, step: 1 }}
            sx={{ flex: 1 }}
          />
          <TextField
            label="Cooldown (seconds)"
            type="number"
            size="small"
            value={draft.config.cooldown_seconds ?? 60}
            onChange={(e) => setNumber("cooldown_seconds", e.target.value)}
            inputProps={{ min: 0, step: 1 }}
            sx={{ flex: 1 }}
          />
        </Stack>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
          <TextField
            label="Final attempts"
            type="number"
            size="small"
            value={draft.config.final_attempts ?? 1}
            onChange={(e) => setNumber("final_attempts", e.target.value)}
            inputProps={{ min: 0, step: 1 }}
            sx={{ flex: 1 }}
          />
          <TextField
            label="Max concurrent requests per replica"
            type="number"
            size="small"
            value={draft.config.max_concurrent_requests ?? 2}
            onChange={(e) => setNumber("max_concurrent_requests", e.target.value)}
            inputProps={{ min: 1, step: 1 }}
            sx={{ flex: 1 }}
          />
          <TextField
            label="Max terms per request"
            type="number"
            size="small"
            value={draft.config.max_terms_per_request ?? 8}
            onChange={(e) => setNumber("max_terms_per_request", e.target.value)}
            inputProps={{ min: 1, step: 1 }}
            sx={{ flex: 1 }}
          />
        </Stack>
      </Stack>
      <Stack direction="row" alignItems="center" spacing={2} sx={{ mt: 2.5 }}>
        <Button
          variant="contained"
          size="small"
          startIcon={saving ? <CircularProgress size={14} /> : <SaveIcon />}
          disabled={!dirty || saving}
          onClick={save}
        >
          Save changes
        </Button>
        {dirty && <Typography variant="caption" color="warning.main" fontWeight={600}>Unsaved changes</Typography>}
        <Typography variant="caption" color="text.secondary">
          Last updated: {fmtDate(draft.updatedAt)}
        </Typography>
      </Stack>
      {msg && <Alert severity={msg.startsWith("Saved") ? "success" : "error"} sx={{ mt: 1.5 }} onClose={() => setMsg(null)}>{msg}</Alert>}
    </Paper>
  );
}

// =============================================================================
// MetricsRow — shows precision / recall / F1 for one phase
// =============================================================================

function MetricsRow({ label, precision, recall }: { label: string; precision: number | null; recall: number | null }) {
  const hasData = precision != null && recall != null;
  return (
    <Stack direction="row" spacing={3} alignItems="center">
      <Typography variant="caption" color="text.secondary" sx={{ width: 90 }}>{label}</Typography>
      {hasData ? (
        <>
          <Chip label={`Precision ${pct(precision)}`} size="small" variant="outlined" />
          <Chip label={`Recall ${pct(recall)}`} size="small" variant="outlined" />
          <Chip label={`F1 ${f1(precision, recall)}`} size="small" color="primary" variant="outlined" />
        </>
      ) : (
        <Typography variant="caption" color="text.disabled">Not recorded yet</Typography>
      )}
    </Stack>
  );
}

// =============================================================================
// CanaryJobPanel — polls background canary gold run job
// =============================================================================

function CanaryJobPanel({ jobId, onComplete }: { jobId: string; onComplete: (job: CanaryJob) => void }) {
  const [job, setJob] = useState<CanaryJob | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    const poll = async () => {
      try {
        const data = await apiFetch<CanaryJob>(`/api/model-registry/canary-jobs/${jobId}`);
        setJob(data);
        if (data.status === "completed" || data.status === "failed") {
          if (timerRef.current) clearInterval(timerRef.current);
          onComplete(data);
        }
      } catch { /* will retry */ }
    };
    poll();
    timerRef.current = setInterval(poll, 3000);
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [jobId, onComplete]);

  if (!job) return <CircularProgress size={16} />;

  const progress = job.progress ?? (job.processed_candidates && job.total_candidates
    ? job.processed_candidates / job.total_candidates
    : null);

  return (
    <Box sx={{ mt: 1 }}>
      <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 0.5 }}>
        {job.status === "running" || job.status === "accepted"
          ? <CircularProgress size={14} />
          : job.status === "completed"
          ? <CheckCircleIcon color="success" fontSize="small" />
          : <ErrorOutlineIcon color="error" fontSize="small" />}
        <Typography variant="caption" fontWeight={600}>
          {job.status === "completed" ? "Gold test finished" : job.status === "failed" ? "Gold test failed" : "Running gold test…"}
        </Typography>
        <Typography variant="caption" color="text.secondary">{job.message}</Typography>
      </Stack>
      {progress != null && job.status === "running" && (
        <LinearProgress variant="determinate" value={progress * 100} sx={{ mb: 1, borderRadius: 1 }} />
      )}
      {job.metrics && (
        <Box sx={{ mt: 1 }}>
          <MetricsRow label="Gold results" precision={job.metrics.overall.precision} recall={job.metrics.overall.recall} />
          {job.metrics.per_label.length > 0 && (
            <TableContainer component={Paper} variant="outlined" sx={{ mt: 1 }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Label</TableCell>
                    <TableCell>Precision</TableCell>
                    <TableCell>Recall</TableCell>
                    <TableCell>F1</TableCell>
                    <TableCell>TP / FP / FN</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {job.metrics.per_label.map((r) => (
                    <TableRow key={r.label}>
                      <TableCell><Typography variant="caption" sx={{ fontFamily: "monospace" }}>{r.label}</Typography></TableCell>
                      <TableCell><Typography variant="caption">{pct(r.precision)}</Typography></TableCell>
                      <TableCell><Typography variant="caption">{pct(r.recall)}</Typography></TableCell>
                      <TableCell><Typography variant="caption" fontWeight={600}>{pct(r.f1)}</Typography></TableCell>
                      <TableCell><Typography variant="caption" color="text.secondary">{r.tp} / {r.fp} / {r.fn}</Typography></TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </Box>
      )}
    </Box>
  );
}

// =============================================================================
// ValidateDialog — enter offline test results
// =============================================================================

function ValidateDialog({
  open, version, onClose, onValidated,
}: { open: boolean; version: string; onClose: () => void; onValidated: () => void }) {
  const [precision, setPrecision] = useState("");
  const [recall, setRecall] = useState("");
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async () => {
    const p = parseFloat(precision);
    const r = parseFloat(recall);
    if (isNaN(p) || isNaN(r) || p < 0 || p > 1 || r < 0 || r > 1) {
      setErr("Enter precision and recall as decimals between 0 and 1 (e.g. 0.87 for 87%).");
      return;
    }
    setSaving(true); setErr(null);
    try {
      await apiFetch(`/api/model-registry/versions/${version}/validate`, {
        method: "POST", body: JSON.stringify({ precision: p, recall: r, notes }),
      });
      onValidated();
      onClose();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not save — try again.");
    } finally { setSaving(false); }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Record offline test results — v{version}</DialogTitle>
      <DialogContent>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Enter the precision and recall from your offline evaluation (e.g. from a test script run against a held-out dataset).
          The system will compare these against the minimum thresholds and decide if this version has passed.
        </Typography>
        <Stack spacing={2}>
          <TextField label="Precision (0–1)" value={precision} onChange={(e) => setPrecision(e.target.value)}
            placeholder="e.g. 0.87" size="small" helperText="What fraction of the model's predictions were correct?" />
          <TextField label="Recall (0–1)" value={recall} onChange={(e) => setRecall(e.target.value)}
            placeholder="e.g. 0.82" size="small" helperText="What fraction of the real entities did the model find?" />
          <TextField label="Notes (optional)" value={notes} onChange={(e) => setNotes(e.target.value)}
            placeholder="e.g. Tested on 200 held-out GP letters" size="small" multiline rows={2} />
        </Stack>
        {err && <Alert severity="error" sx={{ mt: 2 }}>{err}</Alert>}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={saving}>Cancel</Button>
        <Button variant="contained" onClick={submit} disabled={saving}
          startIcon={saving ? <CircularProgress size={14} /> : undefined}>
          Save results
        </Button>
      </DialogActions>
    </Dialog>
  );
}

// =============================================================================
// RegisterVersionDialog — register a new NER model version
// =============================================================================

function RegisterVersionDialog({
  open, onClose, onRegistered,
}: { open: boolean; onClose: () => void; onRegistered: () => void }) {
  const [version, setVersion] = useState("");
  const [name, setName] = useState("");
  const [datasetVersion, setDatasetVersion] = useState("");
  const [schemaVersion, setSchemaVersion] = useState("1.0");
  const [deidVersion, setDeidVersion] = useState("1.0");
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const reset = () => { setVersion(""); setName(""); setDatasetVersion(""); setSchemaVersion("1.0"); setDeidVersion("1.0"); setNotes(""); setErr(null); };

  const submit = async () => {
    if (!version.trim()) { setErr("Version number is required."); return; }
    setSaving(true); setErr(null);
    try {
      await apiFetch("/api/model-registry/register", {
        method: "POST",
        body: JSON.stringify({
          model_version: version.trim(), model_name: name.trim(),
          training_dataset_version: datasetVersion.trim(),
          schema_version: schemaVersion.trim(), deid_version: deidVersion.trim(), notes,
        }),
      });
      reset();
      onRegistered();
      onClose();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not register — try again.");
    } finally { setSaving(false); }
  };

  return (
    <Dialog open={open} onClose={() => { reset(); onClose(); }} maxWidth="sm" fullWidth>
      <DialogTitle>Register a new model version</DialogTitle>
      <DialogContent>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          This is the first step. Once registered, you can upload the model and record test results to move it through to live.
        </Typography>
        <Stack spacing={2}>
          <TextField label="Version number *" value={version} onChange={(e) => setVersion(e.target.value)}
            placeholder="e.g. 1.2.0" size="small" helperText="A unique version tag for this model." />
          <TextField label="Model name" value={name} onChange={(e) => setName(e.target.value)}
            placeholder="e.g. medspacy_gp_v2" size="small" />
          <TextField label="Training dataset version" value={datasetVersion} onChange={(e) => setDatasetVersion(e.target.value)}
            placeholder="e.g. 2026-03" size="small" helperText="Which snapshot of gold labels was used to train this model?" />
          <Stack direction="row" spacing={2}>
            <TextField label="Schema version" value={schemaVersion} onChange={(e) => setSchemaVersion(e.target.value)} size="small" sx={{ flex: 1 }} />
            <TextField label="DI-ID version" value={deidVersion} onChange={(e) => setDeidVersion(e.target.value)} size="small" sx={{ flex: 1 }} helperText="De-identification version used." />
          </Stack>
          <TextField label="Notes" value={notes} onChange={(e) => setNotes(e.target.value)}
            placeholder="Optional — describe what changed in this version" size="small" multiline rows={2} />
        </Stack>
        {err && <Alert severity="error" sx={{ mt: 2 }}>{err}</Alert>}
      </DialogContent>
      <DialogActions>
        <Button onClick={() => { reset(); onClose(); }} disabled={saving}>Cancel</Button>
        <Button variant="contained" onClick={submit} disabled={saving}
          startIcon={saving ? <CircularProgress size={14} /> : <AddIcon />}>
          Register version
        </Button>
      </DialogActions>
    </Dialog>
  );
}

// =============================================================================
// VersionAccordion — full lifecycle panel for one NER model version
// =============================================================================

function VersionAccordion({
  rec, isLive, onRefresh,
}: { rec: ModelVersionDetail; isLive: boolean; onRefresh: () => void }) {
  const [validateOpen, setValidateOpen] = useState(false);
  const [acting, setActing] = useState<string | null>(null);
  const [canaryJobId, setCanaryJobId] = useState<string | null>(null);
  const [actionMsg, setActionMsg] = useState<string | null>(null);
  const [actionErr, setActionErr] = useState<string | null>(null);

  const chip = VERSION_STATUS_CHIPS[rec.status] ?? { label: rec.status, color: "default" as const };
  const idx = stepIdx(rec.status);
  const isTerminal = rec.status === "rollback" || rec.status === "deprecated";

  const act = async (label: string, fn: () => Promise<string>) => {
    setActing(label); setActionMsg(null); setActionErr(null);
    try {
      const msg = await fn();
      setActionMsg(msg);
      onRefresh();
    } catch (e) {
      setActionErr(e instanceof Error ? e.message : "Action failed — try again.");
    } finally { setActing(null); }
  };

  const handleStartCanary = () => act("start_canary", async () => {
    await apiFetch(`/api/model-registry/versions/${rec.model_version}/canary/start`, { method: "POST", body: JSON.stringify({ cohort: "gold_patients" }) });
    return "Trial run started. Run the gold test to measure performance.";
  });

  const handleRunGold = async () => {
    setActing("run_gold"); setActionMsg(null); setActionErr(null);
    try {
      const resp = await apiFetch<{ job_id: string }>(`/api/model-registry/versions/${rec.model_version}/canary/run-gold`, { method: "POST" });
      setCanaryJobId(resp.job_id);
    } catch (e) {
      setActionErr(e instanceof Error ? e.message : "Could not start gold test.");
    } finally { setActing(null); }
  };

  const handlePromote = () => act("promote", async () => {
    await apiFetch(`/api/model-registry/versions/${rec.model_version}/promote`, { method: "POST", body: JSON.stringify({ force: false }) });
    return "Promoted to live. The inference service is reloading the new version.";
  });

  const handleRollback = () => act("rollback", async () => {
    await apiFetch("/api/model-registry/rollback", { method: "POST" });
    return "Rolled back to the previous version.";
  });

  const handleReject = () => act("reject", async () => {
    await apiFetch(`/api/model-registry/versions/${rec.model_version}/reject`, { method: "POST", body: JSON.stringify({ reason: "Rejected in model review" }) });
    return "Version retired.";
  });

  return (
    <>
      <Accordion variant="outlined" sx={{ mb: 1, "&:before": { display: "none" }, borderRadius: 1 }}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Stack direction="row" alignItems="center" spacing={2} sx={{ width: "100%" }}>
            <Typography variant="body2" fontWeight={700} sx={{ fontFamily: "monospace" }}>v{rec.model_version}</Typography>
            <Chip label={chip.label} color={chip.color} size="small" variant={isLive ? "filled" : "outlined"} />
            {isLive && <Chip label="Live now" color="success" size="small" sx={{ height: 18, fontSize: "0.67rem" }} />}
            <Box sx={{ flex: 1 }} />
            {rec.offline_precision != null && (
              <Typography variant="caption" color="text.secondary">
                Precision {pct(rec.offline_precision)} · Recall {pct(rec.offline_recall)} · F1 {f1(rec.offline_precision, rec.offline_recall)}
              </Typography>
            )}
            <Typography variant="caption" color="text.disabled">{fmtDate(rec.registered_at)}</Typography>
          </Stack>
        </AccordionSummary>

        <AccordionDetails sx={{ pt: 0 }}>
          {/* Lifecycle stepper */}
          {!isTerminal && (
            <Box sx={{ mb: 2.5 }}>
              <Stepper activeStep={idx} alternativeLabel>
                {LIFECYCLE_STEP_LABELS.map((l) => <Step key={l}><StepLabel>{l}</StepLabel></Step>)}
              </Stepper>
            </Box>
          )}

          {/* Metrics */}
          <Stack spacing={1} sx={{ mb: 2 }}>
            <MetricsRow label="Offline test" precision={rec.offline_precision} recall={rec.offline_recall} />
            {(rec.canary_precision != null || rec.status === "canary" || rec.status === "promoted") && (
              <MetricsRow label="Trial run" precision={rec.canary_precision} recall={rec.canary_recall} />
            )}
          </Stack>

          {/* Canary gold job panel */}
          {canaryJobId && (
            <CanaryJobPanel jobId={canaryJobId} onComplete={(job) => {
              if (job.status === "completed") { setActionMsg("Gold test complete. Review the results above, then promote or reject."); onRefresh(); }
              else { setActionErr(`Gold test failed: ${job.message}`); }
              setCanaryJobId(null);
            }} />
          )}

          {/* Traceability */}
          <Paper variant="outlined" sx={{ p: 1.5, mb: 2, bgcolor: "grey.50" }}>
            <Typography variant="caption" fontWeight={600} display="block" sx={{ mb: 0.5 }}>Traceability</Typography>
            <Stack spacing={0.25}>
              {[
                ["Training data snapshot", rec.training_dataset_version || "—"],
                ["Schema version", rec.schema_version || "—"],
                ["De-identification version", rec.deid_version || "—"],
                ["Artifact location", rec.artifact_uri || "Not uploaded yet"],
                ["Promoted at", fmtDate(rec.promoted_at)],
                ["Rollback target", rec.rollback_target_version || "—"],
              ].map(([k, v]) => (
                <Stack key={k} direction="row" spacing={1}>
                  <Typography variant="caption" color="text.secondary" sx={{ width: 180, flexShrink: 0 }}>{k}</Typography>
                  <Typography variant="caption" sx={{ fontFamily: "monospace", wordBreak: "break-all" }}>{v}</Typography>
                </Stack>
              ))}
              {rec.notes && (
                <Stack direction="row" spacing={1}>
                  <Typography variant="caption" color="text.secondary" sx={{ width: 180, flexShrink: 0 }}>Notes</Typography>
                  <Typography variant="caption">{rec.notes}</Typography>
                </Stack>
              )}
            </Stack>
          </Paper>

          {/* Actions */}
          {!isTerminal && (
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
              {rec.status === "registered" && (
                <Button size="small" variant="outlined" onClick={() => setValidateOpen(true)} disabled={!!acting}>
                  Enter test results
                </Button>
              )}
              {rec.status === "offline_validated" && (
                <Button size="small" variant="outlined" onClick={handleStartCanary} disabled={!!acting}
                  startIcon={acting === "start_canary" ? <CircularProgress size={14} /> : undefined}>
                  Start trial run
                </Button>
              )}
              {rec.status === "canary" && (
                <>
                  <Button size="small" variant="outlined" onClick={handleRunGold} disabled={!!acting || !!canaryJobId}
                    startIcon={acting === "run_gold" ? <CircularProgress size={14} /> : undefined}>
                    Run gold test
                  </Button>
                  <Button size="small" variant="contained" color="success" onClick={handlePromote} disabled={!!acting}
                    startIcon={acting === "promote" ? <CircularProgress size={14} /> : <RocketLaunchIcon />}>
                    Promote to live
                  </Button>
                  <Button size="small" variant="outlined" color="error" onClick={handleReject} disabled={!!acting}>
                    Reject
                  </Button>
                </>
              )}
              {rec.status === "promoted" && rec.rollback_target_version && (
                <Button size="small" variant="outlined" color="warning" onClick={handleRollback} disabled={!!acting}
                  startIcon={acting === "rollback" ? <CircularProgress size={14} /> : undefined}>
                  Rollback to v{rec.rollback_target_version}
                </Button>
              )}
            </Stack>
          )}

          {actionMsg && <Alert severity="success" sx={{ mt: 1.5 }} onClose={() => setActionMsg(null)}>{actionMsg}</Alert>}
          {actionErr && <Alert severity="error" sx={{ mt: 1.5 }} onClose={() => setActionErr(null)}>{actionErr}</Alert>}
        </AccordionDetails>
      </Accordion>

      <ValidateDialog open={validateOpen} version={rec.model_version}
        onClose={() => setValidateOpen(false)} onValidated={onRefresh} />
    </>
  );
}

// =============================================================================
// Page
// =============================================================================

export default function ModelsPage() {
  const [presets, setPresets]               = useState<ModelPreset[]>([]);
  const [devices, setDevices]               = useState<Device[]>([]);
  const [pipelineConfig, setPipelineConfig] = useState<PipelineConfig | null>(null);
  const [terminologyRuntimeConfig, setTerminologyRuntimeConfig] = useState<ServiceConfig | null>(null);
  const [registryStatus, setRegistryStatus] = useState<RegistryStatus | null>(null);
  const [versions, setVersions]             = useState<ModelVersionDetail[]>([]);
  const [loading, setLoading]               = useState(true);
  const [error, setError]                   = useState<string | null>(null);
  const [registerOpen, setRegisterOpen]     = useState(false);
  const [editPreset, setEditPreset]         = useState<ModelPreset | null>(null);
  const [presetDialogOpen, setPresetDialogOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const [presetsResp, devResp, cfgResp, svcResp, inferenceResp, versionsResp] = await Promise.all([
        apiFetch<{ presets: ModelPreset[] }>("/api/presets").catch(() => ({ presets: [] })),
        apiFetch<{ devices: Device[] }>("/api/devices"),
        apiFetch<PipelineConfig>("/api/devices/pipeline-config"),
        apiFetch<ServiceConfig>("/api/service-configs/terminology:resolve_runtime").catch(() => null),
        // inference/health is the source of truth: loaded version + available in blob
        apiFetch<InferenceHealth>("/api/model-registry/inference/health").catch(() => null),
        // registry versions carry governance metadata (test scores, notes, traceability)
        apiFetch<{ versions: ModelVersionDetail[] }>("/api/model-registry/versions").catch(() => ({ versions: [] })),
      ]);
      setPresets(presetsResp.presets);
      setDevices(devResp.devices);
      setPipelineConfig(cfgResp);
      setTerminologyRuntimeConfig(svcResp);
      // Build a RegistryStatus shape from inference health
      setRegistryStatus(inferenceResp ? {
        active_model: null,
        inference_service: inferenceResp,
        total_versions: inferenceResp.available_versions?.length ?? 0,
      } : null);
      setVersions(versionsResp.versions);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load — try refreshing.");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleToggle = async (device_id: string, next: "active" | "inactive") => {
    await apiFetch(`/api/devices/${device_id}/status`, { method: "PATCH", body: JSON.stringify({ status: next }) });
    setDevices((prev) => prev.map((d) => d.device_id === device_id ? { ...d, status: next } : d));
  };

  const handleSaveConfig = async (cfg: PipelineConfig) => {
    await apiFetch("/api/devices/pipeline-config", { method: "PUT", body: JSON.stringify(cfg) });
    setPipelineConfig(cfg);
  };

  const handleSaveTerminologyRuntimeConfig = async (cfg: ServiceConfig) => {
    await apiFetch(`/api/service-configs/${encodeURIComponent(cfg.key)}`, {
      method: "PUT",
      body: JSON.stringify({
        category: cfg.category,
        displayName: cfg.displayName,
        description: cfg.description,
        config: cfg.config,
      }),
    });
    setTerminologyRuntimeConfig({ ...cfg, source: "user", updatedAt: new Date().toISOString() });
  };

  const handleSetDefault = async (preset_id: string) => {
    await apiFetch(`/api/presets/${preset_id}/default`, { method: "PUT" });
    setPresets((prev) => prev.map((p) => ({ ...p, is_default: p.preset_id === preset_id })));
  };

  const handleDeletePreset = async (preset_id: string) => {
    await apiFetch(`/api/presets/${preset_id}`, { method: "DELETE" });
    setPresets((prev) => prev.filter((p) => p.preset_id !== preset_id));
  };

  const openCreatePreset = () => { setEditPreset(null); setPresetDialogOpen(true); };
  const openEditPreset   = (p: ModelPreset) => { setEditPreset(p); setPresetDialogOpen(true); };

  const health     = registryStatus?.inference_service ?? null;
  const llmDevices = devices.filter((d) => d.device_type === "llm");

  const providerPrefix = pipelineConfig?.provider === "aws" ? "aws" : "azure";
  const activeTier     = pipelineConfig?.tier ?? "small";

  return (
    <Box sx={{ p: 3, maxWidth: 900, mx: "auto" }}>

      {/* Page header */}
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 0.5 }}>
        <Stack direction="row" alignItems="center" spacing={1}>
          <SmartToyOutlinedIcon color="primary" />
          <Typography variant="h5" fontWeight={700}>AI models</Typography>
        </Stack>
        <Tooltip title="Refresh">
          <IconButton onClick={load} disabled={loading}>
            {loading ? <CircularProgress size={20} /> : <RefreshIcon />}
          </IconButton>
        </Tooltip>
      </Stack>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 4 }}>
        Configure which AI tools are available to your pipelines, set the system defaults, and manage the
        medical coder through its full lifecycle — from training to live deployment.
      </Typography>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {loading ? (
        <Box sx={{ py: 8, textAlign: "center" }}><CircularProgress /></Box>
      ) : (
        <>
          {/* ================================================================ */}
          {/* ZONE 1 — Model Library (presets)                                */}
          {/* ================================================================ */}
          <SectionCard
            icon={<SmartToyOutlinedIcon color="primary" />}
            title="Model library"
            description="Named presets that pathway designers choose when building pipeline steps. Each preset defines how the AI should work for that type of task."
            action={
              <Button size="small" variant="outlined" startIcon={<AddIcon />} onClick={openCreatePreset}>
                New preset
              </Button>
            }
          >
            {/* Preset card grid */}
            {presets.length === 0 ? (
              <Box sx={{ py: 2, textAlign: "center" }}>
                <Typography variant="body2" color="text.secondary">
                  No presets yet. Click <strong>New preset</strong> to create one.
                </Typography>
              </Box>
            ) : (
              <Stack direction="row" flexWrap="wrap" spacing={2} useFlexGap sx={{ mb: 2 }}>
                {presets.map((p) => (
                  <PresetCard
                    devices={devices}
                    key={p.preset_id}
                    preset={p}
                    onSetDefault={handleSetDefault}
                    onEdit={openEditPreset}
                    onDelete={handleDeletePreset}
                  />
                ))}
              </Stack>
            )}

            {/* Collapsed admin detail — individual model toggles */}
            <Accordion variant="outlined" sx={{ mt: 1, "&:before": { display: "none" }, borderRadius: 1 }}>
              <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                <Typography variant="body2" color="text.secondary">
                  Available models (admin)
                </Typography>
              </AccordionSummary>
              <AccordionDetails>
                <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1.5 }}>
                  Individual AI model connections. Disable a model here to prevent it from being used by any preset.
                </Typography>
            <InferenceDeployPanel health={health} onReloaded={load} />
            {llmDevices.map((d) => (
                  <LLMModelCard
                    key={d.device_id}
                    device={d}
                    inUse={
                      !pipelineConfig?.consensus_mode
                        ? d.device_id.startsWith(`device-${providerPrefix}`) && d.role === activeTier
                        : d.role === "small"
                    }
                    onToggle={handleToggle}
                  />
                ))}
              </AccordionDetails>
            </Accordion>
          </SectionCard>

          {/* ================================================================ */}
          {/* ZONE 2 — Default Pipeline Settings                               */}
          {/* ================================================================ */}
          <SectionCard
            icon={<StarIcon color="primary" />}
            title="System default settings"
            description="How pipelines behave unless they have their own configuration. Individual pathways in the pathway builder can override these."
            defaultOpen={false}
          >
            {pipelineConfig && <RoutingCard config={pipelineConfig} onSave={handleSaveConfig} />}
          </SectionCard>

          <SectionCard
            icon={<WarningAmberIcon color="primary" />}
            title="Terminology runtime"
            description="Live controls for batched SNOMED resolve behaviour across API replicas."
            defaultOpen={false}
          >
            <TerminologyRuntimeCard
              config={terminologyRuntimeConfig}
              onSave={handleSaveTerminologyRuntimeConfig}
            />
          </SectionCard>

          {/* ================================================================ */}
          {/* ZONE 3 — Medical Coder Lifecycle                                 */}
          {/* ================================================================ */}
          <SectionCard
            icon={<RocketLaunchIcon color="primary" />}
            title="Medical coder — versions & deployment"
            description="Every time a new medical coder is trained it gets a version number and must pass tests before going live. Expand a version to see its metrics, traceability, and available actions."
            action={
              <Button size="small" variant="contained" startIcon={<AddIcon />} onClick={() => setRegisterOpen(true)}>
                Register new version
              </Button>
            }
          >
          {versions.length === 0 ? (
            <Box sx={{ py: 2, textAlign: "center" }}>
              <Typography variant="body2" color="text.secondary">
                No model versions registered yet. Click <strong>Register new version</strong> to start.
              </Typography>
            </Box>
          ) : (
            versions.map((rec) => (
              <VersionAccordion
                key={rec.model_version}
                rec={rec}
                isLive={rec.model_version === health?.active_version}
                onRefresh={load}
              />
            ))
          )}
          </SectionCard>

          {/* Cost rates — always visible regardless of health state */}
          <SectionCard title="Cost rates" description="Per-token USD rates for each model. Seeded from environment variables; editable here without a deployment." icon={null} defaultOpen={false}>
            <ModelCostRates />
          </SectionCard>
        </>
      )}

      <RegisterVersionDialog
        open={registerOpen}
        onClose={() => setRegisterOpen(false)}
        onRegistered={load}
      />

      <PresetDialog
        open={presetDialogOpen}
        initial={editPreset}
        devices={devices}
        onClose={() => setPresetDialogOpen(false)}
        onSaved={load}
      />
    </Box>
  );
}

// =============================================================================
// ModelCostRates — inline cost-rate editor for each ModelConfig
// =============================================================================

const KNOWN_PROVIDERS = ["aws", "azure"] as const;

function ModelCostRates() {
  type MCRow = {
    key: string; provider: string; tier: string; displayName: string; modelId: string;
    costPer1mInput: number; costPer1mCachedInput: number; costPer1mOutput: number;
    isActive: boolean; source: string; updatedAt: string;
  };

  const EMPTY_NEW: Partial<MCRow> = {
    key: "", provider: "aws", tier: "small", displayName: "", modelId: "",
    costPer1mInput: 0, costPer1mCachedInput: 0, costPer1mOutput: 0, isActive: true,
  };

  const [rows, setRows]           = React.useState<MCRow[]>([]);
  const [editing, setEditing]     = React.useState<string | null>(null);
  const [draft, setDraft]         = React.useState<Partial<MCRow>>({});
  const [saving, setSaving]       = React.useState(false);
  const [deleting, setDeleting]   = React.useState<string | null>(null);
  const [addOpen, setAddOpen]     = React.useState(false);
  const [newRow, setNewRow]       = React.useState<Partial<MCRow>>(EMPTY_NEW);
  const [addErr, setAddErr]       = React.useState<string | null>(null);

  const load = React.useCallback(() => {
    apiFetch<{ modelConfigs: MCRow[] }>("/api/model-configs")
      .then((d) => setRows(d.modelConfigs || []))
      .catch(() => {});
  }, []);

  React.useEffect(() => { load(); }, [load]);

  const startEdit = (row: MCRow) => { setEditing(row.key); setDraft({ ...row }); };
  const cancel    = () => { setEditing(null); setDraft({}); };

  const save = async () => {
    if (!editing) return;
    setSaving(true);
    try {
      await apiFetch(`/api/model-configs/${encodeURIComponent(editing)}`, {
        method: "PUT",
        body: JSON.stringify({
          displayName:          draft.displayName,
          modelId:              draft.modelId,
          costPer1mInput:       Number(draft.costPer1mInput),
          costPer1mCachedInput: Number(draft.costPer1mCachedInput),
          costPer1mOutput:      Number(draft.costPer1mOutput),
          isActive:             draft.isActive ?? true,
        }),
      });
      cancel();
      load();
    } finally {
      setSaving(false);
    }
  };

  const deleteRow = async (key: string) => {
    setDeleting(key);
    try {
      await apiFetch(`/api/model-configs/${encodeURIComponent(key)}`, { method: "DELETE" });
      load();
    } finally {
      setDeleting(null);
    }
  };

  const createRow = async () => {
    if (!newRow.key?.trim()) { setAddErr("Key is required (e.g. aws:small)."); return; }
    if (!newRow.displayName?.trim()) { setAddErr("Display name is required."); return; }
    setSaving(true); setAddErr(null);
    try {
      await apiFetch("/api/model-configs", {
        method: "POST",
        body: JSON.stringify({
          key:                  newRow.key!.trim(),
          provider:             newRow.provider || "aws",
          tier:                 newRow.tier || "small",
          displayName:          newRow.displayName!.trim(),
          modelId:              newRow.modelId || "",
          costPer1mInput:       Number(newRow.costPer1mInput ?? 0),
          costPer1mCachedInput: Number(newRow.costPer1mCachedInput ?? 0),
          costPer1mOutput:      Number(newRow.costPer1mOutput ?? 0),
          isActive:             true,
        }),
      });
      setAddOpen(false);
      setNewRow(EMPTY_NEW);
      load();
    } catch (e) {
      setAddErr(e instanceof Error ? e.message : "Could not create — try again.");
    } finally {
      setSaving(false);
    }
  };

  // Group rows: known providers first (ordered), then any others
  const providerRows = (prov: string) => rows.filter((r) => r.key.startsWith(prov + ":"));
  const knownKeys    = new Set(KNOWN_PROVIDERS.flatMap((p) => rows.filter((r) => r.key.startsWith(p + ":")).map((r) => r.key)));
  const otherRows    = rows.filter((r) => !knownKeys.has(r.key));

  const RateField = ({ label, field, src }: {
    label: string;
    field: "costPer1mInput" | "costPer1mCachedInput" | "costPer1mOutput";
    src: Partial<MCRow>;
    onChange?: (v: string) => void;
  }) => null; // placeholder to keep TS happy — we inline below

  const rateDisplay = (row: MCRow) => (
    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
      <Chip size="small" variant="outlined" label={`Input $${row.costPer1mInput.toFixed(3)}/1M`} sx={{ height: 18, fontSize: "0.62rem" }} />
      <Chip size="small" variant="outlined" color="success" label={`Cached $${row.costPer1mCachedInput.toFixed(3)}/1M`} sx={{ height: 18, fontSize: "0.62rem" }} />
      <Chip size="small" variant="outlined" color="secondary" label={`Output $${row.costPer1mOutput.toFixed(3)}/1M`} sx={{ height: 18, fontSize: "0.62rem" }} />
    </Stack>
  );

  const rateEdit = (d: Partial<MCRow>, set: (f: string, v: string) => void) => (
    <Stack spacing={0.75}>
      {(["costPer1mInput", "costPer1mCachedInput", "costPer1mOutput"] as const).map((f, i) => (
        <Stack key={f} direction="row" justifyContent="space-between" alignItems="center">
          <Typography variant="caption" color="text.secondary">
            {["Input ($/1M tokens)", "Cached input ($/1M tokens)", "Output ($/1M tokens)"][i]}
          </Typography>
          <TextField size="small" type="number" value={d[f] ?? ""}
            onChange={(e) => set(f, e.target.value)}
            inputProps={{ step: 0.001, min: 0 }}
            sx={{ width: 110 }}
            InputProps={{ startAdornment: <Typography variant="caption" sx={{ mr: 0.25 }}>$</Typography> }} />
        </Stack>
      ))}
    </Stack>
  );

  const ModelRow = ({ row }: { row: MCRow }) => {
    const isEditing = editing === row.key;
    const tier = row.tier || row.key.split(":")[1] || "";
    return (
      <Paper key={row.key} variant="outlined" sx={{ p: 1.5, borderRadius: 2 }}>
        <Stack direction="row" justifyContent="space-between" alignItems="flex-start" sx={{ mb: 0.75 }}>
          <Stack direction="row" spacing={0.75} alignItems="center" flexWrap="wrap" useFlexGap>
            <Chip size="small" label={tier}
              color={tier === "small" ? "default" : tier === "big" ? "primary" : "secondary"}
              sx={{ height: 20, fontSize: "0.62rem" }} />
            <Typography variant="caption" fontWeight={600}>{row.displayName}</Typography>
            {row.source === "user" && <Chip size="small" label="edited" color="warning" variant="outlined" sx={{ height: 18, fontSize: "0.58rem" }} />}
          </Stack>
          {isEditing ? (
            <Stack direction="row" spacing={0.5}>
              <Button size="small" onClick={cancel}>Cancel</Button>
              <Button size="small" variant="contained" onClick={save} disabled={saving}>
                {saving ? <CircularProgress size={14} /> : "Save"}
              </Button>
            </Stack>
          ) : (
            <Stack direction="row" spacing={0.5}>
              <Button size="small" variant="outlined" onClick={() => startEdit(row)}>Edit rates</Button>
              <Tooltip title="Remove this cost entry">
                <span>
                  <IconButton size="small" color="error" disabled={!!deleting}
                    onClick={() => deleteRow(row.key)}>
                    {deleting === row.key ? <CircularProgress size={14} /> : <ErrorOutlineIcon fontSize="small" />}
                  </IconButton>
                </span>
              </Tooltip>
            </Stack>
          )}
        </Stack>
        <Typography variant="caption" color="text.disabled" sx={{ fontFamily: "monospace", fontSize: "0.6rem", display: "block", mb: 0.75 }}>
          {row.modelId || "—"}
        </Typography>
        {isEditing
          ? rateEdit(draft, (f, v) => setDraft((d) => ({ ...d, [f]: v })))
          : rateDisplay(row)}
      </Paper>
    );
  };

  const ProviderSection = ({ prov, label }: { prov: string; label: string }) => {
    const prows = providerRows(prov);
    if (prows.length === 0) return null;
    return (
      <Box sx={{ mb: 2 }}>
        <Typography variant="caption" fontWeight={700} color="text.disabled" sx={{ textTransform: "uppercase", letterSpacing: 1 }}>
          {label}
        </Typography>
        <Stack spacing={1} sx={{ mt: 0.75 }}>
          {prows.map((row) => <ModelRow key={row.key} row={row} />)}
        </Stack>
      </Box>
    );
  };

  return (
    <Box sx={{ mt: 3 }}>
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1.5 }}>
        <Typography variant="h6" fontWeight={700}>Model cost rates</Typography>
        <Button size="small" variant="outlined" startIcon={<AddIcon />} onClick={() => { setNewRow(EMPTY_NEW); setAddErr(null); setAddOpen(true); }}>
          Add model
        </Button>
      </Stack>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Cost rates used for spend reporting. Rates are set here — no deployment needed.
        Use the delete button (
        <ErrorOutlineIcon sx={{ fontSize: 12, verticalAlign: "middle", color: "error.main" }} />) to remove stale entries.
      </Typography>

      <ProviderSection prov="aws"   label="AWS Bedrock" />
      <ProviderSection prov="azure" label="Azure OpenAI" />

      {otherRows.length > 0 && (
        <Box sx={{ mb: 2 }}>
          <Typography variant="caption" fontWeight={700} color="text.disabled" sx={{ textTransform: "uppercase", letterSpacing: 1 }}>
            Other
          </Typography>
          <Stack spacing={1} sx={{ mt: 0.75 }}>
            {otherRows.map((row) => <ModelRow key={row.key} row={row} />)}
          </Stack>
        </Box>
      )}

      {/* Add model dialog */}
      <Dialog open={addOpen} onClose={() => setAddOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Add cost rate entry</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Add a cost rate entry for a model. The key must be unique (e.g. <code>aws:small</code> or <code>azure:big</code>).
            This only affects spend reporting — to make a model available in presets, add it to
            <code> scripts/seed_devices.py</code> and run the script.
          </Typography>
          <Stack spacing={2}>
            {addErr && <Alert severity="error">{addErr}</Alert>}
            <Stack direction="row" spacing={1.5}>
              <TextField label="Key *" size="small" sx={{ flex: 1 }}
                placeholder="e.g. aws:small" value={newRow.key ?? ""}
                onChange={(e) => setNewRow((r) => ({ ...r, key: e.target.value }))} />
              <TextField label="Provider" size="small" sx={{ flex: 1 }}
                placeholder="aws / azure / custom" value={newRow.provider ?? ""}
                onChange={(e) => setNewRow((r) => ({ ...r, provider: e.target.value }))} />
              <TextField label="Tier" size="small" sx={{ flex: 1 }}
                placeholder="small / big / max" value={newRow.tier ?? ""}
                onChange={(e) => setNewRow((r) => ({ ...r, tier: e.target.value }))} />
            </Stack>
            <TextField label="Display name *" size="small" fullWidth
              placeholder="e.g. Claude Haiku (AWS Bedrock)" value={newRow.displayName ?? ""}
              onChange={(e) => setNewRow((r) => ({ ...r, displayName: e.target.value }))} />
            <TextField label="Model ID" size="small" fullWidth
              placeholder="e.g. eu.anthropic.claude-haiku-4-5-20251001-v1:0" value={newRow.modelId ?? ""}
              onChange={(e) => setNewRow((r) => ({ ...r, modelId: e.target.value }))} />
            {rateEdit(newRow, (f, v) => setNewRow((r) => ({ ...r, [f]: v })))}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAddOpen(false)} disabled={saving}>Cancel</Button>
          <Button variant="contained" onClick={createRow} disabled={saving}
            startIcon={saving ? <CircularProgress size={14} /> : <AddIcon />}>
            Add
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

export { ModelCostRates };
