"use client";

import { useEffect, useState, useCallback } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Grid from "@mui/material/Grid";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Skeleton from "@mui/material/Skeleton";
import Chip from "@mui/material/Chip";
import TextField from "@mui/material/TextField";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import {
  fetchEpisodeSummary,
  fetchDiagnosedSummary,
  fetchKPIBenchmarks,
  fetchSafetyNetAlerts,
} from "@/lib/analyticsApi";
import { useOrgId } from "@/context/OrgContext";
import KPICards from "@/components/dashboard/KPICards";
import EpisodesByTypeChart from "@/components/dashboard/EpisodesByTypeChart";
import DiagnosedByTypeChart from "@/components/dashboard/DiagnosedByTypeChart";
import SafetyNetAlertsSummary from "@/components/dashboard/SafetyNetAlertsSummary";

const TERMINAL_STATUSES = new Set(["closed", "completed", "merged", "excluded"]);

export default function DashboardPage() {
  const orgId = useOrgId();

  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [appliedFrom, setAppliedFrom] = useState<string | undefined>(undefined);
  const [appliedTo, setAppliedTo] = useState<string | undefined>(undefined);

  const [episodes, setEpisodes] = useState<Array<{ condition_type: string; status: string; count: number }>>([]);
  const [diagnosed, setDiagnosed] = useState<Array<{ cancer_type: string; count: number }>>([]);
  const [kpis, setKpis] = useState<any>(null);
  const [alerts, setAlerts] = useState<Array<any>>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (from: string | undefined, to: string | undefined) => {
    setLoading(true);
    setError(null);
    try {
      const [ep, diag, kpi, safetyNetAlerts] = await Promise.all([
        fetchEpisodeSummary(orgId, from, to).catch(() => []),
        fetchDiagnosedSummary(orgId, from, to).catch(() => []),
        fetchKPIBenchmarks(orgId).catch(() => []),
        fetchSafetyNetAlerts(orgId).catch(() => []),
      ]);
      setEpisodes(ep);
      setDiagnosed(diag);
      setKpis(kpi?.[0] ?? null);
      setAlerts(safetyNetAlerts);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [orgId]);

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

  const isFiltered = !!appliedFrom || !!appliedTo;

  const totalEpisodes = episodes.reduce((s, e) => s + e.count, 0);
  const activeEpisodes = episodes
    .filter((e) => !TERMINAL_STATUSES.has(e.status))
    .reduce((s, e) => s + e.count, 0);
  const totalDiagnosed = diagnosed.reduce((s, d) => s + d.count, 0);
  const criticalAlerts = alerts.filter((a) => a.severity === "critical" || a.severity === "high").length;

  return (
    <Box sx={{ p: { xs: 2, sm: 3 }, overflowX: "hidden" }}>

      {/* ── Page title ─────────────────────────────────────────────── */}
      <Typography variant="h5" component="h1" sx={{ mb: 2, fontWeight: 700 }}>
        Overview
      </Typography>

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
          onClick={handleApply}
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
            onClick={handleClear}
            aria-label="Clear date filter"
            sx={{ textTransform: "none" }}
          >
            Clear filter
          </Button>
        )}
        {isFiltered && (
          <Chip
            label={`${appliedFrom ?? "Any date"} to ${appliedTo ?? "today"}`}
            size="small"
            color="primary"
            variant="outlined"
            aria-live="polite"
            aria-atomic="true"
          />
        )}
      </Box>

      {error && (
        <Typography role="alert" color="error" sx={{ mb: 2 }}>
          Something went wrong loading the data. Please refresh and try again.
        </Typography>
      )}

      {/* ── Summary cards ───────────────────────────────────────────── */}
      <Grid container spacing={2.5} sx={{ mb: 3 }} component="section" aria-label="Summary figures">
        <Grid size={{ xs: 12, sm: 6, md: 3 }}>
          <StatCard
            label="Cancer Referrals"
            description="Total number of cancer referral pathways recorded"
            value={loading ? undefined : totalEpisodes}
            color="#1D4ED8"
          />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, md: 3 }}>
          <StatCard
            label="Active Cases"
            description="Referrals still open and being tracked"
            value={loading ? undefined : activeEpisodes}
            color="#0D7C6F"
          />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, md: 3 }}>
          <StatCard
            label="Confirmed Cancers"
            description="Referrals where cancer has been confirmed"
            value={loading ? undefined : totalDiagnosed}
            color="#15803D"
          />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, md: 3 }}>
          <StatCard
            label="Safety Alerts"
            description="Patients who may need follow-up action"
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
                Referrals by Cancer Type
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2, fontSize: "0.8rem" }}>
                How many people were referred, grouped by suspected cancer type
              </Typography>
              {loading ? (
                <Skeleton variant="rectangular" height={280} aria-label="Loading referrals chart" />
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
                Confirmed Cancers by Type
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2, fontSize: "0.8rem" }}>
                Referrals where the cancer diagnosis has been confirmed
              </Typography>
              {loading ? (
                <Skeleton variant="rectangular" height={280} aria-label="Loading confirmed cancers chart" />
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
                Average Waiting Times
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2, fontSize: "0.8rem" }}>
                Average number of days between key stages of the cancer pathway
              </Typography>
              {loading
                ? <Skeleton variant="rectangular" height={240} aria-label="Loading waiting times" />
                : <KPICards kpis={kpis} />
              }
            </CardContent>
          </Card>
        </Grid>
        <Grid size={{ xs: 12, md: 7 }}>
          <Card>
            <CardContent>
              <Typography variant="h6" component="h2" sx={{ mb: 0.5, fontSize: "1rem", fontWeight: 700 }}>
                Recent Safety Alerts
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2, fontSize: "0.8rem" }}>
                Patients who may need follow-up based on clinical guidelines
              </Typography>
              {loading ? (
                <Skeleton variant="rectangular" height={200} aria-label="Loading safety alerts" />
              ) : (
                <SafetyNetAlertsSummary alerts={alerts.slice(0, 8)} />
              )}
            </CardContent>
          </Card>
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
          sx={{ color: "text.secondary", mb: 0.25, fontSize: "0.78rem", fontWeight: 600, textTransform: "uppercase", letterSpacing: 0.5 }}
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
