/**
 * Single episode swimlane card for the EPR Timeline tab.
 *
 * Atlas trace:
 *   DO: DO-5D3EA371
 *   DI: DI-357A7468
 */
"use client";

import { useEffect, useState } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import type {
  EpisodeSummaryEpr,
  TimelineItem,
  EpisodeMilestones,
} from "@/lib/patientEprApi";
import { fetchEpisodeMilestones } from "@/lib/patientEprApi";
import {
  accentFor,
  dateToTs,
  daysBetween,
  episodeTimeWindow,
  fmtDate,
  MILESTONE_LABEL,
  outcomeColor,
  outcomeLabel,
  routeLabel,
} from "./episodeLaneUtils";

export { episodeTimeWindow } from "./episodeLaneUtils";

interface Props {
  patientId: string;
  ep: EpisodeSummaryEpr;
  encounters: TimelineItem[];
  onEncounterClick?: (id: string) => void;
}

export function EpisodeLaneCard({
  patientId,
  ep,
  encounters,
  onEncounterClick,
}: Props) {
  const [milestones, setMilestones] = useState<EpisodeMilestones | null>(null);

  useEffect(() => {
    if (!ep.episode_id) return;
    fetchEpisodeMilestones(patientId, ep.episode_id)
      .then(setMilestones)
      .catch(() => {});
  }, [patientId, ep.episode_id]);

  const accent = accentFor(ep.condition_type);
  const { minTs, maxTs } = episodeTimeWindow(ep, encounters);
  const totalMs = maxTs - minTs || 1;

  function pct(ts: number): number {
    return Math.max(0, Math.min(100, ((ts - minTs) / totalMs) * 100));
  }

  const startTs = dateToTs(ep.referral_date) || minTs;
  const endTs = ep.end_date
    ? dateToTs(ep.end_date)
    : Math.min(maxTs, Math.max(Date.now(), startTs));
  const startPct = pct(startTs);
  const widthPct = Math.max(8, pct(endTs) - startPct);

  type NamedDot = { type: string; label: string; date: string; pct: number };
  const namedDots: NamedDot[] = [];
  if (milestones) {
    for (const step of milestones.steps ?? []) {
      if (!step.dates.length) continue;
      const d = step.dates[0];
      const ts = dateToTs(d);
      if (!ts) continue;
      namedDots.push({
        type: step.milestone_type,
        label: MILESTONE_LABEL[step.milestone_type] ?? step.milestone_type,
        date: d,
        pct: pct(ts),
      });
    }
  }

  const encounterDots = encounters
    .filter((e) => dateToTs(e.item_date) > 0)
    .map((e) => ({
      id: e.item_id,
      label: e.label || "Encounter",
      date: e.item_date,
      pct: pct(dateToTs(e.item_date)),
    }));

  const intervals: { label: string; midPct: number }[] = [];
  for (let i = 1; i < namedDots.length; i++) {
    const a = namedDots[i - 1];
    const b = namedDots[i];
    const d = daysBetween(a.date, b.date);
    if (d !== null && d > 0) {
      intervals.push({ label: `${d}d`, midPct: (a.pct + b.pct) / 2 });
    }
  }

  const stagingText = [ep.staging_value, ep.staging_early_late]
    .filter(Boolean)
    .join(" - ");
  const statusColor =
    (ep.status ?? "").toLowerCase() === "active" ? "#047857" : "#64748B";
  const subtitle = [
    routeLabel(ep.referral_route),
    ep.place_of_presentation,
    ep.referral_date ? `Referred ${fmtDate(ep.referral_date)}` : "",
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <Box
      data-testid="epr-episode-lane"
      sx={{
        position: "relative",
        border: "1px solid #E2E8F0",
        borderRadius: "12px",
        p: "16px 20px 14px 24px",
        mb: 2,
        bgcolor: "#FAFAFA",
        overflow: "hidden",
      }}
    >
      <Box
        aria-hidden="true"
        sx={{
          position: "absolute",
          left: 0,
          top: 12,
          bottom: 12,
          width: 3,
          borderRadius: 2,
          bgcolor: accent,
        }}
      />

      <Stack
        direction="row"
        spacing={1}
        alignItems="center"
        flexWrap="wrap"
        sx={{ mb: 0.5 }}
      >
        <Typography
          variant="body2"
          fontWeight={700}
          color={accent}
          sx={{ textTransform: "capitalize" }}
        >
          {ep.condition_type ?? "Episode"}
        </Typography>
        <Chip
          label={ep.status ?? "unknown"}
          size="small"
          sx={{
            height: 18,
            fontSize: 10,
            bgcolor: `${statusColor}18`,
            color: statusColor,
            textTransform: "capitalize",
          }}
        />
        {ep.inferred_outcome && (
          <Chip
            label={outcomeLabel(ep.inferred_outcome)}
            size="small"
            sx={{
              height: 18,
              fontSize: 10,
              bgcolor: `${outcomeColor(ep.inferred_outcome)}15`,
              color: outcomeColor(ep.inferred_outcome),
            }}
          />
        )}
        {stagingText && (
          <Chip
            label={`Stage ${stagingText}`}
            size="small"
            sx={{ height: 18, fontSize: 10, bgcolor: "#F1F5F9", color: "#334155" }}
          />
        )}
      </Stack>

      {subtitle && (
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ mb: 1.5, display: "block" }}
        >
          {subtitle}
        </Typography>
      )}

      {namedDots.length > 0 && (
        <Box sx={{ position: "relative", height: 22, width: "100%" }}>
          {namedDots.map((dot) => (
            <Box
              key={dot.type}
              sx={{
                position: "absolute",
                left: `calc(${dot.pct}% - 50px)`,
                width: 100,
                textAlign: "center",
              }}
            >
              <Typography
                variant="caption"
                fontWeight={700}
                fontSize={10}
                color={accent}
                noWrap
              >
                {dot.label}
              </Typography>
            </Box>
          ))}
        </Box>
      )}

      <LaneTrack
        accent={accent}
        startPct={startPct}
        widthPct={widthPct}
        encounterDots={encounterDots}
        namedDots={namedDots}
        intervals={intervals}
        onEncounterClick={onEncounterClick}
      />

      <Stack
        direction="row"
        justifyContent="space-between"
        sx={{ mt: 0.5, mb: 1 }}
      >
        <Typography variant="caption" color="text.secondary" fontSize={10}>
          {fmtDate(new Date(minTs).toISOString())}
        </Typography>
        <Typography variant="caption" color="text.secondary" fontSize={10}>
          {fmtDate(new Date(maxTs).toISOString())}
        </Typography>
      </Stack>

      <Stack direction="row" spacing={2} flexWrap="wrap">
        <Typography variant="caption" color="text.secondary">
          {encounterDots.length} encounter
          {encounterDots.length !== 1 ? "s" : ""} on this pathway
        </Typography>
        {ep.prior_consultations_n != null && (
          <Typography variant="caption" color="text.secondary">
            {ep.prior_consultations_n} prior consultation
            {ep.prior_consultations_n !== 1 ? "s" : ""}
          </Typography>
        )}
        {ep.safety_netting_recorded === true && (
          <Typography variant="caption" color="#047857">
            Safety net recorded
          </Typography>
        )}
        {ep.safety_netting_recorded === false && (
          <Typography variant="caption" color="#B45309">
            No safety net recorded
          </Typography>
        )}
      </Stack>
    </Box>
  );
}

