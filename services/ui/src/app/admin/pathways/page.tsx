"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import IconButton from "@mui/material/IconButton";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Divider from "@mui/material/Divider";
import Tooltip from "@mui/material/Tooltip";
import CircularProgress from "@mui/material/CircularProgress";
import Alert from "@mui/material/Alert";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import DialogActions from "@mui/material/DialogActions";
import TextField from "@mui/material/TextField";
import Paper from "@mui/material/Paper";
import AddIcon from "@mui/icons-material/Add";
import EditIcon from "@mui/icons-material/Edit";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import CloudUploadIcon from "@mui/icons-material/CloudUpload";
import ArchiveIcon from "@mui/icons-material/Archive";
import ReplayIcon from "@mui/icons-material/Replay";
import PlayCircleOutlineIcon from "@mui/icons-material/PlayCircleOutline";
import AccountTreeIcon from "@mui/icons-material/AccountTree";
import AutoFixHighIcon from "@mui/icons-material/AutoFixHigh";
import { api } from "@/lib/api";

// ── Pathway templates ──────────────────────────────────────────────────────────

interface PathwayTemplate {
  id: string;
  name: string;
  description: string;
  stepCount: number;
  payload: Record<string, unknown>;
}

const PATHWAY_TEMPLATES: PathwayTemplate[] = [
  {
    id: "blank",
    name: "Start from scratch",
    description: "Empty canvas — add and connect steps yourself.",
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
          config: { subgraphId: "extraction", label: "Find Clinical Facts", description: "Read patient notes and pull out clinical facts.", inputSource: "encounter_text", outputTarget: "patient_graph", enableVerification: false, maxRetries: 2, timeout: 120, modelPresetId: "", modelPresetName: "", temperature: 0, promptConfigId: "", promptConfigName: "", params: {} },
        },
        {
          id: "step_persist",
          subgraphId: "persist",
          label: "Save Results",
          nodeType: "action",
          position: { x: 520, y: 200 },
          config: { subgraphId: "persist", label: "Save Results", description: "Write extracted facts to the patient record.", inputSource: "previous_step", outputTarget: "patient_graph", enableVerification: false, maxRetries: 2, timeout: 120, modelPresetId: "", modelPresetName: "", temperature: 0, promptConfigId: "", promptConfigName: "", params: {} },
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
          config: { subgraphId: "extraction", label: "Find Clinical Facts", description: "Read patient notes and pull out clinical facts.", inputSource: "encounter_text", outputTarget: "patient_graph", enableVerification: false, maxRetries: 2, timeout: 120, modelPresetId: "", modelPresetName: "", temperature: 0, promptConfigId: "", promptConfigName: "", params: {} },
        },
        {
          id: "step_verify",
          subgraphId: "verification",
          label: "Double-Check with AI",
          nodeType: "action",
          position: { x: 460, y: 200 },
          config: { subgraphId: "verification", label: "Double-Check with AI", description: "Run a second AI to catch any errors before saving.", inputSource: "previous_step", outputTarget: "patient_graph", enableVerification: false, maxRetries: 1, timeout: 120, modelPresetId: "", modelPresetName: "", temperature: 0, promptConfigId: "", promptConfigName: "", params: {} },
        },
        {
          id: "step_persist",
          subgraphId: "persist",
          label: "Save Results",
          nodeType: "action",
          position: { x: 760, y: 200 },
          config: { subgraphId: "persist", label: "Save Results", description: "Write verified facts to the patient record.", inputSource: "previous_step", outputTarget: "patient_graph", enableVerification: false, maxRetries: 2, timeout: 120, modelPresetId: "", modelPresetName: "", temperature: 0, promptConfigId: "", promptConfigName: "", params: {} },
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
          config: { subgraphId: "extraction", label: "Find Clinical Facts", description: "Extract clinical facts from de-identified notes.", inputSource: "knowledge_graph", outputTarget: "gold_training", enableVerification: false, maxRetries: 2, timeout: 120, modelPresetId: "", modelPresetName: "", temperature: 0, promptConfigId: "", promptConfigName: "", params: { input_node_label: "TrainingCandidate", input_text_property: "text" } },
        },
        {
          id: "step_verify",
          subgraphId: "verification",
          label: "Double-Check with AI",
          nodeType: "action",
          position: { x: 460, y: 200 },
          config: { subgraphId: "verification", label: "Double-Check with AI", description: "Verify extracted facts against the source text.", inputSource: "previous_step", outputTarget: "gold_training", enableVerification: false, maxRetries: 1, timeout: 120, modelPresetId: "", modelPresetName: "", temperature: 0, promptConfigId: "", promptConfigName: "", params: {} },
        },
        {
          id: "step_persist",
          subgraphId: "persist",
          label: "Save as Training Labels",
          nodeType: "action",
          position: { x: 760, y: 200 },
          config: { subgraphId: "persist", label: "Save as Training Labels", description: "Write gold-labelled facts to the training dataset.", inputSource: "previous_step", outputTarget: "gold_training", enableVerification: false, maxRetries: 2, timeout: 120, modelPresetId: "", modelPresetName: "", temperature: 0, promptConfigId: "", promptConfigName: "", params: {} },
        },
      ],
      edges: [
        { source: "step_extract", target: "step_verify" },
        { source: "step_verify", target: "step_persist" },
      ],
    },
  },
];

