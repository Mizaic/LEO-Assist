"use client";

/**
 * Atlas trace: DO-A9863AB6 / DI-64CA7740
 *
 * "Data" tab of MetricPicker: category filter chips + search + metric cards
 * + specialised widgets at the bottom.
 */

import { useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import TextField from "@mui/material/TextField";
import Skeleton from "@mui/material/Skeleton";
import Alert from "@mui/material/Alert";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import Tooltip from "@mui/material/Tooltip";
import Button from "@mui/material/Button";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import WidgetsOutlinedIcon from "@mui/icons-material/WidgetsOutlined";
import AddCircleOutlineIcon from "@mui/icons-material/AddCircleOutline";
import BarChartIcon from "@mui/icons-material/BarChart";
import ShowChartIcon from "@mui/icons-material/ShowChart";
import NumbersIcon from "@mui/icons-material/Numbers";
import TableChartOutlinedIcon from "@mui/icons-material/TableChartOutlined";
import TimelineIcon from "@mui/icons-material/Timeline";
import TextFieldsIcon from "@mui/icons-material/TextFields";
import {
  type MetricCatalogueEntry,
  type TileType,
  type WidgetCatalogueEntry,
  WIDGET_CATALOGUE,
} from "@/lib/auditTemplateApi";

// ---------------------------------------------------------------------------
// Metric categorisation
// ---------------------------------------------------------------------------

type Category = { id: string; label: string; colour: string };

const CATEGORIES: Category[] = [
  { id: "all",      label: "All",       colour: "#64748B" },
  { id: "patient",  label: "Patient",   colour: "#002178" },
  { id: "clinical", label: "Clinical",  colour: "#047857" },
  { id: "pathway",  label: "Pathway",   colour: "#7C3AED" },
  { id: "referral", label: "Referral",  colour: "#B45309" },
  { id: "outcomes", label: "Outcomes",  colour: "#0E7490" },
];

function categorise(m: MetricCatalogueEntry): string {
  const id = m.metric_id.toLowerCase();
  if (id.includes("referral") || id.includes("stt") || id.includes("route")) return "referral";
  if (id.includes("stage") || id.includes("cancer_type") || id.includes("diagnosis")) return "outcomes";
  if (id.includes("episode") || id.includes("interval") || id.includes("time")) return "pathway";
  if (id.includes("patient") || id.includes("count")) return "patient";
  return "clinical";
}

// ---------------------------------------------------------------------------
// Type chip map
// ---------------------------------------------------------------------------

const TYPE_META: Record<TileType, { Icon: React.ElementType; label: string; colour: string }> = {
  bar_chart:     { Icon: BarChartIcon,           label: "Bar",      colour: "#002178" },
  line_chart:    { Icon: ShowChartIcon,           label: "Line",     colour: "#047857" },
  kpi_strip:     { Icon: NumbersIcon,             label: "KPI",      colour: "#7C3AED" },
  table:         { Icon: TableChartOutlinedIcon,  label: "Table",    colour: "#0E7490" },
  interval_plot: { Icon: TimelineIcon,            label: "Interval", colour: "#B45309" },
  text:          { Icon: TextFieldsIcon,          label: "Text",     colour: "#475569" },
  widget:        { Icon: WidgetsOutlinedIcon,     label: "Widget",   colour: "#92400E" },
};

// ---------------------------------------------------------------------------
// MetricCard
// ---------------------------------------------------------------------------

function MetricCard({ metric, count, onAdd }: {
  metric: MetricCatalogueEntry;
  count: number;
  onAdd: (type: TileType) => void;
}) {
  const defaultType = metric.output_type as TileType;
  const compatible = metric.compatible_tile_types ?? [defaultType];
  const used = count > 0;

  return (
    <Box
      draggable
      onDragStart={(e) => {
        e.dataTransfer.effectAllowed = "copy";
        e.dataTransfer.setData(
          "application/x-audit-metric",
          JSON.stringify({ metric_id: metric.metric_id, tile_type: defaultType }),
        );
      }}
      sx={{
        border: "1px solid",
        borderColor: used ? "primary.200" : "divider",
        borderRadius: 1.5,
        p: 1.25,
        bgcolor: used ? "primary.50" : "background.paper",
        cursor: "grab",
        "&:active": { cursor: "grabbing" },
      }}
    >
      <Box sx={{ display: "flex", alignItems: "flex-start", gap: 0.5, mb: 0.75 }}>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography variant="caption" fontWeight={700} display="block" noWrap>
            {metric.title}
          </Typography>
          <Typography variant="caption" color="text.secondary" display="block"
            sx={{ fontSize: 10, lineHeight: 1.4, mt: 0.15 }}>
            {metric.description}
          </Typography>
        </Box>
        {used && (
          <Tooltip title={`Added ${count} time${count === 1 ? "" : "s"}`}>
            <Box sx={{
              display: "flex", alignItems: "center", gap: 0.25, flexShrink: 0,
              px: 0.5, height: 16, borderRadius: 999, bgcolor: "primary.100", color: "primary.dark",
            }}>
              <CheckCircleOutlineIcon sx={{ fontSize: 11 }} />
              <Typography component="span" sx={{ fontSize: 9, fontWeight: 700, lineHeight: 1 }}>
                {count}
              </Typography>
            </Box>
          </Tooltip>
        )}
      </Box>
      <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5 }}>
        {(Object.keys(TYPE_META) as TileType[]).map((type) => {
          if (!compatible.includes(type)) return null;
          const { Icon, label, colour } = TYPE_META[type];
          const isDefault = type === defaultType;
          return (
            <Tooltip key={type} title={isDefault ? `Add as ${label} (recommended)` : `Add as ${label}`} placement="top">
              <span style={{ display: "inline-flex" }}>
                <Chip
                  icon={<Icon style={{ fontSize: 11 }} />}
                  label={label}
                  size="small"
                  onClick={() => onAdd(type)}
                  sx={{
                    height: 20, fontSize: 10, px: 0.25,
                    bgcolor: isDefault ? `${colour}18` : "transparent",
                    borderColor: isDefault ? colour : "divider",
                    color: isDefault ? colour : "text.secondary",
                    border: "1px solid",
                    fontWeight: isDefault ? 700 : 400,
                    "& .MuiChip-icon": { color: isDefault ? colour : "text.disabled" },
                    "&:hover": { bgcolor: `${colour}20`, borderColor: colour, color: colour },
                    cursor: "pointer",
                  }}
                />
              </span>
            </Tooltip>
          );
        })}
      </Box>
    </Box>
  );
}

