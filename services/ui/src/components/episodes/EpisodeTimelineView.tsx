/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-B1116B14
 *   DI: DI-35494904
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-B1116B14")
 */
"use client";

import { useState, useRef, useCallback, type ReactNode } from "react";
import Link from "next/link";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Typography from "@mui/material/Typography";
import Chip from "@mui/material/Chip";
import Stepper from "@mui/material/Stepper";
import Step from "@mui/material/Step";
import StepLabel from "@mui/material/StepLabel";
import StepContent from "@mui/material/StepContent";
import Alert from "@mui/material/Alert";
import Popover from "@mui/material/Popover";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import DialogActions from "@mui/material/DialogActions";
import TextField from "@mui/material/TextField";
import FormControlLabel from "@mui/material/FormControlLabel";
import Checkbox from "@mui/material/Checkbox";
import Select from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import Collapse from "@mui/material/Collapse";
import IconButton from "@mui/material/IconButton";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import type {
  Episode,
  PathwayRisk,
  BreachStatus,
  Milestone,
} from "@/lib/pathwayRisk";
import { MILESTONE_ORDER, daysBetween, BREACH_TARGETS, formatBreachLabel } from "@/lib/pathwayRisk";
import { closeEpisode, mergeEpisodes, editMilestone } from "@/lib/analyticsApi";
import { fetchEncounter, fetchEncounterCodedLinks } from "@/lib/api";
import type { CodedLink } from "@/lib/types";
import { useDemoMode } from "@/context/DemoModeContext";
import { maskEncounterText, maskPatientId } from "@/lib/demoMode";

type EpisodeWithRisk = Episode & { risk?: PathwayRisk };

const MILESTONE_LABELS: Record<string, string> = {
  presentation: "Presentation",
  first_presentation: "Presentation",
  referral: "Referral",
  referral_sent: "Referral",
  first_clinic: "First Specialist Clinic",
  specialist_visit: "Specialist Visit",
  first_clinic_visit: "First Clinic Visit",
  clinic_visit: "Clinic Visit",
  diagnosis: "Diagnosis",
  diagnosis_confirmed: "Diagnosis Confirmed",
  treatment_decision: "Treatment Decision",
  first_treatment: "First Treatment",
  treatment: "Treatment",
  treatment_started: "Treatment Started",
  investigation: "Investigation",
  related: "Related",
};

const MILESTONE_OPTIONS = [
  { value: "diagnosis_confirmed", label: "Diagnosis" },
  { value: "first_clinic_visit", label: "First Clinic Visit" },
  { value: "treatment_started", label: "First Treatment" },
  { value: "investigation", label: "Investigation" },
  { value: "first_presentation", label: "Presentation" },
  { value: "referral", label: "Referral" },
  { value: "related", label: "Related" },
  { value: "specialist_visit", label: "Specialist Visit" },
  { value: "treatment_decision", label: "Treatment Decision" },
];

function toApiMilestoneType(canonical: string): string {
  const map: Record<string, string> = {
    presentation: "first_presentation",
    first_clinic: "first_clinic_visit",
    diagnosis: "diagnosis_confirmed",
    first_treatment: "treatment_started",
  };
  return map[canonical] ?? canonical;
}

const MILESTONE_COLORS: Record<string, string> = {
  presentation: "#6366f1",
  referral: "#14B8A6",
  first_clinic: "#f59e0b",
  diagnosis: "#1F3A8A",
  treatment_decision: "#8b5cf6",
  first_treatment: "#16a34a",
};

const RISK_CHIP: Record<string, { label: string; color: "error" | "warning" | "success" | "default" }> = {
  breached: { label: "Overdue", color: "error" },
  "at-risk": { label: "At risk", color: "warning" },
  "on-track": { label: "On track", color: "success" },
  completed: { label: "Completed", color: "default" },
  unknown: { label: "Unknown", color: "default" },
};

