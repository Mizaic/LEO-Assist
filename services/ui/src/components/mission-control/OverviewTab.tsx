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

import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import Typography from "@mui/material/Typography";
import ArrowForward from "@mui/icons-material/ArrowForward";
import EpisodeTimeline from "./EpisodeTimeline";
import ReviewActionsPanel from "./ReviewActionsPanel";
import StatusBadge from "./StatusBadge";
import { getStatusLabel, getCancerTypeLabel, getDiagnosticIntervalColour } from "@/lib/pathwayLabels";
import type { MissionEpisode, MissionPatient } from "@/lib/missionControlApi";
import {
  STATUS_COMPLETED,
  STATUS_CLOSED_BENIGN,
  STATUS_STALE_NO_DIAGNOSIS,
  STATUS_STALE_POST_SPECIALIST,
  STATUS_CLOSED_RELATED,
  STATUS_IN_PROGRESS,
} from "@/lib/episodeStatus";

interface Props {
  patient: MissionPatient;
  userEmail: string;
  onEpisodeUpdated: (episodeId: string, patch: Partial<MissionEpisode>) => void;
  onFocusEpisode: (episodeId: string) => void;
  /** Override the episode list (DI-5E47FA5D). When set, used instead of
   *  `patient.episodes` so the drawer can show every EpisodeOfCare for
   *  the patient regardless of the dashboard cohort filter. */
  episodes?: MissionEpisode[];
}

function IntervalChip({ days, label }: { days: number | null; label: string }) {
  if (days == null) return null;
  const colour = getDiagnosticIntervalColour(days);
  return (
    <Chip
      label={`${label}: ${days} days`}
      size="small"
      color={colour}
      variant="outlined"
      sx={{ fontSize: "0.7rem" }}
    />
  );
}

function formatShortDate(iso: string | null | undefined): string {
  if (!iso) return "--";
  try {
    return new Date(iso).toLocaleDateString("en-GB", {
      day: "2-digit",
      month: "short",
      year: "2-digit",
    });
  } catch {
    return String(iso).slice(0, 10);
  }
}

function referredForText(episode: MissionEpisode): string {
  if (episode.cancer_type) {
    return `Suspected ${getCancerTypeLabel(episode.cancer_type).toLowerCase()}.`;
  }
  return "Possible cancer symptoms.";
}

function outcomeText(episode: MissionEpisode): string {
  switch (episode.status) {
    case STATUS_COMPLETED: {
      const type = episode.cancer_type
        ? ` in ${getCancerTypeLabel(episode.cancer_type).toLowerCase()}`
        : "";
      const stage = episode.cancer_stage ? ` (stage ${episode.cancer_stage})` : "";
      return `Cancer confirmed${type}${stage}.`;
    }
    case STATUS_CLOSED_BENIGN:
      return "No cancer found.";
    case STATUS_STALE_NO_DIAGNOSIS:
      return "No diagnosis recorded yet.";
    case STATUS_STALE_POST_SPECIALIST:
      return "Specialist seen, but no diagnosis recorded.";
    case STATUS_CLOSED_RELATED:
      return "This was closed as a duplicate pathway.";
    case STATUS_IN_PROGRESS:
      return "Still being investigated.";
    default:
      return `${getStatusLabel(episode.status)}.`;
  }
}

// "Slot evidence wins" -- the curator may have attached a
// benign_closure or diagnosis_confirmed milestone before the
// pipeline has had a chance to recompute episode.status /
// episode.end_date. The rail already prefers the slot date over
// the stored status; the Outcome / Outcome date pair in the
// header MUST follow the same rule, otherwise the header reads
// "active. Outcome date: --" while the rail right below it shows
// "Diagnosed 18 Sep 25" (the bug from the screenshot).
//
// Returns null when no terminal slot is attached so the caller
// falls back to the status-driven text and end_date.
function findMilestoneDate(
  episode: MissionEpisode,
  types: readonly string[]
): string | null {
  for (const m of episode.milestones ?? []) {
    if (types.includes(m.milestone_type)) return m.date;
  }
  return null;
}

interface SlotOutcome {
  text: string;
  date: string | null;
}

