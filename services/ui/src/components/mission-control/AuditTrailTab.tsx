/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-146D93D0
 *   Also implements: DO-EE78E305
 *   DI: DI-6EA84931
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-146D93D0")
 */
"use client";

import { useEffect, useMemo, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import Typography from "@mui/material/Typography";
import CheckCircleOutline from "@mui/icons-material/CheckCircleOutline";
import FlagOutlined from "@mui/icons-material/FlagOutlined";
import type { MissionEpisode } from "@/lib/missionControlApi";
import {
  fetchPatientPipelineEvents,
  fetchPatientManualEvents,
  type PipelineAuditEvent,
  type ManualAuditEvent,
} from "@/lib/missionControlApi";
import { getStatusLabel } from "@/lib/pathwayLabels";
import { sortByIsoDateDesc } from "@/lib/dateSort";

interface Props {
  patientId: string;
  episode: MissionEpisode | null;
  orgId?: string;
  /** Bumped by the parent drawer after an inline coding edit so this
   *  tab refetches the pipeline / audit history and shows new
   *  events without forcing a drawer close/reopen. */
  refreshKey?: number;
}

function formatDateTime(iso: string | null): string {
  if (!iso) return "--";
  try {
    return new Date(iso).toLocaleString("en-GB", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function pipelineOutcomeLabel(status: string | null): string {
  switch (status) {
    case "completed":
      return "Finished";
    case "empty_extraction":
      return "No codes extracted";
    case "error":
      return "Stopped with error";
    case "needs_review":
      return "Needs review";
    default:
      return status ? status.replace(/_/g, " ") : "Unknown";
  }
}

function pipelineChipColor(
  status: string | null
): "default" | "success" | "warning" | "error" {
  if (status === "completed") return "success";
  if (status === "error") return "error";
  if (status === "empty_extraction" || status === "needs_review") return "warning";
  return "default";
}

function formatDurationMs(ms: number | null): string {
  if (ms == null || ms < 0) return "--";
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

// -- Manual event helpers --

const MANUAL_EVENT_LABELS: Record<string, string> = {
  EpisodeManualCreate: "Created pathway",
  EpisodeManualUpdate: "Updated pathway properties",
  EpisodeManualDelete: "Deleted pathway",
  EpisodeManualAttach: "Attached encounter",
  EpisodeManualDetach: "Detached encounter",
  EpisodeManualReplace: "Replaced encounter on slot",
};

function manualEventLabel(eventType: string | null): string {
  if (!eventType) return "Manual change";
  return MANUAL_EVENT_LABELS[eventType] ?? eventType.replace(/^Episode/, "");
}

function manualEventColor(eventType: string | null): "default" | "info" | "error" | "warning" {
  if (!eventType) return "default";
  if (eventType === "EpisodeManualDelete") return "error";
  if (eventType === "EpisodeManualReplace") return "warning";
  return "info";
}

function formatActor(actor: ManualAuditEvent): string {
  const role = actor.actor_role || "user";
  const email = actor.actor_email || "(unknown)";
  return `${email} (${role})`;
}

export default function AuditTrailTab({
  patientId,
  episode,
  orgId,
  refreshKey = 0,
}: Props) {
  const [pipelineEvents, setPipelineEvents] = useState<PipelineAuditEvent[] | null>(null);
  const [pipelineError, setPipelineError] = useState<string | null>(null);
  const [pipelineLoading, setPipelineLoading] = useState(true);
  const [manualEvents, setManualEvents] = useState<ManualAuditEvent[] | null>(null);
  const [manualError, setManualError] = useState<string | null>(null);
  const [manualLoading, setManualLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setPipelineLoading(true);
    setPipelineError(null);
    fetchPatientPipelineEvents(patientId, {
      episodeId: episode?.episode_id,
      orgId: orgId || undefined,
      limit: 40,
    })
      .then((res) => {
        if (!cancelled) setPipelineEvents(res.events);
      })
      .catch((e: Error) => {
        if (!cancelled) setPipelineError(e.message || "Could not load pipeline history");
      })
      .finally(() => {
        if (!cancelled) setPipelineLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [patientId, episode?.episode_id, orgId, refreshKey]);

  // Manual EpisodeManual* AuditEvent rows -- writes from the curator
  // dialogs (create / update / delete / attach / detach / replace).
  // Loaded in a separate effect so a slow / failing endpoint cannot
  // hide the pipeline runs and vice versa.
  useEffect(() => {
    let cancelled = false;
    setManualLoading(true);
    setManualError(null);
    fetchPatientManualEvents(patientId, {
      episodeId: episode?.episode_id,
      orgId: orgId || undefined,
      limit: 40,
    })
      .then((res) => {
        if (!cancelled) setManualEvents(res.events);
      })
      .catch((e: Error) => {
        if (!cancelled) setManualError(e.message || "Could not load human audit history");
      })
      .finally(() => {
        if (!cancelled) setManualLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [patientId, episode?.episode_id, orgId, refreshKey]);

  const hasReview = Boolean(episode?.reviewed_by);
  const hasHumanAudit =
    hasReview || Boolean(episode?.audit_notes) || Boolean(episode?.audit_flag);
  const pipelineEventsSorted = useMemo(
    () =>
      pipelineEvents
        ? sortByIsoDateDesc(pipelineEvents, (ev) => ev.created_at)
        : null,
    [pipelineEvents],
  );
  const hasPipelineRows = (pipelineEventsSorted?.length ?? 0) > 0;
  const manualEventsSorted = useMemo(
    () =>
      manualEvents
        ? sortByIsoDateDesc(manualEvents, (ev) => ev.created_at)
        : null,
    [manualEvents],
  );
  const hasManualRows = (manualEventsSorted?.length ?? 0) > 0;

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <Box>
        <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1 }}>
          Pipeline runs
        </Typography>
        <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
          Coding and workflow jobs for this pathway. Newest first.
        </Typography>
        {pipelineLoading && (
          <Typography variant="body2" color="text.secondary">
            Loading pipeline history...
          </Typography>
        )}
        {pipelineError && (
          <Alert severity="warning" sx={{ mt: 1 }}>
            {pipelineError}
          </Alert>
        )}
        {!pipelineLoading && !pipelineError && !hasPipelineRows && (
          <Alert severity="info">
            No pipeline runs are recorded for this pathway yet. After you run coding or a full
            patient rebuild, summaries will appear here.
          </Alert>
        )}
        {          !pipelineLoading &&
          !pipelineError &&
          hasPipelineRows &&
          pipelineEventsSorted!.map((ev) => (
            <Box
              key={ev.id ?? ev.run_id ?? String(ev.created_at)}
              sx={{
                mb: 1.5,
                p: 1.5,
                borderRadius: 1,
                border: "1px solid",
                borderColor: "divider",
                bgcolor: "grey.50",
              }}
            >
              {/* Header row: timestamp + outcome chip */}
              <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1, alignItems: "center" }}>
                <Typography variant="body2" sx={{ fontWeight: 600 }}>
                  {formatDateTime(ev.created_at)}
                </Typography>
                <Chip
                  size="small"
                  label={pipelineOutcomeLabel(ev.status)}
                  color={pipelineChipColor(ev.status)}
                  variant="outlined"
                />
              </Box>

              {/* Run summary: run id, scope, timing, codes */}
              <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
                Run {ev.run_id ? `${ev.run_id.slice(0, 8)}...` : "--"}
                {ev.encounter_id ? ` · Encounter ${ev.encounter_id}` : " · Whole patient"}
                {ev.step_count != null ? ` · ${ev.step_count} step${ev.step_count !== 1 ? "s" : ""}` : ""}
                {" · "}
                {formatDurationMs(ev.total_duration_ms)}
                {ev.entity_count != null ? ` · ${ev.entity_count} code${ev.entity_count !== 1 ? "s" : ""} found` : ""}
                {ev.error_count != null && ev.error_count > 0
                  ? ` · ${ev.error_count} issue${ev.error_count !== 1 ? "s" : ""}`
                  : ""}
              </Typography>

              {/* LLM spend */}
              {(ev.llm_input_tokens != null || ev.llm_output_tokens != null) && (
                <Typography variant="caption" color="text.secondary" display="block">
                  LLM tokens: {ev.llm_input_tokens ?? 0} in / {ev.llm_output_tokens ?? 0} out
                  {(ev.llm_cached_tokens ?? 0) > 0
                    ? ` / ${ev.llm_cached_tokens} cached`
                    : ""}
                  {ev.llm_cost_usd != null && ev.llm_cost_usd > 0
                    ? ` · $${ev.llm_cost_usd.toFixed(4)}`
                    : ""}
                </Typography>
              )}

              {/* Extraction step provenance */}
              {ev.extraction_prompt_name && (
                <Typography variant="caption" color="text.secondary" display="block">
                  Prompt: {ev.extraction_prompt_name}
                  {ev.extraction_prompt_version != null
                    ? ` v${ev.extraction_prompt_version}`
                    : ""}
                  {ev.extraction_provider
                    ? ` · ${ev.extraction_provider}${ev.extraction_model_tier ? ` (${ev.extraction_model_tier})` : ""}`
                    : ""}
                  {ev.extraction_prompt_hash
                    ? ` · hash ${ev.extraction_prompt_hash.slice(0, 8)}`
                    : ""}
                </Typography>
              )}

              {/* First error (flat field -- fast to read, no JSON parse needed) */}
              {ev.first_error && (
                <Box
                  sx={{
                    mt: 1,
                    p: 1,
                    fontSize: "0.7rem",
                    overflow: "auto",
                    maxHeight: 80,
                    bgcolor: "error.lighter",
                    color: "error.dark",
                    borderRadius: 0.5,
                    fontFamily: "monospace",
                    whiteSpace: "pre-wrap",
                  }}
                >
                  {ev.first_error}
                </Box>
              )}
            </Box>
          ))}
      </Box>

      <Divider />

      <Box>
        <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1 }}>
          Human edits
        </Typography>
        <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
          Pathway changes a curator made by hand: create, update, delete,
          attach / detach encounters, slot replacements. Newest first.
        </Typography>
        {manualLoading && (
          <Typography variant="body2" color="text.secondary">
            Loading human edit history...
          </Typography>
        )}
        {manualError && (
          <Alert severity="warning" sx={{ mt: 1 }}>
            {manualError}
          </Alert>
        )}
        {!manualLoading && !manualError && !hasManualRows && (
          <Alert severity="info">
            No manual edits recorded for this pathway yet. Changes you make
            via Edit, Delete, or the milestone dialog will appear here.
          </Alert>
        )}
        {!manualLoading &&
          !manualError &&
          hasManualRows &&
          manualEventsSorted!.map((ev) => (
            <Box
              key={ev.id ?? `${ev.event_type}-${ev.created_at}`}
              data-testid="manual-event-row"
              sx={{
                mb: 1.5,
                p: 1.5,
                borderRadius: 1,
                border: "1px solid",
                borderColor: "divider",
                bgcolor: "grey.50",
              }}
            >
              <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1, alignItems: "center" }}>
                <Typography variant="body2" sx={{ fontWeight: 600 }}>
                  {formatDateTime(ev.created_at)}
                </Typography>
                <Chip
                  size="small"
                  label={manualEventLabel(ev.event_type)}
                  color={manualEventColor(ev.event_type)}
                  variant="outlined"
                />
              </Box>
              <Typography
                variant="caption"
                color="text.secondary"
                display="block"
                sx={{ mt: 0.5 }}
              >
                By {formatActor(ev)}
                {ev.episode_id ? ` - episode ${ev.episode_id.slice(0, 8)}...` : ""}
              </Typography>
              {ev.notes && (
                <Typography
                  variant="body2"
                  sx={{ mt: 0.75, whiteSpace: "pre-wrap" }}
                >
                  {ev.notes}
                </Typography>
              )}
            </Box>
          ))}
      </Box>

      <Divider />

      <Typography variant="subtitle2" color="text.secondary">
        Human review
      </Typography>

      {!episode && (
        <Alert severity="info">
          No episode is available yet. Reset removed old pathways and rebuild is still in progress.
          Pipeline run events are shown above when available.
        </Alert>
      )}

      {episode && !hasHumanAudit && (
        <Alert severity="info">
          This episode has not been reviewed yet. Use the Overview tab to mark it as reviewed or
          add notes.
        </Alert>
      )}

      {episode && hasHumanAudit && (
        <>
          {hasReview && (
            <Box sx={{ display: "flex", flexDirection: "column", gap: 0.5 }}>
              <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}>
                <CheckCircleOutline color="success" fontSize="small" />
                <Typography variant="body2" sx={{ fontWeight: 500 }}>
                  Marked as reviewed
                </Typography>
              </Box>
              <Typography variant="caption" color="text.secondary">
                {formatDateTime(episode.reviewed_at)} by {episode.reviewed_by}
              </Typography>
            </Box>
          )}

          {episode.audit_flag && (
            <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}>
              <FlagOutlined color="warning" fontSize="small" />
              <Typography variant="body2">Flagged for follow-up</Typography>
            </Box>
          )}

          {episode.audit_notes && (
            <Box>
              <Typography variant="caption" color="text.secondary">
                Audit notes
              </Typography>
              <Box
                sx={{
                  mt: 0.5,
                  p: 1.5,
                  bgcolor: "grey.50",
                  borderRadius: 1,
                  border: "1px solid",
                  borderColor: "divider",
                  fontSize: "0.85rem",
                  whiteSpace: "pre-wrap",
                }}
              >
                {episode.audit_notes}
              </Box>
            </Box>
          )}

          <Box>
            <Typography variant="caption" color="text.secondary">
              Current pathway status
            </Typography>
            <Box sx={{ mt: 0.5 }}>
              <Chip label={getStatusLabel(episode.status)} size="small" variant="outlined" />
            </Box>
          </Box>
        </>
      )}
    </Box>
  );
}
