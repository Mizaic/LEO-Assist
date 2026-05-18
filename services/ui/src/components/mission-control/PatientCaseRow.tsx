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

import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Collapse from "@mui/material/Collapse";
import IconButton from "@mui/material/IconButton";
import TableCell from "@mui/material/TableCell";
import TableRow from "@mui/material/TableRow";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import KeyboardArrowDown from "@mui/icons-material/KeyboardArrowDown";
import KeyboardArrowUp from "@mui/icons-material/KeyboardArrowUp";
import OpenInNew from "@mui/icons-material/OpenInNew";
import EpisodeTimeline from "./EpisodeTimeline";
import StatusBadge from "./StatusBadge";
import {
  getCancerTypeLabel,
  getDiagnosticIntervalColour,
  getStatusLabel,
} from "@/lib/pathwayLabels";
import { CLOSURE_REASON_STATUSES, STATUS_CLOSED_BENIGN } from "@/lib/episodeStatus";
import type { MissionEpisode, MissionPatient } from "@/lib/missionControlApi";
import { useDemoMode } from "@/context/DemoModeContext";
import { maskAge, maskPatientId } from "@/lib/demoMode";

function formatDate(iso: string | null): string {
  if (!iso) return "--";
  try {
    return new Date(iso).toLocaleDateString("en-GB", {
      day: "2-digit",
      month: "short",
      year: "2-digit",
    });
  } catch {
    return iso.slice(0, 10);
  }
}

