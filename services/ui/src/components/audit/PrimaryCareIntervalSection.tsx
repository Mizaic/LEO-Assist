/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2E8544FD
 *   DI: DI-C65FD45B
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2E8544FD")
 */
"use client";

import { useState } from "react";
import SectionCard from "./SectionCard";
import IntervalEvolutionPanel from "./IntervalEvolutionPanel";
import { resolveBenchmarkValue } from "./BenchmarkLegend";
import {
  type AuditIntervals,
  type AuditSectionResult,
} from "@/lib/analyticsApi";

interface Props {
  result: AuditSectionResult<AuditIntervals> | null;
  loading: boolean;
  error?: string | null;
  orgSelected?: boolean;
}

export default function PrimaryCareIntervalSection({ result, loading, error, orgSelected = false }: Props) {
  const [showBenign, setShowBenign] = useState(true);

  const bm = result?.benchmark?.metrics;
  const practiceMedianBm = bm?.["primary_care_interval.median_pci_days"]?.practice ?? null;
  const nationalMedian = resolveBenchmarkValue(bm, "primary_care_interval.median_pci_days", orgSelected);
  const nationalLabel = orgSelected
    ? (practiceMedianBm != null ? "This Practice (2018)" : "All Patients (2018)")
    : "All Patients (2018)";

  return (
    <SectionCard
      id="section-pci"
      title="Time to Referral (Primary Care Interval, PCI)"
      description="Days from the patient's first GP contact with cancer symptoms to fast-track referral. Red = cancer confirmed, green = benign or excluded outcome. Click any dot to open the patient record."
      availability="ready"
      loading={loading}
      error={error}
    >
      <IntervalEvolutionPanel
        intervalFamily="pci"
        intervalKey="pci_days"
        label="Primary Care Interval"
        showBenign={showBenign}
        onToggleBenign={setShowBenign}
        nationalMedian={nationalMedian}
        nationalLabel={nationalLabel}
        maxDays={90}
      />
    </SectionCard>
  );
}