// ── Template picker dialog ─────────────────────────────────────────────────────

function NewPathwayDialog({
  open,
  onClose,
  onCreate,
  creating,
}: {
  open: boolean;
  onClose: () => void;
  onCreate: (template: PathwayTemplate) => void;
  creating: boolean;
}) {
  const [selected, setSelected] = useState<string>("blank");
  const template = PATHWAY_TEMPLATES.find((t) => t.id === selected) ?? PATHWAY_TEMPLATES[0];

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth PaperProps={{ sx: { borderRadius: 3 } }}>
      <DialogTitle sx={{ pb: 0.5 }}>
        <Stack direction="row" alignItems="center" spacing={1}>
          <AutoFixHighIcon color="primary" sx={{ fontSize: "1.3rem" }} />
          <Typography variant="h6" fontWeight={700}>Start a new pathway</Typography>
        </Stack>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
          Pick a ready-made starting point or build from scratch.
        </Typography>
      </DialogTitle>
      <DialogContent sx={{ pt: 1.5 }}>
        <Stack spacing={1.25}>
          {PATHWAY_TEMPLATES.map((t) => (
            <Paper
              key={t.id}
              variant="outlined"
              onClick={() => setSelected(t.id)}
              sx={{
                p: 1.75,
                borderRadius: 2,
                cursor: "pointer",
                borderColor: selected === t.id ? "primary.main" : "divider",
                borderWidth: selected === t.id ? 2 : 1,
                bgcolor: selected === t.id ? "primary.50" : "background.paper",
                transition: "all 0.15s",
                "&:hover": { borderColor: "primary.light", boxShadow: 1 },
              }}
            >
              <Stack direction="row" alignItems="flex-start" spacing={1.5}>
                <Box sx={{ flex: 1 }}>
                  <Stack direction="row" alignItems="center" spacing={1}>
                    <Typography variant="subtitle2" fontWeight={700}>{t.name}</Typography>
                    {t.stepCount > 0 && (
                      <Chip size="small" label={`${t.stepCount} step${t.stepCount !== 1 ? "s" : ""} ready`}
                        color="success" variant="outlined"
                        sx={{ height: 18, fontSize: "0.6rem" }} />
                    )}
                  </Stack>
                  <Typography variant="caption" color="text.secondary" sx={{ mt: 0.25, display: "block", lineHeight: 1.4 }}>
                    {t.description}
                  </Typography>
                </Box>
                <Box sx={{
                  width: 20, height: 20, borderRadius: "50%", border: "2px solid",
                  borderColor: selected === t.id ? "primary.main" : "grey.300",
                  bgcolor: selected === t.id ? "primary.main" : "transparent",
                  flexShrink: 0, mt: 0.25,
                  display: "flex", alignItems: "center", justifyContent: "center",
                }}>
                  {selected === t.id && <Box sx={{ width: 8, height: 8, borderRadius: "50%", bgcolor: "#fff" }} />}
                </Box>
              </Stack>
            </Paper>
          ))}
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose} disabled={creating} sx={{ textTransform: "none" }}>Cancel</Button>
        <Button
          variant="contained"
          disabled={creating}
          startIcon={creating ? <CircularProgress size={13} color="inherit" /> : <AddIcon />}
          onClick={() => onCreate(template)}
          sx={{ textTransform: "none" }}
        >
          {creating ? "Creating…" : template.id === "blank" ? "Create blank pathway" : "Use this template"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

interface PlanDefinition {
  id: string;
  name: string;
  status: "draft" | "active" | "retired" | string;
  description?: string;
  version?: string;
  date?: string;
  trigger?: { event?: string };
  actions?: Array<{ id: string }>;
  actionCount?: number;
}

// ── Per-card actions ───────────────────────────────────────────────────────────

function statusColor(status: string): "success" | "warning" | "default" | "error" {
  if (status === "active") return "success";
  if (status === "draft")  return "warning";
  if (status === "retired") return "default";
  return "default";
}

function statusLabel(status: string) {
  if (status === "active")  return "Live";
  if (status === "draft")   return "Draft";
  if (status === "retired") return "Retired";
  return status;
}

interface CardProps {
  plan: PlanDefinition;
  onEdit: () => void;
  onPublish: () => void;
  onDuplicate: () => void;
  onRetire: () => void;
  onReactivate: () => void;
  busy: boolean;
}

function PathwayCard({ plan, onEdit, onPublish, onDuplicate, onRetire, onReactivate, busy }: CardProps) {
  const actionCount = plan.actionCount ?? plan.actions?.length ?? 0;
  const triggerLabel = plan.trigger?.event?.replace(/-/g, " ") ?? null;

  return (
    <Box
      sx={{
        display: "flex",
        borderRadius: 2,
        border: "1px solid",
        borderColor: "divider",
        overflow: "hidden",
        bgcolor: "background.paper",
        transition: "box-shadow 0.15s",
        "&:hover": { boxShadow: 2 },
      }}
    >
      {/* Status accent bar */}
      <Box sx={{
        width: 4,
        flexShrink: 0,
        bgcolor: plan.status === "active" ? "success.main" : plan.status === "draft" ? "warning.main" : "grey.300",
      }} />

      <Box sx={{ flex: 1, p: 2 }}>
        <Stack direction="row" alignItems="flex-start" spacing={1}>
          <Box sx={{ flex: 1 }}>
            <Stack direction="row" alignItems="center" spacing={1} flexWrap="wrap" useFlexGap>
              <Typography variant="subtitle2" fontWeight={700} sx={{ lineHeight: 1.3 }}>
                {plan.name || "Untitled pathway"}
              </Typography>
              <Chip
                label={statusLabel(plan.status)}
                size="small"
                color={statusColor(plan.status)}
                sx={{ height: 18, fontSize: "0.62rem", fontWeight: 700 }}
              />
              {plan.version && (
                <Typography variant="caption" color="text.disabled" sx={{ fontSize: "0.62rem" }}>
                  v{plan.version}
                </Typography>
              )}
            </Stack>
            <Typography variant="caption" color="text.secondary" sx={{ mt: 0.4, display: "block", lineHeight: 1.4 }}>
              {plan.description || "No description"}
            </Typography>
          </Box>

          {/* Primary edit button */}
          <Button
            size="small"
            variant="outlined"
            startIcon={<EditIcon sx={{ fontSize: "0.9rem !important" }} />}
            onClick={onEdit}
            sx={{ textTransform: "none", fontSize: "0.75rem", flexShrink: 0 }}
          >
            Edit
          </Button>
        </Stack>

        {/* Metadata row */}
        <Stack direction="row" spacing={1.5} sx={{ mt: 1.25 }} alignItems="center" flexWrap="wrap" useFlexGap>
          {actionCount > 0 && (
            <Stack direction="row" alignItems="center" spacing={0.4}>
              <AccountTreeIcon sx={{ fontSize: "0.75rem", color: "text.disabled" }} />
              <Typography variant="caption" color="text.disabled" sx={{ fontSize: "0.68rem" }}>
                {actionCount} step{actionCount !== 1 ? "s" : ""}
              </Typography>
            </Stack>
          )}
          {triggerLabel && (
            <Stack direction="row" alignItems="center" spacing={0.4}>
              <PlayCircleOutlineIcon sx={{ fontSize: "0.75rem", color: "text.disabled" }} />
              <Typography variant="caption" color="text.disabled" sx={{ fontSize: "0.68rem", textTransform: "capitalize" }}>
                {triggerLabel}
              </Typography>
            </Stack>
          )}
          {plan.date && (
            <Typography variant="caption" color="text.disabled" sx={{ fontSize: "0.68rem" }}>
              Updated {new Date(plan.date).toLocaleDateString()}
            </Typography>
          )}
        </Stack>

        <Divider sx={{ my: 1.25 }} />

        {/* Secondary actions */}
        <Stack direction="row" spacing={0.75} alignItems="center">
          {plan.status === "draft" && (
            <Tooltip title="Publish this draft to live — it will immediately be used by the runtime">
              <span>
                <Button
                  size="small"
                  variant="contained"
                  color="success"
                  startIcon={busy ? <CircularProgress size={11} color="inherit" /> : <CloudUploadIcon sx={{ fontSize: "0.9rem !important" }} />}
                  disabled={busy}
                  onClick={onPublish}
                  sx={{ textTransform: "none", fontSize: "0.72rem" }}
                >
                  Publish to live
                </Button>
              </span>
            </Tooltip>
          )}

          {plan.status === "active" && (
            <Tooltip title="Save a draft copy to edit without affecting the live version">
              <Button
                size="small"
                variant="outlined"
                startIcon={<ContentCopyIcon sx={{ fontSize: "0.9rem !important" }} />}
                onClick={onDuplicate}
                disabled={busy}
                sx={{ textTransform: "none", fontSize: "0.72rem" }}
              >
                New draft
              </Button>
            </Tooltip>
          )}

          {plan.status !== "active" && (
            <Tooltip title="Duplicate as a new draft">
              <IconButton size="small" onClick={onDuplicate} disabled={busy} sx={{ color: "text.secondary" }}>
                <ContentCopyIcon sx={{ fontSize: "1rem" }} />
              </IconButton>
            </Tooltip>
          )}

          {plan.status === "retired" && (
            <Tooltip title="Reactivate — publish this back to live">
              <Button
                size="small"
                variant="outlined"
                color="warning"
                startIcon={<ReplayIcon sx={{ fontSize: "0.9rem !important" }} />}
                onClick={onReactivate}
                disabled={busy}
                sx={{ textTransform: "none", fontSize: "0.72rem" }}
              >
                Reactivate
              </Button>
            </Tooltip>
          )}

          <Box sx={{ flex: 1 }} />

          {plan.status !== "retired" && (
            <Tooltip title={plan.status === "active" ? "Retire this pathway from live use" : "Mark as retired"}>
              <IconButton
                size="small"
                onClick={onRetire}
                disabled={busy}
                sx={{ color: "text.disabled", "&:hover": { color: "error.main" } }}
              >
                <ArchiveIcon sx={{ fontSize: "1rem" }} />
              </IconButton>
            </Tooltip>
          )}
        </Stack>
      </Box>
    </Box>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────────

export default function PathwaysPage() {
  const router = useRouter();
  const [plans, setPlans] = useState<PlanDefinition[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<Record<string, boolean>>({});
  const [error, setError] = useState<string | null>(null);

  // Template picker dialog
  const [newDialogOpen, setNewDialogOpen] = useState(false);
  const [creating, setCreating] = useState(false);

  // Publish confirmation dialog
  const [publishTarget, setPublishTarget] = useState<PlanDefinition | null>(null);
  const [versionNotes, setVersionNotes] = useState("");
  const [publishing, setPublishing] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    api.get<{ entry: Array<{ resource: PlanDefinition }> }>("/fhir/PlanDefinition")
      .then((data) => setPlans((data.entry || []).map((e) => e.resource)))
      .catch(() => setPlans([]))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const setBusyFor = (id: string, val: boolean) =>
    setBusy((prev) => ({ ...prev, [id]: val }));

  const patchStatus = async (plan: PlanDefinition, status: string) => {
    setBusyFor(plan.id, true);
    try {
      await api.put(`/fhir/PlanDefinition/${plan.id}`, { ...plan, status });
      setPlans((prev) => prev.map((p) => p.id === plan.id ? { ...p, status } : p));
    } catch {
      setError("Failed to update pathway status. Please try again.");
    } finally {
      setBusyFor(plan.id, false);
    }
  };

  const handleDuplicate = async (plan: PlanDefinition) => {
    setBusyFor(plan.id, true);
    try {
      const { id: _id, ...rest } = plan;
      const newPlan = { ...rest, name: `Copy of ${plan.name}`, status: "draft", version: undefined };
      await api.post("/fhir/PlanDefinition", newPlan);
      load();
    } catch {
      setError("Failed to duplicate pathway.");
    } finally {
      setBusyFor(plan.id, false);
    }
  };

  const handleCreateFromTemplate = async (template: PathwayTemplate) => {
    setCreating(true);
    try {
      const result = await api.post<{ id: string }>("/fhir/PlanDefinition", template.payload);
      router.push(`/admin/pathways/${result.id}`);
    } catch {
      setError("Could not create pathway. Please try again.");
      setCreating(false);
    }
  };

  const confirmPublish = async () => {
    if (!publishTarget) return;
    setPublishing(true);
    try {
      await api.put(`/fhir/PlanDefinition/${publishTarget.id}`, {
        ...publishTarget,
        status: "active",
        // version notes stored in meta if the API supports it; harmless if not
        meta: { ...(publishTarget as any).meta, versionNotes },
      });
      setPlans((prev) => prev.map((p) => p.id === publishTarget.id ? { ...p, status: "active" } : p));
      setPublishTarget(null);
      setVersionNotes("");
    } catch {
      setError("Publish failed. Please try again.");
    } finally {
      setPublishing(false);
    }
  };

  const active  = plans.filter((p) => p.status === "active");
  const drafts  = plans.filter((p) => p.status === "draft");
  const retired = plans.filter((p) => p.status === "retired");

  const cardProps = (plan: PlanDefinition): CardProps => ({
    plan,
    busy: !!busy[plan.id],
    onEdit: () => router.push(`/admin/pathways/${plan.id}`),
    onPublish: () => { setPublishTarget(plan); setVersionNotes(""); },
    onDuplicate: () => handleDuplicate(plan),
    onRetire: () => patchStatus(plan, "retired"),
    onReactivate: () => { setPublishTarget(plan); setVersionNotes(""); },
  });

  return (
    <Box sx={{ p: 3, maxWidth: 960, mx: "auto" }}>
      {/* Page header */}
      <Stack direction="row" alignItems="center" sx={{ mb: 3 }}>
        <Box sx={{ flex: 1 }}>
          <Typography variant="h5" fontWeight={700}>Clinical Pathways</Typography>
          <Typography variant="caption" color="text.secondary">
            {active.length} live · {drafts.length} draft{drafts.length !== 1 ? "s" : ""} · {retired.length} retired
          </Typography>
        </Box>
        <Button variant="contained" startIcon={<AddIcon />} onClick={() => setNewDialogOpen(true)}>
          New pathway
        </Button>
      </Stack>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>{error}</Alert>
      )}

      {loading ? (
        <Stack alignItems="center" sx={{ pt: 6 }}>
          <CircularProgress size={28} />
          <Typography variant="caption" color="text.secondary" sx={{ mt: 1 }}>Loading pathways…</Typography>
        </Stack>
      ) : plans.length === 0 ? (
        <Box sx={{ textAlign: "center", py: 8 }}>
          <AccountTreeIcon sx={{ fontSize: 48, color: "text.disabled", mb: 1 }} />
          <Typography color="text.secondary" gutterBottom>No pathways configured yet.</Typography>
          <Button variant="contained" startIcon={<AddIcon />} onClick={() => setNewDialogOpen(true)} sx={{ mt: 1 }}>
            Create your first pathway
          </Button>
        </Box>
      ) : (
        <Stack spacing={3}>

          {/* ── Live ── */}
          {active.length > 0 && (
            <Box>
              <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1.5 }}>
                <Box sx={{ width: 8, height: 8, borderRadius: "50%", bgcolor: "success.main" }} />
                <Typography variant="overline" sx={{ fontSize: "0.65rem", letterSpacing: 1.4, lineHeight: 1, color: "text.secondary" }}>
                  Live — running on patient data
                </Typography>
              </Stack>
              <Stack spacing={1.5}>
                {active.map((plan) => <PathwayCard key={plan.id} {...cardProps(plan)} />)}
              </Stack>
            </Box>
          )}

          {/* ── Drafts ── */}
          {drafts.length > 0 && (
            <Box>
              <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1.5 }}>
                <Box sx={{ width: 8, height: 8, borderRadius: "50%", bgcolor: "warning.main" }} />
                <Typography variant="overline" sx={{ fontSize: "0.65rem", letterSpacing: 1.4, lineHeight: 1, color: "text.secondary" }}>
                  In draft — not yet live
                </Typography>
              </Stack>
              <Stack spacing={1.5}>
                {drafts.map((plan) => <PathwayCard key={plan.id} {...cardProps(plan)} />)}
              </Stack>
            </Box>
          )}

          {/* ── Retired ── */}
          {retired.length > 0 && (
            <Box>
              <Divider sx={{ mb: 2 }} />
              <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1.5 }}>
                <Box sx={{ width: 8, height: 8, borderRadius: "50%", bgcolor: "grey.400" }} />
                <Typography variant="overline" sx={{ fontSize: "0.65rem", letterSpacing: 1.4, lineHeight: 1, color: "text.disabled" }}>
                  Retired
                </Typography>
              </Stack>
              <Stack spacing={1.5}>
                {retired.map((plan) => <PathwayCard key={plan.id} {...cardProps(plan)} />)}
              </Stack>
            </Box>
          )}
        </Stack>
      )}

      {/* ── New pathway / template picker ────────────────────────────────────── */}
      <NewPathwayDialog
        open={newDialogOpen}
        onClose={() => setNewDialogOpen(false)}
        onCreate={handleCreateFromTemplate}
        creating={creating}
      />

      {/* ── Publish confirmation dialog ───────────────────────────────────────── */}
      <Dialog
        open={!!publishTarget}
        onClose={() => !publishing && setPublishTarget(null)}
        maxWidth="xs"
        fullWidth
        PaperProps={{ sx: { borderRadius: 3 } }}
      >
        <DialogTitle sx={{ pb: 0.5 }}>
          <Stack direction="row" alignItems="center" spacing={1}>
            <CloudUploadIcon color="success" sx={{ fontSize: "1.3rem" }} />
            <Typography variant="h6" fontWeight={700}>Publish to live</Typography>
          </Stack>
        </DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            <strong>{publishTarget?.name}</strong> will become the live version immediately.
            The runtime will begin using it for new pipeline executions.
          </Typography>
          <Alert severity="info" icon={false} sx={{ mb: 2, fontSize: "0.78rem" }}>
            To roll back, edit the pathway and publish again, or duplicate a previous version.
          </Alert>
          <TextField
            label="Version notes (optional)"
            placeholder="e.g. Added verification step before persist, updated extraction prompt to v3"
            multiline
            minRows={2}
            fullWidth
            size="small"
            value={versionNotes}
            onChange={(e) => setVersionNotes(e.target.value)}
          />
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setPublishTarget(null)} disabled={publishing} sx={{ textTransform: "none" }}>
            Cancel
          </Button>
          <Button
            variant="contained"
            color="success"
            disabled={publishing}
            startIcon={publishing ? <CircularProgress size={13} color="inherit" /> : <CloudUploadIcon />}
            onClick={confirmPublish}
            sx={{ textTransform: "none" }}
          >
            {publishing ? "Publishing…" : "Publish to live"}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
