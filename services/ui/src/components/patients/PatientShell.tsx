/**
 * PatientShell -- persistent EPR shell with sticky header and tab bar.
 *
 * Three-column layout:
 *   Left context rail -- episodes + medications (hidden on mobile)
 *   Main content (flex-grow)
 *   Right clinical context -- problem list + alerts (xl+)
 *
 * Tabs: Overview | Timeline | Encounters | Documents | Alerts
 *
 * Atlas trace:
 *   DO: DO-5D3EA371
 *   DI: DI-357A7468
 */
"use client";

import { useEffect, useState, useCallback } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import AssignmentOutlinedIcon from "@mui/icons-material/AssignmentOutlined";
import DescriptionOutlinedIcon from "@mui/icons-material/DescriptionOutlined";
import MedicalServicesOutlinedIcon from "@mui/icons-material/MedicalServicesOutlined";
import TimelineIcon from "@mui/icons-material/Timeline";
import WarningAmberOutlinedIcon from "@mui/icons-material/WarningAmberOutlined";
import { useAuth } from "@/lib/authContext";
import type { PatientDetail, TimelineItem, CodedEntityRow } from "@/lib/patientEprApi";
import {
  fetchEprPatientDetail,
  fetchEprPatientTimeline,
  fetchCodedEntities,
} from "@/lib/patientEprApi";
import { PatientHeader } from "./PatientHeader";
import { OverviewPanel } from "./OverviewPanel";
import { EpisodeSwimlane } from "./EpisodeSwimlane";
import { EncounterListPanel } from "./EncounterListPanel";
import { DocumentListPanel } from "./DocumentListPanel";
import { AlertsPanel } from "./AlertsPanel";
import { ClinicalContextRail, ContextRail } from "./PatientContextRails";

const TABS = [
  { id: "overview", label: "Overview", icon: <AssignmentOutlinedIcon fontSize="small" /> },
  { id: "timeline", label: "Timeline", icon: <TimelineIcon fontSize="small" /> },
  { id: "encounters", label: "Encounters", icon: <MedicalServicesOutlinedIcon fontSize="small" /> },
  { id: "documents", label: "Documents", icon: <DescriptionOutlinedIcon fontSize="small" /> },
  { id: "alerts", label: "Alerts", icon: <WarningAmberOutlinedIcon fontSize="small" /> },
];

interface Props {
  patientId: string;
  onBack?: () => void;
  /** Label for the optional back control. Defaults to Care patients list. */
  backLabel?: string;
  defaultTab?: string;
}

