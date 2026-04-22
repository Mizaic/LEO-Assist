/**
 * Sub-components for MilestoneCurationDialog. Lives in its own
 * file to keep the dialog itself under the 500-LOC limit.
 *
 * Atlas trace:
 *   DO: DO-7986A957
 *   DI: DI-4B99678C
 */
"use client";

import type { ReactNode } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import FormControlLabel from "@mui/material/FormControlLabel";
import ListItemText from "@mui/material/ListItemText";
import ListSubheader from "@mui/material/ListSubheader";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import type { MissionEpisode } from "@/lib/missionControlApi";
import { getCancerTypeLabel } from "@/lib/pathwayLabels";
import { shortDate } from "./encounterTextUtils";
import {
  MILESTONE_GROUP_LABEL,
  MILESTONE_OPTIONS,
  milestoneLabel,
  type MilestoneGroup,
} from "./milestoneOptions";

// Re-exported for callers that still import the result alerts and
// the action row via MilestoneCurationParts.
export {
  MultiSlotResultAlert,
  NoticeAlert,
  ResultAlert,
} from "./MilestoneCurationResults";
export { DialogActionsRow } from "./MilestoneCurationActions";

// Stage flow: pick -> (conflict | notice) -> confirm -> result.
// conflict = pathway slot already filled on another day (Replace).
// notice = context tag already filled on another day (Add anyway).
// DI-50C7E89C, DI-F5E030ED.
export type Stage = "pick" | "conflict" | "notice" | "confirm" | "result";
export type Busy = "attach" | "detach" | "replace" | null;
export type ExistingLink = { episodeId: string; milestoneType: string };

// Slot-level conflict carried out of detectConflicts() so the
// reviewer sees one entry per milestone slot they picked, even
// across multiple selected slots in one round.
export interface SlotConflict {
  milestoneType: string;
  date: string;
  encounterIds: string[];
  preview: string;
}

// Soft notice for context-tier tags already on other days for the
// same episode (allowed -- context tags repeat). DI-50C7E89C.
export interface SlotNotice {
  milestoneType: string;
  otherDays: string[];
}

export interface MilestoneCurationEncounter {
  encounter_id: string;
  date: string | null;
  text: string | null;
}

export interface ConflictDescription {
  date: string;
  encounterIds: string[];
  preview: string;
}

export function snippet(text: string | null | undefined, max = 80): string {
  if (!text) return "";
  const collapsed = text.replace(/\s+/g, " ").trim();
  return collapsed.length <= max ? collapsed : `${collapsed.slice(0, max)}...`;
}

export function isoDay(value: string | null | undefined): string {
  if (!value) return "";
  return String(value).slice(0, 10);
}

function formatEpisodeOption(ep: MissionEpisode): string {
  const label = ep.cancer_type
    ? getCancerTypeLabel(ep.cancer_type)
    : ep.condition_type ?? ep.status;
  const from = ep.referral_date ? shortDate(ep.referral_date) : "no referral";
  const to = ep.end_date ? shortDate(ep.end_date) : "open";
  return `${label} - ${from} -> ${to}`;
}

// Render the milestone-slot dropdown's MenuItems grouped by tier
// (pathway events first, then supporting context). Each group gets
// a non-selectable ListSubheader. Already-linked options (per the
// chosen episode) are disabled with a hint so the reviewer cannot
// accidentally re-pick them. MUI Select children must be flat, so
// we return a plain array of nodes.
function renderSlotMenuItems(
  milestoneTypes: string[],
  linkedOnEpisode: Set<string>
): ReactNode[] {
  const tiers: MilestoneGroup[] = ["pathway", "context"];
  const nodes: ReactNode[] = [];
  for (const tier of tiers) {
    const tierOptions = MILESTONE_OPTIONS.filter((opt) => opt.group === tier);
    if (tierOptions.length === 0) continue;
    nodes.push(
      <ListSubheader
        key={`subheader-${tier}`}
        data-testid={`milestone-dialog-slot-subheader-${tier}`}
        sx={{ lineHeight: 1.4, py: 0.5 }}
      >
        {MILESTONE_GROUP_LABEL[tier]}
      </ListSubheader>
    );
    for (const opt of tierOptions) {
      const linked = linkedOnEpisode.has(opt.value);
      nodes.push(
        <MenuItem
          key={opt.value}
          value={opt.value}
          disabled={linked}
          data-testid={`milestone-dialog-slot-option-${opt.value}`}
          data-milestone-group={opt.group}
        >
          <Checkbox
            checked={milestoneTypes.includes(opt.value)}
            disabled={linked}
            size="small"
          />
          <ListItemText
            primary={opt.label}
            secondary={linked ? "Already linked" : undefined}
          />
        </MenuItem>
      );
    }
  }
  return nodes;
}

