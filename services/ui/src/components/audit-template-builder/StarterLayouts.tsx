"use client";

/**
 * Atlas trace: DO-A9863AB6 / DI-64CA7740
 *
 * One-click starter layouts for the audit template builder.
 * Each starter pre-populates the canvas with a curated tile arrangement
 * using the first available catalogue metrics of the appropriate type.
 */

import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import DashboardCustomizeOutlinedIcon from "@mui/icons-material/DashboardCustomizeOutlined";
import BarChartIcon from "@mui/icons-material/BarChart";
import NumbersIcon from "@mui/icons-material/Numbers";
import TableChartOutlinedIcon from "@mui/icons-material/TableChartOutlined";
import { type MetricCatalogueEntry, type TileType, type TileLayout } from "@/lib/auditTemplateApi";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface StarterSlot {
  tileType: TileType;
  layout: TileLayout;
}

export interface StarterLayout {
  id: string;
  label: string;
  description: string;
  Icon: React.ElementType;
  colour: string;
  slots: StarterSlot[];
}

// ---------------------------------------------------------------------------
// Starter definitions
// ---------------------------------------------------------------------------

export const STARTERS: StarterLayout[] = [
  {
    id: "kpi-overview",
    label: "KPI overview",
    description: "3 KPI cards across the top, then a bar chart.",
    Icon: NumbersIcon,
    colour: "#7C3AED",
    slots: [
      { tileType: "kpi_strip",  layout: { x: 0, y: 0, w: 4, h: 3 } },
      { tileType: "kpi_strip",  layout: { x: 4, y: 0, w: 4, h: 3 } },
      { tileType: "kpi_strip",  layout: { x: 8, y: 0, w: 4, h: 3 } },
      { tileType: "bar_chart",  layout: { x: 0, y: 3, w: 12, h: 5 } },
    ],
  },
  {
    id: "two-charts",
    label: "Side-by-side charts",
    description: "Two charts side by side for easy comparison.",
    Icon: BarChartIcon,
    colour: "#002178",
    slots: [
      { tileType: "bar_chart",  layout: { x: 0, y: 0, w: 6, h: 5 } },
      { tileType: "line_chart", layout: { x: 6, y: 0, w: 6, h: 5 } },
    ],
  },
  {
    id: "dashboard-full",
    label: "Full dashboard",
    description: "KPIs, two charts, and a data table.",
    Icon: DashboardCustomizeOutlinedIcon,
    colour: "#047857",
    slots: [
      { tileType: "kpi_strip",  layout: { x: 0,  y: 0, w: 4, h: 3 } },
      { tileType: "kpi_strip",  layout: { x: 4,  y: 0, w: 4, h: 3 } },
      { tileType: "kpi_strip",  layout: { x: 8,  y: 0, w: 4, h: 3 } },
      { tileType: "bar_chart",  layout: { x: 0,  y: 3, w: 7, h: 5 } },
      { tileType: "line_chart", layout: { x: 7,  y: 3, w: 5, h: 5 } },
      { tileType: "table",      layout: { x: 0,  y: 8, w: 12, h: 4 } },
    ],
  },
  {
    id: "table-detail",
    label: "Table detail",
    description: "Wide data table with a supporting bar chart.",
    Icon: TableChartOutlinedIcon,
    colour: "#0E7490",
    slots: [
      { tileType: "bar_chart", layout: { x: 0, y: 0, w: 5, h: 5 } },
      { tileType: "table",     layout: { x: 5, y: 0, w: 7, h: 5 } },
    ],
  },
];

// ---------------------------------------------------------------------------
// Helper: pick metrics from catalogue for a given tile type
// ---------------------------------------------------------------------------

export function pickMetricsForSlots(
  slots: StarterSlot[],
  catalogue: MetricCatalogueEntry[],
): Array<{ slot: StarterSlot; metric: MetricCatalogueEntry }> {
  const used = new Map<string, number>();
  return slots.map((slot) => {
    const compatible = catalogue.filter(
      (m) =>
        m.compatible_tile_types?.includes(slot.tileType) ||
        m.output_type === slot.tileType,
    );
    // Prefer least-used to avoid repeating the same metric
    compatible.sort((a, b) => (used.get(a.metric_id) ?? 0) - (used.get(b.metric_id) ?? 0));
    const metric = compatible[0] ?? catalogue[0];
    if (metric) used.set(metric.metric_id, (used.get(metric.metric_id) ?? 0) + 1);
    return { slot, metric };
  });
}

// ---------------------------------------------------------------------------
// StarterLayouts component
// ---------------------------------------------------------------------------

interface StarterLayoutsProps {
  catalogue: MetricCatalogueEntry[];
  onApply: (starter: StarterLayout, catalogue: MetricCatalogueEntry[]) => void;
}

export default function StarterLayouts({ catalogue, onApply }: StarterLayoutsProps) {
  return (
    <Box>
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, mb: 1 }}>
        <DashboardCustomizeOutlinedIcon sx={{ fontSize: 13, color: "text.secondary" }} />
        <Typography variant="caption" fontWeight={700} color="text.secondary">
          Start with a layout
        </Typography>
      </Box>
      <Box sx={{ display: "flex", flexDirection: "column", gap: 0.75 }}>
        {STARTERS.map((starter) => {
          const { Icon, colour } = starter;
          const disabled = catalogue.length === 0;
          return (
            <Tooltip key={starter.id} title={starter.description} placement="right">
              <span>
                <Button
                  fullWidth
                  size="small"
                  disabled={disabled}
                  onClick={() => onApply(starter, catalogue)}
                  startIcon={<Icon style={{ fontSize: 13, color: colour }} />}
                  sx={{
                    justifyContent: "flex-start",
                    textAlign: "left",
                    fontSize: 11,
                    fontWeight: 600,
                    color: "text.primary",
                    borderRadius: 1.5,
                    px: 1,
                    py: 0.5,
                    bgcolor: `${colour}0A`,
                    border: `1px solid ${colour}25`,
                    "&:hover": { bgcolor: `${colour}18`, borderColor: colour },
                    "& .MuiButton-startIcon": { mr: 0.75 },
                  }}
                >
                  {starter.label}
                </Button>
              </span>
            </Tooltip>
          );
        })}
      </Box>
    </Box>
  );
}
