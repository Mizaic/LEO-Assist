"use client";

/**
 * Atlas trace: DO-A9863AB6 / DI-64CA7740
 *
 * Left panel: browse metrics and add them to the template with a chosen
 * chart type. Compatible types are shown as clickable chips per metric;
 * the canonical output_type is highlighted as the default.
 */

import { useState } from "react";
import { motion as fm, useReducedMotion } from "framer-motion";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import TextField from "@mui/material/TextField";
import Skeleton from "@mui/material/Skeleton";
import Alert from "@mui/material/Alert";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import Tooltip from "@mui/material/Tooltip";
import Button from "@mui/material/Button";
import BarChartIcon from "@mui/icons-material/BarChart";
import ShowChartIcon from "@mui/icons-material/ShowChart";
import NumbersIcon from "@mui/icons-material/Numbers";
import TableChartOutlinedIcon from "@mui/icons-material/TableChartOutlined";
import TimelineIcon from "@mui/icons-material/Timeline";
import TextFieldsIcon from "@mui/icons-material/TextFields";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import WidgetsOutlinedIcon from "@mui/icons-material/WidgetsOutlined";
import AddCircleOutlineIcon from "@mui/icons-material/AddCircleOutline";
import {
  type MetricCatalogueEntry,
  type TileType,
  type WidgetCatalogueEntry,
  WIDGET_CATALOGUE,
} from "@/lib/auditTemplateApi";

const TYPE_META: Record<TileType, { Icon: React.ElementType; label: string; colour: string }> = {
  bar_chart:     { Icon: BarChartIcon,           label: "Bar",      colour: "#1E40AF" },
  line_chart:    { Icon: ShowChartIcon,           label: "Line",     colour: "#047857" },
  kpi_strip:     { Icon: NumbersIcon,             label: "KPI",      colour: "#7C3AED" },
  table:         { Icon: TableChartOutlinedIcon,  label: "Table",    colour: "#0E7490" },
  interval_plot: { Icon: TimelineIcon,            label: "Interval", colour: "#B45309" },
  text:          { Icon: TextFieldsIcon,          label: "Text",     colour: "#475569" },
  widget:        { Icon: WidgetsOutlinedIcon,     label: "Widget",   colour: "#92400E" },
};

interface MetricPickerProps {
  catalogue: MetricCatalogueEntry[];
  loading: boolean;
  error: string | null;
  usedMetricIds: Set<string>;
  onAdd: (metric: MetricCatalogueEntry, tileType: TileType) => void;
  onAddWidget: (widget: WidgetCatalogueEntry) => void;
}

const listVariants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.04 } },
};

const itemVariants = {
  hidden: { opacity: 0, x: -10 },
  visible: { opacity: 1, x: 0, transition: { duration: 0.18, ease: "easeOut" } },
};

function MetricCard({
  metric,
  used,
  onAdd,
}: {
  metric: MetricCatalogueEntry;
  used: boolean;
  onAdd: (type: TileType) => void;
}) {
  const reduced = useReducedMotion();
  const defaultType = metric.output_type as TileType;
  const compatible = metric.compatible_tile_types ?? [defaultType];

  return (
    <Box
      sx={{
        border: "1px solid",
        borderColor: used ? "primary.200" : "divider",
        borderRadius: 1.5,
        p: 1.25,
        bgcolor: used ? "primary.50" : "background.paper",
        transition: "border-color 120ms",
      }}
    >
      <Box sx={{ display: "flex", alignItems: "flex-start", gap: 0.5, mb: 0.75 }}>
        {used && (
          <CheckCircleOutlineIcon sx={{ fontSize: 13, color: "primary.main", mt: 0.15, flexShrink: 0 }} />
        )}
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography variant="caption" fontWeight={700} display="block" noWrap>
            {metric.title}
          </Typography>
          <Typography
            variant="caption"
            color="text.secondary"
            display="block"
            sx={{ fontSize: 10, lineHeight: 1.4, mt: 0.15 }}
          >
            {metric.description}
          </Typography>
        </Box>
      </Box>

      {/* Chart type chips */}
      <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5 }}>
        {(Object.keys(TYPE_META) as TileType[]).map((type) => {
          const { Icon, label, colour } = TYPE_META[type];
          const isCompatible = compatible.includes(type);
          const isDefault = type === defaultType;

          if (!isCompatible) return null;

          return (
            <Tooltip
              key={type}
              title={isDefault ? `Add as ${label} (recommended)` : `Add as ${label}`}
              placement="top"
            >
              <fm.div
                whileTap={reduced || used ? {} : { scale: 0.93 }}
                style={{ display: "inline-flex" }}
              >
                <Chip
                  icon={<Icon style={{ fontSize: 11 }} />}
                  label={label}
                  size="small"
                  disabled={used}
                  onClick={() => onAdd(type)}
                  sx={{
                    height: 20,
                    fontSize: 10,
                    px: 0.25,
                    bgcolor: isDefault ? `${colour}18` : "transparent",
                    borderColor: isDefault ? colour : "divider",
                    color: isDefault ? colour : "text.secondary",
                    border: "1px solid",
                    fontWeight: isDefault ? 700 : 400,
                    "& .MuiChip-icon": { color: isDefault ? colour : "text.disabled" },
                    "&:hover:not(:disabled)": {
                      bgcolor: `${colour}20`,
                      borderColor: colour,
                      color: colour,
                    },
                    cursor: used ? "default" : "pointer",
                  }}
                />
              </fm.div>
            </Tooltip>
          );
        })}
      </Box>
    </Box>
  );
}

