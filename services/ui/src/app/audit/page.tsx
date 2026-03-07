"use client";

import { useCallback, useEffect, useState } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import TextField from "@mui/material/TextField";
import MenuItem from "@mui/material/MenuItem";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Alert from "@mui/material/Alert";
import Tooltip from "@mui/material/Tooltip";
import IconButton from "@mui/material/IconButton";
import Tabs from "@mui/material/Tabs";
import Tab from "@mui/material/Tab";
import PrintOutlinedIcon from "@mui/icons-material/PrintOutlined";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import CompareArrowsIcon from "@mui/icons-material/CompareArrows";
import AssessmentOutlinedIcon from "@mui/icons-material/AssessmentOutlined";
import DashboardOutlinedIcon from "@mui/icons-material/DashboardOutlined";

import { useOrgId } from "@/context/OrgContext";
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
  fetchAuditAvoidableDelays,
  type AuditSummary,
  type AuditCancerTypeRow,
  type AuditCancerStageRow,
  type AuditDemographics,
  type AuditComorbidities,
  type AuditPlaceRow,
  type AuditConsultations,
  type AuditInvestigations,
  type AuditReferralRow,
  type AuditIntervals,
  type AuditSafetyNetting,
  type AuditAvoidableDelays,
  type AuditSectionResult,
  type BenchmarkSetSummary,
} from "@/lib/analyticsApi";

import AuditReportShell, { type TocSection } from "@/components/audit/AuditReportShell";
import AuditSnapshotView from "@/components/audit/AuditSnapshotView";
import AuditSummarySection from "@/components/audit/AuditSummarySection";
import CancerTypeSection from "@/components/audit/CancerTypeSection";
import CancerStageSection from "@/components/audit/CancerStageSection";
import DemographicsSection from "@/components/audit/DemographicsSection";
import PlaceOfPresentationSection from "@/components/audit/PlaceOfPresentationSection";
import ConsultationsSection from "@/components/audit/ConsultationsSection";
import MultipleConsultationsSection from "@/components/audit/MultipleConsultationsSection";
import InvestigationsSection from "@/components/audit/InvestigationsSection";
import ReferralsSection from "@/components/audit/ReferralsSection";
import EmergencyReferralRoutesSection from "@/components/audit/EmergencyReferralRoutesSection";
import PrimaryCareIntervalSection from "@/components/audit/PrimaryCareIntervalSection";
import DiagnosticIntervalSection from "@/components/audit/DiagnosticIntervalSection";
import SafetyNettingSection from "@/components/audit/SafetyNettingSection";
import AvoidableDelaysSection from "@/components/audit/AvoidableDelaysSection";

const TOC_SECTIONS: TocSection[] = [
  { id: "section-summary", label: "Summary", group: "overview" },
  { id: "section-cancer-type", label: "Cancer Type", group: "results" },
  { id: "section-cancer-stage", label: "Cancer Stage", group: "results" },
  { id: "section-demographics", label: "Demographics", group: "results" },
  { id: "section-place-of-presentation", label: "Place of Presentation", group: "results" },
  { id: "section-consultations", label: "Consultations", group: "results" },
  { id: "section-multiple-consultations", label: "Multiple Consultations", group: "results" },
  { id: "section-investigations", label: "Investigations", group: "results" },
  { id: "section-referrals", label: "Referrals", group: "results" },
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
  avoidableDelays: boolean;
}

interface SectionErrors {
  [key: string]: string | null;
}

const allTrue = (): SectionLoading => ({
  summary: true, cancerType: true, cancerStage: true, demographics: true, comorbidities: true,
  placeOfPresentation: true, consultations: true, investigations: true,
  referrals: true, intervals: true, safetyNetting: true, avoidableDelays: true,
});

const allFalse = (): SectionLoading => ({
  summary: false, cancerType: false, cancerStage: false, demographics: false, comorbidities: false,
  placeOfPresentation: false, consultations: false, investigations: false,
  referrals: false, intervals: false, safetyNetting: false, avoidableDelays: false,
});

