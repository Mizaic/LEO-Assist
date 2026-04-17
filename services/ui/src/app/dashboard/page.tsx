"use client";

import { useEffect, useState, useCallback } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Grid from "@mui/material/Grid";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Skeleton from "@mui/material/Skeleton";
import Alert from "@mui/material/Alert";
import Chip from "@mui/material/Chip";
import TextField from "@mui/material/TextField";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import {
  fetchAuditSummary,
  fetchEpisodeSummary,
  fetchDiagnosedSummary,
  fetchKPIBenchmarks,
  fetchSafetyNetAlerts,
  actionSafetyNetAlert,
} from "@/lib/analyticsApi";
import { useOrgId } from "@/context/OrgContext";
import { useAnalyticsDateFilter } from "@/context/AnalyticsDateFilterContext";
import { TAX_YEAR_PRESETS } from "@/lib/taxYearPresets";
import KPICards from "@/components/dashboard/KPICards";
import EpisodesByTypeChart from "@/components/dashboard/EpisodesByTypeChart";
import DiagnosedByTypeChart from "@/components/dashboard/DiagnosedByTypeChart";
import SafetyNetAlertsSummary from "@/components/dashboard/SafetyNetAlertsSummary";
import LLMSpendPanel from "@/components/dashboard/LLMSpendPanel";
import PageIntro from "@/components/ui/PageIntro";

// Plain-language intro copy. Every string must read at Flesch-Kincaid
// grade <=9 (DI-LEO-AI-128, verified in VT-LEO-AI-123).
export const CARE_OVERVIEW_INTRO = {
  why: "Care Overview is where you track cancer referrals and find cases that need help.",
  how: "Pick a date at the top. The cards show new referrals, open cases, and new cancer diagnoses.",
  what: "Scroll down for charts, waiting times, and safety alerts. Open an alert to help the patient.",
} as const;

// Sentence-case summary card labels. Kept short so they read as labels,
// not shouty tracked text.
export const CARE_OVERVIEW_SUMMARY_LABELS = {
  referrals: "Cancer referrals",
  active: "Active cases",
  confirmed: "Confirmed cancers",
  alerts: "Safety alerts",
} as const;

// Plain-language chart descriptions. All must read at Flesch-Kincaid
// grade <=9 (VT-LEO-AI-123 TC-004).
export const CARE_OVERVIEW_CHART_COPY = {
  referrals: {
    title: "Referrals by cancer type",
    description: "How many people were referred, grouped by the suspected cancer type.",
  },
  diagnosed: {
    title: "Confirmed cancers by type",
    description: "People whose cancer has been confirmed, grouped by type.",
  },
  kpis: {
    title: "Average waiting times",
    description: "Average days between stages of the cancer pathway.",
  },
  alerts: {
    title: "Recent safety alerts",
    description: "Patients who may need a follow up check.",
  },
} as const;