export function PatientShell({
  patientId,
  onBack,
  backLabel = "Back to patients",
  defaultTab = "overview",
}: Props) {
  const { session } = useAuth();
  const [detail, setDetail] = useState<PatientDetail | null>(null);
  const [timeline, setTimeline] = useState<TimelineItem[]>([]);
  const [entities, setEntities] = useState<CodedEntityRow[]>([]);
  const [detailLoading, setDetailLoading] = useState(true);
  const [timelineLoading, setTimelineLoading] = useState(true);
  const [entitiesLoading, setEntitiesLoading] = useState(true);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState(defaultTab);
  const [selectedEncounterId, setSelectedEncounterId] = useState<string | undefined>();
  const [selectedDocumentId, setSelectedDocumentId] = useState<string | undefined>();
  const [selectedReferralId, setSelectedReferralId] = useState<string | undefined>();

  const isServiceProvider =
    session?.organizations.some((o) => o.scopeType === "service_provider") ??
    false;

  useEffect(() => {
    setDetailLoading(true);
    fetchEprPatientDetail(patientId)
      .then(setDetail)
      .catch((e) =>
        setDetailError(e instanceof Error ? e.message : "Unable to load patient."),
      )
      .finally(() => setDetailLoading(false));
  }, [patientId]);

  useEffect(() => {
    fetchEprPatientTimeline(patientId)
      .then(setTimeline)
      .catch(() => {})
      .finally(() => setTimelineLoading(false));
  }, [patientId]);

  useEffect(() => {
    fetchCodedEntities(patientId)
      .then(setEntities)
      .catch(() => {})
      .finally(() => setEntitiesLoading(false));
  }, [patientId]);

  const handleEncounterClick = useCallback((encId: string) => {
    setSelectedEncounterId(encId);
    setActiveTab("encounters");
  }, []);

  const handleDocumentClick = useCallback((documentId: string) => {
    setSelectedDocumentId(documentId);
    setSelectedReferralId(undefined);
    setActiveTab("documents");
  }, []);

  const handleReferralClick = useCallback((referralId: string) => {
    setSelectedReferralId(referralId);
    setSelectedDocumentId(undefined);
    setActiveTab("documents");
  }, []);

  const handleSbarClick = useCallback((assessmentId: string) => {
    setSelectedDocumentId(`assessment:${assessmentId}`);
    setSelectedReferralId(undefined);
    setActiveTab("documents");
  }, []);

  const scopeEpisodeIds = isServiceProvider
    ? detail?.episodes.map((e) => e.episode_id ?? "").filter(Boolean)
    : undefined;

  const alertCount = detail?.active_alert_count ?? 0;

  return (
    <Box
      sx={{ display: "flex", flexDirection: "column", height: "100vh", overflow: "hidden" }}
    >
      <Box sx={{ flexShrink: 0 }}>
        {onBack && (
          <Box sx={{ px: { xs: 2, sm: 3 }, pt: 1.5, pb: 0.5 }}>
            <Button startIcon={<ArrowBackIcon />} onClick={onBack} size="small">
              {backLabel}
            </Button>
          </Box>
        )}
        <PatientHeader detail={detail} loading={detailLoading} />

        <Box sx={{ bgcolor: "#FFFFFF", borderBottom: "1px solid #E2E8F0" }}>
          <Tabs
            value={activeTab}
            onChange={(_, v) => setActiveTab(v)}
            variant="scrollable"
            scrollButtons="auto"
            sx={{
              px: { xs: 1, sm: 2 },
              "& .MuiTab-root": {
                minHeight: 44,
                fontSize: 13,
                fontWeight: 600,
                textTransform: "none",
              },
            }}
          >
            {TABS.map((tab) => (
              <Tab
                key={tab.id}
                value={tab.id}
                icon={tab.icon}
                iconPosition="start"
                label={
                  tab.id === "alerts" && alertCount > 0
                    ? `${tab.label} (${alertCount})`
                    : tab.label
                }
              />
            ))}
          </Tabs>
        </Box>
      </Box>

      {detailError && (
        <Alert severity="error" sx={{ mx: 2, mt: 1 }}>
          {detailError}
        </Alert>
      )}

      <Box sx={{ flex: 1, display: "flex", overflow: "hidden" }}>
        <Box
          sx={{
            width: 220,
            flexShrink: 0,
            borderRight: "1px solid #E2E8F0",
            overflowY: "auto",
            // Timeline already shows episode lanes -- hide the duplicate rail.
            display: {
              xs: "none",
              lg: activeTab === "timeline" ? "none" : "block",
            },
          }}
        >
          <ContextRail
            detail={detail}
            loading={detailLoading}
            entities={entities}
            entitiesLoading={entitiesLoading}
          />
        </Box>

        <Box sx={{ flex: 1, overflowY: "auto", p: { xs: 2, sm: 2.5 }, minWidth: 0 }}>
          {activeTab === "overview" && (
            <OverviewPanel
              detail={detail}
              loading={detailLoading}
              entities={entities}
              entitiesLoading={entitiesLoading}
            />
          )}
          {activeTab === "timeline" && (
            <EpisodeSwimlane
              patientId={patientId}
              episodes={detail?.episodes ?? []}
              timelineItems={timeline}
              loading={detailLoading || timelineLoading}
              onEncounterClick={handleEncounterClick}
              onDocumentClick={handleDocumentClick}
              onReferralClick={handleReferralClick}
              onSbarClick={handleSbarClick}
            />
          )}
          {activeTab === "encounters" && (
            <EncounterListPanel
              patientId={patientId}
              initialEncounterId={selectedEncounterId}
              scopeEpisodeIds={scopeEpisodeIds}
            />
          )}
          {activeTab === "documents" && (
            <DocumentListPanel
              patientId={patientId}
              scopeEpisodeIds={scopeEpisodeIds}
              initialDocumentId={selectedDocumentId}
              initialReferralId={selectedReferralId}
            />
          )}
          {activeTab === "alerts" && <AlertsPanel patientId={patientId} />}
        </Box>

        <Box
          sx={{
            width: 300,
            flexShrink: 0,
            borderLeft: "1px solid #E2E8F0",
            overflowY: "auto",
            display: { xs: "none", xl: "block" },
          }}
        >
          <ClinicalContextRail
            patientId={patientId}
            entities={entities}
            entitiesLoading={entitiesLoading}
            alertCount={alertCount}
            onOpenAlerts={() => setActiveTab("alerts")}
          />
        </Box>
      </Box>
    </Box>
  );
}
