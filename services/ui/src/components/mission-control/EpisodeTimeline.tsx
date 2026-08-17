/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-EE78E305
 *   DI: DI-6EA84931
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-EE78E305")
 */
"use client";

import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Tooltip from "@mui/material/Tooltip";
import LockOutlined from "@mui/icons-material/LockOutlined";
import type {
  MissionEpisode,
  VerificationLockSummary,
} from "@/lib/missionControlApi";
import { CLOSURE_REASON_STATUSES } from "@/lib/episodeStatus";

// -- Milestone configuration --
//
// The rail uses the canonical post-2026-04 vocabulary that the
// engine and the curator dialog both write. We keep a small alias
// table so any pre-2026 episodes whose milestones still carry the
// legacy keys ("gp_referral", "specialist_visit",
// "specialist_outcome_letter", "cancer_diagnosis") still light up
// the matching node on the rail. Without the aliases a manually
// curated episode would show an empty rail because the legacy keys
// the rail hard-coded against don't match what the curator just
// wrote (e.g. "referral", "first_seen", "diagnosis_confirmed").
//
// "First presentation" is intentionally NOT on the rail: it lives
// in the Encounter Text "Jump to milestone encounter" chips and
// is roll-upped into the Primary care interval pill on the
// pathway header. The rail is the dated 5-step funnel a clinician
// sees at a glance.

// Slot order on the rail. The rail labels are the clinician-facing
// short names; the slot keys are the canonical post-2026-04
// vocabulary used by the engine and the curator dialog. Note the
// "First seen" label maps to first_presentation (the GP visit),
// while "Specialist" maps to first_seen (the specialist visit) --
// the rail labels are deliberately about WHO saw the patient at
// each step, not about which slot key it is.
const MILESTONE_ORDER = [
  "first_presentation",
  "referral",
  "first_seen",
  "outcome_letter",
  "diagnosis_confirmed",
  "benign_closure",
] as const;

const MILESTONE_LABELS: Record<string, string> = {
  first_presentation: "First seen",
  referral: "Referred",
  first_seen: "Specialist",
  outcome_letter: "Outcome letter",
  diagnosis_confirmed: "Diagnosed",
  benign_closure: "Closed",
};

// Legacy slot keys that may still exist on pre-canonical episodes.
// Each maps to the canonical key the rail looks up against. Order
// inside each list matters: the first present wins (so a real
// "diagnosis_confirmed" beats a legacy "cancer_diagnosis" if both
// exist on the same episode).
const LEGACY_ALIASES: Record<string, string[]> = {
  referral: ["gp_referral", "referral_sent"],
  first_seen: ["specialist_visit", "first_clinic", "first_clinic_visit"],
  outcome_letter: ["specialist_outcome_letter"],
  diagnosis_confirmed: ["cancer_diagnosis", "diagnosis"],
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
  /** Optional VerificationLocks for the episode. Each lock with
   * entity_type=is_part_of_edge encodes "encounter:episode"; we surface
   * a tiny lock glyph next to the matching milestone node so the
   * reviewer sees at a glance which milestones are confirmed. */
  locks?: VerificationLockSummary[];
}

interface ResolvedMilestone {
  type: string;
  label: string;
  date: string | null;
  present: boolean;
  isClosure: boolean;
  /** Encounter id linked to this milestone, used for lock matching. */
  encounterId: string | null;
}