export function PickStage({
  episodeId,
  setEpisodeId,
  milestoneTypes,
  setMilestoneTypes,
  episodes,
  sameDayEncounters,
  existingLinks,
  onRemoveExistingLink,
  busyLinkKey,
  selectedIds,
  toggleSelected,
  selectAll,
  clearAll,
}: {
  episodeId: string;
  setEpisodeId: (v: string) => void;
  // Multi-slot picker (DI-F5E030ED): one trip through the dialog
  // can attach the chosen encounters to many milestone slots on the
  // same episode. The picker tolerates an empty array (Continue is
  // disabled) so the dialog can reset cleanly between opens.
  milestoneTypes: string[];
  setMilestoneTypes: (v: string[]) => void;
  episodes: MissionEpisode[];
  sameDayEncounters: MilestoneCurationEncounter[];
  existingLinks: ExistingLink[];
  onRemoveExistingLink: (link: ExistingLink) => void;
  busyLinkKey: string | null;
  selectedIds: Set<string>;
  toggleSelected: (id: string) => void;
  selectAll: () => void;
  clearAll: () => void;
}) {
  const allSelected =
    sameDayEncounters.length > 0 &&
    sameDayEncounters.every((e) => selectedIds.has(String(e.encounter_id)));
  // Slots already filled on the chosen episode for this trigger
  // encounter -- we grey them out in the dropdown so the reviewer
  // can't accidentally re-pick a slot the backend would no-op.
  const linkedOnEpisode = new Set(
    existingLinks
      .filter((l) => l.episodeId === episodeId)
      .map((l) => l.milestoneType)
  );
  return (
    <Stack spacing={2}>
      {existingLinks.length > 0 && (
        <Box data-testid="milestone-dialog-existing-links">
          <Typography variant="caption" color="text.secondary">
            {existingLinks.length === 1
              ? "Currently linked as:"
              : "Currently linked as:"}
          </Typography>
          <Box
            sx={{
              display: "flex",
              flexWrap: "wrap",
              gap: 0.75,
              mt: 0.5,
            }}
          >
            {existingLinks.map((link) => {
              const key = `${link.episodeId}:${link.milestoneType}`;
              const busy = busyLinkKey === key;
              return (
                <Chip
                  key={key}
                  label={milestoneLabel(link.milestoneType)}
                  color="primary"
                  size="small"
                  onDelete={
                    busy ? undefined : () => onRemoveExistingLink(link)
                  }
                  deleteIcon={
                    busy ? (
                      <CircularProgress size={14} color="inherit" />
                    ) : undefined
                  }
                  data-testid={`milestone-dialog-existing-chip-${link.milestoneType}`}
                />
              );
            })}
          </Box>
        </Box>
      )}
      <TextField
        select
        size="small"
        label="Episode"
        value={episodeId}
        onChange={(e) => setEpisodeId(e.target.value)}
        disabled={episodes.length === 0}
        inputProps={{ "aria-label": "Episode" }}
        data-testid="milestone-dialog-episode"
        SelectProps={{
          displayEmpty: true,
          // Cap the popover height so it scrolls inside itself
          // instead of growing tall enough to cover the dialog
          // action row. Anchor under the field so it always opens
          // downward and the curator can see Cancel / Continue.
          MenuProps: {
            PaperProps: {
              "data-testid": "milestone-dialog-episode-menu",
              sx: { maxHeight: 280 },
            },
            anchorOrigin: { vertical: "bottom", horizontal: "left" },
            transformOrigin: { vertical: "top", horizontal: "left" },
          },
        }}
        InputLabelProps={{ shrink: true }}
        helperText={
          !episodeId
            ? "Pick the pathway this encounter belongs to. Nothing is attached until you pick."
            : existingLinks.length > 0
            ? "Pick the episode to add another slot on."
            : "Pick the episode this milestone belongs to."
        }
      >
        {/*
          Placeholder option (DI-74AF7AD8): the dialog opens with no
          episode chosen so the curator cannot accidentally attach
          to whichever pathway was open in the drawer. The Continue
          button stays disabled while this is the selected value.
        */}
        <MenuItem
          value=""
          disabled
          data-testid="milestone-dialog-episode-placeholder"
        >
          <em>Choose a pathway...</em>
        </MenuItem>
        {episodes.map((ep) => (
          <MenuItem key={ep.episode_id} value={ep.episode_id}>
            {formatEpisodeOption(ep)}
          </MenuItem>
        ))}
      </TextField>
      <TextField
        select
        size="small"
        label="Milestone slots"
        value={milestoneTypes}
        onChange={(e) => {
          const raw = e.target.value;
          // MUI Select returns an array when multiple, but the
          // TextField generic types it as string. Normalise either
          // shape so callers always see string[].
          const next = Array.isArray(raw) ? raw : String(raw).split(",");
          setMilestoneTypes(next.filter(Boolean));
        }}
        SelectProps={{
          multiple: true,
          // Render the chosen slots as chips inside the input so the
          // reviewer can see all picks at a glance without opening
          // the dropdown.
          renderValue: (sel) => (
            <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5 }}>
              {(sel as string[]).map((mt) => (
                <Chip
                  key={mt}
                  label={milestoneLabel(mt)}
                  size="small"
                  data-testid={`milestone-dialog-slot-chip-${mt}`}
                />
              ))}
            </Box>
          ),
          // Same cap as the episode picker -- the slot list has 15+
          // entries grouped by tier, so without a maxHeight the
          // popover covers the dialog's Cancel / Continue row and
          // there's no way out without picking one.
          MenuProps: {
            PaperProps: {
              "data-testid": "milestone-dialog-slot-menu",
              sx: { maxHeight: 320 },
            },
            anchorOrigin: { vertical: "bottom", horizontal: "left" },
            transformOrigin: { vertical: "top", horizontal: "left" },
          },
        }}
        inputProps={{ "aria-label": "Milestone slots" }}
        data-testid="milestone-dialog-slot"
        helperText={
          existingLinks.length > 0
            ? "Pick one or more slots. Slots already linked are greyed out."
            : "Pick one or more slots to fill on this episode."
        }
      >
        {renderSlotMenuItems(milestoneTypes, linkedOnEpisode)}
      </TextField>
      <Divider />
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <Typography variant="caption" color="text.secondary">
          {existingLinks.length > 0
            ? "Pick which encounters to add to the slot above"
            : "Pick which encounters belong to this milestone"}
        </Typography>
        <Button
          size="small"
          onClick={allSelected ? clearAll : selectAll}
          disabled={sameDayEncounters.length <= 1}
          data-testid="milestone-dialog-select-toggle"
        >
          {allSelected ? "Clear all" : "Select all"}
        </Button>
      </Box>
      <Box
        data-testid="milestone-dialog-day-encounters"
        sx={{
          border: 1,
          borderColor: "divider",
          borderRadius: 1,
          p: 1,
          maxHeight: 200,
          overflowY: "auto",
        }}
      >
        {sameDayEncounters.map((enc) => {
          const id = String(enc.encounter_id);
          const checked = selectedIds.has(id);
          return (
            <FormControlLabel
              key={enc.encounter_id}
              sx={{
                display: "flex",
                alignItems: "flex-start",
                mx: 0,
                mb: 0.5,
              }}
              control={
                <Checkbox
                  size="small"
                  checked={checked}
                  onChange={() => toggleSelected(id)}
                  inputProps={{
                    "aria-label": `Include encounter ${shortDate(enc.date)}`,
                  }}
                  data-testid={`milestone-dialog-day-encounter-${id}`}
                />
              }
              label={
                <Box>
                  <Typography
                    variant="caption"
                    color="text.secondary"
                    sx={{ display: "block" }}
                  >
                    {shortDate(enc.date)}
                  </Typography>
                  <Typography variant="body2" sx={{ fontSize: "0.8rem" }}>
                    {snippet(enc.text, 120) || "(no text)"}
                  </Typography>
                </Box>
              }
            />
          );
        })}
      </Box>
    </Stack>
  );
}

export function ConflictAlert({
  conflicts,
}: {
  conflicts: SlotConflict[];
}) {
  if (conflicts.length === 0) return null;
  return (
    <Alert severity="warning" data-testid="milestone-dialog-conflict">
      <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.5 }}>
        {conflicts.length === 1
          ? "This slot is already filled on a different day:"
          : `${conflicts.length} of the picked slots are already filled on a different day:`}
      </Typography>
      <Box component="ul" sx={{ pl: 2, mt: 0.5, mb: 0.5 }}>
        {conflicts.map((c) => (
          <li
            key={c.milestoneType}
            data-testid={`milestone-dialog-conflict-item-${c.milestoneType}`}
          >
            <Typography variant="body2">
              <strong>{milestoneLabel(c.milestoneType)}</strong> already on{" "}
              {shortDate(c.date)}
              {c.preview ? ` -- "${c.preview}"` : ""}
            </Typography>
          </li>
        ))}
      </Box>
      <Typography variant="caption" sx={{ display: "block", mt: 0.5 }}>
        Choose: replace the existing milestones (old encounters will be
        detached), or go back and drop the conflicting slots from your
        selection.
      </Typography>
    </Alert>
  );
}

