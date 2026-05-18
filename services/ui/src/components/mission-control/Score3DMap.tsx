/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-5312F884
 *   DI: DI-AA1F5F5B
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-5312F884")
 */
"use client";

import React, { useEffect, useMemo, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import Slider from "@mui/material/Slider";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import CloseIcon from "@mui/icons-material/Close";
import type { EncounterListItem } from "@/lib/missionControlApi";
import { fetchEncounterUniqueness } from "@/lib/missionControlApi";

// Plotly loaded dynamically to keep it out of the initial bundle (~3MB).
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type PlotlyModule = any;

const TYPE_COLOR: Record<string, string> = {
  keyword: "#4F46E5",
  hybrid: "#7C3AED",
  semantic: "#0891B2",
  none: "#94A3B8",
};

const TYPE_LABEL: Record<string, string> = {
  keyword: "Keyword hit",
  hybrid: "Keyword + meaning",
  semantic: "Meaning only",
  none: "Unclassified",
};

// Threshold below which we consider uniqueness variance too small to be useful
// and fall back to coded_norm on the Z axis.
const LOW_VARIANCE_THRESHOLD = 0.05;
const SHAPE_HIGH_THRESHOLD = 0.65;
const SHAPE_LOW_THRESHOLD = 0.35;

type ShapeBucket = "lowYHighX" | "lowXHighY" | "highYHighX" | "other";

const SHAPE_META: Record<ShapeBucket, { label: string; tooltip: string; color: string }> = {
  lowYHighX: {
    label: "Keyword match only",
    tooltip: "These notes use your search words, but the meaning match is weak. They may be false hits.",
    color: "#5C6BC0",
  },
  lowXHighY: {
    label: "Meaning match only",
    tooltip: "These notes mean the same thing but use different words. Good for finding notes you would miss with keyword search alone.",
    color: "#00ACC1",
  },
  highYHighX: {
    label: "Best matches",
    tooltip: "Strong word match and strong meaning match. These are usually your most relevant notes.",
    color: "#43A047",
  },
  other: {
    label: "Mixed",
    tooltip: "Moderate word and meaning match. Worth reviewing alongside the other groups.",
    color: "#78909C",
  },
};

export interface ApplyParams {
  minCombinedScore: number;
  minVectorScore: number;
  requireKeywordAnchor: boolean;
  excludeNearDuplicates: boolean;
  nearDuplicateThreshold: number;
}

interface FilterState {
  minX: number;
  minY: number;
  anchor: boolean;
  dedup: boolean;
  dedupThreshold: number;
}

interface Props {
  open: boolean;
  onClose: () => void;
  rows: EncounterListItem[];
  minCombinedScore?: number;
  minVectorScore?: number;
  requireKeywordAnchor?: boolean;
  excludeNearDuplicates?: boolean;
  nearDuplicateThreshold?: number;
  searching?: boolean;
  onApplyFilters?: (p: ApplyParams) => void;
  onEncounterSelect?: (encounterId: string) => void;
}

// ---- hooks -----------------------------------------------------------------

function useUniqueness(rows: EncounterListItem[], open: boolean) {
  const [scores, setScores] = useState<Map<string, number>>(new Map());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || rows.length === 0) { setScores(new Map()); return; }
    setLoading(true);
    setError(null);
    const ids = rows.slice(0, 500).map((r) => r.encounter_id);
    fetchEncounterUniqueness(ids)
      .then((items) => setScores(new Map(items.map((i) => [i.encounter_id, i.uniqueness_score]))))
      .catch(() => setError("Could not load similarity data. Showing coding completeness on Z axis."))
      .finally(() => setLoading(false));
  }, [open, rows]);

  return { scores, loading, error };
}

function usePlotly() {
  const [Plotly, setPlotly] = useState<PlotlyModule | null>(null);
  const [loadErr, setLoadErr] = useState(false);
  useEffect(() => {
    import("plotly.js-dist-min")
      .then((m) => setPlotly(m.default ?? m))
      .catch(() => setLoadErr(true));
  }, []);
  return { Plotly, loadErr };
}

// ---- helpers ---------------------------------------------------------------

interface Pattern {
  severity: "info" | "warning";
  message: string;
}