function resolveMilestones(episode: MissionEpisode): ResolvedMilestone[] {
  const dateMap: Record<string, string> = {};
  const encMap: Record<string, string> = {};
  for (const m of episode.milestones ?? []) {
    // Prefer the earliest date when a slot has multiple edges (the
    // engine occasionally emits two same-slot rows for the same
    // pathway -- the earliest is the one a clinician would consider
    // "the date of that milestone").
    const existing = dateMap[m.milestone_type];
    if (!existing || m.date < existing) {
      dateMap[m.milestone_type] = m.date;
      if (m.encounter_id) encMap[m.milestone_type] = m.encounter_id;
    }
  }
  // Fallbacks when explicit milestone edges are missing in graph
  // (canonical keys -- the legacy ones are caught by LEGACY_ALIASES
  // below).
  if (!dateMap.referral && episode.referral_date) {
    dateMap.referral = episode.referral_date;
  }
  if (!dateMap.first_seen && episode.specialist_visit_date) {
    dateMap.first_seen = episode.specialist_visit_date;
  }
  if (episode.end_date) {
    if (CLOSURE_STATUSES.has(episode.status)) {
      if (!dateMap.benign_closure) dateMap.benign_closure = episode.end_date;
    } else if (!dateMap.diagnosis_confirmed) {
      dateMap.diagnosis_confirmed = episode.end_date;
    }
  }

  // Legacy alias resolution: if a canonical slot has no date, look
  // for any of its legacy aliases on the episode and copy the date
  // and encounter id across. This means pre-2026 episodes still
  // light up the rail without having to be re-built.
  for (const [canonical, aliases] of Object.entries(LEGACY_ALIASES)) {
    if (dateMap[canonical]) continue;
    for (const alias of aliases) {
      if (dateMap[alias]) {
        dateMap[canonical] = dateMap[alias];
        if (encMap[alias] && !encMap[canonical]) {
          encMap[canonical] = encMap[alias];
        }
        break;
      }
    }
  }

  // Pick the terminal node(s). The rule is "slot evidence wins": if
  // the curator has attached either a benign_closure or a
  // diagnosis_confirmed slot, that node ALWAYS shows on the rail
  // even when the episode status has not yet been recomputed (e.g.
  // status is still "in_review" because a pipeline rebuild hasn't
  // run). When neither slot has data we fall back to the
  // status-based default so the rail still shows the right "what
  // we're waiting for" placeholder.
  const hasClosureSlot = Boolean(dateMap.benign_closure);
  const hasDiagnosisSlot = Boolean(dateMap.diagnosis_confirmed);
  const isClosed = CLOSURE_STATUSES.has(episode.status);

  let order: string[];
  if (hasClosureSlot && hasDiagnosisSlot) {
    // Both attached: show both, with closure last (it's the
    // pathway-end node and the rail is read left-to-right).
    order = MILESTONE_ORDER.slice();
  } else if (hasClosureSlot) {
    order = MILESTONE_ORDER.filter((t) => t !== "diagnosis_confirmed");
  } else if (hasDiagnosisSlot) {
    order = MILESTONE_ORDER.filter((t) => t !== "benign_closure");
  } else if (isClosed) {
    order = MILESTONE_ORDER.filter((t) => t !== "diagnosis_confirmed");
  } else {
    order = MILESTONE_ORDER.filter((t) => t !== "benign_closure");
  }

  return order.map((type) => ({
    type,
    label: MILESTONE_LABELS[type] ?? type,
    date: dateMap[type] ?? null,
    present: Boolean(dateMap[type]),
    isClosure: type === "benign_closure",
    encounterId: encMap[type] ?? null,
  }));
}

function buildLockIndex(
  episodeId: string,
  locks: VerificationLockSummary[] | undefined
): Set<string> {
  const out = new Set<string>();
  for (const lock of locks ?? []) {
    if (lock.entity_type !== "is_part_of_edge") continue;
    const [enc, ep] = lock.entity_id.split(":");
    if (ep === episodeId && enc) out.add(enc);
  }
  return out;
}

interface IntervalBand {
  /** 1-based grid column where the band starts (CSS grid is 1-based). */
  startCol: number;
  /** 1-based grid column AFTER the last column the band covers
   * (CSS grid `start / end` is exclusive on the end). */
  endCol: number;
  days: number;
  colour: string;
  label: string;
  testId: string;
}

