"use client";

/**
 * Renders a pre-built specialised widget inside an audit template.
 *
 * Atlas trace: DO-A9863AB6 / DI-758B73A5
 *
 * Widget tiles carry tile_type="widget" and a metric_id that is the
 * widget_id from WIDGET_CATALOGUE. They never call the /run metric endpoint.
 * Each widget_id maps to a full NCDA audit section component here.
 *
 * Components are lazy-loaded via next/dynamic so the Plotly / recharts bundles
 * for these heavy sections are not included unless the template has the tile.
 */

import dynamic from "next/dynamic";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import CircularProgress from "@mui/material/CircularProgress";
import WidgetsOutlinedIcon from "@mui/icons-material/WidgetsOutlined";

import { type AuditTile } from "@/lib/auditTemplateApi";

// -- Lazy-load audit section components --
const SymptomsSection = dynamic(
  () => import("@/components/audit/SymptomsSection"),
  {
    ssr: false,
    loading: () => <WidgetSkeleton label="Symptoms at Referral" />,
  }
);

const BloodSignalSection = dynamic(
  () => import("@/components/audit/BloodSignalAnalysis"),
  {
    ssr: false,
    loading: () => <WidgetSkeleton label="Blood Result Cancer Signal" />,
  }
);

function WidgetSkeleton({ label }: { label: string }) {
  return (
    <Box
      sx={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 1.5,
        py: 8,
        color: "text.disabled",
      }}
    >
      <CircularProgress size={24} />
      <Typography variant="caption">Loading {label}...</Typography>
    </Box>
  );
}

function defaultDateRange(): { dateFrom: string; dateTo: string } {
  const now = new Date();
  const dateTo = now.toISOString().slice(0, 10);
  const from = new Date(now);
  from.setFullYear(from.getFullYear() - 3);
  return { dateFrom: from.toISOString().slice(0, 10), dateTo };
}

interface WidgetTileProps {
  tile: AuditTile;
  orgId: string;
}

export default function WidgetTile({ tile, orgId }: WidgetTileProps) {
  if (tile.metric_id === "symptoms_ppv") {
    const { dateFrom, dateTo } = defaultDateRange();
    return (
      <SymptomsSection
        loading={false}
        error={null}
        orgId={orgId}
        dateFrom={dateFrom}
        dateTo={dateTo}
      />
    );
  }

  if (tile.metric_id === "blood_signal") {
    return <BloodSignalSection />;
  }

  return (
    <Box
      sx={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 1,
        py: 6,
        border: "1px dashed",
        borderColor: "divider",
        borderRadius: 2,
        color: "text.disabled",
      }}
    >
      <WidgetsOutlinedIcon sx={{ fontSize: 32 }} />
      <Typography variant="body2">
        Unknown widget: <code>{tile.metric_id}</code>
      </Typography>
    </Box>
  );
}
