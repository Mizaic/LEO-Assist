/**
 * PatientShell -- EPR record with sticky identity chrome and one reading column.
 *
 * Tabs: Overview | Timeline | Encounters | Documents | Alerts
 *
 * Atlas trace:
 *   DO: DO-5D3EA371
 *   DI: DI-357A7468
 */
"use client";

import { useMemo, type ReactNode } from "react";
import Box from "@mui/material/Box";
import { SegmentedTabs, color, type SegmentedTab } from "@leo/design-system";
import { useAuth } from "@/lib/authContext";
import { PatientHeader } from "./PatientHeader";
import { PatientRecordBody } from "./PatientRecordBody";
import { RecordLoadAlerts } from "./RecordLoadAlerts";
import { usePatientRecord } from "./usePatientRecord";
import { useRecordNavigation } from "./useRecordNavigation";

const TAB_DEFS: SegmentedTab[] = [
  { id: "overview", label: "Overview" },
  { id: "timeline", label: "Timeline" },
  { id: "encounters", label: "Encounters" },
  { id: "documents", label: "Documents" },
  { id: "alerts", label: "Alerts" },
];

const WIDE_TABS = new Set(["timeline", "encounters", "documents"]);

interface Props {
  patientId: string;
  onBack?: () => void;
  backLabel?: string;
  defaultTab?: string;
}

function ShellFrame({ children }: { children: ReactNode }) {
  return (
    <Box
      sx={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        minHeight: 0,
        overflow: "hidden",
        bgcolor: color.surface.canvas,
      }}
    >
      {children}
    </Box>
  );
}

export function PatientShell({
  patientId,
  onBack,
  backLabel = "Back to patients",
  defaultTab = "overview",
}: Props) {
  const { session } = useAuth();
  const record = usePatientRecord(patientId);
  const nav = useRecordNavigation(defaultTab);
  const isServiceProvider =
    session?.organizations.some((o) => o.scopeType === "service_provider") ??
    false;
  const scopeEpisodeIds = isServiceProvider
    ? record.detail?.episodes.map((e) => e.episode_id ?? "").filter(Boolean)
    : undefined;
  const alertCount = record.detail?.active_alert_count ?? 0;
  const tabs = useMemo(
    () =>
      TAB_DEFS.map((tab) =>
        tab.id === "alerts" ? { ...tab, count: alertCount } : tab,
      ),
    [alertCount],
  );
  const wideTab = WIDE_TABS.has(nav.activeTab);

  return (
    <ShellFrame>
      <PatientHeader
        detail={record.detail}
        loading={record.detailLoading}
        onBack={onBack}
        backLabel={backLabel}
        onOpenAlerts={nav.openAlerts}
      >
        <SegmentedTabs
          tabs={tabs}
          value={nav.activeTab}
          onChange={nav.setActiveTab}
          aria-label="Patient record sections"
          dense
        />
      </PatientHeader>
      <RecordLoadAlerts
        detailError={record.detailError}
        timelineError={record.timelineError}
        entitiesError={record.entitiesError}
        showTimelineError={nav.activeTab === "timeline"}
      />
      <Box sx={{ flex: 1, overflowY: "auto", p: { xs: 2, sm: 2.5 }, minWidth: 0 }}>
        <Box sx={{ maxWidth: wideTab ? "none" : 1120, mx: wideTab ? 0 : "auto" }}>
          <PatientRecordBody
            patientId={patientId}
            record={record}
            nav={nav}
            scopeEpisodeIds={scopeEpisodeIds}
          />
        </Box>
      </Box>
    </ShellFrame>
  );
}