function computeIntervalBands(
  milestones: ResolvedMilestone[]
): IntervalBand[] {
  const idxOf = (type: string) => milestones.findIndex((m) => m.type === type);
  const firstPresIdx = idxOf("first_presentation");
  const referralIdx = idxOf("referral");
  // The terminal node is whichever closure / diagnosis node is on
  // the rail. When BOTH are present (rare re-classification case)
  // the closure wins because it's the actual pathway end.
  const benignIdx = idxOf("benign_closure");
  const diagIdx = idxOf("diagnosis_confirmed");
  const terminalIdx = benignIdx !== -1 ? benignIdx : diagIdx;

  const bands: IntervalBand[] = [];

  // Primary care interval: first_presentation -> referral.
  if (firstPresIdx !== -1 && referralIdx !== -1) {
    const start = milestones[firstPresIdx].date;
    const end = milestones[referralIdx].date;
    const days = daysBetween(start, end);
    if (days != null) {
      bands.push({
        startCol: firstPresIdx + 1,
        endCol: referralIdx + 2,
        days,
        colour: intervalColour(days),
        label: `Primary care: ${days}d`,
        testId: "interval-band-primary-care",
      });
    }
  }

  // Diagnostic interval: referral -> closure / diagnosis terminal.
  if (referralIdx !== -1 && terminalIdx !== -1 && terminalIdx > referralIdx) {
    const start = milestones[referralIdx].date;
    const end = milestones[terminalIdx].date;
    const days = daysBetween(start, end);
    if (days != null) {
      const terminalLabel = milestones[terminalIdx].label.toLowerCase();
      bands.push({
        startCol: referralIdx + 1,
        endCol: terminalIdx + 2,
        days,
        colour: intervalColour(days),
        label: `Referral to ${terminalLabel}: ${days}d`,
        testId: "interval-band-diagnostic",
      });
    }
  }

  return bands;
}

export default function EpisodeTimeline({
  episode,
  compact = false,
  locks,
}: Props) {
  const milestones = resolveMilestones(episode);
  const lockedEncounters = buildLockIndex(episode.episode_id, locks);
  const intervalBands = compact ? [] : computeIntervalBands(milestones);

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
                <Box sx={{ position: "relative", display: "inline-flex" }}>
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
                            : "#0d46d6"
                          : "transparent",
                        flexShrink: 0,
                      }}
                    />
                  </Tooltip>
                  {m.encounterId && lockedEncounters.has(m.encounterId) && (
                    <Tooltip title="Reviewer-confirmed milestone (locked)" arrow>
                      <LockOutlined
                        data-testid={`milestone-lock-${m.type}`}
                        sx={{
                          position: "absolute",
                          right: -8,
                          top: -8,
                          fontSize: compact ? 10 : 12,
                          color: "success.main",
                          backgroundColor: "background.paper",
                          borderRadius: "50%",
                        }}
                      />
                    </Tooltip>
                  )}
                </Box>
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

      {/* Pathway interval overlays. Two coloured bands sit below the
          rail: "Primary care" spans first_presentation -> referral
          and "Referral to diagnosed/closed" spans referral -> the
          terminal node. Each band uses the same green/orange/red
          threshold as the rail connector lines so the eye picks up
          the two key NHS targets (28-day primary care, 62-day FDS)
          in the same visual language. */}
      {intervalBands.length > 0 && (
        <Box
          data-testid="pathway-interval-overlays"
          sx={{
            mt: 1.5,
            px: 1,
            display: "grid",
            gridTemplateColumns: `repeat(${milestones.length}, 1fr)`,
            rowGap: 0.5,
          }}
        >
          {intervalBands.map((band, idx) => (
            <Tooltip
              key={band.testId}
              title={`${band.days} days`}
              arrow
            >
              <Box
                data-testid={band.testId}
                sx={{
                  gridColumn: `${band.startCol} / ${band.endCol}`,
                  gridRow: idx + 1,
                  height: 18,
                  borderRadius: 9,
                  backgroundColor: band.colour,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  px: 1,
                  minWidth: 0,
                }}
              >
                <Typography
                  variant="caption"
                  sx={{
                    fontSize: "0.6rem",
                    fontWeight: 600,
                    color: "#fff",
                    whiteSpace: "nowrap",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                  }}
                >
                  {band.label}
                </Typography>
              </Box>
            </Tooltip>
          ))}
        </Box>
      )}
    </Box>
  );
}