export default function MetricPicker({ catalogue, loading, error, usedMetricIds, onAdd, onAddWidget }: MetricPickerProps) {
  const [search, setSearch] = useState("");

  const filtered = catalogue.filter(
    (m) =>
      m.title.toLowerCase().includes(search.toLowerCase()) ||
      m.description.toLowerCase().includes(search.toLowerCase()),
  );

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5, height: "100%" }}>
      <Typography variant="subtitle2" fontWeight={700}>
        Metric library
      </Typography>
      <TextField
        size="small"
        placeholder="Search metrics..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        fullWidth
      />
      {error && <Alert severity="error" sx={{ fontSize: 12 }}>{error}</Alert>}

      <Box sx={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: 1 }}>
        {loading
          ? [0, 1, 2, 3, 4].map((i) => (
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
            <fm.div
              key={search}
              variants={listVariants}
              initial="hidden"
              animate="visible"
              style={{ display: "flex", flexDirection: "column", gap: 8 }}
            >
              {filtered.map((m) => (
                <fm.div key={m.metric_id} variants={itemVariants}>
                  <MetricCard
                    metric={m}
                    used={usedMetricIds.has(m.metric_id)}
                    onAdd={(type) => onAdd(m, type)}
                  />
                </fm.div>
              ))}
            </fm.div>
          )}

        {!loading && filtered.length === 0 && (
          <Typography variant="caption" color="text.disabled" sx={{ textAlign: "center", mt: 2 }}>
            No metrics match your search.
          </Typography>
        )}
      </Box>

      {/* Specialised widgets */}
      <Box>
        <Divider sx={{ mb: 1.5 }} />
        <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, mb: 1 }}>
          <WidgetsOutlinedIcon sx={{ fontSize: 13, color: "warning.dark" }} />
          <Typography variant="caption" fontWeight={700} color="warning.dark">
            Specialised widgets
          </Typography>
        </Box>
        <Box sx={{ display: "flex", flexDirection: "column", gap: 0.75 }}>
          {WIDGET_CATALOGUE.map((widget) => {
            const used = usedMetricIds.has(widget.widget_id);
            return (
              <Box
                key={widget.widget_id}
                sx={{
                  border: "1px solid",
                  borderColor: used ? "warning.200" : "warning.100",
                  borderRadius: 1.5,
                  p: 1.25,
                  bgcolor: used ? "warning.50" : "#FFFBEB",
                  display: "flex",
                  alignItems: "flex-start",
                  gap: 1,
                }}
              >
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, mb: 0.25 }}>
                    {used && (
                      <CheckCircleOutlineIcon
                        sx={{ fontSize: 11, color: "warning.dark", flexShrink: 0 }}
                      />
                    )}
                    <Typography variant="caption" fontWeight={700} display="block" noWrap>
                      {widget.title}
                    </Typography>
                  </Box>
                  <Typography
                    variant="caption"
                    color="text.secondary"
                    display="block"
                    sx={{ fontSize: 10, lineHeight: 1.4 }}
                  >
                    {widget.description}
                  </Typography>
                </Box>
                <Tooltip
                  title={used ? "Already added" : "Add widget"}
                  placement="top"
                >
                  <span>
                    <Button
                      size="small"
                      disabled={used}
                      onClick={() => onAddWidget(widget)}
                      sx={{
                        minWidth: 0,
                        p: 0.5,
                        color: "warning.dark",
                        "&:hover": { bgcolor: "warning.100" },
                      }}
                    >
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
