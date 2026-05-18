/**
 * EncounterEpisodeChips -- one chip per episode the encounter is
 * linked to. Click X to unlink the encounter from THAT episode in
 * one go; every milestone slot the encounter fills on the episode
 * is removed in the same call.
 *
 * Atlas trace:
 *   DO: DO-2A1F90B7
 *   DI: DI-5159A336
 */
"use client";

import { useState } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import ConfirmDialog from "@/components/ConfirmDialog";
import type { EncounterEpisodeLink } from "./useMilestoneCuration";
import { milestoneLabel } from "./milestoneOptions";

interface Props {
  episodeLinks: EncounterEpisodeLink[];
  onUnlink: (episodeId: string) => Promise<void> | void;
}

export default function EncounterEpisodeChips({
  episodeLinks,
  onUnlink,
}: Props) {
  const [target, setTarget] = useState<EncounterEpisodeLink | null>(null);
  const [busyEpisodeId, setBusyEpisodeId] = useState<string | null>(null);

  if (episodeLinks.length === 0) return null;

  const slotSummary = (link: EncounterEpisodeLink): string => {
    if (link.milestoneTypes.length === 0) return "no milestone slots";
    const labels = link.milestoneTypes.map(milestoneLabel);
    return labels.length === 1
      ? `1 milestone slot (${labels[0]})`
      : `${labels.length} milestone slots (${labels.join(", ")})`;
  };

  const [error, setError] = useState<string | null>(null);
  const handleConfirm = async () => {
    if (!target) return;
    setBusyEpisodeId(target.episodeId);
    setError(null);
    try {
      await onUnlink(target.episodeId);
      setTarget(null);
    } catch (err) {
      // Surface unexpected failures inline rather than letting them
      // bubble to Next.js's runtime overlay. The hook already swallows
      // 404 ("already detached") so anything reaching here is a real
      // server / network error worth showing to the curator.
      const message =
        err instanceof Error ? err.message : "Could not unlink the encounter.";
      setError(message);
    } finally {
      setBusyEpisodeId(null);
    }
  };

  return (
    <>
      <Box
        sx={{ display: "flex", gap: 0.5, alignItems: "center", flexWrap: "wrap" }}
        data-testid="encounter-card-episode-chips"
      >
        {episodeLinks.map((link) => {
          const busy = busyEpisodeId === link.episodeId;
          return (
            <Chip
              key={link.episodeId}
              size="small"
              data-testid={`encounter-card-episode-chip-${link.episodeId}`}
              label={link.episodeLabel}
              variant="outlined"
              icon={
                busy ? (
                  <CircularProgress size={12} sx={{ ml: 1 }} />
                ) : undefined
              }
              onDelete={busy ? undefined : () => setTarget(link)}
              sx={{
                height: 22,
                fontSize: "0.7rem",
                bgcolor: "#EEF2FF",
                color: "#3730A3",
                borderColor: "#C7D2FE",
                "& .MuiChip-deleteIcon": {
                  color: "#3730A3",
                  "&:hover": { color: "#1E1B4B" },
                },
              }}
              aria-label={`Linked to ${link.episodeLabel}, ${slotSummary(link)}. Click X to unlink.`}
            />
          );
        })}
      </Box>
      {target && (
        <ConfirmDialog
          title="Unlink this encounter from the pathway?"
          body={
            error
              ? `${error}\n\nTry again, or close this dialog and refresh.`
              : `This removes ${slotSummary(target)} between this encounter and ${target.episodeLabel}. The encounter and the pathway both stay; only the link is removed. Pathway dates are then re-derived.`
          }
          confirmLabel={error ? "Try again" : "Unlink"}
          variant="danger"
          onCancel={() => {
            setTarget(null);
            setError(null);
          }}
          onConfirm={() => void handleConfirm()}
        />
      )}
    </>
  );
}
