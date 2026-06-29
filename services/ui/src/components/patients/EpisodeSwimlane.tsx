/**
 * EpisodeSwimlane -- horizontal timeline per episode.
 *
 * Each episode card shows:
 *   - A filled band from referral to end/today
 *   - Named clinical milestone dots from the milestones API
 *   - Encounter events overlaid on the band (smaller dots)
 *   - Day-count intervals between milestones
 *
 * Atlas trace:
 *   DO: DO-5D3EA371
 *   DI: DI-357A7468
 */
"use client";

import { useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import type {
  EpisodeSummaryEpr,
  TimelineItem,
  EpisodeMilestones,
} from "@/lib/patientEprApi";
import { fetchEpisodeMilestones } from "@/lib/patientEprApi";

const CONDITION_ACCENT: Record<string, string> = {
  lung: "#1E40AF", breast: "#9D174D", prostate: "#6D28D9",
  colorectal: "#B45309", lower_gi: "#B45309", upper_gi: "#7C3AED",
  skin: "#047857", haematology: "#0369A1", gynaecology: "#BE185D",
  head_and_neck: "#1D4ED8", urology: "#4338CA",
};

const MILESTONE_LABEL: Record<string, string> = {
  referral: "GP Referral",
  specialist_visit: "First specialist",
  diagnosis: "Diagnosis",
  outcome: "Outcome",
};

function accentFor(t: string | null): string {
  const key = (t ?? "").toLowerCase().replace(/ /g, "_");
  return CONDITION_ACCENT[key] ?? "#475569";
}

function dateToTs(iso: string | null | undefined): number {
  if (!iso) return 0;
  try { return new Date(iso).getTime(); } catch { return 0; }
}

function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleDateString("en-GB", {
      day: "numeric", month: "short", year: "numeric",
    });
  } catch { return iso.slice(0, 10); }
}

function fmtShort(iso: string | null | undefined): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleDateString("en-GB", { month: "short", year: "2-digit" });
  } catch { return iso.slice(0, 7); }
}

function daysBetween(a: string | null | undefined, b: string | null | undefined): number | null {
  const ta = dateToTs(a);
  const tb = dateToTs(b);
  if (!ta || !tb) return null;
  return Math.round(Math.abs(tb - ta) / (1000 * 60 * 60 * 24));
}

function routeLabel(r: string | null): string {
  if (!r) return "";
  const v = r.toLowerCase();
  if (v.includes("two_week") || v.includes("2ww") || v === "urgent") return "2WW urgent";
  if (v === "routine") return "Routine";
  if (v.includes("emergency")) return "Emergency";
  return r;
}

function outcomeLabel(o: string | null): string {
  if (!o) return "";
  const v = o.toLowerCase();
  if (v === "cancer") return "Cancer confirmed";
  if (v === "benign") return "Benign";
  if (v.includes("watch")) return "Watchful waiting";
  return o;
}

function outcomeColor(o: string | null): string {
  const v = (o ?? "").toLowerCase();
  if (v === "cancer") return "#B91C1C";
  if (v === "benign") return "#047857";
  return "#475569";
}

// ---------------------------------------------------------------------------
// EpisodeCard (uses milestones API)
// ---------------------------------------------------------------------------

interface EpisodeCardProps {
  patientId: string;
  ep: EpisodeSummaryEpr;
  encounters: TimelineItem[];
  minTs: number;
  maxTs: number;
  onEncounterClick?: (id: string) => void;
}