export default function AuditPage() {
  const orgId = useOrgId();
  const orgSelected = !!orgId;

  // 0 = Report (View 1), 1 = Snapshot (View 2)
  const [activeTab, setActiveTab] = useState(0);

  const handleViewInReport = (sectionId: string) => {
    setActiveTab(1); // Report is now tab index 1
    setTimeout(() => {
      const el = document.getElementById(sectionId);
      if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 100);
  };

  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [appliedFrom, setAppliedFrom] = useState<string | undefined>(undefined);
  const [appliedTo, setAppliedTo] = useState<string | undefined>(undefined);
  const isFiltered = !!appliedFrom || !!appliedTo;

  // Benchmark set selection.
  // null = lookup still in-flight; "none" = loaded but no benchmark selected; else = set id.
  // Using null as the "pending" sentinel lets load() guard itself without adding a
  // new dependency to the useEffect array (which would violate the rules-of-hooks
  // constant-size requirement).
  const [benchmarkSets, setBenchmarkSets] = useState<BenchmarkSetSummary[]>([]);
  const [benchmarkSetId, setBenchmarkSetId] = useState<string | null>(null);

  // Section loading / error state
  const [loading, setLoading] = useState<SectionLoading>(allTrue());
  const [errors, setErrors] = useState<SectionErrors>({});

  // Section data — all wrapped in AuditSectionResult
  const [summary, setSummary] = useState<AuditSummary | null>(null);
  const [cancerType, setCancerType] = useState<AuditSectionResult<AuditCancerTypeRow[]> | null>(null);
  const [cancerStage, setCancerStage] = useState<AuditSectionResult<AuditCancerStageRow[]> | null>(null);
  const [demographics, setDemographics] = useState<AuditSectionResult<AuditDemographics> | null>(null);
  const [comorbidities, setComorbidities] = useState<AuditSectionResult<AuditComorbidities> | null>(null);
  const [placeOfPresentation, setPlaceOfPresentation] = useState<AuditSectionResult<AuditPlaceRow[]> | null>(null);
  const [consultations, setConsultations] = useState<AuditSectionResult<AuditConsultations> | null>(null);
  const [investigations, setInvestigations] = useState<AuditSectionResult<AuditInvestigations> | null>(null);
  const [referrals, setReferrals] = useState<AuditSectionResult<AuditReferralRow[]> | null>(null);
  const [intervals, setIntervals] = useState<AuditSectionResult<AuditIntervals> | null>(null);
  const [safetyNetting, setSafetyNetting] = useState<AuditSectionResult<AuditSafetyNetting> | null>(null);
  const [avoidableDelays, setAvoidableDelays] = useState<AuditSectionResult<AuditAvoidableDelays> | null>(null);

  // Fetch available benchmark sets on mount.
  // Both .then() and .catch() set benchmarkSetId away from null, which recreates
  // the load callback and unblocks the main data fetch — no separate gate state needed.
  useEffect(() => {
    fetchBenchmarkSets()
      .then((sets) => {
        setBenchmarkSets(sets);
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
          .then((v) => setter(v))
          .catch(() => setErrors((e) => ({ ...e, [key]: `Unable to load ${key} data.` })))
          .finally(() => setLoading((l) => ({ ...l, [key]: false })));

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
        settle("avoidableDelays", fetchAuditAvoidableDelays(orgId, from, to, effectiveBenchmarkSetId), setAvoidableDelays),
      ]);
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [orgId, effectiveBenchmarkSetId, benchmarkSetId],
  );

  useEffect(() => {
    load(appliedFrom, appliedTo);
  }, [load, appliedFrom, appliedTo]);

  const handleApply = () => {
    setAppliedFrom(dateFrom || undefined);
    setAppliedTo(dateTo || undefined);
  };
  const handleClear = () => {
    setDateFrom("");
    setDateTo("");
    setAppliedFrom(undefined);
    setAppliedTo(undefined);
  };

  const anyLoading = Object.values(loading).some(Boolean);

  return (
    <Box sx={{ p: { xs: 2, sm: 3 }, overflowX: "clip" }}>
      {/* ── Page header ──────────────────────────────────────────────── */}
      <Box sx={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", flexWrap: "wrap", gap: 1, mb: 2 }}>
        <Box>
          <Typography variant="h5" component="h1" sx={{ fontWeight: 700 }}>
            Clinical Audit
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ fontSize: "0.82rem", mt: 0.25 }}>
            National Cancer Diagnosis Audit (NCDA) — 14 sections with multi-level live benchmarking
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

      {/* ── Filter + benchmark bar ───────────────────────────────────── */}
      <Box
        component="section"
        aria-label="Audit filters"
        sx={{
          display: "flex",
          flexWrap: "wrap",
          alignItems: "center",
          gap: 1.5,
          mb: 3,
          px: 2,
          py: 1.5,
          borderRadius: 2,
          bgcolor: "grey.50",
          border: "1px solid",
          borderColor: "divider",
        }}
      >
        <Typography variant="body2" sx={{ fontWeight: 600, color: "text.secondary", mr: 0.5 }}>
          Audit period:
        </Typography>
        <TextField
          label="From"
          type="date"
          size="small"
          value={dateFrom}
          onChange={(e) => setDateFrom(e.target.value)}
          inputProps={{ "aria-label": "Filter from date" }}
          InputLabelProps={{ shrink: true }}
          sx={{ width: 160 }}
        />
        <TextField
          label="To"
          type="date"
          size="small"
          value={dateTo}
          onChange={(e) => setDateTo(e.target.value)}
          inputProps={{ "aria-label": "Filter to date" }}
          InputLabelProps={{ shrink: true }}
          sx={{ width: 160 }}
        />
        <Button
          variant="contained"
          size="small"
          onClick={handleApply}
          disabled={anyLoading}
          sx={{ textTransform: "none", px: 2.5, fontWeight: 600 }}
        >
          Apply
        </Button>
        {isFiltered && (
          <Button variant="outlined" size="small" onClick={handleClear} sx={{ textTransform: "none" }}>
            Clear
          </Button>
        )}
        {isFiltered && (
          <Chip
            label={`${appliedFrom ?? "Any date"} to ${appliedTo ?? "today"}`}
            size="small"
            color="primary"
            variant="outlined"
          />
        )}

        {/* Benchmark set selector */}
        <Box sx={{ ml: "auto", display: "flex", alignItems: "center", gap: 1 }}>
          <CompareArrowsIcon fontSize="small" sx={{ color: "text.secondary" }} />
          <TextField
            select
            label="Benchmark"
            size="small"
            value={benchmarkSetId ?? "none"}
            onChange={(e) => setBenchmarkSetId(e.target.value)}
            sx={{ width: 200 }}
            inputProps={{ "aria-label": "Select benchmark set for comparison" }}
          >
            <MenuItem value="none">
              <em>No benchmark overlay</em>
            </MenuItem>
            {benchmarkSets.map((s) => (
              <MenuItem key={s.id} value={s.id}>
                {s.name}{s.audit_year ? ` (${s.audit_year})` : ""}
              </MenuItem>
            ))}
          </TextField>
        </Box>
      </Box>

      {/* Comparison mode context banner */}
      {!orgSelected && (
        <Alert severity="info" sx={{ mb: 2, fontSize: "0.82rem" }}>
          <strong>All Organisations view:</strong> Showing England-wide live data.
          {effectiveBenchmarkSetId
            ? " Select an organisation in the sidebar to compare practice vs alliance vs England."
            : " Select an organisation to enable multi-level comparisons, or choose a benchmark set above."}
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
            onViewInReport={handleViewInReport}
          />
        </Box>
      )}

      {/* ── Report shell with TOC sidebar (tab 1) ───────────────────── */}
      {activeTab === 1 && (
      <Box role="tabpanel" id="audit-tabpanel-report" aria-labelledby="audit-tab-report">
      <AuditReportShell sections={TOC_SECTIONS}>
        <AuditSummarySection
          summary={summary}
          loading={loading.summary}
          error={errors.summary}
          totalCases={summary?.total_episodes}
          auditPeriod={isFiltered ? `${appliedFrom ?? "Any date"} to ${appliedTo ?? "today"}` : undefined}
        />

        <CancerTypeSection
          result={cancerType}
          loading={loading.cancerType}
          error={errors.cancerType}
          orgSelected={orgSelected}
        />

        <CancerStageSection
          result={cancerStage}
          loading={loading.cancerStage}
          error={errors.cancerStage}
          orgSelected={orgSelected}
        />

        <DemographicsSection
          result={demographics}
          comorbidities={comorbidities}
          loading={loading.demographics || loading.comorbidities}
          error={errors.demographics}
          orgSelected={orgSelected}
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

        <ReferralsSection
          result={referrals}
          loading={loading.referrals}
          error={errors.referrals}
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

        <AvoidableDelaysSection
          result={avoidableDelays}
          loading={loading.avoidableDelays}
          error={errors.avoidableDelays}
          orgSelected={orgSelected}
        />
      </AuditReportShell>
      </Box>
      )}
    </Box>
  );
}
