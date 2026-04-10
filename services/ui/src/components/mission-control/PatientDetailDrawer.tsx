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
import AuditTrailTab from "./AuditTrailTab";
import CodedDataTab from "./CodedDataTab";
import EncounterTextTab from "./EncounterTextTab";
import OverviewTab from "./OverviewTab";
import type { MissionEpisode, MissionPatient } from "@/lib/missionControlApi";
import { getCancerTypeLabel } from "@/lib/pathwayLabels";
import { rerunEpisodeDetector } from "@/lib/missionControlApi";
import ConfirmDialog from "@/components/ConfirmDialog";

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

  useEffect(() => {
    setTab(tabToIndex(initialTab));
  }, [initialTab, patient.patient_id]);

  useEffect(() => {
    setFocusedEpisodeId(patient.episodes[0]?.episode_id ?? "");
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

      {/* Tabs */}
      {patient.episodes.length > 1 && (
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
        >
          <Typography variant="caption" color="text.secondary">
            Episode in focus:
          </Typography>
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
        </Box>
      )}

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
            {focusedEpisode && (
              <CodedDataTab patientId={patient.patient_id} episode={focusedEpisode} />
            )}
          </Box>
        )}
        {tab === 2 && (
          <Box role="tabpanel" id="panel-text" aria-labelledby="tab-text">
            {focusedEpisode && (
              <EncounterTextTab patientId={patient.patient_id} episode={focusedEpisode} />
            )}
          </Box>
        )}
        {tab === 3 && (
          <Box role="tabpanel" id="panel-audit" aria-labelledby="tab-audit">
            <AuditTrailTab
              patientId={patient.patient_id}
              episode={focusedEpisode ?? null}
              orgId={orgId}
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
    </Drawer>
  );
}
