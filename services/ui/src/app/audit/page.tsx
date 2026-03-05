"use client";

import { useCallback, useEffect, useState } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import TextField from "@mui/material/TextField";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Alert from "@mui/material/Alert";
import Tooltip from "@mui/material/Tooltip";
import IconButton from "@mui/material/IconButton";
import PrintOutlinedIcon from "@mui/icons-material/PrintOutlined";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";

import { useOrgId } from "@/context/OrgContext";
import {
  fetchAuditSummary,
  fetchAuditCancerType,
  fetchAuditCancerStage,
  fetchAuditDemographics,
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
  type AuditPlaceRow,
  type AuditConsultations,
  type AuditInvestigations,
  type AuditReferralRow,
  type AuditIntervals,
  type AuditSafetyNetting,
  type AuditAvoidableDelays,
} from "@/lib/analyticsApi";

import AuditReportShell, { type TocSection } from "@/components/audit/AuditReportShell";
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
  summary: true,
  cancerType: true,
  cancerStage: true,
  demographics: true,
  placeOfPresentation: true,
  consultations: true,
  investigations: true,
  referrals: true,
  intervals: true,
  safetyNetting: true,
  avoidableDelays: true,
});

const allFalse = (): SectionLoading => ({
  summary: false,
  cancerType: false,
  cancerStage: false,
  demographics: false,
  placeOfPresentation: false,
  consultations: false,
  investigations: false,
  referrals: false,
  intervals: false,
  safetyNetting: false,
  avoidableDelays: false,
});

export default function AuditPage() {
  const orgId = useOrgId();

  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [appliedFrom, setAppliedFrom] = useState<string | undefined>(undefined);
  const [appliedTo, setAppliedTo] = useState<string | undefined>(undefined);
  const isFiltered = !!appliedFrom || !!appliedTo;

  const [loading, setLoading] = useState<SectionLoading>(allTrue());
  const [errors, setErrors] = useState<SectionErrors>({});

  const [summary, setSummary] = useState<AuditSummary | null>(null);
  const [cancerType, setCancerType] = useState<AuditCancerTypeRow[]>([]);
  const [cancerStage, setCancerStage] = useState<AuditCancerStageRow[]>([]);
  const [demographics, setDemographics] = useState<AuditDemographics | null>(null);
  const [placeOfPresentation, setPlaceOfPresentation] = useState<AuditPlaceRow[]>([]);
  const [consultations, setConsultations] = useState<AuditConsultations | null>(null);
  const [investigations, setInvestigations] = useState<AuditInvestigations | null>(null);
  const [referrals, setReferrals] = useState<AuditReferralRow[]>([]);
  const [intervals, setIntervals] = useState<AuditIntervals | null>(null);
  const [safetyNetting, setSafetyNetting] = useState<AuditSafetyNetting | null>(null);
  const [avoidableDelays, setAvoidableDelays] = useState<AuditAvoidableDelays | null>(null);

  const load = useCallback(
    async (from: string | undefined, to: string | undefined) => {
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
        settle("cancerType", fetchAuditCancerType(orgId, from, to), setCancerType),
        settle("cancerStage", fetchAuditCancerStage(orgId, from, to), setCancerStage),
        settle("demographics", fetchAuditDemographics(orgId, from, to), setDemographics),
        settle("placeOfPresentation", fetchAuditPlaceOfPresentation(orgId, from, to), setPlaceOfPresentation),
        settle("consultations", fetchAuditConsultations(orgId, from, to), setConsultations),
        settle("investigations", fetchAuditInvestigations(orgId, from, to), setInvestigations),
        settle("referrals", fetchAuditReferrals(orgId, from, to), setReferrals),
        settle("intervals", fetchAuditIntervals(orgId, from, to), setIntervals),
        settle("safetyNetting", fetchAuditSafetyNetting(orgId, from, to), setSafetyNetting),
        settle("avoidableDelays", fetchAuditAvoidableDelays(orgId, from, to), setAvoidableDelays),
      ]);
    },
    [orgId],
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
    <Box sx={{ p: { xs: 2, sm: 3 }, overflowX: "hidden" }}>
      {/* ── Page header ─────────────────────────────────────────────── */}
      <Box sx={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", flexWrap: "wrap", gap: 1, mb: 2 }}>
        <Box>
          <Typography variant="h5" component="h1" sx={{ fontWeight: 700 }}>
            Clinical Audit
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ fontSize: "0.82rem", mt: 0.25 }}>
            National Cancer Diagnosis Audit (NCDA) — all 14 sections with multi-level benchmarking
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

      {/* ── Filter bar ──────────────────────────────────────────────── */}
      <Box
        component="section"
        aria-label="Filter by date"
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
      </Box>

      {Object.values(errors).some(Boolean) && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          Some sections could not be loaded. Errors are shown in each section below.
        </Alert>
      )}

      {/* ── Report shell with TOC sidebar ───────────────────────────── */}
      <AuditReportShell sections={TOC_SECTIONS}>
        <AuditSummarySection
          summary={summary}
          loading={loading.summary}
          error={errors.summary}
          totalCases={summary?.total_episodes}
          auditPeriod={isFiltered ? `${appliedFrom ?? "Any date"} to ${appliedTo ?? "today"}` : undefined}
        />

        <CancerTypeSection
          data={cancerType}
          loading={loading.cancerType}
          error={errors.cancerType}
        />

        <CancerStageSection
          data={cancerStage}
          loading={loading.cancerStage}
          error={errors.cancerStage}
        />

        <DemographicsSection
          data={demographics}
          loading={loading.demographics}
          error={errors.demographics}
        />

        <PlaceOfPresentationSection
          data={placeOfPresentation}
          loading={loading.placeOfPresentation}
          error={errors.placeOfPresentation}
        />

        <ConsultationsSection
          data={consultations}
          loading={loading.consultations}
          error={errors.consultations}
        />

        <MultipleConsultationsSection />

        <InvestigationsSection
          data={investigations}
          loading={loading.investigations}
          error={errors.investigations}
        />

        <ReferralsSection
          data={referrals}
          loading={loading.referrals}
          error={errors.referrals}
        />

        <EmergencyReferralRoutesSection />

        <PrimaryCareIntervalSection
          data={intervals}
          loading={loading.intervals}
          error={errors.intervals}
        />

        <DiagnosticIntervalSection
          data={intervals}
          loading={loading.intervals}
          error={errors.intervals}
        />

        <SafetyNettingSection
          data={safetyNetting}
          loading={loading.safetyNetting}
          error={errors.safetyNetting}
        />

        <AvoidableDelaysSection
          data={avoidableDelays}
          loading={loading.avoidableDelays}
          error={errors.avoidableDelays}
        />
      </AuditReportShell>
    </Box>
  );
}