function detectPattern(
  rows: EncounterListItem[],
  scores: Map<string, number>
): Pattern | null {
  if (rows.length === 0 || scores.size === 0) return null;
  const vals = rows.map((r) => scores.get(r.encounter_id) ?? 0);
  const unique = vals.filter((v) => v > 0.3).length;
  const duplicate = vals.filter((v) => v < 0.05).length;
  const total = rows.length;
  if (unique === 1 && duplicate >= 3) {
    return {
      severity: "info",
      message:
        `1 note stands out as genuinely different. ` +
        `The other ${duplicate} look nearly the same -- they may be template letters or repeated entries. ` +
        `The isolated dot is likely the most useful. Click it to open that note.`,
    };
  }
  if (unique === 0 && duplicate >= 3) {
    return {
      severity: "warning",
      message:
        `All ${total} notes look nearly the same. They may be repeated template entries. ` +
        `Turn on "exclude repeated notes" in the filters to remove them.`,
    };
  }
  if (unique >= 3 && duplicate <= 1) {
    return {
      severity: "info",
      message:
        `Each note has different content -- good variety in your results. ` +
        `Use the filter chips above to focus on the notes most likely to be relevant.`,
    };
  }
  return null;
}

function zAxisConfig(
  values: number[],
  fallback: boolean
): { range: [number, number]; tickformat: string; title: string } {
  if (fallback || values.length === 0) {
    return { range: [0, 1], tickformat: ".0%", title: "Coding completeness" };
  }
  const hi = Math.max(...values);
  const lo = Math.min(...values);
  // Zoom in: show tight range with 0.1% precision when values cluster near 0
  const pad = Math.max((hi - lo) * 0.5, 0.001);
  const range: [number, number] = [Math.max(0, lo - pad), Math.min(1, hi + pad)];
  return { range, tickformat: ".1%", title: "How unique" };
}

function getAxisScores(row: EncounterListItem): { x: number; y: number } {
  return {
    x: row.rank_features?.fulltext_norm ?? row.score ?? 0,
    y: row.rank_features?.vector_norm ?? row.vector_score ?? 0,
  };
}

function classifyShape(row: EncounterListItem): ShapeBucket {
  const { x, y } = getAxisScores(row);
  const highX = x >= SHAPE_HIGH_THRESHOLD;
  const lowX = x <= SHAPE_LOW_THRESHOLD;
  const highY = y >= SHAPE_HIGH_THRESHOLD;
  const lowY = y <= SHAPE_LOW_THRESHOLD;
  if (lowY && highX) return "lowYHighX";
  if (lowX && highY) return "lowXHighY";
  if (highY && highX) return "highYHighX";
  return "other";
}

function shapeCounts(rows: EncounterListItem[]): Record<ShapeBucket, number> {
  const counts: Record<ShapeBucket, number> = {
    lowYHighX: 0,
    lowXHighY: 0,
    highYHighX: 0,
    other: 0,
  };
  for (const row of rows) {
    counts[classifyShape(row)] += 1;
  }
  return counts;
}

// ---- filter controls -------------------------------------------------------

interface Filter3DControlsProps {
  state: FilterState;
  keptCount: number;
  hasChanges: boolean;
  onChange: (patch: Partial<FilterState>) => void;
  onApply?: () => void;
}

