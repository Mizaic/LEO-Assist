/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-EE78E305
 *   DI: DI-6EA84931
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-EE78E305")
 */
"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Dialog from "@mui/material/Dialog";
import IconButton from "@mui/material/IconButton";
import Snackbar from "@mui/material/Snackbar";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import Typography from "@mui/material/Typography";
import Close from "@mui/icons-material/Close";
import RestartAlt from "@mui/icons-material/RestartAlt";
import Tooltip from "@mui/material/Tooltip";
import Add from "@mui/icons-material/Add";
import Edit from "@mui/icons-material/Edit";
import DeleteOutline from "@mui/icons-material/DeleteOutline";
import { useRole } from "@leo/design-system";
import AuditTrailTab from "./AuditTrailTab";
import CodedDataTab from "./CodedDataTab";
import EncounterTextTab from "./EncounterTextTab";
import OverviewTab from "./OverviewTab";
import CreateEpisodeDialog from "./CreateEpisodeDialog";
import EditEpisodeDialog from "./EditEpisodeDialog";
import DeleteEpisodeConfirm from "./DeleteEpisodeConfirm";
import type { MissionEpisode, MissionPatient } from "@/lib/missionControlApi";
import { getCancerTypeLabel } from "@/lib/pathwayLabels";
import {
  fetchMissionPatientEpisodes,
  rerunEpisodeDetector,
} from "@/lib/missionControlApi";
import { useDemoMode } from "@/context/DemoModeContext";
import { maskAge, maskGpName, maskPatientId } from "@/lib/demoMode";
import ConfirmDialog from "@/components/ConfirmDialog";

const EPISODE_CURATOR_ROLES = new Set([
  "triage_clinician",
  "clinician_admin",
  "regulatory_reviewer",
  "administrator",
]);

type DrawerTab = "overview" | "coded" | "encounters" | "audit";

function tabToIndex(tab: DrawerTab): number {
  if (tab === "coded") return 1;
  if (tab === "encounters") return 2;
  if (tab === "audit") return 3;
  return 0;
}

interface Props {
  patient: MissionPatient;
  userEmail: string;
  /** Practice org filter (Mission Control); forwarded to analytics API when set. */
  orgId?: string;
  initialTab?: DrawerTab;
  onClose: () => void;
  onEpisodeUpdated: (episodeId: string, patch: Partial<MissionEpisode>) => void;
  onPatientRebuilt?: (patientId: string) => Promise<void> | void;
  /** Refresh the patient list without closing the drawer. Used for
   *  in-flight edits (milestone attach/detach, episode CRUD) where
   *  the user expects the drawer to stay open and reflect the new
   *  state. DI-4B99678C. */
  onPatientRefreshed?: (patientId: string) => Promise<void> | void;
}

