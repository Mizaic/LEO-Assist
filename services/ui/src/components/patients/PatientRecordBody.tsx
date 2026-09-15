/**
 * Tab bodies for the EPR record. Click-through handlers stay on the shell.
 *
 * Atlas trace:
 *   DO: DO-5D3EA371
 *   DI: DI-357A7468
 */

import { OverviewPanel } from "./OverviewPanel";
import { EpisodeSwimlane } from "./EpisodeSwimlane";
import { EncounterListPanel } from "./EncounterListPanel";
import { DocumentListPanel } from "./DocumentListPanel";
import { AlertsPanel } from "./AlertsPanel";
import type { usePatientRecord } from "./usePatientRecord";
import type { useRecordNavigation } from "./useRecordNavigation";

interface Props {
  patientId: string;
  record: ReturnType<typeof usePatientRecord>;
  nav: ReturnType<typeof useRecordNavigation>;
  scopeEpisodeIds?: string[];
}

export function PatientRecordBody({
  patientId,
  record,
  nav,
  scopeEpisodeIds,
}: Props) {
  if (nav.activeTab === "overview") {
    return (
      <OverviewPanel
        detail={record.detail}
        loading={record.detailLoading}
        entities={record.entities}
        entitiesLoading={record.entitiesLoading}
        onOpenAlerts={nav.openAlerts}
      />
    );
  }
  if (nav.activeTab === "timeline") {
    return (
      <EpisodeSwimlane
        patientId={patientId}
        episodes={record.detail?.episodes ?? []}
        timelineItems={record.timeline}
        loading={record.detailLoading || record.timelineLoading}
        onEncounterClick={nav.handleEncounterClick}
        onDocumentClick={nav.handleDocumentClick}
        onReferralClick={nav.handleReferralClick}
        onSbarClick={nav.handleSbarClick}
      />
    );
  }
  if (nav.activeTab === "encounters") {
    return (
      <EncounterListPanel
        patientId={patientId}
        initialEncounterId={nav.selectedEncounterId}
        scopeEpisodeIds={scopeEpisodeIds}
      />
    );
  }
  if (nav.activeTab === "documents") {
    return (
      <DocumentListPanel
        patientId={patientId}
        scopeEpisodeIds={scopeEpisodeIds}
        initialDocumentId={nav.selectedDocumentId}
        initialReferralId={nav.selectedReferralId}
      />
    );
  }
  if (nav.activeTab === "alerts") {
    return <AlertsPanel patientId={patientId} />;
  }
  return null;
}
