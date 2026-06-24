"use client";

/**
 * Atlas trace: DO-A9863AB6 / DI-64CA7740
 * Left panel: browse and add metrics to the template being edited.
 */

import { useEffect, useState } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import TextField from "@mui/material/TextField";
import CircularProgress from "@mui/material/CircularProgress";
import Alert from "@mui/material/Alert";
import Chip from "@mui/material/Chip";
import Tooltip from "@mui/material/Tooltip";
import IconButton from "@mui/material/IconButton";
import AddCircleOutlineIcon from "@mui/icons-material/AddCircleOutline";
import {
  fetchMetricCatalogue,
  type MetricCatalogueEntry,
  type TileType,
} from "@/lib/auditTemplateApi";

interface MetricPickerProps {
  onAdd: (metric: MetricCatalogueEntry) => void;
  usedMetricIds: Set<string>;
}

const OUTPUT_TYPE_COLOURS: Record<string, "default" | "primary" | "success" | "warning"> = {
  bar_chart: "primary",
  line_chart: "primary",
  kpi_strip: "success",
  table: "default",
  interval_plot: "warning",
  text: "default",
};

export default function MetricPicker({ onAdd, usedMetricIds }: MetricPickerProps) {
  const [catalogue, setCatalogue] = useState<MetricCatalogueEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  useEffect(() => {
    fetchMetricCatalogue()
      .then(setCatalogue)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load metrics"))
      .finally(() => setLoading(false));
  }, []);

  const filtered = catalogue.filter(
    (m) =>
      m.title.toLowerCase().includes(search.toLowerCase()) ||
      m.description.toLowerCase().includes(search.toLowerCase())
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
      {loading && <CircularProgress size={20} sx={{ alignSelf: "center" }} />}
      {error && <Alert severity="error" sx={{ fontSize: 12 }}>{error}</Alert>}
      <Box sx={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: 1 }}>
        {filtered.map((m) => (
          <Box
            key={m.metric_id}
            sx={{
              border: "1px solid",
              borderColor: "divider",
              borderRadius: 1,
              p: 1,
              bgcolor: usedMetricIds.has(m.metric_id) ? "action.selected" : "background.paper",
            }}
          >
            <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
              <Box sx={{ flex: 1 }}>
                <Typography variant="caption" fontWeight={600} display="block">
                  {m.title}
                </Typography>
                <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.25 }}>
                  {m.description}
                </Typography>
                <Chip
                  label={m.output_type}
                  size="small"
                  color={OUTPUT_TYPE_COLOURS[m.output_type as TileType] ?? "default"}
                  sx={{ mt: 0.5, fontSize: 10, height: 18 }}
                />
              </Box>
              <Tooltip title={usedMetricIds.has(m.metric_id) ? "Already added" : "Add to template"}>
                <span>
                  <IconButton
                    size="small"
                    disabled={usedMetricIds.has(m.metric_id)}
                    onClick={() => onAdd(m)}
                  >
                    <AddCircleOutlineIcon fontSize="small" />
                  </IconButton>
                </span>
              </Tooltip>
            </Box>
          </Box>
        ))}
      </Box>
    </Box>
  );
}
