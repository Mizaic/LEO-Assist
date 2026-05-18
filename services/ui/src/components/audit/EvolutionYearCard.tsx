/**
 * Atlas trace:
 *   DO: DO-2E8544FD
 *   DI: DI-C65FD45B
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2E8544FD")
 *
 * Generic year card for the /care/audit "year-on-year evolution"
 * sections. All non-radar sections render a 4-card grid using this
 * component (2018 NCDA baseline + currentYear-2 / -1 / current).
 *
 * Each card shows:
 *   - year label (e.g. "2018", "2024")
 *   - sample-size chip (n = ...) on live years; "2018 NCDA" badge on baseline
 *   - one-line headline KPI in the section's accent colour
 *   - optional sub-label, optional secondary KPI
 *   - optional dashed 2018 baseline tick on top of the headline value
 *     so the year-over-year drift is immediately visible
 *   - optional zoom button that opens a detail dialog with the full chart
 *
 * The card encapsulates the four sparse-data states the audit report
 * cares about (loading / no data / low sample / baseline-only) so each
 * section can stay focused on its own metric.
 */
"use client";

import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import Skeleton from "@mui/material/Skeleton";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import OpenInFullIcon from "@mui/icons-material/OpenInFull";
import type { ReactNode } from "react";

const C_BENCH18 = "#92400E";
const DEFAULT_LOW_SAMPLE_THRESHOLD = 20;

export interface EvolutionYearCardProps {
  yearLabel: string;
  /** Sample size for the live card; omitted on the 2018 baseline card. */
  totalN?: number;
  /** Headline value, e.g. "65%" or "4.2 days". `null` -> "--". */
  headlineValue: string | null;
  /** Optional smaller second value rendered next to the headline. */
  secondaryValue?: string | null;
  /** Sub-label printed below the value, e.g. "median" or "with delay". */
  headlineSubLabel?: string;
  /** Tiny caption underneath the year, e.g. "Live", "Baseline". */
  caption?: string;
  /** Accent colour applied to the headline value. */
  accentColor?: string;
  /** When true, render the 2018 baseline chip + footnote. */
  isBaseline?: boolean;
  loading?: boolean;
  error?: string | null;
  /** Threshold below which the card shows a "limited sample" warning. */
  lowSampleThreshold?: number;
  /** Italic footnote displayed only on the 2018 baseline card. */
  baselineFootnote?: string;
  /** Opens a detail dialog for the full chart. Only rendered when set. */
  onZoom?: () => void;
  /** Optional accessible label override for the zoom button. */
  zoomAriaLabel?: string;
  /** Slot below the headline -- e.g. a small bar chart, sparkline, or breakdown. */
  children?: ReactNode;
}

