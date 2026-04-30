/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2E8544FD
 *   DI: DI-C65FD45B
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2E8544FD")
 */
"use client";

import Box from "@mui/material/Box";
import FormControlLabel from "@mui/material/FormControlLabel";
import Switch from "@mui/material/Switch";
import Typography from "@mui/material/Typography";
import { useRouter } from "next/navigation";
import type { PatientInterval } from "./IntervalStripPlot";

const C = {
  cancer:    "#DC2626",
  benign:    "#16A34A",
  baseline:  "#92400E",
  grid:      "#CBD5E1",
  text:      "#475569",
  muted:     "#94A3B8",
  axis:      "#CBD5E1",
};

export interface IntervalCompositeStats {
  n: number;
  median: number | null;
  q1: number | null;
  q3: number | null;
}

export interface IntervalCompositeYearDatum {
  year: string;
  cancer: IntervalCompositeStats;
  benign: IntervalCompositeStats;
  baseline?: IntervalCompositeStats | null;
  patients: PatientInterval[];
  isBaseline?: boolean;
}

interface Props {
  yearData: IntervalCompositeYearDatum[];
  intervalKey: "pci_days" | "di_days";
  label: string;
  showBenign: boolean;
  onToggleBenign?: (show: boolean) => void;
  maxDays: number;
  baselineLabel?: string;
  unit?: string;
}

function niceMax(v: number): number {
  if (v <= 10) return 10;
  if (v <= 30) return Math.ceil(v / 5) * 5;
  if (v <= 100) return Math.ceil(v / 10) * 10;
  if (v <= 400) return Math.ceil(v / 50) * 50;
  return Math.ceil(v / 100) * 100;
}

function jitter(seed: string, idx: number, half: number): number {
  let h = (idx + 1) * 2654435761;
  for (let i = 0; i < seed.length; i += 1) h = ((h * 31) + seed.charCodeAt(i)) >>> 0;
  return ((h % 1000) / 1000 - 0.5) * half * 1.6;
}

const DOT_FILL = "#1E293B";

function BoxShape({
  cx, bw, stats, colour, yFor, wMin, wMax,
}: {
  cx: number; bw: number; stats: IntervalCompositeStats;
  colour: string; yFor: (v: number) => number;
  wMin?: number | null; wMax?: number | null;
}) {
  if (stats.median == null) return null;
  const q1   = stats.q1 ?? stats.median;
  const q3   = stats.q3 ?? stats.median;
  const yTop = yFor(Math.max(q1, q3));
  const yBot = yFor(Math.min(q1, q3));
  const bh   = Math.max(yBot - yTop, 4);
  const yMed = yFor(stats.median);
  const half = bw / 2;
  const cap  = bw * 0.28;

  return (
    <g>
      {/* upper whisker */}
      {wMax != null && wMax > q3 && (
        <>
          <line x1={cx} x2={cx} y1={yTop} y2={yFor(wMax)}
            stroke={colour} strokeWidth={1} strokeDasharray="3 2" />
          <line x1={cx - cap} x2={cx + cap} y1={yFor(wMax)} y2={yFor(wMax)}
            stroke={colour} strokeWidth={1.5} />
        </>
      )}
      {/* lower whisker */}
      {wMin != null && wMin < q1 && (
        <>
          <line x1={cx} x2={cx} y1={yBot} y2={yFor(wMin)}
            stroke={colour} strokeWidth={1} strokeDasharray="3 2" />
          <line x1={cx - cap} x2={cx + cap} y1={yFor(wMin)} y2={yFor(wMin)}
            stroke={colour} strokeWidth={1.5} />
        </>
      )}
      {/* IQR box */}
      <rect x={cx - half} y={yTop} width={bw} height={bh} rx={3}
        fill={colour} fillOpacity={0.12} stroke={colour} strokeWidth={1.5} />
      {/* median line */}
      <line x1={cx - half} x2={cx + half} y1={yMed} y2={yMed}
        stroke={colour} strokeWidth={2} />
      {/* median dot */}
      <circle cx={cx} cy={yMed} r={3} fill={colour} />
    </g>
  );
}


