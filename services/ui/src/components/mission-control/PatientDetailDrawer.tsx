/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-EE78E305
 *   DI: DI-6EA84931
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-EE78E305")
 */
"use client";

import { useEffect, useMemo, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Drawer from "@mui/material/Drawer";
import IconButton from "@mui/material/IconButton";
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
import { rerunEpisodeDetector } from "@/lib/missionControlApi";
import ConfirmDialog from "@/components/ConfirmDialog";

const EPISODE_CURATOR_ROLES = new Set([
  "clinician",
  "qa_ra_lead",
  "platform_admin",
]);

const DRAWER_WIDTH = "62vw";

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
}

export default function PatientDetailDrawer({
  patient,
  userEmail,
  orgId,
  initialTab = "overview",
  onClose,
  onEpisodeUpdated,
  onPatientRebuilt,
}: Props) {
  const [tab, setTab] = useState(tabToIndex(initialTab));
  const [focusedEpisodeId, setFocusedEpisodeId] = useState(
    patient.episodes[0]?.episode_id ?? ""
  );
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
    if (onPatientRebuilt) {
      void onPatientRebuilt(patient.patient_id);
    }
  };
  const handleEpisodeCreated = (newEpisodeId: string) => {
    setFocusedEpisodeId(newEpisodeId);
    triggerPatientRefresh();
  };
  const handleEpisodeRemoved = (episodeId: string) => {
    if (focusedEpisodeId === episodeId) {
      const next = patient.episodes.find((e) => e.episode_id !== episodeId);
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

  useEffect(() => {
    setTab(tabToIndex(initialTab));
  }, [initialTab, patient.patient_id]);

  useEffect(() => {
    setFocusedEpisodeId(patient.episodes[0]?.episode_id ?? "");
    setRefreshNonce(0);
  }, [patient.patient_id]);

  const focusedEpisode = useMemo(
    () =>
      patient.episodes.find((e) => e.episode_id === focusedEpisodeId) ??
      patient.episodes[0],
    [patient.episodes, focusedEpisodeId]
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
    <Drawer
      anchor="right"
      open
      onClose={onClose}
      PaperProps={{
        sx: { width: DRAWER_WIDTH, maxWidth: "95vw" },
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
            Patient {patient.patient_id} &middot; {patient.age ?? "--"} yrs &middot;{" "}
            {patient.practice_name ?? "Unknown practice"}
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
        {patient.episodes.length > 0 && (
          <Typography variant="caption" color="text.secondary">
            Episode in focus:
          </Typography>
        )}
        {patient.episodes.map((ep) => (
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
              : "Switch to clinician or QA / RA lead to create episodes"
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
                  : "Switch to clinician or QA / RA lead to edit"
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
                  : "Switch to clinician or QA / RA lead to delete"
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
            />
          </Box>
        )}
        {tab === 1 && (
          <Box role="tabpanel" id="panel-coded" aria-labelledby="tab-coded">
            {focusedEpisode ? (
              <CodedDataTab
                patientId={patient.patient_id}
                episode={focusedEpisode}
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
                episodes={patient.episodes}
                reviewerRole={reviewerRole}
                onCodingChanged={bumpRefresh}
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
          siblingEpisodes={patient.episodes}
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
    </Drawer>
  );
}