function formatEta(seconds: number | null | undefined): string {
  if (seconds == null || seconds <= 0) return "--";
  const minutes = Math.round(seconds / 60);
  if (minutes < 1) return "<1 min";
  if (minutes < 60) return `~${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const rem = minutes % 60;
  return rem === 0 ? `~${hours}h` : `~${hours}h ${rem}m`;
}

type DisplayInterval = {
  days: number;
  label: "Time to diagnosis" | "Time to cancer excluded";
};

const DAY_MS = 24 * 60 * 60 * 1000;
const CLOSURE_REASON_STATUS_SET = new Set<string>(CLOSURE_REASON_STATUSES);
const REFERRAL_ANCHOR_MILESTONES = new Set([
  "referral",
  "referral_sent",
  "first_presentation",
]);
const DIAGNOSIS_MILESTONES = new Set(["diagnosis", "diagnosis_confirmed"]);
const BENIGN_CLOSURE_MILESTONES = new Set(["benign_closure"]);

function earliestMilestoneDate(
  episode: MissionEpisode,
  milestoneTypes: ReadonlySet<string>
): string | null {
  const dates = (episode.milestones ?? [])
    .filter((milestone) => milestoneTypes.has(milestone.milestone_type))
    .map((milestone) => milestone.date)
    .filter(Boolean)
    .sort();
  return dates[0] ?? null;
}

function daysBetween(startIso: string | null, endIso: string | null): number | null {
  if (!startIso || !endIso) return null;
  const start = Date.parse(`${startIso.slice(0, 10)}T00:00:00Z`);
  const end = Date.parse(`${endIso.slice(0, 10)}T00:00:00Z`);
  if (Number.isNaN(start) || Number.isNaN(end)) return null;
  return Math.round((end - start) / DAY_MS);
}

export function getEpisodeReferralDate(episode: MissionEpisode): string | null {
  return episode.referral_date ?? earliestMilestoneDate(episode, REFERRAL_ANCHOR_MILESTONES);
}

function derivedDisplayInterval(episode: MissionEpisode): DisplayInterval | null {
  const referralDate = getEpisodeReferralDate(episode);
  const diagnosisDays = daysBetween(
    referralDate,
    earliestMilestoneDate(episode, DIAGNOSIS_MILESTONES)
  );
  const benignDays = daysBetween(
    referralDate,
    earliestMilestoneDate(episode, BENIGN_CLOSURE_MILESTONES)
  );
  if (episode.status === STATUS_CLOSED_BENIGN && benignDays != null) {
    return { days: benignDays, label: "Time to cancer excluded" };
  }
  if (diagnosisDays != null) {
    return { days: diagnosisDays, label: "Time to diagnosis" };
  }
  if (benignDays != null) {
    return { days: benignDays, label: "Time to cancer excluded" };
  }
  // Match EpisodeTimeline.resolveMilestones: when explicit benign_closure
  // milestones are missing, closure-reason statuses still use end_date on the rail.
  if (diagnosisDays == null && CLOSURE_REASON_STATUS_SET.has(episode.status)) {
    const fromEnd = daysBetween(referralDate, episode.end_date);
    if (fromEnd != null) {
      return { days: fromEnd, label: "Time to cancer excluded" };
    }
  }
  return null;
}

export function getEpisodeDisplayInterval(episode: MissionEpisode): DisplayInterval | null {
  if (episode.status === STATUS_CLOSED_BENIGN && episode.benign_interval_days != null) {
    return { days: episode.benign_interval_days, label: "Time to cancer excluded" };
  }
  if (episode.diagnostic_interval_days != null) {
    return { days: episode.diagnostic_interval_days, label: "Time to diagnosis" };
  }
  if (episode.benign_interval_days != null) {
    return { days: episode.benign_interval_days, label: "Time to cancer excluded" };
  }
  return derivedDisplayInterval(episode);
}

export function summarizeEpisodeReviews(episodes: MissionPatient["episodes"]): string {
  const reviewedCount = episodes.filter((episode) => Boolean(episode.reviewed_by)).length;
  if (reviewedCount === 0) return "Needs review";
  if (reviewedCount === episodes.length) return "Reviewed";
  return `${reviewedCount}/${episodes.length} reviewed`;
}

export function getDisplayEpisodes(patient: MissionPatient): MissionPatient["episodes"] {
  const unique = patient.episodes.filter((episode, index, allEpisodes) => {
    return allEpisodes.findIndex((item) => item.episode_id === episode.episode_id) === index;
  });
  return [...unique].sort((a, b) => {
    const aDate = getEpisodeReferralDate(a) ?? a.end_date ?? "";
    const bDate = getEpisodeReferralDate(b) ?? b.end_date ?? "";
    return aDate.localeCompare(bDate) || a.episode_id.localeCompare(b.episode_id);
  });
}

function EpisodeStack({
  episodes,
  children,
}: {
  episodes: MissionPatient["episodes"];
  children: (episode: MissionPatient["episodes"][number]) => ReactNode;
}) {
  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 0.5 }}>
      {episodes.map((episode) => (
        <Box
          key={episode.episode_id}
          sx={{ minHeight: 22, display: "flex", alignItems: "center" }}
        >
          {children(episode)}
        </Box>
      ))}
    </Box>
  );
}

interface Props {
  patient: MissionPatient;
  onOpen: (patient: MissionPatient) => void;
}

export default function PatientCaseRow({ patient, onOpen }: Props) {
  const { isDemoMode } = useDemoMode();
  const [expanded, setExpanded] = useState(false);
  const displayEpisodes = getDisplayEpisodes(patient);
  const hasEpisodes = displayEpisodes.length > 0;
  useEffect(() => {
    if (!hasEpisodes) {
      setExpanded(false);
    }
  }, [hasEpisodes]);

  const reviewLabel = hasEpisodes ? summarizeEpisodeReviews(displayEpisodes) : null;
  const reviewed = hasEpisodes && displayEpisodes.every((episode) => Boolean(episode.reviewed_by));
  const multiEpisode = displayEpisodes.length > 1;
  const rebuild = patient.rebuild_status ?? null;
  const rebuildLabel =
    rebuild?.status === "queued"
      ? `Queued${rebuild.queue_position_estimate != null ? ` (#~${rebuild.queue_position_estimate})` : ""}`
      : rebuild?.status === "running"
      ? "Running"
      : rebuild?.status === "completed"
      ? "Rebuild complete"
      : rebuild?.status === "failed"
      ? "Rebuild failed"
      : "Awaiting rebuild";

  return (
    <>
      <TableRow
        hover
        sx={{ "& > *": { borderBottom: expanded ? "unset" : undefined }, cursor: "pointer" }}
        onClick={() => onOpen(patient)}
      >
        {/* Expand toggle */}
        <TableCell padding="checkbox" onClick={(e) => e.stopPropagation()}>
          <IconButton
            size="small"
            aria-label={
              hasEpisodes
                ? expanded
                  ? "Collapse timeline"
                  : "Expand timeline"
                : "No episodes to expand"
            }
            onClick={() => hasEpisodes && setExpanded((v) => !v)}
            disabled={!hasEpisodes}
          >
            {expanded ? <KeyboardArrowUp /> : <KeyboardArrowDown />}
          </IconButton>
        </TableCell>

        {/* Status dot */}
        <TableCell>
          {hasEpisodes ? (
            <EpisodeStack episodes={displayEpisodes}>
              {(episode) => <StatusBadge status={episode.status} />}
            </EpisodeStack>
          ) : (
            <Chip
              label="No episodes yet"
              size="small"
              color="warning"
              variant="outlined"
              sx={{ fontSize: "0.65rem" }}
            />
          )}
        </TableCell>

        {/* Patient */}
        <TableCell>
          <Typography variant="body2" sx={{ fontFamily: "monospace", fontSize: "0.75rem" }}>
            {isDemoMode ? maskPatientId(patient.patient_id) : patient.patient_id}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {isDemoMode ? maskAge(patient.age) : patient.age ?? "--"} &middot; {patient.gender ?? "--"}
          </Typography>
          {multiEpisode && (
            <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
              {displayEpisodes.length} pathways
            </Typography>
          )}
        </TableCell>

        {/* Cancer type -- show all episodes when there are multiple pathways */}
        <TableCell>
          {hasEpisodes ? (
            <EpisodeStack episodes={displayEpisodes}>
              {(episode) =>
                episode.cancer_type ? (
                  <Typography variant="body2">
                    {getCancerTypeLabel(episode.cancer_type)}
                  </Typography>
                ) : (
                  <Typography variant="body2" color="text.secondary">
                    {getStatusLabel(episode.status)}
                  </Typography>
                )
              }
            </EpisodeStack>
          ) : (
            <Typography variant="body2" color="text.secondary">
              {rebuildLabel}
            </Typography>
          )}
        </TableCell>

        {/* Stage */}
        <TableCell>
          {hasEpisodes ? (
            <EpisodeStack episodes={displayEpisodes}>
              {(episode) =>
                episode.cancer_stage ? (
                  <Chip label={episode.cancer_stage} size="small" variant="outlined" />
                ) : (
                  <Typography variant="body2" color="text.disabled">
                    --
                  </Typography>
                )
              }
            </EpisodeStack>
          ) : (
            <Typography variant="body2" color="text.disabled">
              --
            </Typography>
          )}
        </TableCell>

        {/* Key dates */}
        <TableCell>
          {hasEpisodes ? (
            <EpisodeStack episodes={displayEpisodes}>
              {(episode) => (
                <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: "nowrap" }}>
                  {formatDate(getEpisodeReferralDate(episode))}
                  {episode.end_date && ` -> ${formatDate(episode.end_date)}`}
                </Typography>
              )}
            </EpisodeStack>
          ) : (
            <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: "nowrap" }}>
              ETA {formatEta(rebuild?.eta_seconds_estimate)}
            </Typography>
          )}
        </TableCell>

        {/* Time to diagnosis / cancer excluded */}
        <TableCell>
          {hasEpisodes ? (
            <EpisodeStack episodes={displayEpisodes}>
              {(episode) => {
                const interval = getEpisodeDisplayInterval(episode);
                if (!interval) {
                  return (
                    <Typography variant="body2" color="text.disabled">
                      --
                    </Typography>
                  );
                }
                const intervalColour = getDiagnosticIntervalColour(interval.days);
                return (
                  <Tooltip
                    title={`Days from referral to ${
                      interval.label === "Time to diagnosis" ? "diagnosis" : "cancer excluded"
                    }`}
                    arrow
                  >
                    <Typography
                      variant="body2"
                      aria-label={`${interval.label}: ${interval.days} days`}
                      sx={{
                        color:
                          intervalColour === "success"
                            ? "success.main"
                            : intervalColour === "warning"
                            ? "warning.main"
                            : "error.main",
                        fontWeight: 600,
                      }}
                    >
                      {interval.days}d
                    </Typography>
                  </Tooltip>
                );
              }}
            </EpisodeStack>
          ) : (
            <Typography variant="body2" color="text.disabled">
              --
            </Typography>
          )}
        </TableCell>

        {/* Review */}
        <TableCell>
          <Chip
            label={reviewLabel ?? rebuildLabel}
            size="small"
            color={
              hasEpisodes
                ? (reviewed ? "success" : "warning")
                : rebuild?.status === "failed"
                ? "error"
                : rebuild?.status === "running"
                ? "success"
                : rebuild?.status === "queued"
                ? "warning"
                : "default"
            }
            variant={hasEpisodes ? (reviewed ? "filled" : "outlined") : "outlined"}
            sx={{ fontSize: "0.65rem" }}
          />
        </TableCell>

        {/* Open drawer */}
        <TableCell padding="checkbox" onClick={(e) => e.stopPropagation()}>
          <IconButton
            size="small"
            aria-label="Open patient details"
            onClick={() => onOpen(patient)}
          >
            <OpenInNew fontSize="small" />
          </IconButton>
        </TableCell>
      </TableRow>

      {/* Expanded timeline row */}
      <TableRow>
        <TableCell colSpan={9} sx={{ py: 0, px: 2 }}>
          <Collapse in={expanded} timeout="auto" unmountOnExit>
            <Box sx={{ py: 1.5 }}>
              {displayEpisodes.map((episode) => (
                <Box key={episode.episode_id} sx={{ mb: 1 }}>
                  <EpisodeTimeline episode={episode} />
                </Box>
              ))}
            </Box>
          </Collapse>
        </TableCell>
      </TableRow>
    </>
  );
}
