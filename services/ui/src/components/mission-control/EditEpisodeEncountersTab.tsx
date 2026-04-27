/**
 * EditEpisodeEncountersTab -- read-only view of the encounters
 * currently attached to this EpisodeOfCare, with detach controls
 * for each linked encounter and milestone slot. The raw
 * "paste encounter ID" attach form has been removed -- attaching an
 * encounter to a milestone now happens inline from the encounter
 * card's "Add to milestone" button (see DI-4B99678C and the
 * MilestoneCurationDialog).
 *
 * Atlas trace:
 *   DO: DO-CFB91205, DI: DI-41B71BF8, VT: VT-B5EE8C55 (date-rederive)
 *   DO: DO-7986A957, DI: DI-4B99678C (inline curation -- replaces the
 *       paste-encounter-ID flow that used to live here)
 */
"use client";

import { useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import IconButton from "@mui/material/IconButton";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemText from "@mui/material/ListItemText";
import Typography from "@mui/material/Typography";
import LinkOff from "@mui/icons-material/LinkOff";
import { detachEncounterFromEpisode } from "@/lib/missionControlApi";
import type { MissionEpisode } from "@/lib/missionControlApi";
import { useDemoMode } from "@/context/DemoModeContext";
import { maskPatientId } from "@/lib/demoMode";
import { milestoneLabel } from "./milestoneOptions";

interface Props {
  episode: MissionEpisode;
  patientId: string;
  disabled: boolean;
  onSaved: (info?: string) => void;
  onError: (message: string) => void;
}

export default function EditEpisodeEncountersTab({
  episode,
  patientId,
  disabled,
  onSaved,
  onError,
}: Props) {
  const { isDemoMode } = useDemoMode();
  const [busy, setBusy] = useState<string | null>(null);

  const linkedEncounters = episode.linked_encounter_ids ?? [];
  const milestones = episode.milestones ?? [];

  const handleDetach = async (encounterId: string) => {
    setBusy(`detach:${encounterId}`);
    try {
      const res = await detachEncounterFromEpisode(
        episode.episode_id,
        encounterId
      );
      const referral = res.derived_dates.referral_date ?? "no referral date";
      onSaved(
        `Detached encounter ${encounterId}. Re-derived dates: referral=${referral}.`
      );
    } catch (e) {
      onError(
        e instanceof Error ? e.message : "Could not detach the encounter."
      );
    } finally {
      setBusy(null);
    }
  };

  const rows =
    milestones.length > 0
      ? milestones.map((m) => ({
          encounterId: String(m.encounter_id),
          milestoneType: m.milestone_type,
          date: m.date ?? null,
        }))
      : linkedEncounters.map((id) => ({
          encounterId: String(id),
          milestoneType: null as string | null,
          date: null as string | null,
        }));

  return (
    <Box>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
        Encounters attached to this episode for patient{" "}
        <strong>{isDemoMode ? maskPatientId(patientId) : patientId}</strong>.
        Episode dates re-derive automatically
        from the attached encounters.
      </Typography>
      <Alert severity="info" sx={{ mb: 2 }} data-testid="edit-episode-attach-hint">
        To attach an encounter to a milestone, open the patient timeline
        and use the &quot;Add to milestone&quot; button on the encounter
        card. This removes the need to copy and paste encounter IDs.
      </Alert>

      <Typography variant="subtitle2" sx={{ mb: 1 }}>
        Currently linked encounters
      </Typography>
      {rows.length === 0 ? (
        <Typography
          variant="body2"
          color="text.secondary"
          sx={{ mb: 2, fontStyle: "italic" }}
        >
          No encounters are linked to this episode yet.
        </Typography>
      ) : (
        <List
          dense
          aria-label="Linked encounters"
          data-testid="edit-episode-linked-encounters"
          sx={{ mb: 2, border: 1, borderColor: "divider", borderRadius: 1 }}
        >
          {rows.map((row, idx) => {
            const isBusy = busy === `detach:${row.encounterId}`;
            return (
              <ListItem
                key={`${row.encounterId}-${idx}`}
                secondaryAction={
                  <IconButton
                    edge="end"
                    aria-label={`Detach encounter ${row.encounterId}`}
                    onClick={() => handleDetach(row.encounterId)}
                    disabled={disabled || Boolean(busy)}
                  >
                    {isBusy ? (
                      <CircularProgress size={16} />
                    ) : (
                      <LinkOff fontSize="small" />
                    )}
                  </IconButton>
                }
              >
                <ListItemText
                  primary={row.encounterId}
                  secondary={
                    row.milestoneType
                      ? `${milestoneLabel(row.milestoneType)} - ${row.date ?? "no date"}`
                      : "encounter"
                  }
                />
              </ListItem>
            );
          })}
        </List>
      )}
    </Box>
  );
}
