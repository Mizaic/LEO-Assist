"use client";

import { useEffect, useMemo, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
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

interface Props {
  open: boolean;
  onClose: () => void;
  rows: EncounterListItem[];
  minCombinedScore?: number;
  minVectorScore?: number;
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
        `1 result stands out as genuinely different (high uniqueness). ` +
        `The other ${duplicate} are very similar to each other -- ` +
        `they may be template letters or repeated entries. ` +
        `The isolated dot is likely the most clinically relevant. Click it to highlight it in the table.`,
    };
  }
  if (unique === 0 && duplicate >= 3) {
    return {
      severity: "warning",
      message:
        `All ${total} results are very similar to each other -- they may contain repeated template text. ` +
        `Enable "exclude near-duplicates" in the search filters to reduce noise.`,
    };
  }
  if (unique >= 3 && duplicate <= 1) {
    return {
      severity: "info",
      message:
        `Results are spread across the uniqueness axis -- each encounter has distinct content. ` +
        `Use the X/Y axes to focus on the highest-quality matches.`,
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

// ---- component -------------------------------------------------------------

export default function Score3DMap({
  open,
  onClose,
  rows,
  minCombinedScore,
  minVectorScore,
  onEncounterSelect,
}: Props) {
  const { scores, loading, error } = useUniqueness(rows, open);
  const { Plotly, loadErr } = usePlotly();

  // Only plot encounters that pass the applied thresholds
  const filteredRows = useMemo(() => {
    const cap = rows.slice(0, 500);
    return cap.filter((r) => {
      if (
        minCombinedScore != null &&
        typeof r.score === "number" &&
        r.score < minCombinedScore
      ) return false;
      if (
        minVectorScore != null &&
        typeof r.vector_score === "number" &&
        r.vector_score < minVectorScore
      ) return false;
      return true;
    });
  }, [rows, minCombinedScore, minVectorScore]);

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
    ? "X: keyword match  |  Y: meaning similarity  |  Z: coding completeness (uniqueness too similar to distinguish)"
    : `X: keyword match  |  Y: meaning similarity  |  Z: uniqueness (${zAxis.tickformat === ".1%" ? "0.1% precision" : "0-100%"}). Drag to spin. Scroll to zoom.`;

  const keptCount = filteredRows.length;
  const totalCount = Math.min(rows.length, 500);
  const isReady = Plotly && !loading && traces.length > 0;

  return (
    <Dialog open={open} onClose={onClose} maxWidth="lg" fullWidth>
      <DialogTitle sx={{ pb: 0.5 }}>
        <Stack direction="row" justifyContent="space-between" alignItems="center">
          <Stack>
            <Typography variant="h6" sx={{ fontWeight: 700, fontSize: "1rem" }}>
              3D score map
            </Typography>
            {minCombinedScore != null && (
              <Typography variant="caption" sx={{ color: "primary.main", fontWeight: 600 }}>
                Showing {keptCount} of {totalCount} results above your {Math.round(minCombinedScore * 100)}% cut-off
              </Typography>
            )}
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
            All results are very similar to each other (uniqueness below {Math.round(LOW_VARIANCE_THRESHOLD * 100)}%).
            Z axis shows coding completeness instead. Enable &quot;exclude near-duplicates&quot; in the search filters to reduce repetition.
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
          <PlotlyChart
            Plotly={Plotly}
            traces={traces}
            layout={layout}
            onPointClick={onEncounterSelect}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

// Minimum CSS-pixel distance the pointer must travel since the last accepted
// event before Plotly receives another one. Raise to slow rotation further.
const MIN_DRAG_PX = 5;

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
  useEffect(() => {
    const el = document.getElementById("score-3d-plot");
    if (!el) return;

    Plotly.newPlot(el, traces, layout, {
      responsive: true,
      displayModeBar: true,
      modeBarButtonsToRemove: ["toImage", "sendDataToCloud"],
      displaylogo: false,
    });

    if (onPointClick) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (el as any).on("plotly_click", (data: any) => {
        const encId = data?.points?.[0]?.customdata as string | undefined;
        if (encId) onPointClick(encId);
      });
    }

    // Distance-based rotation throttle.
    // Events are suppressed until the pointer has moved MIN_DRAG_PX pixels
    // from the last event that was allowed through.  This eliminates jitter
    // from tiny/accidental movements completely, while still feeling smooth
    // during deliberate drags.  Works for both mouse and touch/stylus
    // (pointermove fires for all device types).
    let dragging = false;
    let lastX = 0;
    let lastY = 0;

    const suppress = (e: Event) => e.stopImmediatePropagation();

    const onDown = (e: MouseEvent | PointerEvent) => {
      dragging = true;
      lastX = e.clientX;
      lastY = e.clientY;
    };
    const onUp = () => { dragging = false; };

    const onMove = (e: MouseEvent | PointerEvent) => {
      if (!dragging) return;
      const dx = e.clientX - lastX;
      const dy = e.clientY - lastY;
      if (dx * dx + dy * dy < MIN_DRAG_PX * MIN_DRAG_PX) {
        e.stopImmediatePropagation();
      } else {
        lastX = e.clientX;
        lastY = e.clientY;
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
      // Belt-and-braces: also suppress any residual pointer events on the
      // scene drag layer that Plotly attaches internally.
      el.querySelectorAll(".drag").forEach((layer) => {
        layer.addEventListener("pointermove", suppress, { capture: true });
      });
      Plotly.purge(el);
    };
  }, [Plotly, traces, layout]);

  return <Box id="score-3d-plot" sx={{ width: "100%", height: 480 }} />;
}
