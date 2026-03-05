"use client";

import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import SectionCard from "./SectionCard";
import ComparisonBarChart, { type ComparisonDataRow } from "./ComparisonBarChart";
import BenchmarkLegend from "./BenchmarkLegend";
import type { AuditSectionResult, BenchmarkMetricValues } from "@/lib/analyticsApi";

interface Props {
  result?: AuditSectionResult<unknown> | null;
  loading?: boolean;
  error?: string | null;
  orgSelected?: boolean;
}

const ROUTES = [
  { key: "0", label: "0. Self-referred to A&E — no prior GP consultations", metricKey: "emergency_referral_routes.route_0_pct" },
  { key: "1", label: "1. GP/OOH referred to A&E — no prior GP consultations", metricKey: "" },
  { key: "2", label: "2. Self-referred to A&E — previously consulted GP, not awaiting test/referral", metricKey: "" },
  { key: "3", label: "3. GP/OOH referred to A&E — previously consulted GP, not awaiting test/referral", metricKey: "" },
  { key: "4", label: "4. Self-referred to A&E — awaiting GP-arranged test/referral", metricKey: "" },
  { key: "5", label: "5. GP/OOH referred to A&E — awaiting prior referral", metricKey: "" },
  { key: "6", label: "6. Other", metricKey: "" },
  { key: "7", label: "7. Not known / cannot verify", metricKey: "" },
];

export default function EmergencyReferralRoutesSection({ result, loading, error, orgSelected = false }: Props) {
  const bm = result?.benchmark?.metrics as Record<string, BenchmarkMetricValues> | undefined;
  const visibleKeys = ["practice", "alliance", "national"] as const;

  const chartData: ComparisonDataRow[] = ROUTES.filter((r) => r.metricKey).map((r) => ({
    category: `Route ${r.key}`,
    practice: null,
    alliance: bm?.[r.metricKey]?.alliance ?? null,
    national: bm?.[r.metricKey]?.national ?? null,
  }));

  return (
    <SectionCard
      id="section-emergency-routes"
      title="Emergency Referral Routes"
      description="For patients referred by emergency route — details of whether the patient had prior GP contact and whether a referral/investigation was already pending. Requires structured data entry."
      availability="manual_entry"
      loading={loading}
      error={error}
    >
      <BenchmarkLegend visibleKeys={visibleKeys} orgSelected={orgSelected} />
      <ComparisonBarChart
        data={chartData}
        unit="percent"
        height={220}
        visibleKeys={visibleKeys}
        ariaLabel="Emergency referral sub-routes compared to benchmarks"
      />
      <Box sx={{ mt: 2, overflowX: "auto" }}>
        <Table size="small" aria-label="Emergency referral route key">
          <TableHead>
            <TableRow>
              <TableCell sx={{ fontWeight: 700, fontSize: "0.78rem", width: 60 }}>Route</TableCell>
              <TableCell sx={{ fontWeight: 700, fontSize: "0.78rem" }}>Description</TableCell>
              <TableCell align="center" sx={{ fontWeight: 700, fontSize: "0.78rem", whiteSpace: "nowrap" }}>National %</TableCell>
              <TableCell align="center" sx={{ fontWeight: 700, fontSize: "0.78rem", whiteSpace: "nowrap" }}>Alliance %</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {ROUTES.map((r) => {
              const natVal = r.metricKey ? (bm?.[r.metricKey]?.national ?? null) : null;
              const alVal = r.metricKey ? (bm?.[r.metricKey]?.alliance ?? null) : null;
              return (
                <TableRow key={r.key} hover>
                  <TableCell sx={{ fontWeight: 700, fontSize: "0.8rem" }}>{r.key}</TableCell>
                  <TableCell sx={{ fontSize: "0.78rem" }}>{r.label}</TableCell>
                  <TableCell align="center" sx={{ fontSize: "0.8rem" }}>{natVal != null ? `${natVal}%` : "—"}</TableCell>
                  <TableCell align="center" sx={{ fontSize: "0.8rem" }}>{alVal != null ? `${alVal}%` : "—"}</TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </Box>
      <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: "block", fontSize: "0.73rem" }}>
        Note: Proportions are calculated only from patients referred by an emergency route. Only route 0 national/alliance data were available in the reference reports.
      </Typography>
    </SectionCard>
  );
}