function BreachSummaryBar({ breaches }: { breaches: BreachStatus[] }) {
  const relevant = breaches.filter(
    (b) => b.daysElapsed !== null && b.daysRemaining !== null,
  );
  if (!relevant.length) return null;

  return (
    <Box sx={{ display: "flex", gap: 1.5, mb: 2, flexWrap: "wrap" }}>
      {relevant.map((b) => {
        const overdue = !b.achieved && (b.daysRemaining ?? 0) < 0;
        const atRisk =
          !b.achieved &&
          !overdue &&
          b.daysElapsed !== null &&
          b.daysElapsed >= b.target.standardDays * 0.75;

        let color: "error" | "warning" | "success" | "default" = "success";
        let label: string;

        if (b.achieved && b.breached) {
          color = "error";
          label = formatBreachLabel(b);
        } else if (b.achieved) {
          color = "success";
          label = formatBreachLabel(b);
        } else if (overdue) {
          color = "error";
          label = formatBreachLabel(b);
        } else if (atRisk) {
          color = "warning";
          label = `${b.target.label}: ${b.daysRemaining} days left`;
        } else {
          color = "default";
          label = `${b.target.label}: ${b.daysRemaining} days left`;
        }

        return (
          <Chip
            key={b.target.label}
            label={label}
            size="small"
            color={color}
            variant="outlined"
            sx={{ fontWeight: 600, fontSize: "0.75rem" }}
          />
        );
      })}
    </Box>
  );
}

function PendingMilestoneAlert({ risk }: { risk: PathwayRisk }) {
  if (!risk.nextExpectedMilestone) return null;

  const nextLabel =
    MILESTONE_LABELS[risk.nextExpectedMilestone] ??
    risk.nextExpectedMilestone;

  const worst = risk.worstBreach;
  if (!worst || worst.achieved) return null;

  const remaining = worst.daysRemaining ?? 0;
  if (remaining >= 0 && risk.level === "on-track") return null;

  const severity = remaining < 0 ? "error" : "warning";
  const staleNote =
    remaining < 0 && Math.abs(remaining) > 365
      ? " This pathway may be stale."
      : "";
  const msg =
    remaining < 0
      ? `${nextLabel} is ${Math.abs(remaining)} days overdue.${staleNote}`
      : `${nextLabel} is due within ${remaining} days.`;

  return (
    <Alert severity={severity} sx={{ mb: 2, fontSize: "0.85rem" }}>
      {msg}
    </Alert>
  );
}

