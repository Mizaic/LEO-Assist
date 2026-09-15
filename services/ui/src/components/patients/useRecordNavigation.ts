/**
 * Tab and click-through state for the EPR record.
 *
 * Atlas trace:
 *   DO: DO-5D3EA371
 *   DI: DI-357A7468
 */

import { useCallback, useState } from "react";

export function useRecordNavigation(defaultTab: string) {
  const [activeTab, setActiveTab] = useState(defaultTab);
  const [selectedEncounterId, setSelectedEncounterId] = useState<string>();
  const [selectedDocumentId, setSelectedDocumentId] = useState<string>();
  const [selectedReferralId, setSelectedReferralId] = useState<string>();

  const openAlerts = useCallback(() => setActiveTab("alerts"), []);
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

  return {
    activeTab,
    setActiveTab,
    selectedEncounterId,
    selectedDocumentId,
    selectedReferralId,
    openAlerts,
    handleEncounterClick,
    handleDocumentClick,
    handleReferralClick,
    handleSbarClick,
  };
}