export default function DashboardPage() {
  const orgId = useOrgId();
  const {
    dateFrom,
    dateTo,
    appliedFrom,
    appliedTo,
    setDateFrom,
    setDateTo,
    apply,
    applyPreset,
    clear,
    isFiltered,
  } = useAnalyticsDateFilter();

  const [episodes, setEpisodes] = useState<Array<{ condition_type: string; status: string; count: number }>>([]);
  const [diagnosed, setDiagnosed] = useState<Array<{ cancer_type: string; count: number }>>([]);
  const [summary, setSummary] = useState<{
    total_episodes: number;
    active_episodes: number;
    confirmed_cancers: number;
  } | null>(null);
  const [kpis, setKpis] = useState<any>(null);
  const [alerts, setAlerts] = useState<Array<any>>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sectionErrors, setSectionErrors] = useState<Record<string, string>>({});

  const load = useCallback(async (from: string | undefined, to: string | undefined) => {
    setLoading(true);
    setError(null);
    setSectionErrors({});
    // Clear previous data before loading to prevent stale sections mixing with fresh ones
    // when only some requests succeed on a re-fetch.
    setEpisodes([]);
    setDiagnosed([]);
    setSummary(null);
    setKpis(null);
    setAlerts([]);
    try {
      const [summaryResult, epResult, diagResult, kpiResult, alertResult] = await Promise.allSettled([
        fetchAuditSummary(orgId, from, to),
        fetchEpisodeSummary(orgId, from, to),
        fetchDiagnosedSummary(orgId, from, to),
        fetchKPIBenchmarks(orgId, from, to),
        fetchSafetyNetAlerts(orgId),
      ]);
      const errors: Record<string, string> = {};
      if (summaryResult.status === "fulfilled") {
        setSummary({
          total_episodes: summaryResult.value.total_episodes,
          active_episodes: summaryResult.value.active_episodes,
          confirmed_cancers: summaryResult.value.confirmed_cancers,
        });
      } else {
        errors.summary = "Unable to load summary metrics.";
      }
      if (epResult.status === "fulfilled") setEpisodes(epResult.value);
      else errors.episodes = "Unable to load referral data.";
      if (diagResult.status === "fulfilled") setDiagnosed(diagResult.value);
      else errors.diagnosed = "Unable to load cancer diagnosis data.";
      if (kpiResult.status === "fulfilled") setKpis(kpiResult.value?.[0] ?? null);
      else errors.kpis = "Unable to load waiting times.";
      if (alertResult.status === "fulfilled") setAlerts(alertResult.value);
      else errors.alerts = "Unable to load safety alerts.";
      if (Object.keys(errors).length > 0) setSectionErrors(errors);
    } catch (e: any) {
      setError(e.message ?? "Something went wrong loading the data.");
    } finally {
      setLoading(false);
    }
  }, [orgId]);

  useEffect(() => {
    load(appliedFrom, appliedTo);
  }, [load, appliedFrom, appliedTo]);

  const handleAlertAction = useCallback(async (alertId: string, actioned: boolean) => {
    try {
      await actionSafetyNetAlert(alertId, actioned);
      setAlerts((prev) => prev.map((a) => (a.id === alertId ? { ...a, actioned } : a)));
    } catch {
      setSectionErrors((prev) => ({
        ...prev,
        alerts: "Could not update the alert. Please try again.",
      }));
    }
  }, []);

  const totalEpisodes = summary?.total_episodes ?? 0;
  const activeEpisodes = summary?.active_episodes ?? 0;
  const totalDiagnosed = summary?.confirmed_cancers ?? 0;
  const criticalAlerts = alerts.filter((a) => a.severity === "critical" || a.severity === "high").length;

  return (
    <Box sx={{ p: { xs: 2, sm: 3 }, overflowX: "hidden" }}>

      {/* -- Page title ------------------------------------------------ */}
      <Typography variant="h5" component="h1" sx={{ mb: 2, fontWeight: 700 }}>
        Overview
      </Typography>

      {/* -- Plain-language intro (DI-LEO-AI-128) ---------------------- */}
      <PageIntro
        screenId="care-overview"
        why={CARE_OVERVIEW_INTRO.why}
        how={CARE_OVERVIEW_INTRO.how}
        what={CARE_OVERVIEW_INTRO.what}
        headingLevel={2}
      />

      {/* ── Date filter bar ─────────────────────────────────────────── */}
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
          Filter by referral date:
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
          onClick={apply}
          disabled={loading}
          aria-label="Apply date filter"
          sx={{ textTransform: "none", px: 2.5, fontWeight: 600 }}
        >
          Apply
        </Button>
        {isFiltered && (
          <Button
            variant="outlined"
            size="small"
            onClick={clear}
            aria-label="Clear date filter"
            sx={{ textTransform: "none" }}
          >
            Clear filter
          </Button>
        )}
        <Stack direction="row" spacing={0.75} alignItems="center" sx={{ ml: 0.5 }}>
          <Typography variant="caption" sx={{ color: "text.secondary", fontWeight: 600, whiteSpace: "nowrap" }}>
            Year:
          </Typography>
          {TAX_YEAR_PRESETS.map((preset) => (
            <Chip
              key={preset.label}
              label={preset.label}
              size="small"
              clickable
              disabled={loading}
              onClick={() => applyPreset(preset.from, preset.to)}
              color={appliedFrom === preset.from && appliedTo === preset.to ? "primary" : "default"}
              variant={appliedFrom === preset.from && appliedTo === preset.to ? "filled" : "outlined"}
              sx={{ fontWeight: 600, fontSize: "0.75rem" }}
            />
          ))}
        </Stack>
        {isFiltered && (
          <Chip
            label={`${appliedFrom ?? "Any date"} to ${appliedTo ?? "present"}`}
            size="small"
            color="primary"
            variant="outlined"
            aria-live="polite"
            aria-atomic="true"
          />
        )}
      </Box>

      {error && (
        <Alert role="alert" severity="error" sx={{ mb: 2 }}>
          Something went wrong loading the data. Please refresh and try again.
        </Alert>
      )}
      {Object.keys(sectionErrors).length > 0 && !error && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          Some data could not be loaded. Sections with errors are marked below.
        </Alert>
      )}

      {/* ── Summary cards ───────────────────────────────────────────── */}
      <Grid container spacing={2.5} sx={{ mb: 3 }} component="section" aria-label="Summary figures">
        <Grid size={{ xs: 12, sm: 6, md: 3 }}>
          <StatCard
            label={CARE_OVERVIEW_SUMMARY_LABELS.referrals}
            description="Total cancer referral pathways we have on record."
            value={loading ? undefined : totalEpisodes}
            color="#1D4ED8"
          />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, md: 3 }}>
          <StatCard
            label={CARE_OVERVIEW_SUMMARY_LABELS.active}
            description="Referrals still open and being tracked."
            value={loading ? undefined : activeEpisodes}
            color="#0D7C6F"
          />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, md: 3 }}>
          <StatCard
            label={CARE_OVERVIEW_SUMMARY_LABELS.confirmed}
            description="Referrals where cancer has been confirmed."
            value={loading ? undefined : totalDiagnosed}
            color="#15803D"
          />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, md: 3 }}>
          <StatCard
            label={CARE_OVERVIEW_SUMMARY_LABELS.alerts}
            description="Patients who may need a follow up check."
            value={loading ? undefined : alerts.length}
            color="#92400E"
            badge={criticalAlerts > 0 ? `${criticalAlerts} urgent` : undefined}
          />
        </Grid>
      </Grid>

      {/* ── Charts row 1 ────────────────────────────────────────────── */}
      <Grid container spacing={2.5} sx={{ mb: 2.5 }}>
        <Grid size={{ xs: 12, md: 6 }}>
          <Card>
            <CardContent>
              <Typography variant="h6" component="h2" sx={{ mb: 0.5, fontSize: "1rem", fontWeight: 700 }}>
                {CARE_OVERVIEW_CHART_COPY.referrals.title}
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2, fontSize: "0.8rem" }}>
                {CARE_OVERVIEW_CHART_COPY.referrals.description}
              </Typography>
              {loading ? (
                <Skeleton variant="rectangular" height={280} aria-label="Loading referrals chart" />
              ) : sectionErrors.episodes ? (
                <Alert severity="error">{sectionErrors.episodes}</Alert>
              ) : episodes.length === 0 ? (
                <Typography variant="body2" color="text.secondary" sx={{ py: 4, textAlign: "center" }}>
                  No referral data for the selected period.
                </Typography>
              ) : (
                <EpisodesByTypeChart data={episodes} />
              )}
            </CardContent>
          </Card>
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <Card>
            <CardContent>
              <Typography variant="h6" component="h2" sx={{ mb: 0.5, fontSize: "1rem", fontWeight: 700 }}>
                {CARE_OVERVIEW_CHART_COPY.diagnosed.title}
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2, fontSize: "0.8rem" }}>
                {CARE_OVERVIEW_CHART_COPY.diagnosed.description}
              </Typography>
              {loading ? (
                <Skeleton variant="rectangular" height={280} aria-label="Loading confirmed cancers chart" />
              ) : sectionErrors.diagnosed ? (
                <Alert severity="error">{sectionErrors.diagnosed}</Alert>
              ) : diagnosed.length === 0 ? (
                <Typography variant="body2" color="text.secondary" sx={{ py: 4, textAlign: "center" }}>
                  No confirmed cancer data for the selected period.
                </Typography>
              ) : (
                <DiagnosedByTypeChart data={diagnosed} />
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* ── Charts row 2 ────────────────────────────────────────────── */}
      <Grid container spacing={2.5}>
        <Grid size={{ xs: 12, md: 5 }}>
          <Card>
            <CardContent>
              <Typography variant="h6" component="h2" sx={{ mb: 0.5, fontSize: "1rem", fontWeight: 700 }}>
                {CARE_OVERVIEW_CHART_COPY.kpis.title}
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2, fontSize: "0.8rem" }}>
                {CARE_OVERVIEW_CHART_COPY.kpis.description}
              </Typography>
              {loading ? (
                <Skeleton variant="rectangular" height={240} aria-label="Loading waiting times" />
              ) : sectionErrors.kpis ? (
                <Alert severity="error">{sectionErrors.kpis}</Alert>
              ) : (
                <KPICards kpis={kpis} />
              )}
            </CardContent>
          </Card>
        </Grid>
        <Grid size={{ xs: 12, md: 7 }}>
          <Card>
            <CardContent>
              <Typography variant="h6" component="h2" sx={{ mb: 0.5, fontSize: "1rem", fontWeight: 700 }}>
                {CARE_OVERVIEW_CHART_COPY.alerts.title}
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2, fontSize: "0.8rem" }}>
                {CARE_OVERVIEW_CHART_COPY.alerts.description}
                {isFiltered && (
                  <> Shown regardless of the date filter above.</>
                )}
              </Typography>
              {loading ? (
                <Skeleton variant="rectangular" height={200} aria-label="Loading safety alerts" />
              ) : sectionErrors.alerts ? (
                <Alert severity="error">{sectionErrors.alerts}</Alert>
              ) : alerts.length === 0 ? (
                <Typography variant="body2" color="text.secondary" sx={{ py: 4, textAlign: "center" }}>
                  No open safety alerts.
                </Typography>
              ) : (
                <SafetyNetAlertsSummary alerts={alerts.slice(0, 8)} onAction={handleAlertAction} />
              )}
            </CardContent>
          </Card>
        </Grid>
        <Grid size={{ xs: 12 }}>
          <LLMSpendPanel orgId={orgId} from={appliedFrom} to={appliedTo} />
        </Grid>
      </Grid>
    </Box>
  );
}