export function slotDerivedOutcome(
  episode: MissionEpisode
): SlotOutcome | null {
  // Closure beats diagnosis (same rule as the rail terminal node):
  // if a benign_closure slot was attached after a diagnosis the
  // pathway end is the closure event.
  const closureDate = findMilestoneDate(episode, ["benign_closure"]);
  if (closureDate) {
    return { text: "No cancer found.", date: closureDate };
  }
  // Accept the legacy "cancer_diagnosis" key as well so pre-2026
  // episodes resolve, matching EpisodeTimeline LEGACY_ALIASES.
  const diagDate = findMilestoneDate(episode, [
    "diagnosis_confirmed",
    "cancer_diagnosis",
  ]);
  if (diagDate) {
    const type = episode.cancer_type
      ? ` in ${getCancerTypeLabel(episode.cancer_type).toLowerCase()}`
      : "";
    const stage = episode.cancer_stage
      ? ` (stage ${episode.cancer_stage})`
      : "";
    return { text: `Cancer confirmed${type}${stage}.`, date: diagDate };
  }
  return null;
}

export default function OverviewTab({
  patient,
  userEmail,
  onEpisodeUpdated,
  onFocusEpisode,
  episodes,
}: Props) {
  const episodeList = episodes ?? patient.episodes;
  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 3 }}>
      {/* Demographics */}
      <Box>
        <Typography variant="subtitle2" color="text.secondary" gutterBottom>
          Patient
        </Typography>
        <Box sx={{ display: "flex", gap: 2, flexWrap: "wrap" }}>
          <Box>
            <Typography variant="caption" color="text.secondary">
              ID
            </Typography>
            <Typography variant="body2" sx={{ fontFamily: "monospace" }}>
              {patient.patient_id}
            </Typography>
          </Box>
          <Box>
            <Typography variant="caption" color="text.secondary">
              Age
            </Typography>
            <Typography variant="body2">{patient.age ?? "--"}</Typography>
          </Box>
          <Box>
            <Typography variant="caption" color="text.secondary">
              Gender
            </Typography>
            <Typography variant="body2" sx={{ textTransform: "capitalize" }}>
              {patient.gender ?? "--"}
            </Typography>
          </Box>
          <Box>
            <Typography variant="caption" color="text.secondary">
              Practice
            </Typography>
            <Typography variant="body2">{patient.practice_name ?? "--"}</Typography>
          </Box>
        </Box>
      </Box>

      <Divider />

      {/* Episodes */}
      {episodeList.map((episode) => (
        <Box key={episode.episode_id}>
          {/* Episode header */}
          <Box sx={{ display: "flex", gap: 1, alignItems: "center", mb: 1, flexWrap: "wrap" }}>
            <StatusBadge status={episode.status} />
            <Typography variant="subtitle2">
              {episode.cancer_type
                ? getCancerTypeLabel(episode.cancer_type)
                : getStatusLabel(episode.status)}
            </Typography>
            {episode.cancer_stage && (
              <Chip label={`Stage ${episode.cancer_stage}`} size="small" variant="outlined" />
            )}
            <IntervalChip days={episode.diagnostic_interval_days} label="Time to diagnosis" />
            <IntervalChip
              days={episode.primary_care_interval_days}
              label="Primary care interval"
            />
            <Button
              size="small"
              variant="outlined"
              endIcon={<ArrowForward fontSize="small" />}
              sx={{ ml: "auto", textTransform: "none" }}
              onClick={() => onFocusEpisode(episode.episode_id)}
            >
              Review this episode
            </Button>
          </Box>

          {/* Plain-English pathway summary for fast understanding */}
          <Box
            sx={{
              mb: 1.5,
              p: 1.25,
              bgcolor: "grey.50",
              border: "1px solid",
              borderColor: "divider",
              borderRadius: 1,
              display: "grid",
              gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" },
              gap: 1,
            }}
          >
            <Box>
              <Typography variant="caption" color="text.secondary">
                Referred for
              </Typography>
              <Typography variant="body2" sx={{ fontWeight: 600 }}>
                {referredForText(episode)}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                Referral date: {formatShortDate(episode.referral_date)}
              </Typography>
            </Box>
            <Box>
              <Typography variant="caption" color="text.secondary">
                Outcome
              </Typography>
              {(() => {
                const slotOutcome = slotDerivedOutcome(episode);
                const text = slotOutcome?.text ?? outcomeText(episode);
                const date = slotOutcome?.date ?? episode.end_date;
                return (
                  <>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>
                      {text}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      Outcome date: {formatShortDate(date)}
                    </Typography>
                  </>
                );
              })()}
            </Box>
          </Box>

          {/* Timeline */}
          <Box sx={{ mb: 2 }}>
            <EpisodeTimeline episode={episode} />
          </Box>

          <Divider sx={{ mb: 2 }} />

          {/* Review actions */}
          <ReviewActionsPanel
            episode={episode}
            userEmail={userEmail}
            onReviewed={(patch) => onEpisodeUpdated(episode.episode_id, patch)}
          />
        </Box>
      ))}
    </Box>
  );
}
