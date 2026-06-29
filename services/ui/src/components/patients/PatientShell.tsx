/**
 * PatientShell -- persistent EPR shell with sticky header and tab bar.
 *
 * Three-column layout:
 *   Left context rail (240px, hidden on mobile)
 *   Main content (flex-grow)
 *   Right guidance panel (hidden on small screens)
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
import Divider from "@mui/material/Divider";
import Paper from "@mui/material/Paper";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import Typography from "@mui/material/Typography";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import AssignmentOutlinedIcon from "@mui/icons-material/AssignmentOutlined";
import DescriptionOutlinedIcon from "@mui/icons-material/DescriptionOutlined";
import HealingOutlinedIcon from "@mui/icons-material/HealingOutlined";
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

const TABS = [
  { id: "overview", label: "Overview", icon: <AssignmentOutlinedIcon fontSize="small" /> },
  { id: "timeline", label: "Timeline", icon: <TimelineIcon fontSize="small" /> },
  { id: "encounters", label: "Encounters", icon: <MedicalServicesOutlinedIcon fontSize="small" /> },
  { id: "documents", label: "Documents", icon: <DescriptionOutlinedIcon fontSize="small" /> },
  { id: "alerts", label: "Alerts", icon: <WarningAmberOutlinedIcon fontSize="small" /> },
];

const CONDITION_ACCENT: Record<string, string> = {
  lung: "#1E40AF", breast: "#9D174D", prostate: "#6D28D9",
  colorectal: "#B45309", lower_gi: "#B45309", upper_gi: "#7C3AED",
  skin: "#047857", haematology: "#0369A1", gynaecology: "#BE185D",
  head_and_neck: "#1D4ED8", urology: "#4338CA",
};

function railAccent(type: string | null): string {
  const key = (type ?? "").toLowerCase().replace(/ /g, "_");
  return CONDITION_ACCENT[key] ?? "#475569";
}

function outcomeLabel(outcome: string | null): string {
  const o = (outcome ?? "").toLowerCase();
  if (o === "cancer") return "Cancer confirmed";
  if (o === "benign") return "Benign";
  return outcome ?? "";
}

function RailSection({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <Box sx={{ mb: 2 }}>
      <Typography
        variant="caption"
        fontWeight={700}
        color="text.secondary"
        sx={{ textTransform: "uppercase", fontSize: 10, display: "block", mb: 0.5 }}
      >
        {label}
      </Typography>
      {children}
    </Box>
  );
}

function ContextRail({
  detail,
  loading,
  entities,
  entitiesLoading,
}: {
  detail: PatientDetail | null;
  loading: boolean;
  entities: CodedEntityRow[];
  entitiesLoading: boolean;
}) {
  if (loading || !detail) {
    return (
      <Stack spacing={1.5} sx={{ p: 2 }}>
        {[1, 2, 3].map((i) => <Skeleton key={i} variant="rounded" height={72} />)}
      </Stack>
    );
  }

  const medications = entities.filter((e) => e.entity_type === "medication").slice(0, 5);
  const conditions = entities
    .filter((e) => ["disorder", "disease", "finding"].includes(e.entity_type))
    .slice(0, 5);

  return (
    <Box sx={{ p: 2 }}>
      {/* Episodes */}
      {detail.episodes.slice(0, 3).map((ep, i) => {
        const accent = railAccent(ep.condition_type);
        return (
          <Box
            key={ep.episode_id ?? i}
            sx={{
              position: "relative",
              border: "1px solid #E2E8F0",
              borderRadius: "8px",
              p: "10px 10px 10px 14px",
              mb: 1.5,
              bgcolor: "#FAFAFA",
            }}
          >
            <Box
              aria-hidden="true"
              sx={{ position: "absolute", left: 0, top: 8, bottom: 8, width: 3, borderRadius: 2, bgcolor: accent }}
            />
            <Typography variant="caption" fontWeight={700} color={accent} sx={{ textTransform: "capitalize", display: "block" }}>
              {ep.condition_type ?? "Episode"}
            </Typography>
            {ep.inferred_outcome && (
              <Typography variant="caption" color="text.secondary">
                {outcomeLabel(ep.inferred_outcome)}
              </Typography>
            )}
            {ep.referral_date && (
              <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
                Referred {ep.referral_date.slice(0, 10)}
              </Typography>
            )}
            {ep.staging_value && (
              <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
                Stage {ep.staging_value}{ep.staging_early_late ? ` (${ep.staging_early_late})` : ""}
              </Typography>
            )}
          </Box>
        );
      })}

      <Divider sx={{ mb: 2 }} />

      <RailSection label="GP Practice">
        <Typography variant="body2">{detail.practice_name ?? "Not recorded"}</Typography>
      </RailSection>

      {/* Conditions */}
      {entitiesLoading ? (
        <Stack spacing={0.75} sx={{ mb: 2 }}>
          {[1, 2].map((i) => <Skeleton key={i} height={20} />)}
        </Stack>
      ) : conditions.length > 0 && (
        <RailSection label="Known conditions">
          <Stack spacing={0.5}>
            {conditions.map((e, i) => (
              <Typography key={i} variant="caption" color="text.secondary">{e.name}</Typography>
            ))}
          </Stack>
        </RailSection>
      )}

      {/* Medications */}
      {!entitiesLoading && medications.length > 0 && (
        <RailSection label="Medications">
          <Stack spacing={0.5}>
            {medications.map((e, i) => (
              <Typography key={i} variant="caption" color="text.secondary">{e.name}</Typography>
            ))}
          </Stack>
        </RailSection>
      )}
    </Box>
  );
}