// ---------------------------------------------------------------------------
// DataPanel
// ---------------------------------------------------------------------------

interface DataPanelProps {
  catalogue: MetricCatalogueEntry[];
  loading: boolean;
  error: string | null;
  usedCounts: Map<string, number>;
  onAdd: (metric: MetricCatalogueEntry, tileType: TileType) => void;
  onAddWidget: (widget: WidgetCatalogueEntry) => void;
}

export default function DataPanel({ catalogue, loading, error, usedCounts, onAdd, onAddWidget }: DataPanelProps) {
  const [search, setSearch] = useState("");
  const [activeCat, setActiveCat] = useState("all");

  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    return catalogue.filter((m) => {
      const matchSearch = !q || m.title.toLowerCase().includes(q) || m.description.toLowerCase().includes(q);
      const matchCat = activeCat === "all" || categorise(m) === activeCat;
      return matchSearch && matchCat;
    });
  }, [catalogue, search, activeCat]);

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 1, p: 1.5, height: "100%", overflow: "hidden" }}>
      <style>{`@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }`}</style>

      <TextField
        size="small"
        placeholder="Search metrics..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        fullWidth
      />

      {error && <Alert severity="error" sx={{ fontSize: 12 }}>{error}</Alert>}

      {/* Category filter chips */}
      {!loading && (
        <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap" }}>
          {CATEGORIES.map((cat) => (
            <Chip
              key={cat.id}
              label={cat.label}
              size="small"
              onClick={() => setActiveCat(cat.id)}
              sx={{
                height: 20,
                fontSize: 10,
                fontWeight: activeCat === cat.id ? 700 : 400,
                bgcolor: activeCat === cat.id ? `${cat.colour}20` : "transparent",
                borderColor: activeCat === cat.id ? cat.colour : "divider",
                color: activeCat === cat.id ? cat.colour : "text.secondary",
                border: "1px solid",
                cursor: "pointer",
              }}
            />
          ))}
        </Box>
      )}

      {/* Metric list */}
      <Box sx={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: 1 }}>
        {loading
          ? [0, 1, 2, 3].map((i) => (
              <Box key={i} sx={{ border: "1px solid", borderColor: "divider", borderRadius: 1.5, p: 1.25 }}>
                <Skeleton variant="text" width="80%" height={14} />
                <Skeleton variant="text" width="60%" height={11} sx={{ mt: 0.25 }} />
                <Box sx={{ display: "flex", gap: 0.5, mt: 0.75 }}>
                  <Skeleton variant="rounded" width={42} height={20} />
                  <Skeleton variant="rounded" width={42} height={20} />
                </Box>
              </Box>
            ))
          : (
            <Box key={`${search}-${activeCat}`} style={{ display: "flex", flexDirection: "column", gap: 8, animation: "fadeIn 0.15s ease-out" }}>
              {filtered.map((m) => (
                <MetricCard
                  key={m.metric_id}
                  metric={m}
                  count={usedCounts.get(m.metric_id) ?? 0}
                  onAdd={(type) => onAdd(m, type)}
                />
              ))}
              {filtered.length === 0 && (
                <Typography variant="caption" color="text.disabled" sx={{ textAlign: "center", mt: 2 }}>
                  No metrics match.
                </Typography>
              )}
            </Box>
          )}
      </Box>

      {/* Specialised widgets */}
      <Box>
        <Divider sx={{ mb: 1 }} />
        <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, mb: 0.75 }}>
          <WidgetsOutlinedIcon sx={{ fontSize: 13, color: "warning.dark" }} />
          <Typography variant="caption" fontWeight={700} color="warning.dark">
            Specialised widgets
          </Typography>
        </Box>
        <Box sx={{ display: "flex", flexDirection: "column", gap: 0.75 }}>
          {WIDGET_CATALOGUE.map((widget) => {
            const count = usedCounts.get(widget.widget_id) ?? 0;
            return (
              <Box
                key={widget.widget_id}
                draggable
                onDragStart={(e) => {
                  e.dataTransfer.effectAllowed = "copy";
                  e.dataTransfer.setData("application/x-audit-widget", JSON.stringify({ widget_id: widget.widget_id }));
                }}
                sx={{
                  border: "1px solid", borderColor: count > 0 ? "warning.200" : "warning.100",
                  borderRadius: 1.5, p: 1.25, bgcolor: count > 0 ? "warning.50" : "#FFFBEB",
                  display: "flex", alignItems: "flex-start", gap: 1,
                  cursor: "grab", "&:active": { cursor: "grabbing" },
                }}
              >
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Typography variant="caption" fontWeight={700} display="block" noWrap>
                    {widget.title}
                  </Typography>
                  <Typography variant="caption" color="text.secondary" display="block" sx={{ fontSize: 10, lineHeight: 1.4 }}>
                    {widget.description}
                  </Typography>
                </Box>
                <Tooltip title="Add widget" placement="top">
                  <span>
                    <Button size="small" onClick={() => onAddWidget(widget)}
                      sx={{ minWidth: 0, p: 0.5, color: "warning.dark", "&:hover": { bgcolor: "warning.100" } }}>
                      <AddCircleOutlineIcon sx={{ fontSize: 16 }} />
                    </Button>
                  </span>
                </Tooltip>
              </Box>
            );
          })}
        </Box>
      </Box>
    </Box>
  );
}