function StatCard({
  label,
  description,
  value,
  color,
  badge,
}: {
  label: string;
  description: string;
  value: number | string | undefined;
  color: string;
  badge?: string;
}) {
  return (
    <Card
      component="article"
      aria-label={`${label}: ${value ?? "loading"}`}
      sx={{ height: "100%" }}
    >
      <CardContent sx={{ py: 2.5 }}>
        <Typography
          variant="body2"
          sx={{
            color: "text.secondary",
            mb: 0.25,
            fontSize: "0.8125rem",
            fontWeight: 600,
          }}
        >
          {label}
        </Typography>
        {value === undefined ? (
          <Skeleton width={80} height={36} aria-label="Loading" />
        ) : (
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, mt: 0.5 }}>
            <Typography
              variant="h4"
              aria-label={`${value} ${label.toLowerCase()}`}
              sx={{ color, fontSize: "2rem", fontWeight: 700, lineHeight: 1 }}
            >
              {value}
            </Typography>
            {badge && (
              <Chip
                label={badge}
                size="small"
                color="error"
                aria-label={badge}
                sx={{ fontWeight: 600 }}
              />
            )}
          </Box>
        )}
        <Typography variant="caption" color="text.secondary" sx={{ mt: 0.75, display: "block", fontSize: "0.75rem" }}>
          {description}
        </Typography>
      </CardContent>
    </Card>
  );
}