function Filter3DControls({ state, keptCount, hasChanges, onChange, onApply }: Filter3DControlsProps) {
  return (
    <Box sx={{ p: 1.5, border: "1px solid", borderColor: "divider", borderRadius: 1.5, bgcolor: "background.paper", mb: 1 }}>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
        Adjust filters — the plot updates immediately. Click &quot;Apply to search&quot; to re-run.
      </Typography>
      <Stack spacing={1}>
        <Stack direction="row" alignItems="center" spacing={1.5}>
          <Typography variant="caption" sx={{ minWidth: 110, color: "text.secondary" }}>Keyword match (X)</Typography>
          <Slider size="small" min={0} max={1} step={0.05} value={state.minX}
            onChange={(_, v) => onChange({ minX: v as number })} sx={{ flex: 1 }} />
          <Typography variant="caption" sx={{ minWidth: 38, textAlign: "right", fontWeight: 600 }}>
            {state.minX > 0 ? `${Math.round(state.minX * 100)}%+` : "off"}
          </Typography>
        </Stack>
        <Stack direction="row" alignItems="center" spacing={1.5}>
          <Typography variant="caption" sx={{ minWidth: 110, color: "text.secondary" }}>Meaning match (Y)</Typography>
          <Slider size="small" min={0} max={1} step={0.05} value={state.minY}
            onChange={(_, v) => onChange({ minY: v as number })} sx={{ flex: 1 }} />
          <Typography variant="caption" sx={{ minWidth: 38, textAlign: "right", fontWeight: 600 }}>
            {state.minY > 0 ? `${Math.round(state.minY * 100)}%+` : "off"}
          </Typography>
        </Stack>
        <Divider />
        <Stack direction="row" alignItems="center" justifyContent="space-between">
          <Typography variant="caption" color="text.secondary">Must contain search word (keyword anchor)</Typography>
          <Switch size="small" checked={state.anchor} onChange={(e) => onChange({ anchor: e.target.checked })} />
        </Stack>
        <Stack direction="row" alignItems="center" justifyContent="space-between">
          <Typography variant="caption" color="text.secondary">Remove repeated notes</Typography>
          <Switch size="small" checked={state.dedup} onChange={(e) => onChange({ dedup: e.target.checked })} />
        </Stack>
        {state.dedup && (
          <Stack direction="row" alignItems="center" spacing={1.5}>
            <Typography variant="caption" sx={{ minWidth: 110, color: "text.secondary" }}>Similarity cut-off</Typography>
            <Slider size="small" min={0.80} max={0.999} step={0.01} value={state.dedupThreshold}
              onChange={(_, v) => onChange({ dedupThreshold: v as number })} sx={{ flex: 1 }} />
            <Typography variant="caption" sx={{ minWidth: 38, textAlign: "right", fontWeight: 600 }}>
              {Math.round(state.dedupThreshold * 100)}%
            </Typography>
          </Stack>
        )}
        {onApply && (
          <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ pt: 0.5 }}>
            <Typography variant="caption" color="text.secondary">{keptCount} notes match these filters</Typography>
            <Chip label={hasChanges ? "Apply to search" : "Applied"} size="small"
              color={hasChanges ? "primary" : "default"}
              variant={hasChanges ? "filled" : "outlined"}
              onClick={hasChanges ? onApply : undefined}
              sx={{ cursor: hasChanges ? "pointer" : "default" }}
            />
          </Stack>
        )}
      </Stack>
    </Box>
  );
}

// ---- component -------------------------------------------------------------

function initialFilter(p: Omit<Props, "open" | "onClose" | "rows" | "onEncounterSelect" | "onApplyFilters">): FilterState {
  return {
    minX: p.minCombinedScore ?? 0,
    minY: p.minVectorScore ?? 0,
    anchor: p.requireKeywordAnchor ?? false,
    dedup: p.excludeNearDuplicates ?? false,
    dedupThreshold: p.nearDuplicateThreshold ?? 0.95,
  };
}

