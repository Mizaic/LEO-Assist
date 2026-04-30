/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-4DADBA3F
 *   DI: DI-87D92943
 *   Risk: R-05B6DDA7
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-4DADBA3F")
 */
"use client";

/**
 * Single-year demographics card (sex pie + marginal age area chart).
 *
 * Every year uses the same visual language: an inline SVG sex pie and an
 * age-at-diagnosis area chart keyed to the canonical six NCDA age bands.
 *
 * Baseline mode (isBaseline) draws benchmark male/female % and marginal
 * age-band % from the 2018 NCDA metrics on the page-level result. Live
 * years draw the same charts from the audit demographics API for that
 * calendar-year window (marginal sex + age_bands arrays).
 *
 * Sparse-data states (R-05B6DDA7 mitigations):
 *   loading           -> "Loading..." caption
 *   live with n == 0  -> "No data yet for {year}"
 *   live with 0<n<20  -> "Limited sample - treat as indicative"
 */

import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import OpenInFullIcon from "@mui/icons-material/OpenInFull";

const C_MALE = "#2563EB";
const C_FEMALE = "#DB2777";
const C_GREY = "#CBD5E1";
const C_BENCH18 = "#92400E";

const LOW_SAMPLE_THRESHOLD = 20;

/** Canonical six NCDA age bands, youngest-first (area chart x-axis order). */
export const PYRAMID_AGE_BANDS = [
  "0-24",
  "25-49",
  "50-64",
  "65-74",
  "75-84",
  "85+",
] as const;
export type PyramidAgeBand = (typeof PYRAMID_AGE_BANDS)[number];

export interface PyramidRow {
  gender: string;
  age_band: string;
  pct: number;
  n: number;
}

export interface BaselineMarginal {
  malePct: number | null;
  femalePct: number | null;
  ageBandPct: Partial<Record<PyramidAgeBand, number | null>>;
  medianAge: number | null;
}

export interface PopulationPyramidCardProps {
  yearLabel: string;
  totalN: number;
  malePct: number | null;
  femalePct: number | null;
  medianAge: number | null;
  /** Live-year marginal age-band % from API `age_bands` (ignored when isBaseline). */
  ageBandPct?: Partial<Record<PyramidAgeBand, number | null>>;
  loading?: boolean;
  isBaseline?: boolean;
  baselineMarginal?: BaselineMarginal | null;
  /**
   * Optional shared age-band y-axis max (%). When provided, the area chart
   * uses this value instead of fitting to the card's own data, so all year
   * cards in the section share the same scale.
   */
  ageMaxPct?: number | null;
  /** When provided, renders a small expand button in the card header. */
  onZoom?: () => void;
  /** Bare mode: skip card border/padding/header for use inside ChartZoomDialog. */
  bare?: boolean;
}

function fmtPct(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "--";
  return `${Math.round(value)}%`;
}

interface SexPieProps {
  yearLabel: string;
  malePct: number | null;
  femalePct: number | null;
}

function arcPath(
  cx: number,
  cy: number,
  r: number,
  startFrac: number,
  endFrac: number,
): string {
  if (endFrac - startFrac <= 0) return "";
  if (endFrac - startFrac >= 0.999) {
    return `M${cx - r},${cy} A${r},${r} 0 1 1 ${cx + r},${cy} A${r},${r} 0 1 1 ${cx - r},${cy} Z`;
  }
  const start = startFrac * 2 * Math.PI - Math.PI / 2;
  const end = endFrac * 2 * Math.PI - Math.PI / 2;
  const x1 = cx + r * Math.cos(start);
  const y1 = cy + r * Math.sin(start);
  const x2 = cx + r * Math.cos(end);
  const y2 = cy + r * Math.sin(end);
  const largeArc = endFrac - startFrac > 0.5 ? 1 : 0;
  return `M${cx},${cy} L${x1},${y1} A${r},${r} 0 ${largeArc} 1 ${x2},${y2} Z`;
}

