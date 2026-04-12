"use client";

import Box from "@mui/material/Box";
import Card from "@mui/material/Card";
import Skeleton from "@mui/material/Skeleton";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import Assignment from "@mui/icons-material/Assignment";
import CheckCircle from "@mui/icons-material/CheckCircle";
import Equalizer from "@mui/icons-material/Equalizer";
import People from "@mui/icons-material/People";
import type { EncounterKPIs } from "@/lib/missionControlApi";

interface KpiCardProps {
  icon: React.ReactNode;
  label: string;
  value: string | number;
  tooltip: string;
}

function KpiCard({ icon, label, value, tooltip }: KpiCardProps) {
  return (
    <Tooltip title={tooltip} arrow placement="bottom">
      <Card
        elevation={0}
        sx={{
          flex: 1,
          minWidth: 130,
          px: 2,
          py: 1.5,
          border: "1px solid",
          borderColor: "divider",
          borderRadius: 2,
          display: "flex",
          alignItems: "center",
          gap: 1.5,
          cursor: "default",
        }}
      >
        <Box sx={{ color: "primary.main", display: "flex", opacity: 0.7 }}>{icon}</Box>
        <Box>
          <Typography variant="h5" sx={{ fontWeight: 700, lineHeight: 1.1 }}>
            {value}
          </Typography>
          <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: "nowrap" }}>
            {label}
          </Typography>
        </Box>
      </Card>
    </Tooltip>
  );
}

function KpiSkeleton() {
  return (
    <Card
      elevation={0}
      sx={{
        flex: 1,
        minWidth: 130,
        px: 2,
        py: 1.5,
        border: "1px solid",
        borderColor: "divider",
        borderRadius: 2,
      }}
    >
      <Skeleton width={56} height={36} />
      <Skeleton width={80} height={14} />
    </Card>
  );
}

interface Props {
  kpis: EncounterKPIs | null;
  loading?: boolean;
}

export default function EncounterKpiStrip({ kpis, loading }: Props) {
  if (loading || !kpis) {
    return (
      <Box sx={{ display: "flex", gap: 1.5, flexWrap: "wrap" }}>
        {[0, 1, 2, 3].map((i) => <KpiSkeleton key={i} />)}
      </Box>
    );
  }

  return (
    <Box sx={{ display: "flex", gap: 1.5, flexWrap: "wrap" }}>
      <KpiCard
        icon={<Assignment fontSize="small" />}
        label="Encounters"
        value={kpis.total_encounters.toLocaleString()}
        tooltip="Total encounters matching the current date filter"
      />
      <KpiCard
        icon={<People fontSize="small" />}
        label="Patients"
        value={kpis.total_patients.toLocaleString()}
        tooltip="Distinct patients in this encounter set"
      />
      <KpiCard
        icon={<CheckCircle fontSize="small" />}
        label="Coded"
        value={kpis.coded_encounters.toLocaleString()}
        tooltip="Encounters with at least one coded clinical term"
      />
      <KpiCard
        icon={<Equalizer fontSize="small" />}
        label="Median codes"
        value={kpis.median_codes_per_encounter.toFixed(1)}
        tooltip="Median number of coded terms per encounter"
      />
    </Box>
  );
}
