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

const ROUTES = [
  { key: "0", label: "0. Self-referred to A&E — no prior GP consultations", national: 29.2, alliance: 25.6 },
  { key: "1", label: "1. GP/OOH referred to A&E — no prior GP consultations", national: null, alliance: null },
  { key: "2", label: "2. Self-referred to A&E — previously consulted GP, not awaiting test/referral", national: null, alliance: null },
  { key: "3", label: "3. GP/OOH referred to A&E — previously consulted GP, not awaiting test/referral", national: null, alliance: null },
  { key: "4", label: "4. Self-referred to A&E — awaiting GP-arranged test/referral", national: null, alliance: null },
  { key: "5", label: "5. GP/OOH referred to A&E — awaiting prior referral", national: null, alliance: null },
  { key: "6", label: "6. Other", national: null, alliance: null },
  { key: "7", label: "7. Not known / cannot verify", national: null, alliance: null },
];

const chartData: ComparisonDataRow[] = ROUTES.filter((r) => r.national != null).map((r) => ({
  category: `Route ${r.key}`,
  practice: null,
  alliance: r.alliance ?? null,
  national: r.national ?? null,
}));

export default function EmergencyReferralRoutesSection() {
  return (
    <SectionCard
      id="section-emergency-routes"
      title="Emergency Referral Routes"
      description="For patients referred by emergency route — details of whether the patient had prior GP contact and whether a referral/investigation was already pending. Requires structured data entry."
      availability="manual_entry"
    >
      <BenchmarkLegend visibleKeys={["practice", "alliance", "national"]} />
      <ComparisonBarChart
        data={chartData}
        unit="percent"
        height={220}
        visibleKeys={["practice", "alliance", "national"]}
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
            {ROUTES.map((r) => (
              <TableRow key={r.key} hover>
                <TableCell sx={{ fontWeight: 700, fontSize: "0.8rem" }}>{r.key}</TableCell>
                <TableCell sx={{ fontSize: "0.78rem" }}>{r.label}</TableCell>
                <TableCell align="center" sx={{ fontSize: "0.8rem" }}>{r.national != null ? `${r.national}%` : "—"}</TableCell>
                <TableCell align="center" sx={{ fontSize: "0.8rem" }}>{r.alliance != null ? `${r.alliance}%` : "—"}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Box>
      <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: "block", fontSize: "0.73rem" }}>
        Note: Proportions are calculated only from patients referred by an emergency route. Only route 0 national/alliance data were available in the reference reports.
      </Typography>
    </SectionCard>
  );
}