function SexPie({ yearLabel, malePct, femalePct }: SexPieProps) {
  const SIZE = 84;
  const R = 34;
  const CX = SIZE / 2;
  const CY = SIZE / 2;
  const m = malePct ?? 0;
  const f = femalePct ?? 0;
  const total = m + f;
  if (total <= 0) {
    return (
      <Box
        component="svg"
        role="img"
        aria-label={`Sex distribution for ${yearLabel} -- no data`}
        viewBox={`0 0 ${SIZE} ${SIZE}`}
        sx={{ width: SIZE, height: SIZE, flexShrink: 0 }}
      >
        <circle
          cx={CX}
          cy={CY}
          r={R}
          fill={C_GREY}
          opacity={0.4}
        />
      </Box>
    );
  }
  const malefrac = m / total;
  return (
    <Box
      component="svg"
      role="img"
      aria-label={`Sex distribution for ${yearLabel}: male ${fmtPct(m)}, female ${fmtPct(f)}`}
      viewBox={`0 0 ${SIZE} ${SIZE}`}
      sx={{ width: SIZE, height: SIZE, flexShrink: 0 }}
    >
      <path
        d={arcPath(CX, CY, R, 0, malefrac)}
        fill={C_MALE}
        opacity={0.85}
      />
      <path
        d={arcPath(CX, CY, R, malefrac, 1)}
        fill={C_FEMALE}
        opacity={0.85}
      />
      <circle
        cx={CX}
        cy={CY}
        r={R}
        fill="none"
        stroke="#FFFFFF"
        strokeWidth={1.5}
      />
      <text
        x={CX - R * 0.55}
        y={CY + 3}
        textAnchor="middle"
        fontSize="10"
        fontWeight={700}
        fill="#FFFFFF"
      >
        {Math.round(m)}%
      </text>
      <text
        x={CX + R * 0.55}
        y={CY + 3}
        textAnchor="middle"
        fontSize="10"
        fontWeight={700}
        fill="#FFFFFF"
      >
        {Math.round(f)}%
      </text>
    </Box>
  );
}

interface AgeAreaProps {
  yearLabel: string;
  data: Array<{ band: PyramidAgeBand; pct: number | null }>;
  /** Optional shared y-axis max (%) so all year cards share the same scale. */
  maxPctOverride?: number | null;
}