export default function Score3DMap({
  open,
  onClose,
  rows,
  minCombinedScore,
  minVectorScore,
  requireKeywordAnchor,
  excludeNearDuplicates,
  nearDuplicateThreshold,
  searching = false,
  onApplyFilters,
  onEncounterSelect,
}: Props) {
  const { scores, loading, error } = useUniqueness(rows, open);
  const { Plotly, loadErr } = usePlotly();
  const [shapeFilter, setShapeFilter] = useState<ShapeBucket | "all">("all");
  const [filters, setFilters] = useState<FilterState>(() =>
    initialFilter({ minCombinedScore, minVectorScore, requireKeywordAnchor, excludeNearDuplicates, nearDuplicateThreshold })
  );

  // Sync local filter state when dialog opens or parent props change
  useEffect(() => {
    if (open) {
      setShapeFilter("all");
      setFilters(initialFilter({ minCombinedScore, minVectorScore, requireKeywordAnchor, excludeNearDuplicates, nearDuplicateThreshold }));
    }
  }, [open, minCombinedScore, minVectorScore, requireKeywordAnchor, excludeNearDuplicates, nearDuplicateThreshold]);

  const hasChanges =
    filters.minX !== (minCombinedScore ?? 0) ||
    filters.minY !== (minVectorScore ?? 0) ||
    filters.anchor !== (requireKeywordAnchor ?? false) ||
    filters.dedup !== (excludeNearDuplicates ?? false) ||
    filters.dedupThreshold !== (nearDuplicateThreshold ?? 0.95);

  // Filter by local X/Y thresholds — updates the plot immediately as sliders move
  const thresholdRows = useMemo(() => {
    return rows.slice(0, 500).filter((r) => {
      const x = r.rank_features?.fulltext_norm ?? r.score ?? 0;
      const y = r.rank_features?.vector_norm ?? r.vector_score ?? 0;
      if (x < filters.minX) return false;
      if (filters.minY > 0 && y < filters.minY) return false;
      return true;
    });
  }, [rows, filters.minX, filters.minY]);

  const countsByShape = useMemo(() => shapeCounts(thresholdRows), [thresholdRows]);

  const filteredRows = useMemo(() => {
    if (shapeFilter === "all") return thresholdRows;
    return thresholdRows.filter((row) => classifyShape(row) === shapeFilter);
  }, [thresholdRows, shapeFilter]);

  // Decide whether uniqueness has enough variance to be useful on Z
  const uniquenessValues = useMemo(
    () => filteredRows.map((r) => scores.get(r.encounter_id) ?? null).filter((v): v is number => v !== null),
    [filteredRows, scores]
  );
  const maxUniqueness = uniquenessValues.length ? Math.max(...uniquenessValues) : 0;
  const useFallbackZ = scores.size > 0 && maxUniqueness < LOW_VARIANCE_THRESHOLD;

  const zAxis = useMemo(
    () => zAxisConfig(uniquenessValues, useFallbackZ),
    [uniquenessValues, useFallbackZ]
  );

  const pattern = useMemo(
    () => detectPattern(filteredRows, scores),
    [filteredRows, scores]
  );

  const traces = useMemo(() => {
    const groups: Record<string, EncounterListItem[]> = {};
    for (const row of filteredRows) {
      const t = row.match_type ?? "none";
      if (!groups[t]) groups[t] = [];
      groups[t]!.push(row);
    }
    return Object.entries(groups).map(([type, items]) => {
      const zVals = items.map((r) => {
        if (useFallbackZ) return r.rank_features?.coded_norm ?? 0;
        return scores.get(r.encounter_id) ?? maxUniqueness / 2;
      });
      const snippet = (r: EncounterListItem) => {
        const t = r.text ?? "";
        return t.length > 90 ? t.slice(0, 90) + "…" : t || "(no text)";
      };
      return {
        type: "scatter3d" as const,
        mode: "markers" as const,
        name: TYPE_LABEL[type] ?? type,
        x: items.map((r) => r.rank_features?.fulltext_norm ?? r.score ?? 0),
        y: items.map((r) => r.rank_features?.vector_norm ?? r.vector_score ?? 0),
        z: zVals,
        customdata: items.map((r) => r.encounter_id),
        text: items.map(
          (r) =>
            `<b>${r.encounter_date ?? "Unknown date"}</b><br>` +
            `Match: ${Math.round((r.score ?? 0) * 100)}% &nbsp;` +
            `Meaning: ${Math.round(((r.rank_features?.vector_norm ?? r.vector_score ?? 0)) * 100)}%<br>` +
            `Unique: ${Math.round((scores.get(r.encounter_id) ?? 0) * 100)}%<br>` +
            `<i>${snippet(r)}</i>`
        ),
        hovertemplate: "%{text}<extra>%{fullData.name}</extra>",
        marker: {
          size: 8,
          color: TYPE_COLOR[type] ?? "#94A3B8",
          opacity: 0.85,
          line: { color: "rgba(255,255,255,0.4)", width: 1 },
        },
      };
    });
  }, [filteredRows, scores, useFallbackZ, maxUniqueness]);

  const layout = useMemo(
    () => ({
      scene: {
        xaxis: {
          title: "Keyword match",
          range: [0, 1],
          tickformat: ".0%",
          gridcolor: "#E2E8F0",
        },
        yaxis: {
          title: "Meaning match",
          range: [0, 1],
          tickformat: ".0%",
          gridcolor: "#E2E8F0",
        },
        zaxis: {
          title: zAxis.title,
          range: zAxis.range,
          tickformat: zAxis.tickformat,
          gridcolor: "#E2E8F0",
        },
        camera: { eye: { x: 2.0, y: -1.8, z: 1.2 }, up: { x: 0, y: 0, z: 1 } },
        dragmode: "turntable",
        bgcolor: "#F8FAFC",
        aspectmode: "cube" as const,
      },
      paper_bgcolor: "#F8FAFC",
      margin: { l: 0, r: 0, t: 0, b: 0 },
      legend: {
        x: 0.01,
        y: 0.99,
        bgcolor: "rgba(255,255,255,0.9)",
        bordercolor: "#E2E8F0",
        borderwidth: 1,
        font: { size: 11 },
      },
      font: { family: "Inter, system-ui, sans-serif", size: 11, color: "#475569" },
    }),
    [zAxis]
  );

  const subTitle = useFallbackZ
    ? "Each dot is one patient note. Left-right = word match. Front-back = meaning match. Height = how many codes the note has."
    : "Each dot is one patient note. Left-right = word match. Front-back = meaning match. Height = how different the note is from the others. Drag to spin. Scroll to zoom.";

  const keptCount = filteredRows.length;
  const thresholdCount = thresholdRows.length;
  const totalCount = Math.min(rows.length, 500);
  const isReady = Plotly && !loading && traces.length > 0;
  const shapeLabel =
    shapeFilter === "all" ? null : SHAPE_META[shapeFilter].label;


  return (
    <Dialog open={open} onClose={onClose} maxWidth="lg" fullWidth>
      <DialogTitle sx={{ pb: 0.5 }}>
        <Stack direction="row" justifyContent="space-between" alignItems="center">
          <Stack>
            <Typography variant="h6" sx={{ fontWeight: 700, fontSize: "1rem" }}>
              3D score map
            </Typography>
            <Typography variant="caption" sx={{ color: "primary.main", fontWeight: 600 }}>
              {shapeLabel
                ? `Showing ${keptCount} of ${thresholdCount} notes in "${shapeLabel}"`
                : minCombinedScore != null
                  ? `Showing ${keptCount} of ${totalCount} notes above your ${Math.round(minCombinedScore * 100)}% quality cut-off`
                  : `Showing ${keptCount} notes`}
            </Typography>
          </Stack>
          <IconButton size="small" onClick={onClose}>
            <CloseIcon fontSize="small" />
          </IconButton>
        </Stack>
        <Typography variant="caption" color="text.secondary" sx={{ mt: 0.25, display: "block" }}>
          {subTitle}
        </Typography>
      </DialogTitle>

      <DialogContent sx={{ p: 1, pt: "8px !important" }}>
        <Filter3DControls
          state={filters}
          keptCount={filteredRows.length}
          hasChanges={hasChanges}
          onChange={(patch) => setFilters((prev) => ({ ...prev, ...patch }))}
          onApply={onApplyFilters ? () => onApplyFilters({
            minCombinedScore: filters.minX,
            minVectorScore: filters.minY,
            requireKeywordAnchor: filters.anchor,
            excludeNearDuplicates: filters.dedup,
            nearDuplicateThreshold: filters.dedupThreshold,
          }) : undefined}
        />
        <Box
          sx={{
            mb: 1,
            p: 1,
            border: "1px solid",
            borderColor: "divider",
            borderRadius: 1.5,
            bgcolor: "background.paper",
          }}
        >
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.75 }}>
            Filter notes by match type. Click a group to highlight only those dots.
          </Typography>
          <Stack direction="row" spacing={0.75} sx={{ flexWrap: "wrap" }} useFlexGap>
            <Chip
              size="small"
              label={`All notes (${thresholdRows.length})`}
              variant={shapeFilter === "all" ? "filled" : "outlined"}
              color={shapeFilter === "all" ? "primary" : "default"}
              onClick={() => setShapeFilter("all")}
            />
            {(["lowYHighX", "lowXHighY", "highYHighX"] as const).map((bucket) => (
              <Tooltip key={bucket} title={SHAPE_META[bucket].tooltip} arrow placement="top">
                <Chip
                  size="small"
                  label={`${SHAPE_META[bucket].label} (${countsByShape[bucket]})`}
                  variant={shapeFilter === bucket ? "filled" : "outlined"}
                  onClick={() => setShapeFilter(bucket)}
                  sx={{
                    borderColor: SHAPE_META[bucket].color,
                    color: shapeFilter === bucket ? "#fff" : SHAPE_META[bucket].color,
                    bgcolor: shapeFilter === bucket ? SHAPE_META[bucket].color : undefined,
                    "&:hover": { bgcolor: `${SHAPE_META[bucket].color}22` },
                  }}
                />
              </Tooltip>
            ))}
          </Stack>
        </Box>
        {pattern && (
          <Alert severity={pattern.severity} sx={{ mb: 1, fontSize: "0.76rem" }}>
            {pattern.message}
          </Alert>
        )}
        {error && (
          <Alert severity="warning" sx={{ mb: 1, fontSize: "0.76rem" }}>{error}</Alert>
        )}
        {useFallbackZ && !loading && (
          <Alert severity="info" sx={{ mb: 1, fontSize: "0.76rem" }}>
            All notes are very similar to each other, so the height axis now shows how many codes each note has instead.
            To remove repeated notes, turn on &quot;exclude repeated notes&quot; in the search filters.
          </Alert>
        )}
        {loadErr && (
          <Alert severity="error" sx={{ mb: 1 }}>Could not load 3D chart library.</Alert>
        )}
        {!isReady ? (
          <Stack alignItems="center" justifyContent="center" sx={{ height: 480 }}>
            <CircularProgress size={32} />
            <Typography variant="caption" color="text.secondary" sx={{ mt: 1 }}>
              {loading ? "Computing similarity scores..." : "Loading 3D chart..."}
            </Typography>
          </Stack>
        ) : (
          <Box sx={{ position: "relative" }}>
            <PlotlyChart
              Plotly={Plotly}
              traces={traces}
              layout={layout}
              onPointClick={onEncounterSelect}
            />
            {searching && (
              <Stack
                alignItems="center"
                justifyContent="center"
                spacing={1}
                sx={{
                  position: "absolute",
                  inset: 0,
                  bgcolor: "rgba(248,250,252,0.80)",
                  borderRadius: 1,
                  zIndex: 10,
                }}
              >
                <CircularProgress size={28} />
                <Typography variant="caption" color="text.secondary">
                  Re-running search with new filters...
                </Typography>
              </Stack>
            )}
          </Box>
        )}
      </DialogContent>
    </Dialog>
  );
}