export default function EpisodeTimelineView({
  episode,
  risk,
  siblingEpisodes = [],
  onRefresh,
}: {
  episode: EpisodeWithRisk;
  risk?: PathwayRisk;
  siblingEpisodes?: EpisodeWithRisk[];
  onRefresh?: () => void;
}) {
  const { isDemoMode } = useDemoMode();
  const pathwayRisk = risk ?? episode.risk;
  const riskLevel = pathwayRisk?.level ?? "unknown";
  const chipCfg = RISK_CHIP[riskLevel] ?? RISK_CHIP.unknown;

  const milestones = episode.milestones ?? [];
  const achieved = new Set(milestones.map((m) => m.milestone_type));

  const sorted = [...milestones].sort((a, b) => {
    const ia = MILESTONE_ORDER.indexOf(a.milestone_type);
    const ib = MILESTONE_ORDER.indexOf(b.milestone_type);
    return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
  });

  const pendingSteps = MILESTONE_ORDER.filter((ms) => !achieved.has(ms));
  const activeStepIndex = sorted.length;

  const [showCloseDialog, setShowCloseDialog] = useState(false);
  const [closeReason, setCloseReason] = useState("");
  const [closeStatus, setCloseStatus] = useState<"closed" | "completed">("closed");
  const [closeSubmitting, setCloseSubmitting] = useState(false);
  const [closeError, setCloseError] = useState<string | null>(null);

  const [showMergeDialog, setShowMergeDialog] = useState(false);
  const [mergeSelected, setMergeSelected] = useState<Set<string>>(() =>
    new Set(siblingEpisodes.map((s) => s.episode_id)),
  );
  const [mergeReason, setMergeReason] = useState("");
  const [mergeSubmitting, setMergeSubmitting] = useState(false);
  const [mergeError, setMergeError] = useState<string | null>(null);

  const [editingMilestone, setEditingMilestone] = useState<string | null>(null);
  const [milestoneSubmitting, setMilestoneSubmitting] = useState(false);

  const canClose =
    episode.status !== "merged" &&
    episode.status !== "completed" &&
    episode.status !== "closed";
  const canMerge = siblingEpisodes.length > 0 && episode.status !== "merged";

  async function handleClose() {
    if (!closeReason.trim()) return;
    setCloseSubmitting(true);
    setCloseError(null);
    try {
      await closeEpisode(episode.episode_id, closeStatus, closeReason.trim());
      setShowCloseDialog(false);
      setCloseReason("");
      onRefresh?.();
    } catch (e) {
      setCloseError(e instanceof Error ? e.message : "Failed to close pathway");
    } finally {
      setCloseSubmitting(false);
    }
  }

  async function handleMerge() {
    const ids = Array.from(mergeSelected);
    if (ids.length === 0 || !mergeReason.trim()) return;
    setMergeSubmitting(true);
    setMergeError(null);
    try {
      await mergeEpisodes(episode.episode_id, ids, mergeReason.trim());
      setShowMergeDialog(false);
      setMergeReason("");
      setMergeSelected(new Set(siblingEpisodes.map((s) => s.episode_id)));
      onRefresh?.();
    } catch (e) {
      setMergeError(e instanceof Error ? e.message : "Failed to merge pathways");
    } finally {
      setMergeSubmitting(false);
    }
  }

  async function handleMilestoneChange(encounterId: string, milestoneType: string) {
    setMilestoneSubmitting(true);
    try {
      await editMilestone(episode.episode_id, encounterId, milestoneType);
      setEditingMilestone(null);
      onRefresh?.();
    } finally {
      setMilestoneSubmitting(false);
    }
  }

  return (
    <Box>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, mb: 1 }}>
        <Typography variant="h6">
          {episode.condition_type || "Referral Pathway"}
        </Typography>
        <Chip
          label={chipCfg.label}
          size="small"
          color={chipCfg.color}
        />
      </Box>

      <Box sx={{ display: "flex", gap: 1.5, mb: 1, flexWrap: "wrap", alignItems: "center" }}>
        {episode.patient_id && (
          <InfoChip
            label="Patient"
            value={isDemoMode ? maskPatientId(episode.patient_id) : episode.patient_id}
          />
        )}
        {episode.referral_date && (
          <InfoChip label="Referred" value={episode.referral_date} />
        )}
      </Box>

      <Box sx={{ display: "flex", gap: 1, mb: 2, flexWrap: "wrap", alignItems: "center" }}>
        {episode.patient_id && (
          <Button
            component={Link}
            href={`/care/patients/${episode.patient_id}?from=pathways`}
            variant="outlined"
            size="small"
            sx={{ textTransform: "none" }}
          >
            View patient encounters
          </Button>
        )}
        {canClose && (
          <Button
            variant="outlined"
            size="small"
            color="secondary"
            sx={{ textTransform: "none" }}
            onClick={() => setShowCloseDialog(true)}
          >
            Close pathway
          </Button>
        )}
        {canMerge && (
          <Button
            variant="outlined"
            size="small"
            color="warning"
            sx={{ textTransform: "none" }}
            onClick={() => {
              setMergeSelected(new Set(siblingEpisodes.map((s) => s.episode_id)));
              setShowMergeDialog(true);
            }}
          >
            Merge with\u2026
          </Button>
        )}
      </Box>

      {showCloseDialog && (
        <Dialog open onClose={() => !closeSubmitting && setShowCloseDialog(false)} maxWidth="xs" fullWidth>
          <DialogTitle>Close Pathway</DialogTitle>
          <DialogContent>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              This will mark the pathway as closed or completed. Provide a reason for the audit trail.
            </Typography>
            <TextField
              select
              fullWidth
              label="Status"
              value={closeStatus}
              onChange={(e) => setCloseStatus(e.target.value as "closed" | "completed")}
              sx={{ mb: 2 }}
            >
              <MenuItem value="closed">Closed</MenuItem>
              <MenuItem value="completed">Completed</MenuItem>
            </TextField>
            <TextField
              fullWidth
              label="Reason"
              value={closeReason}
              onChange={(e) => setCloseReason(e.target.value)}
              placeholder="e.g. Stale referral, patient discharged, duplicate"
              multiline
              rows={2}
            />
            {closeError && (
              <Typography color="error" variant="caption" sx={{ mt: 1, display: "block" }}>
                {closeError}
              </Typography>
            )}
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setShowCloseDialog(false)} disabled={closeSubmitting}>
              Cancel
            </Button>
            <Button
              variant="contained"
              onClick={handleClose}
              disabled={closeSubmitting || !closeReason.trim()}
            >
              {closeSubmitting ? "Closing..." : "Close Pathway"}
            </Button>
          </DialogActions>
        </Dialog>
      )}

      {showMergeDialog && (
        <Dialog open onClose={() => !mergeSubmitting && setShowMergeDialog(false)} maxWidth="sm" fullWidth>
          <DialogTitle>Merge Pathways</DialogTitle>
          <DialogContent>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              Merge the selected pathways into this primary pathway. All encounters will be linked to the primary.
            </Typography>
            <Box sx={{ display: "flex", flexDirection: "column", gap: 0.5, mb: 2 }}>
              {siblingEpisodes.map((sib) => (
                <FormControlLabel
                  key={sib.episode_id}
                  control={
                    <Checkbox
                      checked={mergeSelected.has(sib.episode_id)}
                      onChange={(_, checked) => {
                        setMergeSelected((prev) => {
                          const next = new Set(prev);
                          if (checked) next.add(sib.episode_id);
                          else next.delete(sib.episode_id);
                          return next;
                        });
                      }}
                    />
                  }
                  label={
                    <Typography variant="body2">
                      {sib.condition_type} - Referred {sib.referral_date} ({sib.episode_id})
                    </Typography>
                  }
                />
              ))}
            </Box>
            <TextField
              fullWidth
              label="Reason"
              value={mergeReason}
              onChange={(e) => setMergeReason(e.target.value)}
              placeholder="e.g. Same diagnostic journey, duplicate referrals"
              multiline
              rows={2}
            />
            {mergeError && (
              <Typography color="error" variant="caption" sx={{ mt: 1, display: "block" }}>
                {mergeError}
              </Typography>
            )}
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setShowMergeDialog(false)} disabled={mergeSubmitting}>
              Cancel
            </Button>
            <Button
              variant="contained"
              onClick={handleMerge}
              disabled={mergeSubmitting || mergeSelected.size === 0 || !mergeReason.trim()}
            >
              {mergeSubmitting ? "Merging..." : `Merge ${mergeSelected.size} pathway${mergeSelected.size !== 1 ? "s" : ""}`}
            </Button>
          </DialogActions>
        </Dialog>
      )}

      {episode.status === "merged" && episode.merged_into && (
        <Alert severity="info" sx={{ mb: 2 }}>
          This pathway was merged into <strong>{episode.merged_into}</strong>.
          {episode.consolidation_reasoning && (
            <Typography variant="caption" display="block" sx={{ mt: 0.5 }}>
              Reason: {episode.consolidation_reasoning}
            </Typography>
          )}
        </Alert>
      )}

      {episode.merged_from && episode.merged_from.length > 0 && (
        <Alert severity="success" sx={{ mb: 2 }}>
          This is the primary pathway. {episode.merged_from.length} pathway
          {episode.merged_from.length !== 1 ? "s were" : " was"} merged into it
          ({episode.merged_from.join(", ")}).
          {episode.consolidation_reasoning && (
            <Typography variant="caption" display="block" sx={{ mt: 0.5 }}>
              Reason: {episode.consolidation_reasoning}
            </Typography>
          )}
        </Alert>
      )}

      {episode.needs_review && (
        <ReviewAlert episode={episode} />
      )}

      {pathwayRisk && <BreachSummaryBar breaches={pathwayRisk.breaches} />}
      {pathwayRisk && <PendingMilestoneAlert risk={pathwayRisk} />}

      {siblingEpisodes.length > 0 && (
        <RelatedPathways siblings={siblingEpisodes} />
      )}

      {sorted.length === 0 && pendingSteps.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          No milestones recorded for this pathway yet.
        </Typography>
      ) : (
        <Stepper orientation="vertical" activeStep={activeStepIndex}>
          {sorted.map((m, idx) => {
            const prev = idx > 0 ? sorted[idx - 1] : null;
            const gap = prev ? daysBetween(prev.date, m.date) : null;
            const color = MILESTONE_COLORS[m.milestone_type] ?? "#64748b";
            const breachInfo = findBreachForGap(prev, m);
            const stepContent = (
              <Step key={m.encounter_id + m.milestone_type} completed>
                <StepLabel
                  StepIconProps={{
                    sx: { color: `${color} !important` },
                  }}
                >
                  <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                    <Typography sx={{ fontWeight: 600, fontSize: "0.9rem" }}>
                      {MILESTONE_LABELS[m.milestone_type] ?? m.milestone_type}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {m.date}
                    </Typography>
                    {gap != null && (
                      <Chip
                        label={`${gap}d`}
                        size="small"
                        variant="outlined"
                        sx={{ fontSize: "0.7rem", height: 20, ml: 0.5 }}
                        color={
                          breachInfo && gap > breachInfo.standardDays
                            ? "error"
                            : gap > 60
                              ? "warning"
                              : "default"
                        }
                      />
                    )}
                  </Box>
                </StepLabel>
                <StepContent>
                  <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
                    {episode.patient_id ? (
                      <Link
                        href={`/care/patients/${episode.patient_id}/encounters/view/${m.encounter_id}`}
                        style={{ textDecoration: "none" }}
                      >
                        <Typography
                          variant="caption"
                          color="primary"
                          sx={{
                            fontFamily: "monospace",
                            "&:hover": { textDecoration: "underline" },
                          }}
                        >
                          {m.encounter_id}
                        </Typography>
                      </Link>
                    ) : (
                      <Typography
                        variant="caption"
                        color="text.secondary"
                        sx={{ fontFamily: "monospace" }}
                      >
                        {m.encounter_id}
                      </Typography>
                    )}
                    <FormControl size="small" sx={{ minWidth: 140 }}>
                      <InputLabel>Milestone type</InputLabel>
                      <Select
                        value={
                          MILESTONE_OPTIONS.find(
                            (o) =>
                              o.value === m.milestone_type ||
                              o.value === toApiMilestoneType(m.milestone_type),
                          )?.value ?? toApiMilestoneType(m.milestone_type) ?? "related"
                        }
                        label="Milestone type"
                        disabled={milestoneSubmitting}
                        onChange={(e) =>
                          handleMilestoneChange(m.encounter_id, e.target.value)
                        }
                        onOpen={() => setEditingMilestone(m.encounter_id)}
                        onClose={() => setEditingMilestone(null)}
                        sx={{ height: 32, fontSize: "0.75rem" }}
                      >
                        {MILESTONE_OPTIONS.map((opt) => (
                          <MenuItem key={opt.value} value={opt.value}>
                            {opt.label}
                          </MenuItem>
                        ))}
                      </Select>
                    </FormControl>
                  </Box>
                </StepContent>
              </Step>
            );
            return episode.patient_id ? (
              <MilestoneEncounterTooltip
                key={m.encounter_id + m.milestone_type}
                patientId={episode.patient_id}
                milestone={m}
              >
                {stepContent}
              </MilestoneEncounterTooltip>
            ) : (
              stepContent
            );
          })}

          {pendingSteps.map((ms) => (
            <Step key={`pending-${ms}`} completed={false}>
              <StepLabel
                StepIconProps={{
                  sx: {
                    color:
                      ms === pathwayRisk?.nextExpectedMilestone
                        ? "warning.main"
                        : "grey.400",
                  },
                }}
              >
                <Typography
                  sx={{
                    fontWeight:
                      ms === pathwayRisk?.nextExpectedMilestone ? 600 : 400,
                    fontSize: "0.9rem",
                    color:
                      ms === pathwayRisk?.nextExpectedMilestone
                        ? "text.primary"
                        : "text.disabled",
                  }}
                >
                  {MILESTONE_LABELS[ms] ?? ms}
                  {ms === pathwayRisk?.nextExpectedMilestone && " (next)"}
                </Typography>
              </StepLabel>
            </Step>
          ))}
        </Stepper>
      )}
    </Box>
  );
}

