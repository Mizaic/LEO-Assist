/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2E8544FD
 *   DI: DI-C65FD45B
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2E8544FD")
 */
"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Stack from "@mui/material/Stack";
import Alert from "@mui/material/Alert";
import Tooltip from "@mui/material/Tooltip";
import IconButton from "@mui/material/IconButton";
import Tabs from "@mui/material/Tabs";
import Tab from "@mui/material/Tab";
import PrintOutlinedIcon from "@mui/icons-material/PrintOutlined";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import AssessmentOutlinedIcon from "@mui/icons-material/AssessmentOutlined";
import DashboardOutlinedIcon from "@mui/icons-material/DashboardOutlined";

import { useOrgId } from "@/context/OrgContext";
import { useAnalyticsDateFilter } from "@/context/AnalyticsDateFilterContext";
import {
  fetchBenchmarkSets,
  fetchAuditSummary,
  fetchAuditCancerType,
  fetchAuditCancerStage,
  fetchAuditDemographics,
  fetchAuditComorbidities,
  fetchAuditPlaceOfPresentation,
  fetchAuditConsultations,
  fetchAuditInvestigations,
  fetchAuditReferrals,
  fetchAuditIntervals,
  fetchAuditSafetyNetting,
  fetchAuditCareObstructions,
  fetchAuditPriorConsultations,
  fetchAuditAvoidableDelays,
  type AuditSummary,
  type AuditCancerTypeRow,
  type AuditCancerStageSummary,
  type AuditDemographics,
  type AuditComorbidities,
  type AuditPlaceRow,
  type AuditConsultations,
  type AuditInvestigations,
  type AuditReferralRow,
  type AuditIntervals,
  type AuditSafetyNetting,
  type AuditCareObstruction,
  type AuditPriorConsultations,
  type AuditAvoidableDelays,
  type AuditSectionResult,
} from "@/lib/analyticsApi";
import FastTrackReferralEvolutionSection from "@/components/audit/FastTrackReferralEvolutionSection";

import AuditReportShell, { type TocSection } from "@/components/audit/AuditReportShell";
import AuditSnapshotView, { type YearSummaryPoint } from "@/components/audit/AuditSnapshotView";
import { useAuditYearWindows } from "@/components/audit/_useAuditYearWindows";
import AuditSummarySection from "@/components/audit/AuditSummarySection";
import CancerTypeEvolutionSection from "@/components/audit/CancerTypeEvolutionSection";
import CancerStageEvolutionSection from "@/components/audit/CancerStageEvolutionSection";
import DemographicsEvolutionSection from "@/components/audit/DemographicsEvolutionSection";
import ComorbiditiesSection from "@/components/audit/ComorbiditiesSection";
import SymptomsSection from "@/components/audit/SymptomsSection";
import PlaceOfPresentationSection from "@/components/audit/PlaceOfPresentationSection";
import ConsultationsSection from "@/components/audit/ConsultationsSection";
import MultipleConsultationsSection from "@/components/audit/MultipleConsultationsSection";
import InvestigationsSection from "@/components/audit/InvestigationsSection";
import EmergencyReferralRoutesSection from "@/components/audit/EmergencyReferralRoutesSection";
import PrimaryCareIntervalSection from "@/components/audit/PrimaryCareIntervalSection";
import DiagnosticIntervalSection from "@/components/audit/DiagnosticIntervalSection";
import SafetyNettingSection from "@/components/audit/SafetyNettingSection";
import CareObstructionsSection from "@/components/audit/CareObstructionsSection";
import PriorConsultationsSection from "@/components/audit/PriorConsultationsSection";
import { AuditBenchmarkOverlayProvider } from "@/context/AuditBenchmarkOverlayContext";