function AgeArea({ yearLabel, data, maxPctOverride }: AgeAreaProps) {
  const W = 200;
  const H = 110;
  const PAD_X = 6;
  const PAD_TOP = 14;
  const PAD_BOTTOM = 18;
  const innerW = W - PAD_X * 2;
  const innerH = H - PAD_TOP - PAD_BOTTOM;

  const values = data.map((d) => d.pct ?? 0);
  const maxPct = maxPctOverride && maxPctOverride > 0
    ? maxPctOverride
    : Math.max(...values, 1);
  const C_AREA = "#16A34A";

  const points = data.map((d, i) => {
    const x = PAD_X + (i / Math.max(1, data.length - 1)) * innerW;
    const y = PAD_TOP + innerH - ((d.pct ?? 0) / maxPct) * innerH;
    return { x, y, band: d.band, pct: d.pct };
  });

  const linePath = points
    .map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`)
    .join(" ");
  const baseY = PAD_TOP + innerH;
  const areaPath = `${linePath} L${points[points.length - 1].x.toFixed(1)},${baseY} L${points[0].x.toFixed(1)},${baseY} Z`;

  return (
    <Box
      component="svg"
      role="img"
      aria-label={`Age at diagnosis (% of cases) for ${yearLabel}`}
      viewBox={`0 0 ${W} ${H}`}
      sx={{ width: "100%", height: "100%", display: "block" }}
    >
      <line
        x1={PAD_X}
        y1={baseY}
        x2={W - PAD_X}
        y2={baseY}
        stroke="#CBD5E1"
        strokeWidth={0.5}
      />
      <path d={areaPath} fill={C_AREA} opacity={0.18} />
      <path
        d={linePath}
        stroke={C_AREA}
        strokeWidth={1.5}
        fill="none"
        strokeLinejoin="round"
      />
      {points.map((p) => (
        <g key={p.band}>
          <circle
            cx={p.x}
            cy={p.y}
            r={2.4}
            fill={C_AREA}
          />
          <text
            x={p.x}
            y={p.y - 4}
            textAnchor="middle"
            fontSize="8"
            fontWeight={700}
            fill="#15803D"
          >
            {p.pct == null ? "--" : `${Math.round(p.pct)}%`}
          </text>
          <text
            x={p.x}
            y={baseY + 10}
            textAnchor="middle"
            fontSize="7.5"
            fontWeight={600}
            fill="#475569"
          >
            {p.band}
          </text>
        </g>
      ))}
    </Box>
  );
}

interface DemographicsChartsProps {
  yearLabel: string;
  isBaseline: boolean;
  baselineMarginal: BaselineMarginal | null | undefined;
  malePct: number | null;
  femalePct: number | null;
  ageBandPctLive?: Partial<Record<PyramidAgeBand, number | null>>;
  ageMaxPct?: number | null;
}

function DemographicsCharts({
  yearLabel,
  isBaseline,
  baselineMarginal,
  malePct,
  femalePct,
  ageBandPctLive,
  ageMaxPct,
}: DemographicsChartsProps) {
  const m = isBaseline ? baselineMarginal?.malePct ?? null : malePct;
  const f = isBaseline ? baselineMarginal?.femalePct ?? null : femalePct;

  const ageData = PYRAMID_AGE_BANDS.map((band) => ({
    band,
    pct: isBaseline
      ? baselineMarginal?.ageBandPct?.[band] ?? null
      : ageBandPctLive?.[band] ?? null,
  }));

  const sexCaption = isBaseline
    ? "Marginal split published in the 2018 NCDA baseline."
    : "Marginal split for confirmed cancer cases in this calendar year.";

  return (
    <Box
      sx={{
        display: "flex",
        flexDirection: "column",
        gap: 1.5,
        height: "100%",
      }}
    >
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          gap: 1.5,
        }}
      >
        <SexPie yearLabel={yearLabel} malePct={m} femalePct={f} />
        <Box sx={{ minWidth: 0, flexShrink: 1 }}>
          <Typography
            component="div"
            sx={{
              fontSize: "0.68rem",
              fontWeight: 700,
              color: "text.secondary",
              textTransform: "uppercase",
              letterSpacing: 0.4,
            }}
          >
            Sex
          </Typography>
          <Typography
            variant="caption"
            sx={{
              fontSize: "0.7rem",
              color: "text.secondary",
              display: "block",
              lineHeight: 1.3,
            }}
          >
            {sexCaption}
          </Typography>
        </Box>
      </Box>
      <Box>
        <Typography
          component="div"
          sx={{
            fontSize: "0.68rem",
            fontWeight: 700,
            color: "text.secondary",
            textTransform: "uppercase",
            letterSpacing: 0.4,
            mb: 0.25,
          }}
        >
          Age at diagnosis (% of cases)
        </Typography>
        <Box sx={{ height: 110 }}>
          <AgeArea
            yearLabel={yearLabel}
            data={ageData}
            maxPctOverride={ageMaxPct}
          />
        </Box>
      </Box>
    </Box>
  );
}

export default function PopulationPyramidCard({
  yearLabel,
  totalN,
  malePct,
  femalePct,
  medianAge,
  ageBandPct,
  loading = false,
  isBaseline = false,
  baselineMarginal = null,
  ageMaxPct = null,
  onZoom,
  bare = false,
}: PopulationPyramidCardProps) {
  const isEmpty = !loading && !isBaseline && totalN === 0;
  const isLowSample =
    !loading &&
    !isBaseline &&
    totalN > 0 &&
    totalN < LOW_SAMPLE_THRESHOLD;

  const hasChartData =
    !loading &&
    (isBaseline ||
      (!isBaseline && totalN > 0));

  const headerCaption = loading
    ? "Loading..."
    : isBaseline
      ? "Baseline"
      : isEmpty
        ? "No data yet"
        : isLowSample
          ? "Limited sample"
          : "Live";

  const baselineMale = isBaseline ? baselineMarginal?.malePct ?? null : null;
  const baselineFemale = isBaseline
    ? baselineMarginal?.femalePct ?? null
    : null;
  const baselineMedian = isBaseline
    ? baselineMarginal?.medianAge ?? null
    : null;

  const headerRow = (
    <Box
      sx={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 1,
      }}
    >
        <Box sx={{ minWidth: 0 }}>
          <Typography
            component="h3"
            sx={{
              fontSize: "0.95rem",
              fontWeight: 700,
              color: "text.primary",
            }}
          >
            {yearLabel}
          </Typography>
          <Typography
            variant="caption"
            sx={{ color: "text.secondary", fontSize: "0.7rem" }}
          >
            {headerCaption}
          </Typography>
        </Box>
        <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, flexShrink: 0 }}>
          {!isBaseline && (
            <Chip
              label={`n = ${totalN}`}
              size="small"
              variant="outlined"
              sx={{ fontWeight: 600, fontSize: "0.72rem" }}
              aria-label={`Sample size for ${yearLabel}: ${totalN} confirmed cancer cases`}
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
          {onZoom && (
            <Tooltip title="Expand chart" placement="top">
              <IconButton
                aria-label={`Expand ${yearLabel} demographics chart`}
                size="small"
                onClick={onZoom}
                sx={{ p: 0.25, color: "text.secondary", "&:hover": { color: "primary.main" } }}
              >
                <OpenInFullIcon sx={{ fontSize: "0.85rem" }} />
              </IconButton>
            </Tooltip>
          )}
        </Box>
    </Box>
  );

  const bodyContent = (
    <>
      <Box
        sx={{
          display: "flex",
          gap: 2,
          alignItems: "baseline",
          fontSize: "0.78rem",
          color: "text.secondary",
        }}
      >
        <Box sx={{ display: "flex", alignItems: "baseline", gap: 0.5 }}>
          <Box
            aria-hidden="true"
            sx={{
              width: 10,
              height: 10,
              borderRadius: 0.5,
              bgcolor: C_MALE,
              opacity: 0.85,
            }}
          />
          <Typography
            component="span"
            sx={{
              fontWeight: 700,
              color: C_MALE,
              fontSize: "0.85rem",
            }}
          >
            M {fmtPct(isBaseline ? baselineMale : malePct)}
          </Typography>
        </Box>
        <Box sx={{ display: "flex", alignItems: "baseline", gap: 0.5 }}>
          <Box
            aria-hidden="true"
            sx={{
              width: 10,
              height: 10,
              borderRadius: 0.5,
              bgcolor: C_FEMALE,
              opacity: 0.85,
            }}
          />
          <Typography
            component="span"
            sx={{
              fontWeight: 700,
              color: C_FEMALE,
              fontSize: "0.85rem",
            }}
          >
            F {fmtPct(isBaseline ? baselineFemale : femalePct)}
          </Typography>
        </Box>
        <Box sx={{ ml: "auto" }}>
          <Typography
            component="span"
            variant="caption"
            sx={{ fontSize: "0.7rem" }}
          >
            median age{" "}
            <strong>
              {isBaseline
                ? baselineMedian != null
                  ? `${baselineMedian}`
                  : "--"
                : medianAge != null
                  ? `${medianAge}`
                  : "--"}
            </strong>
          </Typography>
        </Box>
      </Box>

      <Box sx={{ flexGrow: 1, minHeight: 168 }}>
        {hasChartData ? (
          <DemographicsCharts
            yearLabel={yearLabel}
            isBaseline={isBaseline}
            baselineMarginal={baselineMarginal}
            malePct={malePct}
            femalePct={femalePct}
            ageBandPctLive={ageBandPct}
            ageMaxPct={ageMaxPct}
          />
        ) : (
          <Box
            aria-hidden={loading ? "true" : undefined}
            sx={{
              height: 168,
              borderRadius: 2,
              backgroundImage: `repeating-linear-gradient(45deg, ${C_GREY} 0, ${C_GREY} 4px, #E2E8F0 4px, #E2E8F0 8px)`,
              opacity: loading ? 0.5 : 0.35,
            }}
          />
        )}
      </Box>

      {isBaseline && (
        <Typography
          variant="caption"
          sx={{
            color: "text.secondary",
            fontStyle: "italic",
            fontSize: "0.7rem",
            display: "block",
          }}
        >
          2018 NCDA baseline publishes marginal age and sex only -- no
          cross-tab.
        </Typography>
      )}

      {isEmpty && (
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
          Limited sample (n = {totalN}) - treat as indicative, not
          representative.
        </Typography>
      )}
    </>
  );

  if (bare) {
    return (
      <Box
        role="group"
        aria-label={`Demographics chart for ${yearLabel}`}
        sx={{
          display: "flex",
          flexDirection: "column",
          gap: 1,
          width: "100%",
          height: "100%",
        }}
      >
        {bodyContent}
      </Box>
    );
  }

  return (
    <Box
      role="group"
      aria-label={`Demographics chart card for ${yearLabel}`}
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
      }}
    >
      {headerRow}
      {bodyContent}
    </Box>
  );
}