interface Props {
  patientId: string;
  onBack?: () => void;
  defaultTab?: string;
}

export function PatientShell({ patientId, onBack, defaultTab = "overview" }: Props) {
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

  const selectedRole = session?.selectedRole ?? "";
  const isServiceProvider = session?.organizations.some(
    (o) => o.scopeType === "service_provider"
  ) ?? false;

  useEffect(() => {
    setDetailLoading(true);
    fetchEprPatientDetail(patientId)
      .then(setDetail)
      .catch((e) => setDetailError(e instanceof Error ? e.message : "Unable to load patient."))
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

  const scopeEpisodeIds = isServiceProvider
    ? detail?.episodes.map((e) => e.episode_id ?? "").filter(Boolean)
    : undefined;

  const alertCount = detail?.active_alert_count ?? 0;

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100vh", overflow: "hidden" }}>
      {/* Sticky header */}
      <Box sx={{ flexShrink: 0 }}>
        {onBack && (
          <Box sx={{ px: { xs: 2, sm: 3 }, pt: 1.5, pb: 0.5 }}>
            <Button
              startIcon={<ArrowBackIcon />}
              onClick={onBack}
              size="small"
            >
              Back to patients
            </Button>
          </Box>
        )}
        <PatientHeader detail={detail} loading={detailLoading} />

        {/* Tab bar */}
        <Box sx={{ bgcolor: "#FFFFFF", borderBottom: "1px solid #E2E8F0" }}>
          <Tabs
            value={activeTab}
            onChange={(_, v) => setActiveTab(v)}
            variant="scrollable"
            scrollButtons="auto"
            sx={{
              px: { xs: 1, sm: 2 },
              "& .MuiTab-root": { minHeight: 44, fontSize: 13, fontWeight: 600, textTransform: "none" },
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

      {/* Three-column body */}
      <Box sx={{ flex: 1, display: "flex", overflow: "hidden" }}>
        {/* Left context rail */}
        <Box
          sx={{
            width: 240,
            flexShrink: 0,
            borderRight: "1px solid #E2E8F0",
            overflowY: "auto",
            display: { xs: "none", lg: "block" },
          }}
        >
          <ContextRail
            detail={detail}
            loading={detailLoading}
            entities={entities}
            entitiesLoading={entitiesLoading}
          />
        </Box>

        {/* Main content */}
        <Box sx={{ flex: 1, overflowY: "auto", p: { xs: 2, sm: 2.5 } }}>
          {activeTab === "overview" && (
            <OverviewPanel detail={detail} loading={detailLoading} />
          )}
          {activeTab === "timeline" && (
            <EpisodeSwimlane
              patientId={patientId}
              episodes={detail?.episodes ?? []}
              timelineItems={timeline}
              loading={detailLoading || timelineLoading}
              onEncounterClick={handleEncounterClick}
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
            />
          )}
          {activeTab === "alerts" && <AlertsPanel patientId={patientId} />}
        </Box>

        {/* Right guidance panel */}
        <Box
          sx={{
            width: 280,
            flexShrink: 0,
            borderLeft: "1px solid #E2E8F0",
            overflowY: "auto",
            display: { xs: "none", xl: "block" },
          }}
        >
          <Box sx={{ p: 2 }}>
            <Typography
              variant="caption"
              fontWeight={700}
              color="text.secondary"
              sx={{ textTransform: "uppercase", fontSize: 10, mb: 1.5, display: "block" }}
            >
              Clinical guidance
            </Typography>
            <Paper
              variant="outlined"
              sx={{ p: 1.5, borderRadius: "8px", mb: 1 }}
            >
              <Stack direction="row" spacing={1} alignItems="center">
                <HealingOutlinedIcon sx={{ fontSize: 16, color: "#1E40AF" }} />
                <Typography variant="caption" fontWeight={700} color="#1E40AF">
                  Applicable guidelines
                </Typography>
              </Stack>
              <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: "block" }}>
                Guidelines will appear here when episode context is selected.
              </Typography>
            </Paper>
          </Box>
        </Box>
      </Box>
    </Box>
  );
}
