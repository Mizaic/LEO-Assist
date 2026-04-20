"use client";

import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Tooltip from "@mui/material/Tooltip";
import type { MissionEpisode } from "@/lib/missionControlApi";
import { CLOSURE_REASON_STATUSES } from "@/lib/episodeStatus";

// -- Milestone configuration --

const MILESTONE_ORDER = [
  "first_presentation",
  "gp_referral",
  "specialist_visit",
  "specialist_outcome_letter",
  "cancer_diagnosis",
  "benign_closure",
] as const;

const MILESTONE_LABELS: Record<string, string> = {
  first_presentation: "First seen",
  gp_referral: "Referred",
  specialist_visit: "Specialist",
  specialist_outcome_letter: "Outcome letter",
  cancer_diagnosis: "Diagnosed",
  benign_closure: "Closed",
};

const CLOSURE_STATUSES: ReadonlySet<string> = new Set(CLOSURE_REASON_STATUSES);

// -- Interval colour thresholds --

function intervalColour(days: number | null): string {
  if (days == null) return "#bdbdbd";
  if (days <= 28) return "#4caf50";
  if (days <= 62) return "#ff9800";
  return "#f44336";
}

function daysBetween(a: string | null, b: string | null): number | null {
  if (!a || !b) return null;
  try {
    const diff = new Date(b).getTime() - new Date(a).getTime();
    return Math.round(diff / 86400000);
  } catch {
    return null;
  }
}

function shortDate(iso: string | null): string {
  if (!iso) return "";
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

// -- Component --

interface Props {
  episode: MissionEpisode;
  compact?: boolean;
}

interface ResolvedMilestone {
  type: string;
  label: string;
  date: string | null;
  present: boolean;
  isClosure: boolean;
}

function resolveMilestones(episode: MissionEpisode): ResolvedMilestone[] {
  const dateMap: Record<string, string> = {};
  for (const m of episode.milestones ?? []) {
    dateMap[m.milestone_type] = m.date;
  }
  // Fallbacks when explicit milestone edges are missing in graph.
  if (!dateMap.gp_referral && episode.referral_date) {
    dateMap.gp_referral = episode.referral_date;
  }
  if (!dateMap.specialist_visit && episode.specialist_visit_date) {
    dateMap.specialist_visit = episode.specialist_visit_date;
  }
  if (episode.end_date) {
    if (CLOSURE_STATUSES.has(episode.status)) {
      if (!dateMap.benign_closure) dateMap.benign_closure = episode.end_date;
    } else if (!dateMap.cancer_diagnosis) {
      dateMap.cancer_diagnosis = episode.end_date;
    }
  }

  const isClosed = CLOSURE_STATUSES.has(episode.status);
  const order = isClosed
    ? MILESTONE_ORDER.filter((t) => t !== "cancer_diagnosis")
    : MILESTONE_ORDER.filter((t) => t !== "benign_closure");

  return order.map((type) => ({
    type,
    label: MILESTONE_LABELS[type] ?? type,
    date: dateMap[type] ?? null,
    present: Boolean(dateMap[type]),
    isClosure: type === "benign_closure",
  }));
}

export default function EpisodeTimeline({ episode, compact = false }: Props) {
  const milestones = resolveMilestones(episode);

  return (
    <Box sx={{ overflowX: "auto", py: compact ? 0.5 : 1 }}>
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          minWidth: 400,
          px: compact ? 0 : 1,
        }}
      >
        {milestones.map((m, idx) => {
          const prevDate = idx > 0 ? milestones[idx - 1].date : null;
          const days = daysBetween(prevDate, m.date);
          const lineColour = intervalColour(days);

          return (
            <Box key={m.type} sx={{ display: "flex", alignItems: "center", flex: 1 }}>
              {/* Connector line (not before first node) */}
              {idx > 0 && (
                <Tooltip
                  title={days != null ? `${days} days` : "Interval unknown"}
                  arrow
                >
                  <Box sx={{ flex: 1, position: "relative", mx: 0.5 }}>
                    <Box
                      sx={{
                        height: 3,
                        backgroundColor: lineColour,
                        borderRadius: 1,
                      }}
                    />
                    {!compact && days != null && (
                      <Typography
                        variant="caption"
                        sx={{
                          position: "absolute",
                          top: -16,
                          left: "50%",
                          transform: "translateX(-50%)",
                          fontSize: "0.6rem",
                          color: lineColour,
                          whiteSpace: "nowrap",
                          fontWeight: 600,
                        }}
                      >
                        {days}d
                      </Typography>
                    )}
                  </Box>
                </Tooltip>
              )}

              {/* Milestone node */}
              <Box
                sx={{ display: "flex", flexDirection: "column", alignItems: "center" }}
              >
                <Tooltip
                  title={m.date ? shortDate(m.date) : "Not yet recorded"}
                  arrow
                >
                  <Box
                    sx={{
                      width: compact ? 10 : 14,
                      height: compact ? 10 : 14,
                      borderRadius: m.isClosure ? "3px" : "50%",
                      border: m.present ? "none" : "2px dashed #bdbdbd",
                      backgroundColor: m.present
                        ? m.isClosure
                          ? "#9e9e9e"
                          : "#1F3A8A"
                        : "transparent",
                      flexShrink: 0,
                    }}
                  />
                </Tooltip>
                {!compact && (
                  <>
                    <Typography
                      variant="caption"
                      sx={{
                        fontSize: "0.6rem",
                        mt: 0.5,
                        color: m.present ? "text.secondary" : "text.disabled",
                        textAlign: "center",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {m.label}
                    </Typography>
                    <Typography
                      variant="caption"
                      sx={{
                        fontSize: "0.55rem",
                        color: m.present ? "text.secondary" : "text.disabled",
                        textAlign: "center",
                      }}
                    >
                      {m.date ? shortDate(m.date) : "--"}
                    </Typography>
                  </>
                )}
              </Box>
            </Box>
          );
        })}
      </Box>
    </Box>
  );
}
