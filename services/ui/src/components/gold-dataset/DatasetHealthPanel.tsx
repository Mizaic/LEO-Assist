"use client";

import { useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Collapse from "@mui/material/Collapse";
import Divider from "@mui/material/Divider";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import BuildIcon from "@mui/icons-material/Build";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import IconButton from "@mui/material/IconButton";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RTooltip,
  ReferenceLine,
  Cell,
  ResponsiveContainer,
} from "recharts";

// Minimum total span count per label needed for reliable training.
// The exporter uses an 80/20 train/dev split, so 30 total spans -> ~24 in
// training -- the practical floor for the frozen-ClinicalBERT linear head.
const MIN_SPANS_PER_LABEL = 30;
import {
  fetchLabelDistribution,
  fetchExportDiagnostics,
  type LabelDistribution,
  type ExportDiagnostics,
} from "@/lib/api/legacy";
import { FONT_SIZES } from "@/theme/tokens";
import { entityLabelColour } from "./goldDatasetUtils";

// -- Span-misaligned record list ---------------------------------------------
// Assertion filtering is intentionally disabled: the spancat model trains on
// (start, end, label) only -- assertion is not part of the training signal.
// ConText handles assertion detection post-extraction.  Only span-misaligned
// records (where surface text can't be matched in the sentence) need fixing.

interface MisalignedRecord {
  label_id: string;
  text: string;
  entities: Array<{ entity_text: string; label: string }>;
}

function groupMisaligned(diag: ExportDiagnostics): MisalignedRecord[] {
  const map = new Map<string, MisalignedRecord>();
  for (const item of diag.span_misaligned) {
    if (!map.has(item.label_id)) {
      map.set(item.label_id, {
        label_id: item.label_id,
        text: item.text ?? "",
        entities: [],
      });
    }
    map.get(item.label_id)!.entities.push({
      entity_text: item.entity_text,
      label: item.label,
    });
  }
  return Array.from(map.values());
}

function MisalignedList({
  diag,
  onOpenLabel,
}: {
  diag: ExportDiagnostics;
  onOpenLabel?: (labelId: string) => void;
}) {
  const records = groupMisaligned(diag);
  if (records.length === 0) return null;

  return (
    <Box>
      <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.75 }}>
        <WarningAmberIcon sx={{ fontSize: 15, color: "error.main" }} />
        <Typography sx={{ fontWeight: 600, fontSize: FONT_SIZES.subtitle }}>
          Span mismatch ({records.length} record{records.length !== 1 ? "s" : ""})
        </Typography>
        <Chip
          size="small"
          label={`${diag.summary.span_misaligned_count} entities`}
          color="error"
          sx={{ height: 18, fontSize: "0.68rem" }}
        />
      </Stack>

      <Box
        sx={{
          mb: 1.25,
          p: 1,
          bgcolor: "error.50",
          border: "1px solid",
          borderColor: "error.200",
          borderRadius: 1,
        }}
      >
        <Typography sx={{ fontSize: 11, color: "text.secondary" }}>
          The entity text no longer matches any span in the sentence — usually
          because the record was edited after coding. Open the record, delete
          the mismatched entity, then re-add it by highlighting the correct text.
        </Typography>
      </Box>

      <Stack spacing={0.75}>
        {records.map((rec) => (
          <Box
            key={rec.label_id}
            sx={{
              p: 1,
              border: "1px solid",
              borderColor: "error.200",
              borderLeft: "3px solid",
              borderLeftColor: "error.main",
              borderRadius: 1,
              bgcolor: "background.paper",
              cursor: onOpenLabel ? "pointer" : "default",
              transition: "box-shadow 0.12s",
              "&:hover": onOpenLabel
                ? { boxShadow: "0 2px 6px rgba(0,0,0,0.10)" }
                : undefined,
            }}
            onClick={() => onOpenLabel?.(rec.label_id)}
          >
            <Stack direction="row" alignItems="flex-start" justifyContent="space-between" spacing={1}>
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Typography
                  sx={{
                    fontSize: 11,
                    fontStyle: "italic",
                    color: "text.secondary",
                    mb: 0.5,
                    whiteSpace: "nowrap",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                  }}
                >
                  {rec.text || "(sentence not available)"}
                </Typography>
                <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                  {rec.entities.map((ent, i) => (
                    <Tooltip
                      key={i}
                      title={`"${ent.entity_text}" could not be found in the sentence text`}
                    >
                      <Chip
                        size="small"
                        label={`${ent.entity_text}${ent.label ? ` [${ent.label}]` : ""}`}
                        color="error"
                        variant="outlined"
                        sx={{ height: 20, fontSize: "0.68rem", maxWidth: 280 }}
                      />
                    </Tooltip>
                  ))}
                </Stack>
              </Box>
              {onOpenLabel && (
                <Tooltip title="Open this record to fix the span">
                  <IconButton
                    size="small"
                    color="error"
                    onClick={(e) => {
                      e.stopPropagation();
                      onOpenLabel(rec.label_id);
                    }}
                    sx={{ p: 0.4, flexShrink: 0 }}
                  >
                    <BuildIcon sx={{ fontSize: 15 }} />
                  </IconButton>
                </Tooltip>
              )}
            </Stack>
          </Box>
        ))}
      </Stack>
    </Box>
  );
}