export default function PatientDetailDrawer({
  patient,
  userEmail,
  orgId,
  initialTab = "overview",
  onClose,
  onEpisodeUpdated,
  onPatientRebuilt,
  onPatientRefreshed,
}: Props) {
  const { isDemoMode } = useDemoMode();
  const [tab, setTab] = useState(tabToIndex(initialTab));
  // Drawer-local episode list: hydrated from the new
  // /mission-control/patients/{patient_id}/episodes endpoint
  // (DI-5E47FA5D), which returns every EpisodeOfCare for the patient
  // regardless of the dashboard cohort filter. Seeded from
  // patient.episodes so the first paint is never blank.
  const [drawerEpisodes, setDrawerEpisodes] = useState<MissionEpisode[]>(
    patient.episodes,
  );
  const [drawerEpisodesNonce, setDrawerEpisodesNonce] = useState(0);
  const refreshDrawerEpisodes = () =>
    setDrawerEpisodesNonce((n) => n + 1);
  const [focusedEpisodeId, setFocusedEpisodeId] = useState(
    patient.episodes[0]?.episode_id ?? ""
  );
  const [encounterTextFocusId, setEncounterTextFocusId] = useState<string | null>(null);
  const previousPatientIdRef = useRef(patient.patient_id);
  // Manual EpisodeOfCare CRUD dialogs (DI-3A19BE12 / DI-F4C06C92 /
  // DI-41B71BF8 / DI-B35DCA0F / DI-6C3E4783). Role-gated locally;
  // the backend enforces the same gate independently. Verified by
  // VT-26729755 / VT-79845292 / VT-B5EE8C55 / VT-4A333473 /
  // VT-80AAC194.
  const { selectedRole } = useRole();
  const reviewerRole = selectedRole ?? "";
  const isEpisodeCurator = EPISODE_CURATOR_ROLES.has(reviewerRole);
  const [editEpisodeOpen, setEditEpisodeOpen] = useState(false);
  const [deleteEpisodeOpen, setDeleteEpisodeOpen] = useState(false);
  const [createEpisodeOpen, setCreateEpisodeOpen] = useState(false);
  const triggerPatientRefresh = () => {
    refreshDrawerEpisodes();
    if (onPatientRebuilt) {
      void onPatientRebuilt(patient.patient_id);
    }
  };
  // Refresh-without-close path for in-flight edits like milestone
  // attach / detach. Falls back to the rebuild handler so legacy
  // hosts still get a refresh, even if the drawer collapses.
  const triggerLiveRefresh = () => {
    refreshDrawerEpisodes();
    if (onPatientRefreshed) {
      void onPatientRefreshed(patient.patient_id);
      return;
    }
    triggerPatientRefresh();
  };
  // After a successful create we want to KEEP the drawer open and
  // surface a clear toast, because:
  //   1. The full rebuild path (`onPatientRebuilt`) closes the drawer
  //      via setSelectedPatient(null) -- the user loses context and
  //      thinks "nothing happened".
  //   2. New episodes default to status='in_review', so the
  //      Mission Control cohort filter (e.g. lifecycle_bucket=
  //      confirmed_cancer) will hide them. The toast tells the user
  //      where to look.
  const [createdToast, setCreatedToast] = useState<string | null>(null);
  const handleEpisodeCreated = (newEpisodeId: string) => {
    // The drawer fetches the patient's full episode list independent
    // of the dashboard cohort filter (DI-5E47FA5D), so the new
    // in_review episode WILL appear in the drawer chip rail after
    // the next refresh -- focus it so the curator sees the change.
    setFocusedEpisodeId(newEpisodeId);
    setCreatedToast(newEpisodeId);
    triggerLiveRefresh();
  };
  const handleEpisodeRemoved = (episodeId: string) => {
    if (focusedEpisodeId === episodeId) {
      const next = drawerEpisodes.find((e) => e.episode_id !== episodeId);
      setFocusedEpisodeId(next?.episode_id ?? "");
    }
    triggerPatientRefresh();
  };
  // Bumped whenever a child surface (today: the encounter text editor)
  // commits a coding change. Sibling tabs that fetch their own
  // patient-scoped data observe this nonce in their effect deps so
  // they refetch live data without the user having to close and
  // reopen the drawer. Verifies DI-AA1F5F5B AC: "Live pipeline
  // events appear without manual refresh" and "Reviewer actions
  // complete optimistically and reconcile against the server
  // response." Pinned by VT-E3F857AA.
  const [refreshNonce, setRefreshNonce] = useState(0);
  const bumpRefresh = () => setRefreshNonce((n) => n + 1);
  // Wired into EncounterTextTab.onCodingChanged so an "Edit codes"
  // save refreshes the same surfaces a milestone attach / detach
  // does: sibling tabs (via the nonce) AND the drawer-local
  // episode list (via triggerLiveRefresh). Without the latter the
  // chip rail and Overview tab keep showing pre-edit coded counts
  // and audit_flag state until the user closes and reopens the
  // drawer. DI-AA1F5F5B + DI-5E47FA5D.
  const handleCodingChanged = () => {
    bumpRefresh();
    triggerLiveRefresh();
  };

  useEffect(() => {
    setTab(tabToIndex(initialTab));
  }, [initialTab, patient.patient_id]);

  useEffect(() => {
    const patientChanged = previousPatientIdRef.current !== patient.patient_id;
    previousPatientIdRef.current = patient.patient_id;
    setFocusedEpisodeId((current) => {
      if (patientChanged) return patient.episodes[0]?.episode_id ?? "";
      // Same-patient refreshes can briefly contain the dashboard-filtered
      // episode list before the drawer-local full list arrives. Preserve
      // the current focus so milestone edits do not jump to another pathway.
      if (current) return current;
      return patient.episodes[0]?.episode_id ?? "";
    });
    setDrawerEpisodes(patient.episodes);
    setDrawerEpisodesNonce(0);
    setRefreshNonce(0);
    setEncounterTextFocusId(null);
  }, [patient.patient_id, patient.episodes]);

  // Hydrate the drawer-local episode list from the dedicated
  // patient-scoped endpoint so a manually-created in_review episode
  // is visible in the drawer even when the dashboard cohort filter
  // (e.g. lifecycle_bucket=confirmed_cancer) hides it from the
  // patient row. DI-5E47FA5D, mitigates R-A737EE12.
  useEffect(() => {
    let cancelled = false;
    void fetchMissionPatientEpisodes(patient.patient_id, { orgId })
      .then((res) => {
        if (cancelled) return;
        if (Array.isArray(res?.episodes)) {
          setDrawerEpisodes(res.episodes);
          setFocusedEpisodeId((current) => {
            if (current && res.episodes.some((e) => e.episode_id === current)) {
              return current;
            }
            return res.episodes[0]?.episode_id ?? "";
          });
        }
      })
      .catch(() => {
        // Fail open: keep showing the cohort-filtered list from
        // patient.episodes. The curator can still operate; only the
        // hidden-by-filter case degrades back to the old behaviour.
      });
    return () => {
      cancelled = true;
    };
  }, [patient.patient_id, orgId, drawerEpisodesNonce]);

  const focusedEpisode = useMemo(
    () =>
      drawerEpisodes.find((e) => e.episode_id === focusedEpisodeId) ??
      drawerEpisodes[0],
    [drawerEpisodes, focusedEpisodeId]
  );

  const title = focusedEpisode?.cancer_type
    ? getCancerTypeLabel(focusedEpisode.cancer_type)
    : "Cancer pathway";
  const [confirmRebuild, setConfirmRebuild] = useState(false);
  const [rebuildBusy, setRebuildBusy] = useState(false);
  const [rebuildMessage, setRebuildMessage] = useState<string | null>(null);
  const [rebuildJobState, setRebuildJobState] = useState<
    "queued" | "running" | "completed" | "failed" | null
  >(null);

  const focusEpisodeAndOpenEvidence = (episodeId: string) => {
    setFocusedEpisodeId(episodeId);
    setTab(1); // Switch to Coded data tab
  };
  const openEncounterTextFromCode = (encounterId: string) => {
    setEncounterTextFocusId(encounterId);
    setTab(2);
  };

  const handleRebuildConfirmed = async () => {
    setConfirmRebuild(false);
    setRebuildBusy(true);
    setRebuildMessage(null);
    setRebuildJobState(null);
    try {
      const res = await rerunEpisodeDetector(patient.patient_id, true);
      setRebuildJobState("queued");
      setRebuildMessage(
        `Queued: run ${res.run_id.slice(0, 8)} is waiting for worker pickup.`
      );

      await new Promise<void>((resolve, reject) => {
        const source = new EventSource(
          `${window.location.origin}/api/pipeline/progress/${encodeURIComponent(res.run_id)}`
        );
        let settled = false;
        const complete = (nextState: "completed" | "failed", message: string) => {
          if (settled) return;
          settled = true;
          setRebuildJobState(nextState);
          setRebuildMessage(message);
          source.close();
          if (nextState === "completed") resolve();
          else reject(new Error(message));
        };
        const onEvent = (ev: MessageEvent) => {
          try {
            const payload = JSON.parse(ev.data) as {
              type?: string;
              message?: string;
              subgraph_id?: string;
            };
            const type = payload.type ?? "";
            if (type === "run_started" || type === "patient_started" || type === "encounter_started") {
              setRebuildJobState("running");
              setRebuildMessage(`Running: ${payload.message ?? "full patient pipeline is processing."}`);
            }
            if (type === "step_completed") {
              setRebuildJobState("running");
              const step = payload.subgraph_id ? ` (${payload.subgraph_id})` : "";
              setRebuildMessage(`Running: pipeline step completed${step}.`);
            }
            if (type === "run_completed" || type === "pipeline_done" || type === "extraction_done") {
              complete("completed", "Completed: full patient rebuild finished.");
            }
            if (type === "pipeline_error" || type === "run_error") {
              complete("failed", `Failed: ${payload.message ?? "pipeline execution error."}`);
            }
          } catch {
            // Ignore malformed progress events.
          }
        };
        source.addEventListener("run_started", onEvent as EventListener);
        source.addEventListener("patient_started", onEvent as EventListener);
        source.addEventListener("encounter_started", onEvent as EventListener);
        source.addEventListener("step_completed", onEvent as EventListener);
        source.addEventListener("run_completed", onEvent as EventListener);
        source.addEventListener("pipeline_done", onEvent as EventListener);
        source.addEventListener("extraction_done", onEvent as EventListener);
        source.addEventListener("pipeline_error", onEvent as EventListener);
        source.addEventListener("run_error", onEvent as EventListener);
        source.onerror = () => {
          complete("failed", "Failed: connection to live pipeline status was lost.");
        };
      });

      await onPatientRebuilt?.(patient.patient_id);
    } catch (e) {
      setRebuildJobState("failed");
      setRebuildMessage(
        e instanceof Error
          ? `Re-run failed: ${e.message}`
          : "Re-run failed. Please try again."
      );
    } finally {
      setRebuildBusy(false);
    }
  };

  return (
    <Dialog
      open
      onClose={onClose}
      maxWidth="xl"
      fullWidth
      PaperProps={{
        sx: {
          height: "92vh",
          maxHeight: "92vh",
          borderRadius: 2,
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        },
      }}
    >
      {/* Header */}
      <Box
        sx={{
          px: 3,
          py: 2,
          borderBottom: "1px solid",
          borderColor: "divider",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          flexShrink: 0,
        }}
      >
        <Box>
          <Typography variant="h6" component="h2" sx={{ lineHeight: 1.2 }}>
            {title}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            Patient {isDemoMode ? maskPatientId(patient.patient_id) : patient.patient_id} &middot;{" "}
            {isDemoMode ? maskAge(patient.age) : `${patient.age ?? "--"} yrs`} &middot;{" "}
            {isDemoMode
              ? maskGpName(patient.practice_name)
              : patient.practice_name ?? "Unknown practice"}
          </Typography>
        </Box>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
          <Button
            size="small"
            variant="outlined"
            startIcon={<RestartAlt fontSize="small" />}
            onClick={() => setConfirmRebuild(true)}
            disabled={rebuildBusy}
          >
            Reset and re-run detector
          </Button>
          <IconButton onClick={onClose} aria-label="Close patient details" size="small">
            <Close />
          </IconButton>
        </Box>
      </Box>
      {rebuildMessage && (
        <Box sx={{ px: 3, pt: 1 }}>
          <Alert
            severity={
              rebuildJobState === "failed"
                ? "error"
                : rebuildJobState === "queued" || rebuildJobState === "running"
                  ? "info"
                  : "success"
            }
          >
            {rebuildMessage}
          </Alert>
        </Box>
      )}

      {/* Episode focus chips + manual CRUD affordances. The +New /
          Edit / Delete buttons are role-gated locally; the backend
          enforces the same gate independently. */}
      <Box
        sx={{
          px: 3,
          py: 1,
          borderBottom: "1px solid",
          borderColor: "divider",
          display: "flex",
          gap: 1,
          alignItems: "center",
          flexWrap: "wrap",
        }}
        data-testid="patient-drawer-episode-controls"
      >
        {drawerEpisodes.length > 0 && (
          <Typography variant="caption" color="text.secondary">
            Episode in focus:
          </Typography>
        )}
        {drawerEpisodes.map((ep) => (
          <Chip
            key={ep.episode_id}
            size="small"
            label={ep.cancer_type ? getCancerTypeLabel(ep.cancer_type) : ep.status}
            variant={focusedEpisodeId === ep.episode_id ? "filled" : "outlined"}
            color={focusedEpisodeId === ep.episode_id ? "primary" : "default"}
            onClick={() => setFocusedEpisodeId(ep.episode_id)}
          />
        ))}
        <Box sx={{ flex: 1 }} />
        <Tooltip
          title={
            isEpisodeCurator
              ? "Create a new episode"
              : "Switch to a clinical or administrator role to create episodes"
          }
        >
          <span>
            <Button
              size="small"
              variant="outlined"
              startIcon={<Add fontSize="small" />}
              onClick={() => setCreateEpisodeOpen(true)}
              disabled={!isEpisodeCurator}
              data-testid="patient-drawer-create-episode"
            >
              New episode
            </Button>
          </span>
        </Tooltip>
        {focusedEpisode && (
          <>
            <Tooltip
              title={
                isEpisodeCurator
                  ? `Edit episode ${focusedEpisode.episode_id}`
                  : "Switch to a clinical or administrator role to edit"
              }
            >
              <span>
                <Button
                  size="small"
                  variant="outlined"
                  startIcon={<Edit fontSize="small" />}
                  onClick={() => setEditEpisodeOpen(true)}
                  disabled={!isEpisodeCurator}
                  data-testid="patient-drawer-edit-episode"
                >
                  Edit
                </Button>
              </span>
            </Tooltip>
            <Tooltip
              title={
                isEpisodeCurator
                  ? `Delete episode ${focusedEpisode.episode_id}`
                  : "Switch to a clinical or administrator role to delete"
              }
            >
              <span>
                <Button
                  size="small"
                  variant="outlined"
                  color="error"
                  startIcon={<DeleteOutline fontSize="small" />}
                  onClick={() => setDeleteEpisodeOpen(true)}
                  disabled={!isEpisodeCurator}
                  data-testid="patient-drawer-delete-episode"
                >
                  Delete
                </Button>
              </span>
            </Tooltip>
          </>
        )}
      </Box>

      <Box sx={{ borderBottom: "1px solid", borderColor: "divider", flexShrink: 0 }}>
        <Tabs
          value={tab}
          onChange={(_, v) => setTab(v)}
          variant="scrollable"
          scrollButtons="auto"
        >
          <Tab label="Overview" id="tab-overview" aria-controls="panel-overview" />
          <Tab label="Coded data" id="tab-coded" aria-controls="panel-coded" />
          <Tab label="Encounter text" id="tab-text" aria-controls="panel-text" />
          <Tab label="Audit trail" id="tab-audit" aria-controls="panel-audit" />
        </Tabs>
      </Box>

      {/* Tab panels */}
      <Box sx={{ flex: 1, overflow: "auto", px: 3, py: 2 }}>
        {tab === 0 && (
          <Box role="tabpanel" id="panel-overview" aria-labelledby="tab-overview">
            <OverviewTab
              patient={patient}
              userEmail={userEmail}
              onEpisodeUpdated={onEpisodeUpdated}
              onFocusEpisode={focusEpisodeAndOpenEvidence}
              episodes={drawerEpisodes}
            />
          </Box>
        )}
        {tab === 1 && (
          <Box role="tabpanel" id="panel-coded" aria-labelledby="tab-coded">
            {focusedEpisode ? (
              <CodedDataTab
                patientId={patient.patient_id}
                episode={focusedEpisode}
                onOpenEncounterText={openEncounterTextFromCode}
                refreshKey={refreshNonce}
              />
            ) : (
              <Alert severity="info">
                No pathway is available yet for this patient. Coded data appears after rebuild
                creates a pathway.
              </Alert>
            )}
          </Box>
        )}
        {tab === 2 && (
          <Box role="tabpanel" id="panel-text" aria-labelledby="tab-text">
            {focusedEpisode ? (
              <EncounterTextTab
                patientId={patient.patient_id}
                episode={focusedEpisode}
                episodes={drawerEpisodes}
                reviewerRole={reviewerRole}
                focusEncounterId={encounterTextFocusId}
                onCodingChanged={handleCodingChanged}
                onEpisodeStructureChanged={triggerLiveRefresh}
              />
            ) : (
              <Alert severity="info">
                No pathway is available yet for this patient. Encounter text linked to a pathway
                appears after rebuild completes.
              </Alert>
            )}
          </Box>
        )}
        {tab === 3 && (
          <Box role="tabpanel" id="panel-audit" aria-labelledby="tab-audit">
            <AuditTrailTab
              patientId={patient.patient_id}
              episode={focusedEpisode ?? null}
              orgId={orgId}
              refreshKey={refreshNonce}
            />
          </Box>
        )}
      </Box>
      {confirmRebuild && (
        <ConfirmDialog
          title="Reset and re-run episode detector?"
          body={`This will delete current episode links for this patient and rebuild pathways from coded encounters. Use this after adding or removing codes.`}
          confirmLabel="Reset and re-run"
          variant="danger"
          onConfirm={handleRebuildConfirmed}
          onCancel={() => setConfirmRebuild(false)}
        />
      )}
      <CreateEpisodeDialog
        open={createEpisodeOpen}
        patientId={patient.patient_id}
        reviewerRole={reviewerRole}
        onClose={() => setCreateEpisodeOpen(false)}
        onCreated={handleEpisodeCreated}
      />
      {focusedEpisode && (
        <EditEpisodeDialog
          open={editEpisodeOpen}
          episode={focusedEpisode}
          patientId={patient.patient_id}
          siblingEpisodes={drawerEpisodes}
          reviewerEmail={userEmail}
          reviewerRole={reviewerRole}
          onClose={() => setEditEpisodeOpen(false)}
          onSaved={triggerPatientRefresh}
          onEpisodeRemoved={handleEpisodeRemoved}
        />
      )}
      {focusedEpisode && (
        <DeleteEpisodeConfirm
          open={deleteEpisodeOpen}
          episodeId={focusedEpisode.episode_id}
          episodeLabel={
            focusedEpisode.cancer_type
              ? getCancerTypeLabel(focusedEpisode.cancer_type)
              : focusedEpisode.condition_type
          }
          reviewerRole={reviewerRole}
          onClose={() => setDeleteEpisodeOpen(false)}
          onDeleted={handleEpisodeRemoved}
        />
      )}
      <Snackbar
        open={createdToast !== null}
        autoHideDuration={9000}
        onClose={() => setCreatedToast(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      >
        <Alert
          severity="success"
          onClose={() => setCreatedToast(null)}
          sx={{ width: "100%" }}
          data-testid="patient-drawer-create-episode-toast"
        >
          Episode created (id: {createdToast}) and now in focus. New
          episodes start in &quot;In review&quot;. To see it in the
          patient list, change the cohort filter to &quot;In
          review&quot; or &quot;All pathways&quot; to see it in the list.
        </Alert>
      </Snackbar>
    </Dialog>
  );
}