function EpisodeCard({
  patientId, ep, encounters, minTs, maxTs, onEncounterClick,
}: EpisodeCardProps) {
  const [milestones, setMilestones] = useState<EpisodeMilestones | null>(null);

  useEffect(() => {
    if (!ep.episode_id) return;
    fetchEpisodeMilestones(patientId, ep.episode_id)
      .then(setMilestones)
      .catch(() => {});
  }, [patientId, ep.episode_id]);

  const accent = accentFor(ep.condition_type);
  const totalMs = maxTs - minTs || 1;

  function pct(ts: number): number {
    return Math.max(0, Math.min(100, ((ts - minTs) / totalMs) * 100));
  }

  const startTs = dateToTs(ep.referral_date);
  const endTs = ep.end_date
    ? dateToTs(ep.end_date)
    : Math.max(maxTs, startTs + 60 * 86400000);
  const startPct = pct(startTs);
  const widthPct = Math.max(4, pct(endTs) - startPct);

  // Named milestone dots from API
  type NamedDot = { type: string; label: string; date: string; pct: number };
  const namedDots: NamedDot[] = [];
  if (milestones) {
    for (const step of milestones.steps) {
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

  // Encounter overlay dots from timeline
  const encounterDots = encounters
    .filter((e) => dateToTs(e.item_date) > 0)
    .map((e) => ({
      id: e.item_id,
      label: e.label || "Encounter",
      date: e.item_date,
      pct: pct(dateToTs(e.item_date)),
    }));

  // Day-count intervals between consecutive named milestones
  const intervals: { label: string; days: number; midPct: number }[] = [];
  for (let i = 1; i < namedDots.length; i++) {
    const a = namedDots[i - 1];
    const b = namedDots[i];
    const d = daysBetween(a.date, b.date);
    if (d !== null && d > 0) {
      intervals.push({ label: `${d}d`, days: d, midPct: (a.pct + b.pct) / 2 });
    }
  }

  const stagingText = [ep.staging_value, ep.staging_early_late].filter(Boolean).join(" - ");
  const statusColor = (ep.status ?? "").toLowerCase() === "active" ? "#047857" : "#64748B";

  return (
    <Box
      sx={{
        position: "relative",
        border: "1px solid #E2E8F0",
        borderRadius: "12px",
        p: "16px 20px 14px 24px",
        mb: 3,
        bgcolor: "#FAFAFA",
        overflow: "hidden",
      }}
    >
      <Box
        aria-hidden="true"
        sx={{
          position: "absolute", left: 0, top: 12, bottom: 12,
          width: 3, borderRadius: 2, bgcolor: accent,
        }}
      />

      {/* Header */}
      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" sx={{ mb: 0.5 }}>
        <Typography variant="body2" fontWeight={700} color={accent} sx={{ textTransform: "capitalize" }}>
          {ep.condition_type ?? "Episode"}
        </Typography>
        <Chip
          label={ep.status ?? "unknown"}
          size="small"
          sx={{ height: 18, fontSize: 10, bgcolor: `${statusColor}18`, color: statusColor, textTransform: "capitalize" }}
        />
        {ep.inferred_outcome && (
          <Chip
            label={outcomeLabel(ep.inferred_outcome)}
            size="small"
            sx={{ height: 18, fontSize: 10, bgcolor: `${outcomeColor(ep.inferred_outcome)}15`, color: outcomeColor(ep.inferred_outcome) }}
          />
        )}
        {stagingText && (
          <Chip label={`Stage ${stagingText}`} size="small"
            sx={{ height: 18, fontSize: 10, bgcolor: "#F1F5F9", color: "#334155" }} />
        )}
      </Stack>

      <Typography variant="caption" color="text.secondary" sx={{ mb: 2, display: "block" }}>
        {[routeLabel(ep.referral_route), ep.place_of_presentation].filter(Boolean).join(" · ")}
        {ep.referral_date ? ` · Referred ${fmtShort(ep.referral_date)}` : ""}
      </Typography>

      {/* Milestone label row */}
      {namedDots.length > 0 && (
        <Box sx={{ position: "relative", height: 24, width: "100%", mb: 0 }}>
          {namedDots.map((dot) => (
            <Box
              key={dot.type}
              sx={{ position: "absolute", left: `calc(${dot.pct}% - 50px)`, width: 100, textAlign: "center" }}
            >
              <Typography variant="caption" fontWeight={700} fontSize={10} color={accent} noWrap>
                {dot.label}
              </Typography>
            </Box>
          ))}
        </Box>
      )}

      {/* Main track */}
      <Box
        sx={{
          position: "relative",
          height: 32,
          width: "100%",
          bgcolor: "#F1F5F9",
          borderRadius: "16px",
          mb: 0,
        }}
      >
        {/* Filled episode band */}
        <Box
          sx={{
            position: "absolute",
            left: `${startPct}%`,
            width: `${widthPct}%`,
            top: 10, bottom: 10,
            bgcolor: `${accent}28`,
            borderRadius: "6px",
            border: `1.5px solid ${accent}55`,
          }}
        />

        {/* Encounter overlay dots (small, grey) */}
        {encounterDots.map((dot) => (
          <Tooltip key={dot.id} title={`${dot.label} - ${fmtDate(dot.date)}`} arrow>
            <Box
              component="button"
              onClick={() => onEncounterClick?.(dot.id)}
              aria-label={`${dot.label} on ${fmtDate(dot.date)}`}
              sx={{
                position: "absolute",
                left: `calc(${dot.pct}% - 5px)`,
                top: "50%", transform: "translateY(-50%)",
                width: 10, height: 10, borderRadius: "50%",
                bgcolor: "#94A3B8", border: "1.5px solid #fff",
                cursor: "pointer", p: 0,
                "&:hover": { bgcolor: accent, transform: "translateY(-50%) scale(1.4)" },
                transition: "all 0.15s",
              }}
            />
          </Tooltip>
        ))}

        {/* Named milestone dots (larger, coloured) */}
        {namedDots.map((dot) => (
          <Tooltip key={dot.type} title={`${dot.label} - ${fmtDate(dot.date)}`} arrow>
            <Box
              aria-label={`${dot.label} on ${fmtDate(dot.date)}`}
              sx={{
                position: "absolute",
                left: `calc(${dot.pct}% - 8px)`,
                top: "50%", transform: "translateY(-50%)",
                width: 16, height: 16,
                borderRadius: "3px",
                bgcolor: accent,
                border: "2px solid #fff",
                boxShadow: "0 1px 4px rgba(0,0,0,0.18)",
                transform: "translateY(-50%) rotate(45deg)",
                left: `calc(${dot.pct}% - 8px)`,
              }}
            />
          </Tooltip>
        ))}

        {/* Day-count interval labels */}
        {intervals.map((iv, i) => (
          <Box
            key={i}
            sx={{
              position: "absolute",
              left: `calc(${iv.midPct}% - 18px)`,
              top: "50%", transform: "translateY(-50%)",
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

      {/* Date labels row */}
      {namedDots.length > 0 && (
        <Box sx={{ position: "relative", height: 18, width: "100%", mt: 0.25, mb: 1.5 }}>
          {namedDots.map((dot) => (
            <Box
              key={dot.type}
              sx={{ position: "absolute", left: `calc(${dot.pct}% - 40px)`, width: 80, textAlign: "center" }}
            >
              <Typography variant="caption" fontSize={10} color="text.secondary" noWrap>
                {fmtDate(dot.date)}
              </Typography>
            </Box>
          ))}
        </Box>
      )}

      {/* Footer */}
      <Stack direction="row" spacing={2} flexWrap="wrap" sx={{ mt: namedDots.length > 0 ? 0 : 1.5 }}>
        {encounterDots.length > 0 && (
          <Typography variant="caption" color="text.secondary">
            {encounterDots.length} encounter{encounterDots.length !== 1 ? "s" : ""}
          </Typography>
        )}
        {ep.prior_consultations_n != null && (
          <Typography variant="caption" color="text.secondary">
            {ep.prior_consultations_n} prior consultation{ep.prior_consultations_n !== 1 ? "s" : ""}
          </Typography>
        )}
        {ep.safety_netting_recorded === true && (
          <Typography variant="caption" color="#047857">Safety net recorded</Typography>
        )}
        {ep.safety_netting_recorded === false && (
          <Typography variant="caption" color="#B45309">No safety net recorded</Typography>
        )}
      </Stack>
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Public export
// ---------------------------------------------------------------------------

interface SwimlaneProps {
  patientId: string;
  episodes: EpisodeSummaryEpr[];
  timelineItems: TimelineItem[];
  loading?: boolean;
  onEncounterClick?: (encounterId: string) => void;
}

export function EpisodeSwimlane({
  patientId, episodes, timelineItems, loading, onEncounterClick,
}: SwimlaneProps) {
  if (loading) {
    return (
      <Stack spacing={2}>
        {[1, 2].map((i) => <Skeleton key={i} variant="rounded" height={160} />)}
      </Stack>
    );
  }

  if (episodes.length === 0) {
    return <Alert severity="info">No episodes on record for this patient.</Alert>;
  }

  const pad = 30 * 24 * 60 * 60 * 1000;
  const allTs = [
    ...episodes.map((e) => dateToTs(e.referral_date)),
    ...episodes.map((e) => dateToTs(e.end_date)),
    ...timelineItems.map((t) => dateToTs(t.item_date)),
  ].filter(Boolean);

  const minTs = (Math.min(...allTs) || Date.now()) - pad;
  const maxTs = (Math.max(...allTs) || Date.now()) + pad;

  function encountersForEpisode(ep: EpisodeSummaryEpr): TimelineItem[] {
    const types = new Set(["encounter", "episode"]);
    return timelineItems.filter((t) => {
      if (!types.has(t.item_type)) return false;
      const ts = dateToTs(t.item_date);
      if (!ts) return false;
      const start = dateToTs(ep.referral_date);
      const end = ep.end_date ? dateToTs(ep.end_date) : maxTs;
      if (start && ts < start - pad) return false;
      if (end && ts > end + pad) return false;
      return true;
    });
  }

  return (
    <Box sx={{ pb: 2 }}>
      <Stack direction="row" spacing={2} sx={{ mb: 2 }} alignItems="center" flexWrap="wrap">
        <Stack direction="row" spacing={0.75} alignItems="center">
          <Box sx={{ width: 16, height: 16, borderRadius: "3px", transform: "rotate(45deg)", bgcolor: "#64748B" }} />
          <Typography variant="caption" color="text.secondary">Clinical milestone</Typography>
        </Stack>
        <Stack direction="row" spacing={0.75} alignItems="center">
          <Box sx={{ width: 10, height: 10, borderRadius: "50%", bgcolor: "#94A3B8" }} />
          <Typography variant="caption" color="text.secondary">Encounter</Typography>
        </Stack>
      </Stack>
      {episodes.map((ep, i) => (
        <EpisodeCard
          key={ep.episode_id ?? String(i)}
          patientId={patientId}
          ep={ep}
          encounters={encountersForEpisode(ep)}
          minTs={minTs}
          maxTs={maxTs}
          onEncounterClick={onEncounterClick}
        />
      ))}
    </Box>
  );
}