// -- Main component ----------------------------------------------------------

export default function DatasetHealthPanel({
  onOpenLabel,
  onLabelFilter,
  activeLabel,
  refreshKey = 0,
}: {
  onOpenLabel?: (labelId: string) => void;
  /** Called with a label name when a chart bar is clicked; null to clear. */
  onLabelFilter?: (label: string | null) => void;
  /** Currently active label filter (bar will be highlighted). */
  activeLabel?: string | null;
  /** Increment to trigger a re-fetch of diagnostics (e.g. after a label edit). */
  refreshKey?: number;
}) {
  const [dist, setDist] = useState<LabelDistribution | null>(null);
  const [diag, setDiag] = useState<ExportDiagnostics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([fetchLabelDistribution(), fetchExportDiagnostics()])
      .then(([d, diag]) => {
        if (!cancelled) { setDist(d); setDiag(diag); }
      })
      .catch((e) => { if (!cancelled) setError(String(e?.message ?? e)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [refreshKey]);

  const totalNotReady = diag?.summary.span_misaligned_count ?? 0;

  return (
    <Box
      sx={{
        mb: 2,
        border: "1px solid",
        borderColor: "divider",
        borderRadius: 1.5,
        overflow: "hidden",
      }}
    >
      {/* Header */}
      <Stack
        direction="row"
        alignItems="center"
        justifyContent="space-between"
        sx={{ px: 1.5, py: 1, bgcolor: "grey.50", cursor: "pointer" }}
        onClick={() => setExpanded((e) => !e)}
      >
        <Stack direction="row" alignItems="center" spacing={1}>
          <Typography sx={{ fontWeight: 600, fontSize: FONT_SIZES.subtitle }}>
            Dataset health
          </Typography>
          {!loading && dist && (
            <Chip
              size="small"
              label={`${dist.total_entities} entity spans`}
              sx={{ height: 18, fontSize: "0.68rem" }}
            />
          )}
          {!loading && totalNotReady > 0 && (
            <Chip
              size="small"
              label={`${totalNotReady} not ready`}
              color="warning"
              sx={{ height: 18, fontSize: "0.68rem" }}
            />
          )}
        </Stack>
        <IconButton size="small" sx={{ p: 0.25 }}>
          {expanded ? <ExpandLessIcon fontSize="small" /> : <ExpandMoreIcon fontSize="small" />}
        </IconButton>
      </Stack>

      <Collapse in={expanded}>
        <Box sx={{ p: 1.5 }}>
          {error && (
            <Alert severity="error" sx={{ mb: 1.5, fontSize: FONT_SIZES.body }}>
              {error}
            </Alert>
          )}

          {/* Label distribution chart */}
          <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1 }}>
            <Typography sx={{ fontWeight: 600, fontSize: FONT_SIZES.subtitle }}>
              Label distribution
            </Typography>
            {activeLabel && onLabelFilter && (
              <Chip
                size="small"
                label={activeLabel.replace(/_/g, " ")}
                onDelete={() => onLabelFilter(null)}
                sx={{
                  height: 20,
                  fontSize: "0.68rem",
                  bgcolor: entityLabelColour(activeLabel),
                  color: "#fff",
                  "& .MuiChip-deleteIcon": { color: "rgba(255,255,255,0.7)" },
                }}
              />
            )}
          </Stack>

          {loading ? (
            <Skeleton variant="rounded" height={Math.max(80, 10 * 22)} />
          ) : dist && dist.distribution.length > 0 ? (
            <ResponsiveContainer
              width="100%"
              height={Math.max(80, dist.distribution.length * 22)}
            >
              <BarChart
                data={dist.distribution}
                layout="vertical"
                margin={{ left: 8, right: 56, top: 2, bottom: 2 }}
              >
                <CartesianGrid strokeDasharray="3 3" horizontal={false} opacity={0.3} />
                <XAxis type="number" tick={{ fontSize: 11 }} allowDecimals={false} />
                <YAxis
                  type="category"
                  dataKey="label"
                  tick={({ x, y, payload }) => {
                    const label = String(payload.value ?? "");
                    const count = dist.distribution.find((d) => d.label === label)?.count ?? 0;
                    const below = count < MIN_SPANS_PER_LABEL;
                    return (
                      <text
                        x={x}
                        y={y}
                        dy={4}
                        textAnchor="end"
                        fontSize={11}
                        fill={below ? "#ed6c02" : "#555"}
                      >
                        {below ? `⚠ ${label}` : label}
                      </text>
                    );
                  }}
                  width={150}
                />
                <RTooltip
                  formatter={(v: number, _name, props) => {
                    const label = (props.payload as { label?: string })?.label ?? "";
                    const isActive = activeLabel === label;
                    const below = (v as number) < MIN_SPANS_PER_LABEL;
                    const suffix = isActive ? " (filtered)" : below ? " — below minimum" : "";
                    return [`${v} spans${suffix}`, "Count"];
                  }}
                  cursor={{ fill: "rgba(0,0,0,0.04)" }}
                />
                <ReferenceLine
                  x={MIN_SPANS_PER_LABEL}
                  stroke="#ed6c02"
                  strokeDasharray="5 3"
                  strokeWidth={1.5}
                  label={{
                    value: `Min ${MIN_SPANS_PER_LABEL}`,
                    position: "right",
                    fontSize: 10,
                    fill: "#ed6c02",
                  }}
                />
                <Bar
                  dataKey="count"
                  maxBarSize={16}
                  radius={[0, 3, 3, 0]}
                  cursor={onLabelFilter ? "pointer" : "default"}
                  onClick={
                    onLabelFilter
                      ? (data: { label?: string }) => {
                          const clicked = data.label ?? "";
                          onLabelFilter(activeLabel === clicked ? null : clicked);
                        }
                      : undefined
                  }
                >
                  {dist.distribution.map((row) => {
                    const below = row.count < MIN_SPANS_PER_LABEL;
                    const dimmed = activeLabel && activeLabel !== row.label;
                    return (
                      <Cell
                        key={row.label}
                        fill={below ? "#bdbdbd" : entityLabelColour(row.label)}
                        opacity={dimmed ? 0.25 : 1}
                      />
                    );
                  })}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <Typography sx={{ fontSize: FONT_SIZES.body, color: "text.secondary" }}>
              No entity data yet.
            </Typography>
          )}
          {dist && dist.distribution.length > 0 && (
            <Typography sx={{ fontSize: 10, color: "text.disabled", mt: 0.5 }}>
              {activeLabel
                ? "Click the bar again or clear the chip to remove the filter."
                : `Dashed line = minimum ${MIN_SPANS_PER_LABEL} spans for reliable training. Grey bars need more examples. Click a bar to filter.`}
            </Typography>
          )}

          {/* Span-misaligned section */}
          {!loading && diag && totalNotReady > 0 && (
            <>
              <Divider sx={{ my: 1.5 }} />
              <MisalignedList diag={diag} onOpenLabel={onOpenLabel} />
            </>
          )}

          {!loading && diag && totalNotReady === 0 && (
            <Typography sx={{ fontSize: 11, color: "success.dark", mt: 1 }}>
              All verified records are ready for training.
            </Typography>
          )}
        </Box>
      </Collapse>
    </Box>
  );
}