const TOC_SECTIONS: TocSection[] = [
  { id: "section-summary", label: "Summary", group: "overview" },
  { id: "section-cancer-type", label: "Cancer Type", group: "results" },
  { id: "section-cancer-stage", label: "Cancer Stage", group: "results" },
  { id: "section-demographics", label: "Demographics", group: "results" },
  { id: "section-comorbidities", label: "Comorbidities", group: "results" },
  { id: "section-symptoms", label: "Symptoms at Referral", group: "results" },
  { id: "section-place-of-presentation", label: "Place of Presentation", group: "results" },
  { id: "section-consultations", label: "Consultations", group: "results" },
  { id: "section-multiple-consultations", label: "Multiple Consultations", group: "results" },
  { id: "section-prior-consultations", label: "Prior Consultations (NCDA S7)", group: "results" },
  { id: "section-investigations", label: "Investigations", group: "results" },
  { id: "section-ftr-types", label: "Fast Track Referral Types", group: "results" },
  { id: "section-emergency-routes", label: "Emergency Referral Routes", group: "results" },
  { id: "section-pci", label: "Primary Care Interval", group: "intervals" },
  { id: "section-di", label: "Diagnostic Interval", group: "intervals" },
  { id: "section-safety-netting", label: "Safety Netting", group: "quality" },
  { id: "section-avoidable-delays", label: "Avoidable Delays", group: "quality" },
];

interface SectionLoading {
  summary: boolean;
  cancerType: boolean;
  cancerStage: boolean;
  demographics: boolean;
  comorbidities: boolean;
  placeOfPresentation: boolean;
  consultations: boolean;
  investigations: boolean;
  referrals: boolean;
  intervals: boolean;
  safetyNetting: boolean;
  careObstructions: boolean;
  priorConsultations: boolean;
  avoidableDelays: boolean;
}

interface SectionErrors {
  [key: string]: string | null;
}

const allTrue = (): SectionLoading => ({
  summary: true, cancerType: true, cancerStage: true, demographics: true, comorbidities: true,
  placeOfPresentation: true, consultations: true, investigations: true,
  referrals: true, intervals: true, safetyNetting: true, careObstructions: true,
  priorConsultations: true, avoidableDelays: true,
});

const allFalse = (): SectionLoading => ({
  summary: false, cancerType: false, cancerStage: false, demographics: false, comorbidities: false,
  placeOfPresentation: false, consultations: false, investigations: false,
  referrals: false, intervals: false, safetyNetting: false, careObstructions: false,
  priorConsultations: false, avoidableDelays: false,
});

