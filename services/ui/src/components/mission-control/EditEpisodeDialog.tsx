/**
 * EditEpisodeDialog -- the unified, role-gated dialog for editing an
 * EpisodeOfCare from the Mission Control patient drawer. Replaces
 * ReconcilePathwayDrawer entirely.
 *
 * Atlas trace:
 *   DO: DO-BDBEDA43, DO-CFB91205, DO-08FF9DE0
 *   DI: DI-F4C06C92 (manual update + audit), DI-41B71BF8 (encounter
 *       attach/detach + date re-derivation), DI-6C3E4783 (unified
 *       EditEpisodeDialog replaces ReconcilePathwayDrawer)
 *   Risks: R-E951555E, R-A737EE12
 *   VT: VT-79845292 (manual update), VT-B5EE8C55 (attach/detach),
 *       VT-80AAC194 (unified dialog + drawer integration)
 *
 * Tabs:
 *   - Details      -- edit cancer_type/stage, dates, audit notes/flag.
 *   - Encounters   -- attach / detach encounters with milestone slots.
 *                     Triggers server-side date re-derivation.
 *   - Review       -- in-review reconciliation (PATCH .../review),
 *                     mark reviewed with reviewer notes + role.
 *   - Close        -- close or complete the episode (existing
 *                     PATCH .../status route).
 *   - Merge        -- merge sibling episodes into this one (existing
 *                     POST /episodes/merge route).
 *
 * Role-gating is enforced server-side; this component additionally
 * disables the destructive sections when the caller's role is outside
 * the curator set.
 */
"use client";

import { useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import IconButton from "@mui/material/IconButton";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import Close from "@mui/icons-material/Close";
import EditEpisodeDetailsTab from "./EditEpisodeDetailsTab";
import EditEpisodeEncountersTab from "./EditEpisodeEncountersTab";
import EditEpisodeLifecycleTab from "./EditEpisodeLifecycleTab";
import type { MissionEpisode } from "@/lib/missionControlApi";

export type EditEpisodeDialogTab =
  | "details"
  | "encounters"
  | "review"
  | "close"
  | "merge";

const TAB_LABELS: Record<EditEpisodeDialogTab, string> = {
  details: "Details",
  encounters: "Encounters",
  review: "Review",
  close: "Close",
  merge: "Merge",
};

const TAB_ORDER: EditEpisodeDialogTab[] = [
  "details",
  "encounters",
  "review",
  "close",
  "merge",
];

interface Props {
  open: boolean;
  episode: MissionEpisode;
  patientId: string;
  /** Sibling episodes for this patient, used by the Merge tab. */
  siblingEpisodes: MissionEpisode[];
  /** Reviewer email from the session. */
  reviewerEmail: string;
  /** Reviewer's selected role. Used both for server payloads and for
   *  the local "is curator" check that disables destructive controls. */
  reviewerRole: string;
  initialTab?: EditEpisodeDialogTab;
  onClose: () => void;
  /** Notify the parent so it can refresh the episode/lock view. */
  onSaved: () => void;
  /** Notify the parent that the episode was deleted, merged, or
   *  closed -- the parent should drop it from the focused list. */
  onEpisodeRemoved?: (episodeId: string) => void;
}

const CURATOR_ROLES = new Set(["clinician", "qa_ra_lead", "platform_admin"]);

export default function EditEpisodeDialog({
  open,
  episode,
  patientId,
  siblingEpisodes,
  reviewerEmail,
  reviewerRole,
  initialTab = "details",
  onClose,
  onSaved,
  onEpisodeRemoved,
}: Props) {
  const [tab, setTab] = useState<EditEpisodeDialogTab>(initialTab);
  const [bannerError, setBannerError] = useState<string | null>(null);
  const [bannerInfo, setBannerInfo] = useState<string | null>(null);

  const isCurator = CURATOR_ROLES.has(reviewerRole);
  const tabIndex = TAB_ORDER.indexOf(tab);

  const handleSaved = (info?: string) => {
    setBannerError(null);
    if (info) setBannerInfo(info);
    onSaved();
  };

  const handleError = (message: string) => {
    setBannerInfo(null);
    setBannerError(message);
  };

  const handleRemoved = () => {
    onEpisodeRemoved?.(episode.episode_id);
    onClose();
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      fullWidth
      maxWidth="md"
      PaperProps={{ sx: { minHeight: "60vh" } }}
      aria-labelledby="edit-episode-dialog-title"
    >
      <DialogTitle id="edit-episode-dialog-title" sx={{ pr: 6 }}>
        Edit episode
        <IconButton
          aria-label="Close edit episode dialog"
          onClick={onClose}
          sx={{ position: "absolute", right: 8, top: 8 }}
        >
          <Close />
        </IconButton>
      </DialogTitle>
      <Box sx={{ borderBottom: 1, borderColor: "divider", px: 3 }}>
        <Tabs
          value={tabIndex}
          onChange={(_, v) => setTab(TAB_ORDER[v as number])}
          aria-label="Edit episode sections"
        >
          {TAB_ORDER.map((key) => (
            <Tab
              key={key}
              label={TAB_LABELS[key]}
              id={`edit-episode-tab-${key}`}
              aria-controls={`edit-episode-panel-${key}`}
            />
          ))}
        </Tabs>
      </Box>
      <DialogContent dividers>
        {!isCurator && (
          <Alert severity="warning" sx={{ mb: 2 }}>
            Your current role can only view this episode. Switch to
            clinician or QA / RA lead to make changes.
          </Alert>
        )}
        {bannerError && (
          <Alert severity="error" sx={{ mb: 2 }} onClose={() => setBannerError(null)}>
            {bannerError}
          </Alert>
        )}
        {bannerInfo && (
          <Alert severity="success" sx={{ mb: 2 }} onClose={() => setBannerInfo(null)}>
            {bannerInfo}
          </Alert>
        )}
        {tab === "details" && (
          <Box
            role="tabpanel"
            id="edit-episode-panel-details"
            aria-labelledby="edit-episode-tab-details"
          >
            <EditEpisodeDetailsTab
              episode={episode}
              disabled={!isCurator}
              onSaved={handleSaved}
              onError={handleError}
            />
          </Box>
        )}
        {tab === "encounters" && (
          <Box
            role="tabpanel"
            id="edit-episode-panel-encounters"
            aria-labelledby="edit-episode-tab-encounters"
          >
            <EditEpisodeEncountersTab
              episode={episode}
              patientId={patientId}
              disabled={!isCurator}
              onSaved={handleSaved}
              onError={handleError}
            />
          </Box>
        )}
        {(tab === "review" || tab === "close" || tab === "merge") && (
          <Box
            role="tabpanel"
            id={`edit-episode-panel-${tab}`}
            aria-labelledby={`edit-episode-tab-${tab}`}
          >
            <EditEpisodeLifecycleTab
              section={tab}
              episode={episode}
              siblingEpisodes={siblingEpisodes}
              reviewerEmail={reviewerEmail}
              reviewerRole={reviewerRole}
              disabled={!isCurator}
              onSaved={handleSaved}
              onError={handleError}
              onEpisodeRemoved={handleRemoved}
            />
          </Box>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Done</Button>
      </DialogActions>
    </Dialog>
  );
}
