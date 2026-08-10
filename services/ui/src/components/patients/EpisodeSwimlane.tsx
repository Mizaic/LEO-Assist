/**
 * EpisodeSwimlane -- Timeline tab: pathway swimlanes + activity list.
 *
 * Each episode card uses a local time window so the band is dense.
 * Below the swimlanes, ActivityTimeline lists every clinical event.
 *
 * Atlas trace:
 *   DO: DO-5D3EA371
 *   DI: DI-357A7468
 */
"use client";

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import type { EpisodeSummaryEpr, TimelineItem } from "@/lib/patientEprApi";
import { ActivityTimeline } from "./ActivityTimeline";
import { EpisodeLaneCard } from "./EpisodeLaneCard";

const DAY_MS = 24 * 60 * 60 * 1000;

function dateToTs(iso: string | null | undefined): number {
  if (!iso) return 0;
  try {
    return new Date(iso).getTime();
  } catch {
    return 0;
  }
}

function encountersForEpisode(
  ep: EpisodeSummaryEpr,
  timelineItems: TimelineItem[],
): TimelineItem[] {
  const pad = 14 * DAY_MS;
  const start = dateToTs(ep.referral_date);
  const end = ep.end_date ? dateToTs(ep.end_date) : Date.now() + pad;
  return timelineItems.filter((t) => {
    if (t.item_type !== "encounter") return false;
    const ts = dateToTs(t.item_date);
    if (!ts) return false;
    if (start && ts < start - pad) return false;
    if (end && ts > end + pad) return false;
    return true;
  });
}

function sortNewestFirst(items: TimelineItem[]): TimelineItem[] {
  return [...items].sort(
    (a, b) => dateToTs(b.item_date) - dateToTs(a.item_date),
  );
}

interface SwimlaneProps {
  patientId: string;
  episodes: EpisodeSummaryEpr[];
  timelineItems: TimelineItem[];
  loading?: boolean;
  onEncounterClick?: (encounterId: string) => void;
  onDocumentClick?: (documentId: string) => void;
  onReferralClick?: (referralId: string) => void;
  onSbarClick?: (assessmentId: string) => void;
}

export function EpisodeSwimlane({
  patientId,
  episodes,
  timelineItems,
  loading,
  onEncounterClick,
  onDocumentClick,
  onReferralClick,
  onSbarClick,
}: SwimlaneProps) {
  if (loading) {
    return (
      <Stack spacing={2}>
        {[1, 2].map((i) => (
          <Skeleton key={i} variant="rounded" height={160} />
        ))}
      </Stack>
    );
  }

  if (!loading && episodes.length === 0 && timelineItems.length === 0) {
    return (
      <Alert severity="info">No episodes or clinical activity on record.</Alert>
    );
  }

  const activityItems = sortNewestFirst(timelineItems);
  const hasEpisodes = episodes.length > 0;

  return (
    <Box sx={{ pb: 2 }} data-testid="epr-episode-swimlane">
      {hasEpisodes && (
        <>
          <Stack
            direction="row"
            spacing={2}
            sx={{ mb: 2 }}
            alignItems="center"
            flexWrap="wrap"
          >
            <Stack direction="row" spacing={0.75} alignItems="center">
              <Box
                sx={{
                  width: 16,
                  height: 16,
                  borderRadius: "3px",
                  transform: "rotate(45deg)",
                  bgcolor: "#64748B",
                }}
              />
              <Typography variant="caption" color="text.secondary">
                Clinical milestone
              </Typography>
            </Stack>
            <Stack direction="row" spacing={0.75} alignItems="center">
              <Box
                sx={{ width: 10, height: 10, borderRadius: "50%", bgcolor: "#94A3B8" }}
              />
              <Typography variant="caption" color="text.secondary">
                Encounter
              </Typography>
            </Stack>
          </Stack>

          {episodes.map((ep, i) => (
            <EpisodeLaneCard
              key={ep.episode_id ?? String(i)}
              patientId={patientId}
              ep={ep}
              encounters={encountersForEpisode(ep, timelineItems)}
              onEncounterClick={onEncounterClick}
            />
          ))}
        </>
      )}

      <Paper
        variant="outlined"
        sx={{ p: 2, borderRadius: "10px", mt: hasEpisodes ? 1 : 0 }}
        data-testid="epr-timeline-activity"
      >
        <Typography variant="subtitle2" fontWeight={700} sx={{ mb: 1.5 }}>
          Clinical activity
        </Typography>
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ display: "block", mb: 1.5 }}
        >
          Referrals, documents, SBAR assessments, encounters, episodes, and alerts
          in date order. Select an item to open it.
        </Typography>
        <ActivityTimeline
          items={activityItems}
          onItemClick={(item) => {
            if (item.item_type === "encounter") {
              onEncounterClick?.(item.item_id);
              return;
            }
            if (item.item_type === "document") {
              onDocumentClick?.(item.item_id);
              return;
            }
            if (item.item_type === "referral") {
              onReferralClick?.(item.item_id);
              return;
            }
            if (item.item_type === "sbar") {
              onSbarClick?.(item.item_id);
            }
          }}
        />
      </Paper>
    </Box>
  );
}