export default function EvolutionYearCard({
  yearLabel,
  totalN,
  headlineValue,
  secondaryValue,
  headlineSubLabel,
  caption,
  accentColor = "#1D4ED8",
  isBaseline = false,
  loading = false,
  error = null,
  lowSampleThreshold = DEFAULT_LOW_SAMPLE_THRESHOLD,
  baselineFootnote,
  onZoom,
  zoomAriaLabel,
  children,
}: EvolutionYearCardProps) {
  const showN = !isBaseline && totalN != null;
  const isEmpty =
    !loading && !error && !isBaseline && (totalN ?? 0) === 0;
  const isLowSample =
    !loading &&
    !error &&
    !isBaseline &&
    (totalN ?? 0) > 0 &&
    (totalN ?? 0) < lowSampleThreshold;

  const resolvedCaption =
    caption ??
    (loading
      ? "Loading..."
      : error
        ? "Error"
        : isBaseline
          ? "Baseline"
          : isEmpty
            ? "No data yet"
            : isLowSample
              ? "Limited sample"
              : "Live");

  return (
    <Box
      role="group"
      aria-label={`Audit card for ${yearLabel}`}
      sx={{
        display: "flex",
        flexDirection: "column",
        border: "1px solid",
        borderColor: "divider",
        borderRadius: 2,
        p: 1.75,
        bgcolor: "background.paper",
        height: "100%",
        gap: 1,
        minHeight: 168,
      }}
    >
      <Box
        sx={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          gap: 1,
        }}
      >
        <Box sx={{ minWidth: 0 }}>
          <Typography
            component="h3"
            sx={{ fontSize: "0.95rem", fontWeight: 700, color: "text.primary" }}
          >
            {yearLabel}
          </Typography>
          <Typography
            variant="caption"
            sx={{ color: "text.secondary", fontSize: "0.7rem" }}
          >
            {resolvedCaption}
          </Typography>
        </Box>
        {showN && (
          <Chip
            label={`n = ${totalN}`}
            size="small"
            variant="outlined"
            sx={{ fontWeight: 600, fontSize: "0.72rem" }}
            aria-label={`Sample size for ${yearLabel}: ${totalN} cases`}
          />
        )}
        {isBaseline && (
          <Chip
            label="2018 NCDA"
            size="small"
            sx={{
              fontWeight: 600,
              fontSize: "0.7rem",
              bgcolor: "#FEF3C7",
              color: C_BENCH18,
              border: `1px solid ${C_BENCH18}33`,
            }}
          />
        )}
      </Box>

      {loading ? (
        <Box role="status" aria-label={`Loading ${yearLabel} audit metric`} sx={{ mt: 0.5 }}>
          <Box sx={{ display: "flex", alignItems: "baseline", gap: 1.5 }}>
            <Skeleton variant="text" width={76} height={40} />
            <Skeleton variant="text" width={96} height={22} />
          </Box>
          <Box sx={{ display: "flex", gap: 0.75, mt: 1.25 }}>
            <Skeleton variant="rounded" width="45%" height={16} />
            <Skeleton variant="rounded" width="28%" height={16} />
            <Skeleton variant="rounded" width="18%" height={16} />
          </Box>
        </Box>
      ) : (
        <Box sx={{ display: "flex", alignItems: "baseline", gap: 1.5, mt: 0.5 }}>
          <Typography
            component="span"
            sx={{
              fontWeight: 800,
              fontSize: "1.5rem",
              color: isBaseline ? C_BENCH18 : accentColor,
              lineHeight: 1,
              opacity: isEmpty ? 0.4 : 1,
            }}
          >
            {headlineValue ?? "--"}
          </Typography>
          {secondaryValue && (
            <Typography
              component="span"
              sx={{
                fontWeight: 600,
                fontSize: "0.95rem",
                color: "text.secondary",
                lineHeight: 1,
              }}
            >
              {secondaryValue}
            </Typography>
          )}
          {headlineSubLabel && (
            <Typography
              component="span"
              variant="caption"
              color="text.secondary"
              sx={{ fontSize: "0.72rem" }}
            >
              {headlineSubLabel}
            </Typography>
          )}
        </Box>
      )}

      {children && <Box sx={{ flexGrow: 1 }}>{children}</Box>}

      {isBaseline && baselineFootnote && (
        <Typography
          variant="caption"
          sx={{
            color: "text.secondary",
            fontStyle: "italic",
            fontSize: "0.7rem",
            display: "block",
          }}
        >
          {baselineFootnote}
        </Typography>
      )}

      {isEmpty && !isBaseline && (
        <Typography
          variant="caption"
          sx={{
            color: "text.secondary",
            fontStyle: "italic",
            fontSize: "0.72rem",
            display: "block",
          }}
        >
          No data yet for {yearLabel}.
        </Typography>
      )}

      {isLowSample && (
        <Typography
          variant="caption"
          sx={{
            color: "text.secondary",
            fontStyle: "italic",
            fontSize: "0.7rem",
            display: "block",
          }}
        >
          Limited sample (n = {totalN}) - treat as indicative.
        </Typography>
      )}

      {error && (
        <Typography
          variant="caption"
          color="error"
          sx={{ fontSize: "0.7rem", display: "block" }}
        >
          {error}
        </Typography>
      )}

      {onZoom && !isBaseline && !isEmpty && !error && (
        <Box sx={{ mt: "auto", display: "flex", justifyContent: "flex-end" }}>
          <Tooltip title={zoomAriaLabel ?? `Open detail for ${yearLabel}`}>
            <IconButton
              size="small"
              onClick={onZoom}
              aria-label={zoomAriaLabel ?? `Open detail for ${yearLabel}`}
            >
              <OpenInFullIcon fontSize="inherit" />
            </IconButton>
          </Tooltip>
        </Box>
      )}
    </Box>
  );
}

export interface EvolutionLegendSwatchProps {
  colour: string;
  label: string;
  dashed?: boolean;
}

export function EvolutionLegendSwatch({
  colour,
  label,
  dashed = false,
}: EvolutionLegendSwatchProps) {
  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
      <Box
        aria-hidden="true"
        sx={{
          width: 18,
          height: 10,
          borderRadius: 0.5,
          border: dashed ? `1.5px dashed ${colour}` : "none",
          bgcolor: dashed ? "transparent" : colour,
          opacity: dashed ? 1 : 0.85,
          flexShrink: 0,
        }}
      />
      <Typography
        variant="caption"
        sx={{ fontSize: "0.72rem", color: "text.secondary" }}
      >
        {label}
      </Typography>
    </Box>
  );
}

interface EvolutionBaselineUnavailableProps {
  message?: string;
}

/** Convenience baseline card used when 2018 NCDA does not publish a metric. */
export function EvolutionBaselineUnavailable({
  message,
}: EvolutionBaselineUnavailableProps) {
  return (
    <EvolutionYearCard
      yearLabel="2018"
      headlineValue={null}
      isBaseline
      caption="No baseline"
      baselineFootnote={
        message ?? "This metric was not published in the 2018 NCDA audit."
      }
    />
  );
}