interface Dot {
  id?: string;
  type?: string;
  label: string;
  date: string;
  pct: number;
}

function LaneTrack({
  accent,
  startPct,
  widthPct,
  encounterDots,
  namedDots,
  intervals,
  onEncounterClick,
}: {
  accent: string;
  startPct: number;
  widthPct: number;
  encounterDots: Dot[];
  namedDots: Dot[];
  intervals: { label: string; midPct: number }[];
  onEncounterClick?: (id: string) => void;
}) {
  return (
    <Box
      sx={{
        position: "relative",
        height: 36,
        width: "100%",
        bgcolor: "#F1F5F9",
        borderRadius: "16px",
      }}
    >
      <Box
        sx={{
          position: "absolute",
          left: `${startPct}%`,
          width: `${widthPct}%`,
          top: 10,
          bottom: 10,
          bgcolor: `${accent}28`,
          borderRadius: "6px",
          border: `1.5px solid ${accent}55`,
        }}
      />

      {encounterDots.map((dot) => (
        <Tooltip
          key={dot.id}
          title={`${dot.label} - ${fmtDate(dot.date)}`}
          arrow
        >
          <Box
            component="button"
            onClick={() => dot.id && onEncounterClick?.(dot.id)}
            aria-label={`${dot.label} on ${fmtDate(dot.date)}`}
            sx={{
              position: "absolute",
              left: `calc(${dot.pct}% - 5px)`,
              top: "50%",
              transform: "translateY(-50%)",
              width: 10,
              height: 10,
              borderRadius: "50%",
              bgcolor: "#94A3B8",
              border: "1.5px solid #fff",
              cursor: "pointer",
              p: 0,
              "&:hover": {
                bgcolor: accent,
                transform: "translateY(-50%) scale(1.4)",
              },
              transition: "all 0.15s",
            }}
          />
        </Tooltip>
      ))}

      {namedDots.map((dot) => (
        <Tooltip
          key={dot.type}
          title={`${dot.label} - ${fmtDate(dot.date)}`}
          arrow
        >
          <Box
            aria-label={`${dot.label} on ${fmtDate(dot.date)}`}
            sx={{
              position: "absolute",
              left: `calc(${dot.pct}% - 8px)`,
              top: "50%",
              width: 16,
              height: 16,
              borderRadius: "3px",
              bgcolor: accent,
              border: "2px solid #fff",
              boxShadow: "0 1px 4px rgba(0,0,0,0.18)",
              transform: "translateY(-50%) rotate(45deg)",
            }}
          />
        </Tooltip>
      ))}

      {intervals.map((iv, i) => (
        <Box
          key={i}
          sx={{
            position: "absolute",
            left: `calc(${iv.midPct}% - 18px)`,
            top: "50%",
            transform: "translateY(-50%)",
            pointerEvents: "none",
          }}
        >
          <Typography
            variant="caption"
            fontSize={9}
            fontWeight={600}
            sx={{
              bgcolor: "#fff",
              border: "1px solid #E2E8F0",
              borderRadius: "8px",
              px: "4px",
              color: "#64748B",
              lineHeight: 1.6,
              whiteSpace: "nowrap",
            }}
          >
            {iv.label}
          </Typography>
        </Box>
      ))}
    </Box>
  );
}