export default function IntervalCompositeBoxScatterPlot({
  yearData, intervalKey, label, showBenign, onToggleBenign, maxDays,
  baselineLabel = "2018 baseline", unit = "days",
}: Props) {
  const router = useRouter();

  const W = 800, H = 300;
  const mar = { top: 18, right: 18, bottom: 52, left: 52 };
  const pw = W - mar.left - mar.right;
  const ph = H - mar.top - mar.bottom;

  const yMax = niceMax(maxDays * 1.05);
  const yFor = (v: number) => mar.top + ph - (Math.max(0, v) / yMax) * ph;
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => Math.round(f * yMax));

  function nav(pid?: string | null) {
    if (pid) router.push(`/care/patients?patient_id=${encodeURIComponent(pid)}`);
  }

  if (!yearData.length) {
    return (
      <Typography variant="body2" color="text.secondary" sx={{ py: 4, textAlign: "center" }}>
        No yearly {label.toLowerCase()} data available yet.
      </Typography>
    );
  }

  const band = pw / yearData.length;
  const bw   = Math.min(62, band * 0.27);
  const gap  = Math.min(16, band * 0.07);

  return (
    <Box sx={{ maxWidth: 880, mx: "auto" }}>
      <Box
        role="group"
        aria-label={`${label} composite box and scatter by year`}
        sx={{ width: "100%", overflowX: "auto" }}
      >
        <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: "block" }}>
          {/* horizontal grid lines */}
          {ticks.map((tick) => {
            const y = yFor(tick);
            return (
              <g key={tick}>
                <line x1={mar.left} x2={W - mar.right} y1={y} y2={y}
                  stroke={C.grid} strokeWidth={tick === 0 ? 1 : 1}
                  strokeDasharray={tick === 0 ? undefined : "4 4"} />
                <text x={mar.left - 8} y={y + 4} textAnchor="end"
                  fontSize={10} fill={C.text} fontFamily="inherit">
                  {tick}
                </text>
              </g>
            );
          })}

          {/* y-axis label */}
          <text x={14} y={mar.top + ph / 2} textAnchor="middle"
            fontSize={10} fill={C.muted} fontFamily="inherit"
            transform={`rotate(-90, 14, ${mar.top + ph / 2})`}>
            {unit}
          </text>

          {/* per-year columns */}
          {yearData.map((datum, i) => {
            const cx = mar.left + band * i + band / 2;
            const cancerCX = datum.isBaseline ? cx
              : (showBenign ? cx - gap / 2 - bw / 2 : cx);
            const benignCX = cx + gap / 2 + bw / 2;

            const cPts = datum.patients.filter((p) => {
              const days = p[intervalKey];
              return !p.is_benign && days != null && (days as number) >= 0 && (days as number) <= yMax;
            });
            const bPts = datum.patients.filter((p) => {
              const days = p[intervalKey];
              return !!p.is_benign && days != null && (days as number) >= 0 && (days as number) <= yMax;
            });

            const cVals = cPts.map((p) => p[intervalKey] as number);
            const bVals = bPts.map((p) => p[intervalKey] as number);
            const cMin = cVals.length ? Math.min(...cVals) : null;
            const cMax = cVals.length ? Math.max(...cVals) : null;
            const bMin = bVals.length ? Math.min(...bVals) : null;
            const bMax = bVals.length ? Math.max(...bVals) : null;

            return (
              <g key={datum.year}>
                <line x1={mar.left + band * i} x2={mar.left + band * i}
                  y1={mar.top} y2={mar.top + ph} stroke={C.grid} strokeWidth={1} />

                {datum.isBaseline ? (
                  datum.baseline?.median != null && (
                    <g>
                      <line
                        x1={cx - bw * 0.9} x2={cx + bw * 0.9}
                        y1={yFor(datum.baseline.median)} y2={yFor(datum.baseline.median)}
                        stroke={C.baseline} strokeWidth={2} strokeLinecap="square" />
                      <text x={cx} y={yFor(datum.baseline.median) - 8}
                        textAnchor="middle" fontSize={10} fill={C.baseline}
                        fontFamily="inherit">
                        {datum.baseline.median} {unit}
                      </text>
                    </g>
                  )
                ) : (
                  <>
                    <BoxShape cx={cancerCX} bw={bw} stats={datum.cancer}
                      colour={C.cancer} yFor={yFor} wMin={cMin} wMax={cMax} />
                    {cPts.map((p, j) => {
                      const days = p[intervalKey] as number;
                      return (
                        <circle
                          key={`c-${p.episode_id}`}
                          cx={cancerCX + jitter(p.episode_id || `c${j}`, j, bw * 0.36)}
                          cy={yFor(days)} r={3.5}
                          fill={DOT_FILL} stroke={C.cancer} strokeWidth={1}
                          tabIndex={p.patient_id ? 0 : undefined}
                          role={p.patient_id ? "button" : undefined}
                          aria-label={`${datum.year} ${label}: ${days} ${unit} - ${p.cancer_type ?? "Unknown"}`}
                          style={{ cursor: p.patient_id ? "pointer" : "default" }}
                          onClick={() => nav(p.patient_id)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" || e.key === " ") {
                              e.preventDefault(); nav(p.patient_id);
                            }
                          }}
                        >
                          <title>{`${datum.year} - ${p.cancer_type ?? "Unknown"}: ${days} ${unit}`}</title>
                        </circle>
                      );
                    })}
                    <text x={cancerCX} y={mar.top + ph + 14} textAnchor="middle"
                      fontSize={10} fill={C.cancer} fontFamily="inherit">
                      n={datum.cancer.n}
                    </text>

                    {showBenign && (
                      <>
                        <BoxShape cx={benignCX} bw={bw} stats={datum.benign}
                          colour={C.benign} yFor={yFor} wMin={bMin} wMax={bMax} />
                        {bPts.map((p, j) => {
                          const days = p[intervalKey] as number;
                          return (
                            <circle
                              key={`b-${p.episode_id}`}
                              cx={benignCX + jitter(p.episode_id || `b${j}`, j, bw * 0.36)}
                              cy={yFor(days)} r={3.5}
                              fill={DOT_FILL} stroke={C.benign} strokeWidth={1}
                              tabIndex={p.patient_id ? 0 : undefined}
                              role={p.patient_id ? "button" : undefined}
                              aria-label={`${datum.year} ${label}: ${days} ${unit} - ${p.cancer_type ?? "Unknown"} (benign/excluded)`}
                              style={{ cursor: p.patient_id ? "pointer" : "default" }}
                              onClick={() => nav(p.patient_id)}
                              onKeyDown={(e) => {
                                if (e.key === "Enter" || e.key === " ") {
                                  e.preventDefault(); nav(p.patient_id);
                                }
                              }}
                            >
                              <title>{`${datum.year} - ${p.cancer_type ?? "Unknown"}: ${days} ${unit} (benign/excluded)`}</title>
                            </circle>
                          );
                        })}
                        <text x={benignCX} y={mar.top + ph + 14} textAnchor="middle"
                          fontSize={10} fill={C.benign} fontFamily="inherit">
                          n={datum.benign.n}
                        </text>
                      </>
                    )}
                  </>
                )}

                {/* year label */}
                <text x={cx} y={H - 28} textAnchor="middle"
                  fontSize={12} fontWeight={500} fill={C.text} fontFamily="inherit">
                  {datum.year}
                </text>
                {datum.isBaseline && (
                  <text x={cx} y={H - 14} textAnchor="middle"
                    fontSize={10} fill={C.baseline} fontFamily="inherit">
                    baseline
                  </text>
                )}
              </g>
            );
          })}

          {/* right border */}
          <line x1={W - mar.right} x2={W - mar.right} y1={mar.top} y2={mar.top + ph}
            stroke={C.grid} strokeWidth={1} />
        </svg>
      </Box>

      {/* legend */}
      <Box sx={{ display: "flex", flexWrap: "wrap", gap: 2, mt: 0.5, alignItems: "center" }}>
        <Typography variant="caption" sx={{ color: "text.secondary" }}>
          <Box component="span" sx={{ color: C.cancer, fontWeight: 700 }}>Red</Box>
          {" "}= cancer confirmed.
        </Typography>
        {showBenign && (
          <Typography variant="caption" sx={{ color: "text.secondary" }}>
            <Box component="span" sx={{ color: C.benign, fontWeight: 700 }}>Green</Box>
            {" "}= benign / excluded.
          </Typography>
        )}
        <Typography variant="caption" sx={{ color: "text.secondary" }}>
          <Box component="span" sx={{ color: C.baseline, fontWeight: 700 }}>Brown</Box>
          {" "}= {baselineLabel}.
        </Typography>
        <Box sx={{ ml: "auto", display: "flex", alignItems: "center", gap: 2 }}>
        <Typography variant="caption" color="text.secondary">
          Box = IQR, centre line = median, whiskers = min/max. Click any dot to open patient record.
        </Typography>
          {onToggleBenign && (
            <FormControlLabel
              control={
                <Switch
                  size="small"
                  checked={showBenign}
                  onChange={(e) => onToggleBenign(e.target.checked)}
                />
              }
              label={<Typography variant="caption">Show benign/excluded</Typography>}
              sx={{ mr: 0, ml: 0 }}
            />
          )}
        </Box>
      </Box>
    </Box>
  );
}
