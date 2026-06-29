"use client";

/**
 * Registry that maps a widget_id to a full NCDA audit section component plus
 * the analytics fetch that feeds it. This is what gives the template builder
 * visual parity with the hand-built Clinical Audit report: any of these rich
 * sections can be dropped onto a report as a widget tile.
 *
 * Atlas trace:
 *   DO: DO-A9863AB6
 *   DI: DI-AUDIT-WIDGET-PARITY, DI-758B73A5
 */

import { useEffect, useState, type ComponentType } from "react";
import dynamic from "next/dynamic";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import Typography from "@mui/material/Typography";

import { AuditBenchmarkOverlayProvider } from "@/context/AuditBenchmarkOverlayContext";
import { useAnalyticsDateFilter } from "@/context/AnalyticsDateFilterContext";
import {
  fetchAuditCancerType,
  fetchAuditCancerStage,
  fetchAuditDemographics,
  fetchAuditPlaceOfPresentation,
  fetchAuditConsultations,
  fetchAuditInvestigations,
  fetchAuditIntervals,
  fetchAuditSafetyNetting,
  fetchAuditCareObstructions,
  fetchAuditAvoidableDelays,
  fetchAuditComorbidities,
} from "@/lib/analyticsApi";

function Skeleton({ label }: { label: string }) {
  return (
    <Box
      sx={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 1.5,
        py: 8,
        color: "text.disabled",
      }}
    >
      <CircularProgress size={24} />
      <Typography variant="caption">Loading {label}...</Typography>
    </Box>
  );
}

function lazy<P>(
  loader: () => Promise<{ default: ComponentType<P> }>,
  label: string,
): ComponentType<SectionProps> {
  return dynamic(loader, {
    ssr: false,
    loading: () => <Skeleton label={label} />,
  }) as unknown as ComponentType<SectionProps>;
}

/** Common prop shape shared by the NCDA section components. */
interface SectionProps {
  result: unknown;
  loading: boolean;
  error: string | null;
  orgSelected: boolean;
}

type SectionFetcher = (
  orgId?: string,
  dateFrom?: string,
  dateTo?: string,
) => Promise<unknown>;

interface SectionWidgetDef {
  title: string;
  Component: ComponentType<SectionProps>;
  fetcher: SectionFetcher;
}

export const SECTION_WIDGETS: Record<string, SectionWidgetDef> = {
  cancer_type: {
    title: "Cancer Type Breakdown",
    Component: lazy(() => import("@/components/audit/CancerTypeSection"), "Cancer Type Breakdown"),
    fetcher: fetchAuditCancerType,
  },
  cancer_stage: {
    title: "Cancer Stage at Diagnosis",
    Component: lazy(() => import("@/components/audit/CancerStageSection"), "Cancer Stage at Diagnosis"),
    fetcher: fetchAuditCancerStage,
  },
  demographics: {
    title: "Patient Demographics",
    Component: lazy(() => import("@/components/audit/DemographicsSection"), "Patient Demographics"),
    fetcher: fetchAuditDemographics,
  },
  place_of_presentation: {
    title: "Place of Presentation",
    Component: lazy(() => import("@/components/audit/PlaceOfPresentationSection"), "Place of Presentation"),
    fetcher: fetchAuditPlaceOfPresentation,
  },
  consultations: {
    title: "Consultations Before Referral",
    Component: lazy(() => import("@/components/audit/ConsultationsSection"), "Consultations Before Referral"),
    fetcher: fetchAuditConsultations,
  },
  investigations: {
    title: "Investigations",
    Component: lazy(() => import("@/components/audit/InvestigationsSection"), "Investigations"),
    fetcher: fetchAuditInvestigations,
  },
  diagnostic_intervals: {
    title: "Diagnostic Intervals",
    Component: lazy(() => import("@/components/audit/DiagnosticIntervalSection"), "Diagnostic Intervals"),
    fetcher: fetchAuditIntervals,
  },
  safety_netting: {
    title: "Safety Netting",
    Component: lazy(() => import("@/components/audit/SafetyNettingSection"), "Safety Netting"),
    fetcher: fetchAuditSafetyNetting,
  },
  care_obstructions: {
    title: "Care Obstructions",
    Component: lazy(() => import("@/components/audit/CareObstructionsSection"), "Care Obstructions"),
    fetcher: fetchAuditCareObstructions,
  },
  avoidable_delays: {
    title: "Avoidable Delays",
    Component: lazy(() => import("@/components/audit/AvoidableDelaysSection"), "Avoidable Delays"),
    fetcher: fetchAuditAvoidableDelays,
  },
  comorbidities: {
    title: "Comorbidities",
    Component: lazy(() => import("@/components/audit/ComorbiditiesSection"), "Comorbidities"),
    fetcher: fetchAuditComorbidities,
  },
};

function defaultRange(): { from: string; to: string } {
  const now = new Date();
  const from = new Date(now);
  from.setFullYear(from.getFullYear() - 3);
  return { from: from.toISOString().slice(0, 10), to: now.toISOString().slice(0, 10) };
}

/**
 * Fetches the section result for a widget and renders the matching NCDA
 * component, wrapped in the benchmark-overlay provider it expects.
 */
export function SectionWidget({ widgetId, orgId }: { widgetId: string; orgId: string }) {
  const def = SECTION_WIDGETS[widgetId];
  const { appliedFrom, appliedTo } = useAnalyticsDateFilter();
  const [result, setResult] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!def) return;
    let cancelled = false;
    const range = defaultRange();
    setLoading(true);
    setError(null);
    def
      .fetcher(orgId || undefined, appliedFrom ?? range.from, appliedTo ?? range.to)
      .then((r) => !cancelled && setResult(r))
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [def, orgId, appliedFrom, appliedTo]);

  if (!def) return null;
  const { Component } = def;
  return (
    <AuditBenchmarkOverlayProvider>
      <Component
        result={result}
        loading={loading}
        error={error}
        orgSelected={Boolean(orgId)}
      />
    </AuditBenchmarkOverlayProvider>
  );
}