function ReviewAlert({ episode }: { episode: Episode }) {
  const [showDetails, setShowDetails] = useState(false);
  const hasDetails = Boolean(episode.agent_reasoning);

  return (
    <Alert severity="warning" sx={{ mb: 2 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
        <Typography variant="body2" sx={{ fontWeight: 500 }}>
          This pathway needs review.
        </Typography>
        {hasDetails && (
          <Button
            size="small"
            onClick={() => setShowDetails((p) => !p)}
            sx={{ textTransform: "none", fontSize: "0.75rem", minWidth: 0, p: 0.5 }}
          >
            {showDetails ? "Hide details" : "Show details"}
          </Button>
        )}
      </Box>
      <Collapse in={showDetails}>
        {episode.agent_reasoning && (
          <Typography variant="caption" display="block" sx={{ mt: 1, lineHeight: 1.5 }}>
            {episode.agent_reasoning}
          </Typography>
        )}
        {episode.confidence != null && (
          <Typography variant="caption" display="block" sx={{ mt: 0.5, color: "text.secondary" }}>
            Confidence: {episode.confidence}%
          </Typography>
        )}
        {episode.inferred_outcome && (
          <Typography
            variant="caption"
            display="block"
            sx={{ mt: 0.75, color: "#92400E", fontWeight: 600 }}
            title={`Outcome inferred from post-clinic encounter text — not a coded diagnosis. Signals: ${episode.inference_signals ?? "none"}`}
          >
            ~ Inferred outcome: {episode.inferred_outcome}
            {episode.inferred_confidence != null && ` (${Math.round(episode.inferred_confidence * 100)}% confidence)`}
            {episode.inferred_outcome_date && ` from ${episode.inferred_outcome_date}`}
            {" — review before acting on this"}
          </Typography>
        )}
      </Collapse>
    </Alert>
  );
}

function RelatedPathways({ siblings }: { siblings: EpisodeWithRisk[] }) {
  const [open, setOpen] = useState(false);

  return (
    <Box
      sx={{
        mb: 2,
        borderRadius: 1.5,
        border: "1px solid",
        borderColor: "divider",
        bgcolor: "grey.50",
      }}
    >
      <Box
        onClick={() => setOpen((p) => !p)}
        sx={{
          display: "flex",
          alignItems: "center",
          gap: 1,
          px: 1.5,
          py: 1,
          cursor: "pointer",
          "&:hover": { bgcolor: "action.hover" },
          borderRadius: 1.5,
        }}
      >
        <IconButton
          aria-label={open ? "Collapse pathways" : "Expand pathways"}
          size="small"
          sx={{
            transform: open ? "rotate(180deg)" : "rotate(0deg)",
            transition: "transform 0.2s",
            p: 0.25,
          }}
          tabIndex={-1}
        >
          <ExpandMoreIcon fontSize="small" />
        </IconButton>
        <Typography variant="body2" sx={{ fontWeight: 500 }}>
          {siblings.length} other pathway{siblings.length !== 1 && "s"} for this patient
        </Typography>
      </Box>
      <Collapse in={open}>
        <Box sx={{ display: "flex", flexDirection: "column", gap: 0.5, px: 1.5, pb: 1.5 }}>
          {siblings.map((sib) => {
            const chipCfg = RISK_CHIP[sib.risk?.level ?? "unknown"];
            return (
              <Box
                key={sib.episode_id}
                sx={{
                  display: "flex",
                  alignItems: "center",
                  gap: 1,
                  px: 1,
                  py: 0.5,
                  borderRadius: 1,
                  bgcolor: "background.paper",
                }}
              >
                <Typography variant="caption" sx={{ fontWeight: 600 }}>
                  {sib.condition_type || "Unknown"}
                </Typography>
                <Chip
                  label={chipCfg.label}
                  size="small"
                  color={chipCfg.color}
                  sx={{ height: 18, fontSize: "0.65rem" }}
                />
                {sib.referral_date && (
                  <Typography variant="caption" color="text.secondary">
                    Referred: {sib.referral_date}
                  </Typography>
                )}
              </Box>
            );
          })}
        </Box>
      </Collapse>
    </Box>
  );
}

function CodedLinkTooltipItem({ link }: { link: CodedLink }) {
  const { isDemoMode } = useDemoMode();
  const relProps: string[] = [];
  if (link.evidence) {
    relProps.push(
      `evidence: "${
        isDemoMode ? maskEncounterText(link.evidence) : link.evidence
      }"`,
    );
  }
  if (link.confidence != null) relProps.push(`confidence: ${Math.round(link.confidence * 100)}%`);
  if (link.domain) relProps.push(`domain: ${link.domain}`);
  if (link.coded_at) relProps.push(`coded_at: ${link.coded_at}`);
  const ctx = link.context as Record<string, unknown> | undefined;
  if (ctx && Object.keys(ctx).length > 0) {
    const ctxStr = Object.entries(ctx)
      .filter(([, v]) => v != null && v !== false)
      .map(([k, v]) => `${k}: ${String(v)}`)
      .join(", ");
    if (ctxStr) relProps.push(`context: {${ctxStr}}`);
  }
  const mod = link.modifiers as Record<string, unknown> | undefined;
  if (mod && Object.keys(mod).length > 0) {
    const modStr = Object.entries(mod)
      .filter(([, v]) => v != null && v !== "")
      .map(([k, v]) => `${k}: ${String(v)}`)
      .join(", ");
    if (modStr) relProps.push(`modifiers: {${modStr}}`);
  }

  return (
    <Box sx={{ py: 0.25 }}>
      <Typography component="span" variant="caption">
        {link.term || link.concept_id}
        {link.read_code && ` (${link.read_code})`}
        {link.semantic_tag && ` [${link.semantic_tag}]`}
      </Typography>
      {relProps.length > 0 && (
        <Typography
          component="span"
          variant="caption"
          sx={{ display: "block", color: "text.secondary", fontSize: "0.7rem", mt: 0.25, pl: 1 }}
        >
          {relProps.join(" · ")}
        </Typography>
      )}
    </Box>
  );
}

function MilestoneEncounterTooltip({
  patientId,
  milestone,
  children,
}: {
  patientId: string;
  milestone: Milestone;
  children: React.ReactNode;
}) {
  const { isDemoMode } = useDemoMode();
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null);
  const [encounter, setEncounter] = useState<{ text: string } | null>(null);
  const [codedLinks, setCodedLinks] = useState<CodedLink[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const hoverTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const leaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const loadEncounter = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [encData, links] = await Promise.all([
        fetchEncounter(patientId, milestone.encounter_id),
        fetchEncounterCodedLinks(patientId, milestone.encounter_id),
      ]);
      setEncounter(encData);
      setCodedLinks(links);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load encounter");
    } finally {
      setLoading(false);
    }
  }, [patientId, milestone.encounter_id]);

  const handleMouseEnter = useCallback(
    (e: React.MouseEvent<HTMLElement>) => {
      if (leaveTimerRef.current) {
        clearTimeout(leaveTimerRef.current);
        leaveTimerRef.current = null;
      }
      hoverTimerRef.current = setTimeout(() => {
        hoverTimerRef.current = null;
        setAnchorEl(e.currentTarget);
        loadEncounter();
      }, 150);
    },
    [loadEncounter],
  );

  const handleMouseLeave = useCallback(() => {
    if (hoverTimerRef.current) {
      clearTimeout(hoverTimerRef.current);
      hoverTimerRef.current = null;
    }
    leaveTimerRef.current = setTimeout(() => {
      leaveTimerRef.current = null;
      setAnchorEl(null);
      setEncounter(null);
      setCodedLinks(null);
    }, 400);
  }, []);

  const open = Boolean(anchorEl);

  return (
    <>
      <Box
        component="span"
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
        title="Hover for encounter text and coded links"
        sx={{
          display: "block",
          width: "100%",
          cursor: "help",
        }}
      >
        {children}
      </Box>
      <Popover
        open={open}
        anchorEl={anchorEl}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
        transformOrigin={{ vertical: "top", horizontal: "center" }}
        onClose={() => setAnchorEl(null)}
        onMouseEnter={() => {
          if (leaveTimerRef.current) {
            clearTimeout(leaveTimerRef.current);
            leaveTimerRef.current = null;
          }
        }}
        onMouseLeave={handleMouseLeave}
        slotProps={{
          root: { sx: { zIndex: 1400 } },
          paper: {
            sx: {
              maxWidth: 420,
              maxHeight: 360,
              p: 1.5,
              overflow: "auto",
            },
          },
        }}
      >
        {loading && (
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, p: 2 }}>
            <CircularProgress aria-label="Loading" size={20} />
            <Typography variant="body2" color="text.secondary">
              Loading encounter...
            </Typography>
          </Box>
        )}
        {error && (
          <Typography variant="body2" color="error" sx={{ p: 1 }}>
            {error}
          </Typography>
        )}
        {!loading && !error && encounter && (
          <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
            <Typography variant="caption" fontWeight={600} color="text.secondary">
              Encounter {milestone.encounter_id} ({milestone.date})
            </Typography>
            <Typography
              variant="body2"
              component="pre"
              sx={{
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
                maxHeight: 160,
                overflow: "auto",
                fontSize: "0.8rem",
                bgcolor: "grey.50",
                p: 1,
                borderRadius: 1,
              }}
            >
              {isDemoMode
                ? maskEncounterText(encounter.text)
                : encounter.text || "(No text)"}
            </Typography>
            <Box>
              <Typography variant="caption" fontWeight={600} color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                DOCUMENTS (coded links)
              </Typography>
              {codedLinks && codedLinks.length > 0 ? (
                <Box
                  component="ul"
                  sx={{
                    m: 0,
                    pl: 2,
                    fontSize: "0.75rem",
                    maxHeight: 100,
                    overflow: "auto",
                  }}
                >
                  {codedLinks.map((link, i) => (
                    <li key={link.concept_id + String(i)}>
                      <CodedLinkTooltipItem link={link} />
                    </li>
                  ))}
                </Box>
              ) : (
                <Typography variant="caption" color="text.secondary">
                  No coded links
                </Typography>
              )}
            </Box>
          </Box>
        )}
      </Popover>
    </>
  );
}

function findBreachForGap(
  prev: Milestone | null,
  current: Milestone,
): { standardDays: number } | null {
  if (!prev) return null;
  const match = BREACH_TARGETS.find(
    (t) =>
      t.startMilestone === prev.milestone_type &&
      t.endMilestone === current.milestone_type,
  );
  return match ? { standardDays: match.standardDays } : null;
}

function InfoChip({ label, value }: { label: string; value: string }) {
  return (
    <Box
      sx={{
        px: 1.5,
        py: 0.5,
        borderRadius: 1.5,
        bgcolor: "grey.100",
        display: "inline-flex",
        alignItems: "center",
        gap: 0.5,
      }}
    >
      <Typography
        variant="caption"
        color="text.secondary"
        sx={{ fontWeight: 600 }}
      >
        {label}:
      </Typography>
      <Typography
        variant="caption"
        sx={{ fontFamily: "monospace", fontSize: "0.75rem" }}
      >
        {value}
      </Typography>
    </Box>
  );
}