export default function AuditPage() {
  const orgId = useOrgId();
  const orgSelected = !!orgId;

  // 0 = Insight Snapshot, 1 = Full Report
  const [activeTab, setActiveTab] = useState(0);
  const [pendingReportScrollSectionId, setPendingReportScrollSectionId] = useState<string | null>(null);

  const handleViewInReport = (sectionId: string) => {
    setPendingReportScrollSectionId(sectionId);
    setActiveTab(1);
  };

  // After every section migrated to the year-on-year evolution model
  // (DI-077C8810 + this commit), each section owns its own per-year
  // fetch via useAuditYearWindows; the page-level fetch is now
  // restricted to the same Jan(Y-2) -> Dec(Y) cohort window so the
  // Summary headline, the cohort breakdown, the snapshot trend
  // table, and every section radar agree on the same denominator
  // (year of diagnosis or benign closure -- see _OUTCOME_DATE_BIND
  // on the backend). Users may still narrow the window via the
  // global analytics-date-filter context; otherwise we anchor on the
  // 3-year default that all evolution cards cover.
  const { appliedFrom, appliedTo, isFiltered } = useAnalyticsDateFilter();
  const currentYear = new Date().getUTCFullYear();
  const defaultWindowFrom = `${currentYear - 2}-01-01`;
  const defaultWindowTo = `${currentYear}-12-31`;
  const effectiveFrom = appliedFrom ?? defaultWindowFrom;
  const effectiveTo = appliedTo ?? defaultWindowTo;
  const cohortWindowLabel = `${currentYear - 2}-${currentYear} (year of diagnosis or benign closure)`;

  // Benchmark set selection.
  // null = lookup still in-flight; "none" = loaded but no benchmark selected; else = set id.
  // Using null as the "pending" sentinel lets load() guard itself without
  // adding a new dependency to the useEffect array (which would violate the
  // rules-of-hooks constant-size requirement).  The user-facing selector was
  // removed when the cancer-type section moved to a fixed evolution view; the
  // first available benchmark set is selected automatically on mount so the
  // 2019 benchmark can still be resolved by every section.
  const [benchmarkSetId, setBenchmarkSetId] = useState<string | null>(null);

  // Section loading / error state
  const [loading, setLoading] = useState<SectionLoading>(allTrue());
  const [errors, setErrors] = useState<SectionErrors>({});

  // Section data — all wrapped in AuditSectionResult
  const [summary, setSummary] = useState<AuditSummary | null>(null);
  const [cancerType, setCancerType] = useState<AuditSectionResult<AuditCancerTypeRow[]> | null>(null);
  const [cancerStage, setCancerStage] = useState<AuditSectionResult<AuditCancerStageSummary> | null>(null);
  const [demographics, setDemographics] = useState<AuditSectionResult<AuditDemographics> | null>(null);
  const [comorbidities, setComorbidities] = useState<AuditSectionResult<AuditComorbidities> | null>(null);
  const [placeOfPresentation, setPlaceOfPresentation] = useState<AuditSectionResult<AuditPlaceRow[]> | null>(null);
  const [consultations, setConsultations] = useState<AuditSectionResult<AuditConsultations> | null>(null);
  const [investigations, setInvestigations] = useState<AuditSectionResult<AuditInvestigations> | null>(null);
  const [referrals, setReferrals] = useState<AuditSectionResult<AuditReferralRow[]> | null>(null);
  const [intervals, setIntervals] = useState<AuditSectionResult<AuditIntervals> | null>(null);
  const [safetyNetting, setSafetyNetting] = useState<AuditSectionResult<AuditSafetyNetting> | null>(null);
  const [careObstructions, setCareObstructions] = useState<AuditSectionResult<AuditCareObstruction> | null>(null);
  const [priorConsultations, setPriorConsultations] = useState<AuditSectionResult<AuditPriorConsultations> | null>(null);
  const [avoidableDelays, setAvoidableDelays] = useState<AuditSectionResult<AuditAvoidableDelays> | null>(null);

  // Fetch available benchmark sets on mount and auto-select the first.
  // Both .then() and .catch() set benchmarkSetId away from null, which recreates
  // the load callback and unblocks the main data fetch -- no separate gate
  // state needed.
  useEffect(() => {
    fetchBenchmarkSets()
      .then((sets) => {
        setBenchmarkSetId(sets.length > 0 ? sets[0].id : "none");
      })
      .catch(() => {
        setBenchmarkSetId("none"); // proceed without benchmark overlay
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // null means benchmark lookup is still pending — treat same as "no benchmark" for the API
  const effectiveBenchmarkSetId = (benchmarkSetId === null || benchmarkSetId === "none")
    ? undefined
    : benchmarkSetId;

  // ── Per-year fetchers for the Insight Snapshot trend table ─────────────────
  // These use stable references so useAuditYearWindows doesn't loop. Note: we
  // don't pass benchmarkSetId because the snapshot's trend table only needs
  // live practice values; the 2019 benchmark column comes from the page-level
  // benchmark envelope already in scope.
  const stageFetcher = useCallback(
    (o: string | undefined, from: string, to: string) => fetchAuditCancerStage(o, from, to),
    [],
  );
  const intervalFetcher = useCallback(
    (o: string | undefined, from: string, to: string) => fetchAuditIntervals(o, from, to),
    [],
  );
  const referralFetcher = useCallback(
    (o: string | undefined, from: string, to: string) => fetchAuditReferrals(o, from, to),
    [],
  );
  const consultFetcher = useCallback(
    (o: string | undefined, from: string, to: string) => fetchAuditConsultations(o, from, to),
    [],
  );
  const snFetcher = useCallback(
    (o: string | undefined, from: string, to: string) => fetchAuditSafetyNetting(o, from, to),
    [],
  );
  const adFetcher = useCallback(
    (o: string | undefined, from: string, to: string) => fetchAuditAvoidableDelays(o, from, to),
    [],
  );
  const coFetcher = useCallback(
    (o: string | undefined, from: string, to: string) => fetchAuditCareObstructions(o, from, to),
    [],
  );
  const placeFetcher = useCallback(
    (o: string | undefined, from: string, to: string) => fetchAuditPlaceOfPresentation(o, from, to),
    [],
  );
  // fetchAuditSummary returns AuditSummary directly (not AuditSectionResult),
  // so wrap it in the multi-scope envelope shape that useAuditYearWindows expects.
  const summaryFetcher = useCallback(
    async (o: string | undefined, from: string, to: string) => {
      const data = await fetchAuditSummary(o, from, to);
      return { scopes: { practice: data as AuditSummary }, benchmark: undefined } as {
        scopes: { practice: AuditSummary };
        benchmark: undefined;
      };
    },
    [],
  );

  const { liveYears: stageYears }    = useAuditYearWindows(stageFetcher,    { orgId });
  const { liveYears: intervalYears } = useAuditYearWindows(intervalFetcher, { orgId });
  const { liveYears: referralYears } = useAuditYearWindows(referralFetcher, { orgId });
  const { liveYears: consultYears }  = useAuditYearWindows(consultFetcher,  { orgId });
  const { liveYears: snYears }       = useAuditYearWindows(snFetcher,       { orgId });
  const { liveYears: adYears }       = useAuditYearWindows(adFetcher,       { orgId });
  const { liveYears: coYears }       = useAuditYearWindows(coFetcher,       { orgId });
  const { liveYears: placeYears }    = useAuditYearWindows(placeFetcher,    { orgId });
  const { liveYears: summaryYears }  = useAuditYearWindows(summaryFetcher,  { orgId });

  const yearSummary = useMemo((): YearSummaryPoint[] => {
    return stageYears.map((sy, idx) => {
      const iy   = intervalYears[idx];
      const cy   = consultYears[idx];
      const sny  = snYears[idx];
      const ady  = adYears[idx];
      const coy  = coYears[idx];
      const py   = placeYears[idx];
      const sy2  = summaryYears[idx];

      const stageData   = sy.data;
      const intData     = iy?.data;
      const consultData = cy?.data;
      const snData      = sny?.data;
      const adData      = ady?.data;
      const coData      = coy?.data;
      const placeData   = py?.data;
      const sumData     = sy2?.data as AuditSummary | null;

      const earlyRow = stageData?.rows?.find((r) => r.stage_group === "early");

      // Fast-track rate excludes diagnoses presented through screening.
      const c1a = sumData?.cohort_1a_n ?? null;
      const c3  = sumData?.cohort_3_n  ?? null;
      const confirmed = c1a != null && c3 != null ? c1a + c3 : null;
      const twwPct = sumData?.confirmed_cancers_via_2ww_excluding_screening_pct ?? null;

      // Emergency rate = (Cohort 3 − Screening) / (1A + 3) × 100
      const screeningRow = Array.isArray(placeData)
        ? placeData.find((r) => r.place?.toLowerCase().includes("screening"))
        : undefined;
      const screeningN   = screeningRow?.n ?? 0;
      const emergencyN   = c3 != null ? Math.max(0, c3 - screeningN) : null;
      const emergencyPct = confirmed != null && confirmed > 0 && emergencyN != null
        ? Math.round((emergencyN / confirmed) * 1000) / 10
        : null;
      const safetyNettingPct = snData != null && snData.total_episodes > 0
        ? snData.recorded_pct
        : null;
      const careObstructionPct = coData != null && coData.total_episodes > 0
        ? coData.recorded_pct
        : null;

      return {
        year: sy.year,
        earlyStage:         earlyRow?.pct ?? null,
        pciMedian:          intData?.pci?.median ?? null,
        diMedian:           intData?.di?.median ?? null,
        twwPct,
        emergencyPct,
        fewerThan3Pct:      consultData?.fewer_than_3_pct ?? null,
        safetyNettingPct,
        avoidableDelayPct:  adData?.avoidable_delay_pct ?? null,
        careObstructionPct,
      };
    });
  }, [stageYears, intervalYears, consultYears, snYears, adYears, coYears, placeYears, summaryYears]);

  const load = useCallback(
    async (from: string | undefined, to: string | undefined) => {
      // Bail out if the benchmark set lookup hasn't resolved yet. When it does,
      // benchmarkSetId changes from null → a real value, which recreates this
      // callback and triggers the useEffect below to call load() again.
      if (benchmarkSetId === null) return;

      setLoading(allTrue());
      setErrors({});

      const settle = <T,>(
        key: keyof SectionLoading,
        promise: Promise<T>,
        setter: (v: T) => void,
      ) =>
        promise
          .then((v) => {
            setter(v);
          })
          .catch(() => {
            setErrors((e) => ({ ...e, [key]: `Unable to load ${key} data.` }));
          });

      await Promise.all([
        settle("summary", fetchAuditSummary(orgId, from, to), setSummary),
        settle("cancerType", fetchAuditCancerType(orgId, from, to, effectiveBenchmarkSetId), setCancerType),
        settle("cancerStage", fetchAuditCancerStage(orgId, from, to, effectiveBenchmarkSetId), setCancerStage),
        settle("demographics", fetchAuditDemographics(orgId, from, to, effectiveBenchmarkSetId), setDemographics),
        settle("comorbidities", fetchAuditComorbidities(orgId, from, to, effectiveBenchmarkSetId), setComorbidities),
        settle("placeOfPresentation", fetchAuditPlaceOfPresentation(orgId, from, to, effectiveBenchmarkSetId), setPlaceOfPresentation),
        settle("consultations", fetchAuditConsultations(orgId, from, to, effectiveBenchmarkSetId), setConsultations),
        settle("investigations", fetchAuditInvestigations(orgId, from, to, effectiveBenchmarkSetId), setInvestigations),
        settle("referrals", fetchAuditReferrals(orgId, from, to, effectiveBenchmarkSetId), setReferrals),
        settle("intervals", fetchAuditIntervals(orgId, from, to, effectiveBenchmarkSetId), setIntervals),
        settle("safetyNetting", fetchAuditSafetyNetting(orgId, from, to, effectiveBenchmarkSetId), setSafetyNetting),
        settle("careObstructions", fetchAuditCareObstructions(orgId, from, to, effectiveBenchmarkSetId), setCareObstructions),
        settle("priorConsultations", fetchAuditPriorConsultations(orgId, from, to, effectiveBenchmarkSetId), setPriorConsultations),
        settle("avoidableDelays", fetchAuditAvoidableDelays(orgId, from, to, effectiveBenchmarkSetId), setAvoidableDelays),
      ]);
      setLoading(allFalse());
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [orgId, effectiveBenchmarkSetId, benchmarkSetId],
  );

  useEffect(() => {
    load(effectiveFrom, effectiveTo);
  }, [load, effectiveFrom, effectiveTo]);

  const anyLoading = Object.values(loading).some(Boolean);

  return (
    <AuditBenchmarkOverlayProvider>
    <Box sx={{ p: { xs: 2, sm: 3 }, overflowX: "clip" }}>
      {/* ── Page header ──────────────────────────────────────────────── */}
      <Box sx={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", flexWrap: "wrap", gap: 1, mb: 2 }}>
        <Box>
          <Typography variant="h5" component="h1" sx={{ fontWeight: 700 }}>
            Clinical Audit
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ fontSize: "0.82rem", mt: 0.25 }}>
            National Cancer Diagnosis Audit (NCDA) -- 14 sections, year-on-year evolution against the 2019 NCDA benchmark.
            <br />
            Cohort window: {cohortWindowLabel}.
          </Typography>
        </Box>
        <Stack direction="row" spacing={1} alignItems="center">
          <Tooltip title="How to use this report">
            <IconButton size="small" aria-label="Help">
              <InfoOutlinedIcon fontSize="small" />
            </IconButton>
          </Tooltip>
          <Tooltip title="Print / export to PDF">
            <IconButton size="small" onClick={() => window.print()} aria-label="Print report">
              <PrintOutlinedIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        </Stack>
      </Box>

      {/* Comparison mode context banner */}
      {!orgSelected && (
        <Alert severity="info" sx={{ mb: 2, fontSize: "0.82rem" }}>
          <strong>All Organisations view:</strong> Showing England-wide live data.
          {" "}Select an organisation in the sidebar to compare your practice
          against the 2019 NCDA benchmark year-on-year.
        </Alert>
      )}

      {Object.values(errors).some(Boolean) && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          Some sections could not be loaded. Errors are shown in each section below.
        </Alert>
      )}

      {/* ── View tabs — Snapshot first ──────────────────────────────── */}
      <Tabs
        value={activeTab}
        onChange={(_, v) => setActiveTab(v)}
        sx={{ mb: 2, borderBottom: 1, borderColor: "divider" }}
        aria-label="Audit views"
      >
        <Tab
          label="Insight Snapshot"
          icon={<DashboardOutlinedIcon fontSize="small" />}
          iconPosition="start"
          sx={{ textTransform: "none", fontWeight: 600, minHeight: 44 }}
          aria-controls="audit-tabpanel-snapshot"
          id="audit-tab-snapshot"
        />
        <Tab
          label="Full Report"
          icon={<AssessmentOutlinedIcon fontSize="small" />}
          iconPosition="start"
          sx={{ textTransform: "none", fontWeight: 600, minHeight: 44 }}
          aria-controls="audit-tabpanel-report"
          id="audit-tab-report"
        />
      </Tabs>

      {/* ── Snapshot view (tab 0) ────────────────────────────────────── */}
      {activeTab === 0 && (
        <Box role="tabpanel" id="audit-tabpanel-snapshot" aria-labelledby="audit-tab-snapshot">
          <AuditSnapshotView
            orgSelected={orgSelected}
            loading={anyLoading}
            summary={summary}
            cancerType={cancerType}
            cancerStage={cancerStage}
            demographics={demographics}
            placeOfPresentation={placeOfPresentation}
            consultations={consultations}
            investigations={investigations}
            referrals={referrals}
            intervals={intervals}
            safetyNetting={safetyNetting}
            avoidableDelays={avoidableDelays}
            careObstructions={careObstructions}
            onViewInReport={handleViewInReport}
            cohortWindowLabel={isFiltered ? undefined : cohortWindowLabel}
            yearSummary={isFiltered ? undefined : yearSummary}
          />
        </Box>
      )}

      {/* ── Report shell with TOC sidebar (tab 1) ───────────────────── */}
      {activeTab === 1 && (
      <Box role="tabpanel" id="audit-tabpanel-report" aria-labelledby="audit-tab-report">
      <AuditReportShell
        sections={TOC_SECTIONS}
        pendingScrollSectionId={pendingReportScrollSectionId}
        pendingScrollReady={!anyLoading}
        onPendingScrollHandled={() => setPendingReportScrollSectionId(null)}
      >
        <AuditSummarySection
          summary={summary}
          loading={loading.summary}
          error={errors.summary}
          totalCases={summary?.total_episodes}
          auditPeriod={
            isFiltered
              ? `${appliedFrom ?? "Any date"} to ${appliedTo ?? "present"}`
              : cohortWindowLabel
          }
          orgSelected={orgSelected}
        />

        <CancerTypeEvolutionSection
          result={cancerType}
          loading={loading.cancerType}
          error={errors.cancerType}
          orgSelected={orgSelected}
        />

        <CancerStageEvolutionSection
          result={cancerStage}
          loading={loading.cancerStage}
          error={errors.cancerStage}
          orgSelected={orgSelected}
        />

        <DemographicsEvolutionSection
          result={demographics}
          loading={loading.demographics}
          error={errors.demographics}
          orgSelected={orgSelected}
        />

        <ComorbiditiesSection
          result={comorbidities}
          loading={loading.comorbidities}
          error={errors.comorbidities}
          orgSelected={orgSelected}
          dateFrom={effectiveFrom}
          dateTo={effectiveTo}
        />

        <SymptomsSection
          orgId={orgId ?? undefined}
          dateFrom={effectiveFrom}
          dateTo={effectiveTo}
        />

        <PlaceOfPresentationSection
          result={placeOfPresentation}
          loading={loading.placeOfPresentation}
          error={errors.placeOfPresentation}
          orgSelected={orgSelected}
        />

        <ConsultationsSection
          result={consultations}
          loading={loading.consultations}
          error={errors.consultations}
          orgSelected={orgSelected}
        />

        <MultipleConsultationsSection
          result={consultations}
          orgSelected={orgSelected}
        />

        <InvestigationsSection
          result={investigations}
          loading={loading.investigations}
          error={errors.investigations}
          orgSelected={orgSelected}
        />

        <FastTrackReferralEvolutionSection
          result={null}
          loading={false}
          orgSelected={orgSelected}
        />

        <EmergencyReferralRoutesSection
          result={referrals}
          orgSelected={orgSelected}
        />

        <PrimaryCareIntervalSection
          result={intervals}
          loading={loading.intervals}
          error={errors.intervals}
          orgSelected={orgSelected}
        />

        <DiagnosticIntervalSection
          result={intervals}
          loading={loading.intervals}
          error={errors.intervals}
          orgSelected={orgSelected}
        />

        <SafetyNettingSection
          result={safetyNetting}
          loading={loading.safetyNetting}
          error={errors.safetyNetting}
          orgSelected={orgSelected}
        />

        <CareObstructionsSection
          result={careObstructions}
          loading={loading.careObstructions}
          error={errors.careObstructions}
          orgSelected={orgSelected}
          avoidableDelaysResult={avoidableDelays}
        />

        <PriorConsultationsSection
          result={priorConsultations}
          loading={loading.priorConsultations}
          error={errors.priorConsultations}
          orgSelected={orgSelected}
        />
      </AuditReportShell>
      </Box>
      )}
    </Box>
    </AuditBenchmarkOverlayProvider>
  );
}
