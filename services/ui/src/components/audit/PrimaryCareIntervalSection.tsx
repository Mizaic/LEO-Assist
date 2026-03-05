"use client";

import Box from "@mui/material/Box";
import SectionCard from "./SectionCard";
import IntervalStripPlot from "./IntervalStripPlot";
import SummaryStatsTable from "./SummaryStatsRow";
import BenchmarkLegend from "./BenchmarkLegend";
import type { AuditIntervals, AuditSectionResult } from "@/lib/analyticsApi";

interface Props {
  result: AuditSectionResult<AuditIntervals> | null;
  loading: boolean;
  error?: string | null;
  orgSelected?: boolean;
}

export default function PrimaryCareIntervalSection({ result, loading, error, orgSelected = false }: Props) {
  const practice = result?.scopes.practice;
  const allianceLive = result?.scopes.alliance_live;
  const englandLive = result?.scopes.england_live;
  const bm = result?.benchmark?.metrics;

  const visibleKeys = orgSelected
    ? (["practice", "similar", "alliance", "national"] as const)
    : (["practice", "national"] as const);

  const nationalMedian = bm?.["primary_care_interval.median_pci_days"]?.national ?? null;
  const allianceMedian = orgSelected
    ? (allianceLive?.pci?.median ?? bm?.["primary_care_interval.median_pci_days"]?.alliance ?? null)
    : null;

  const tableRows = [
    {
      label: "Median primary care interval (days)",
      unit: "days",
      practice: practice?.pci
        ? { value: practice.pci.median, n: practice.pci.n ?? undefined, iqr: [practice.pci.q1, practice.pci.q3] as [number | null, number | null] }
        : null,
      similar: allianceLive?.pci ? { value: allianceLive.pci.median } : null,
      alliance: englandLive?.pci
        ? { value: englandLive.pci.median }
        : { value: bm?.["primary_care_interval.median_pci_days"]?.alliance ?? null },
      national: { value: nationalMedian },
    },
  ];

  return (
    <SectionCard
      id="section-pci"
      title="Primary Care Interval (PCI)"
      description="Days from when the patient first presented with cancer-related symptoms to the date of first referral from primary care."
      availability="ready"
      loading={loading}
      error={error}
    >
      <BenchmarkLegend visibleKeys={visibleKeys} orgSelected={orgSelected} />
      <IntervalStripPlot
        patients={practice?.patients ?? []}
        intervalKey="pci_days"
        label="Primary Care Interval"
        median={practice?.pci?.median ?? null}
        q1={practice?.pci?.q1 ?? null}
        q3={practice?.pci?.q3 ?? null}
        nationalMedian={nationalMedian}
        allianceMedian={allianceMedian}
        maxDays={180}
      />
      <Box sx={{ mt: 2 }}>
        <SummaryStatsTable rows={tableRows} visibleKeys={visibleKeys} caption="Primary care interval statistics" />
      </Box>
    </SectionCard>
  );
}
