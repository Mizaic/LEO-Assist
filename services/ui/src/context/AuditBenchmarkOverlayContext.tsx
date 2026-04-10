"use client";

import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

export type AuditBenchmarkOverlayValue = {
  showCancerAlliance: boolean;
  showAllPatients: boolean;
  setShowCancerAlliance: (v: boolean) => void;
  setShowAllPatients: (v: boolean) => void;
};

const noop = () => {};

const AuditBenchmarkOverlayContext = createContext<AuditBenchmarkOverlayValue>({
  showCancerAlliance: false,
  showAllPatients: false,
  setShowCancerAlliance: noop,
  setShowAllPatients: noop,
});

export function AuditBenchmarkOverlayProvider({ children }: { children: ReactNode }) {
  const [showCancerAlliance, setShowCancerAlliance] = useState(false);
  const [showAllPatients, setShowAllPatients] = useState(false);
  const value = useMemo(
    () => ({
      showCancerAlliance,
      showAllPatients,
      setShowCancerAlliance,
      setShowAllPatients,
    }),
    [showCancerAlliance, showAllPatients],
  );
  return (
    <AuditBenchmarkOverlayContext.Provider value={value}>{children}</AuditBenchmarkOverlayContext.Provider>
  );
}

export function useAuditBenchmarkOverlay(): AuditBenchmarkOverlayValue {
  return useContext(AuditBenchmarkOverlayContext);
}