// Minimum CSS-pixel distance the pointer must travel since the last accepted
// event before Plotly receives another one. Raise to slow rotation further.
const MIN_DRAG_PX = 5;

const PLOTLY_CONFIG = {
  responsive: true,
  displayModeBar: true,
  modeBarButtonsToRemove: ["toImage", "sendDataToCloud"],
  displaylogo: false,
} as const;

function usePlotPointerThrottle(elRef: React.RefObject<HTMLDivElement | null>) {
  useEffect(() => {
    const el = elRef.current;
    if (!el) return;
    let dragging = false;
    let lastX = 0;
    let lastY = 0;
    const onDown = (e: MouseEvent | PointerEvent) => {
      dragging = true; lastX = e.clientX; lastY = e.clientY;
    };
    const onUp = () => { dragging = false; };
    const onMove = (e: MouseEvent | PointerEvent) => {
      if (!dragging) return;
      const dx = e.clientX - lastX;
      const dy = e.clientY - lastY;
      if (dx * dx + dy * dy < MIN_DRAG_PX * MIN_DRAG_PX) {
        e.stopImmediatePropagation();
      } else {
        lastX = e.clientX; lastY = e.clientY;
      }
    };
    el.addEventListener("mousedown", onDown, { capture: true });
    el.addEventListener("pointerdown", onDown, { capture: true });
    window.addEventListener("mouseup", onUp, { capture: true });
    window.addEventListener("pointerup", onUp, { capture: true });
    el.addEventListener("mousemove", onMove, { capture: true });
    el.addEventListener("pointermove", onMove, { capture: true });
    return () => {
      el.removeEventListener("mousedown", onDown, { capture: true });
      el.removeEventListener("pointerdown", onDown, { capture: true });
      window.removeEventListener("mouseup", onUp, { capture: true });
      window.removeEventListener("pointerup", onUp, { capture: true });
      el.removeEventListener("mousemove", onMove, { capture: true });
      el.removeEventListener("pointermove", onMove, { capture: true });
    };
  });
}

