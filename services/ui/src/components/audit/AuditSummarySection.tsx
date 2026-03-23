"use client";

import Box from "@mui/material/Box";
import Grid from "@mui/material/Grid";
import Typography from "@mui/material/Typography";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Skeleton from "@mui/material/Skeleton";
import Divider from "@mui/material/Divider";
import SectionCard from "./SectionCard";
import type { AuditSummary } from "@/lib/analyticsApi";

interface Props {
  summary: AuditSummary | null;
  loading: boolean;
  error?: string | null;
  orgName?: string;
  auditPeriod?: string;
  totalCases?: number;
}

interface StatTileProps {
  label: string;
  value: string | number | null | undefined;
  sub?: string;
  color?: string;
}

function StatTile({ label, value, sub, color = "#1D4ED8" }: StatTileProps) {
  return (
    <Card variant="outlined" sx={{ height: "100%" }}>
      <CardContent sx={{ py: 1.5, px: 2, "&:last-child": { pb: 1.5 } }}>
        <Typography variant="caption" sx={{ color: "text.secondary", fontSize: "0.72rem", textTransform: "uppercase", letterSpacing: 0.5, fontWeight: 600 }}>
          {label}
        </Typography>
        {value == null ? (
          <Skeleton width={80} height={32} />
        ) : (
          <Typography variant="h5" sx={{ color, fontWeight: 700, lineHeight: 1.2, mt: 0.25 }}>
            {value}
          </Typography>
        )}
        {sub && (
          <Typography variant="caption" color="text.secondary" sx={{ fontSize: "0.72rem" }}>
            {sub}
          </Typography>
        )}
      </CardContent>
    </Card>
  );
}

const fmt = (v: number | null | undefined, decimals = 1) =>
  v == null ? null : Number(v.toFixed(decimals));

export default function AuditSummarySection({ summary, loading, error, orgName, auditPeriod, totalCases }: Props) {
  return (
    <SectionCard
      id="section-summary"
      title="Summary of Results"
      description={`Key metrics for ${orgName ?? "this organisation"}.${auditPeriod ? ` Audit period: ${auditPeriod}.` : ""}`}
      availability="ready"
      loading={loading}
      error={error}
    >
      {summary && (
        <>
          {totalCases != null && (
            <Box sx={{ mb: 2, p: 1.5, bgcolor: "grey.50", borderRadius: 1, border: "1px solid", borderColor: "divider" }}>
              <Typography variant="body2" sx={{ fontSize: "0.82rem" }}>
                <strong>{totalCases.toLocaleString("en-GB")}</strong> completed audit cases
                {orgName ? ` for ${orgName}` : ""}.
              </Typography>
            </Box>
          )}
          <Grid container spacing={1.5} sx={{ mb: 2 }}>
            <Grid size={{ xs: 6, sm: 4, md: 2 }}>
              <StatTile label="Total Pathways" value={summary.total_episodes?.toLocaleString("en-GB")} color="#1D4ED8" />
            </Grid>
            <Grid size={{ xs: 6, sm: 4, md: 2 }}>
              <StatTile label="Active" value={summary.active_episodes?.toLocaleString("en-GB")} color="#0D7C6F" />
            </Grid>
            <Grid size={{ xs: 6, sm: 4, md: 2 }}>
              <StatTile label="Confirmed" value={summary.confirmed_cancers?.toLocaleString("en-GB")} color="#15803D" />
            </Grid>
            <Grid size={{ xs: 6, sm: 4, md: 2 }}>
              <StatTile
                label="Median PCI"
                value={fmt(summary.median_pci_days) != null ? `${fmt(summary.median_pci_days)} days` : "—"}
                sub="First presentation to referral"
                color="#7C3AED"
              />
            </Grid>
            <Grid size={{ xs: 6, sm: 4, md: 2 }}>
              <StatTile
                label="Median DI"
                value={fmt(summary.median_di_days) != null ? `${fmt(summary.median_di_days)} days` : "—"}
                sub="First presentation to diagnosis"
                color="#92400E"
              />
            </Grid>
            <Grid size={{ xs: 6, sm: 4, md: 2 }}>
              <StatTile
                label="Safety Netting"
                value={fmt(summary.safety_netting_pct) != null ? `${fmt(summary.safety_netting_pct)}%` : "—"}
                sub="Cases with safety netting recorded"
                color="#C2410C"
              />
            </Grid>
          </Grid>

          <Divider sx={{ mb: 2 }} />

          <Typography variant="body2" color="text.secondary" sx={{ fontSize: "0.8rem" }}>
            Use the sections below to review each NCDA audit domain in detail. Each section compares your practice or organisation
            against similar practices, the Cancer Alliance, and national (England) benchmarks.
          </Typography>
        </>
      )}
    </SectionCard>
  );
}
