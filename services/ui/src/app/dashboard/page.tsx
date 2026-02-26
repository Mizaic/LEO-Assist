"use client";

import { useEffect, useState } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Grid from "@mui/material/Grid";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Skeleton from "@mui/material/Skeleton";
import Chip from "@mui/material/Chip";
import { fetchEpisodeSummary, fetchKPIBenchmarks, fetchCSSAlerts } from "@/lib/analyticsApi";
import KPICards from "@/components/dashboard/KPICards";
import EpisodesByTypeChart from "@/components/dashboard/EpisodesByTypeChart";
import CSSAlertsSummary from "@/components/dashboard/CSSAlertsSummary";

export default function DashboardPage() {
  const [episodes, setEpisodes] = useState<Array<{ cancer_type: string; status: string; count: number }>>([]);
  const [kpis, setKpis] = useState<any>(null);
  const [alerts, setAlerts] = useState<Array<any>>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const [ep, kpi, css] = await Promise.all([
          fetchEpisodeSummary().catch(() => []),
          fetchKPIBenchmarks().catch(() => []),
          fetchCSSAlerts().catch(() => []),
        ]);
        setEpisodes(ep);
        setKpis(kpi?.[0] ?? null);
        setAlerts(css);
      } catch (e: any) {
        setError(e.message);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const totalEpisodes = episodes.reduce((s, e) => s + e.count, 0);
  const activeEpisodes = episodes.filter((e) => e.status === "active").reduce((s, e) => s + e.count, 0);
  const criticalAlerts = alerts.filter((a) => a.severity === "critical" || a.severity === "high").length;

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h5" sx={{ mb: 3 }}>
        Dashboard
      </Typography>

      {error && (
        <Typography color="error" sx={{ mb: 2 }}>
          {error}
        </Typography>
      )}

      <Grid container spacing={2.5} sx={{ mb: 3 }}>
        <Grid size={{ xs: 12, sm: 6, md: 3 }}>
          <StatCard
            label="Total Episodes"
            value={loading ? undefined : totalEpisodes}
            color="primary.main"
          />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, md: 3 }}>
          <StatCard
            label="Active Episodes"
            value={loading ? undefined : activeEpisodes}
            color="secondary.main"
          />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, md: 3 }}>
          <StatCard
            label="CSS Alerts"
            value={loading ? undefined : alerts.length}
            color="warning.main"
            badge={criticalAlerts > 0 ? `${criticalAlerts} critical` : undefined}
          />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, md: 3 }}>
          <StatCard
            label="Avg Days to Diagnosis"
            value={loading ? undefined : kpis?.avg_days_to_diagnosis != null ? Math.round(kpis.avg_days_to_diagnosis) : "—"}
            color="info.main"
          />
        </Grid>
      </Grid>

      <Grid container spacing={2.5}>
        <Grid size={{ xs: 12, md: 7 }}>
          <Card>
            <CardContent>
              <Typography variant="h6" sx={{ mb: 2, fontSize: "1rem" }}>
                Episodes by Cancer Type
              </Typography>
              {loading ? (
                <Skeleton variant="rectangular" height={280} />
              ) : (
                <EpisodesByTypeChart data={episodes} />
              )}
            </CardContent>
          </Card>
        </Grid>
        <Grid size={{ xs: 12, md: 5 }}>
          <Card>
            <CardContent>
              <Typography variant="h6" sx={{ mb: 2, fontSize: "1rem" }}>
                KPI Overview
              </Typography>
              {loading ? <Skeleton variant="rectangular" height={280} /> : <KPICards kpis={kpis} />}
            </CardContent>
          </Card>
        </Grid>
        <Grid size={{ xs: 12 }}>
          <Card>
            <CardContent>
              <Typography variant="h6" sx={{ mb: 2, fontSize: "1rem" }}>
                Recent CSS Alerts
              </Typography>
              {loading ? (
                <Skeleton variant="rectangular" height={200} />
              ) : (
                <CSSAlertsSummary alerts={alerts.slice(0, 10)} />
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
  value,
  color,
  badge,
}: {
  label: string;
  value: number | string | undefined;
  color: string;
  badge?: string;
}) {
  return (
    <Card>
      <CardContent sx={{ py: 2.5 }}>
        <Typography variant="body2" sx={{ color: "text.secondary", mb: 0.5, fontSize: "0.8rem" }}>
          {label}
        </Typography>
        {value === undefined ? (
          <Skeleton width={80} height={36} />
        ) : (
          <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
            <Typography variant="h4" sx={{ color, fontSize: "1.8rem" }}>
              {value}
            </Typography>
            {badge && <Chip label={badge} size="small" color="error" />}
          </Box>
        )}
      </CardContent>
    </Card>
  );
}