function PlotlyChart({
  Plotly,
  traces,
  layout,
  onPointClick,
}: {
  Plotly: PlotlyModule;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  traces: any[];
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  layout: any;
  onPointClick?: (encounterId: string) => void;
}) {
  const elRef = React.useRef<HTMLDivElement | null>(null);
  const initialised = React.useRef(false);

  usePlotPointerThrottle(elRef);

  useEffect(() => {
    const el = elRef.current;
    if (!el) return;

    // Use react() for updates to avoid destroy/rebuild cycles that leave
    // in-flight Plotly animation frames referencing a purged container
    // (_redrawFromAutoMarginCount TypeError).
    const plotFn = initialised.current ? Plotly.react : Plotly.newPlot;
    try {
      plotFn(el, traces, layout, PLOTLY_CONFIG);
      initialised.current = true;
    } catch {
      return;
    }

    if (onPointClick) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (el as any).on("plotly_click", (data: any) => {
        const encId = data?.points?.[0]?.customdata as string | undefined;
        if (encId) onPointClick(encId);
      });
    }

    return () => {
      initialised.current = false;
      try { Plotly.purge(el); } catch { /* already purged */ }
    };
  }, [Plotly, traces, layout, onPointClick]);

  return (
    <Box
      ref={elRef}
      sx={{ width: "100%", height: 480 }}
    />
  );
}
