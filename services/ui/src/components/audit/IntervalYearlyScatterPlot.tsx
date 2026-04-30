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
import Typography from "@mui/material/Typography";
import { useRouter } from "next/navigation";
import type { PatientInterval } from "./IntervalStripPlot";

const CANCER_COLOUR = "#DC2626";
const BENIGN_COLOUR = "#16A34A";
const AXIS_COLOUR = "#CBD5E1";
const TEXT_COLOUR = "#475569";

interface YearScatterDatum {
  year: string;
  patients: PatientInterval[];
}

interface Props {
  yearData: YearScatterDatum[];
  intervalKey: "pci_days" | "di_days";
  label: string;
  showBenign: boolean;
  maxDays: number;
  unit?: string;
}

interface ScatterPoint {
  year: string;
  x: number;
  y: number;
  days: number;
  patientId?: string | null;
  episodeId: string;
  cancerType: string;
  isBenign: boolean;
  inferred: boolean;
}

function pointJitter(seed: string, index: number): number {
  let hash = index + 17;
  for (let i = 0; i < seed.length; i += 1) {
    hash = (hash * 31 + seed.charCodeAt(i)) % 997;
  }
  return (hash / 997 - 0.5) * 42;
}

export default function IntervalYearlyScatterPlot({
  yearData,
  intervalKey,
  label,
  showBenign,
  maxDays,
  unit = "days",
}: Props) {
  const router = useRouter();
  const width = 720;
  const height = 230;
  const margin = { top: 18, right: 18, bottom: 46, left: 52 };
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;
  const yFor = (value: number) =>
    margin.top + plotHeight - (Math.max(0, value) / maxDays) * plotHeight;
  const tickValues = [0, maxDays / 2, maxDays].map((v) => Math.round(v));

  const points = yearData.flatMap((datum, yearIndex) => {
    const band = plotWidth / Math.max(yearData.length, 1);
    const groupX = margin.left + band * yearIndex + band / 2;
    return datum.patients
      .filter((patient) => {
        const days = patient[intervalKey];
        return (
          days != null &&
          days >= 0 &&
          days <= maxDays &&
          (showBenign || !patient.is_benign)
        );
      })
      .map((patient, pointIndex): ScatterPoint => {
        const days = patient[intervalKey] as number;
        const seed = patient.episode_id || `${datum.year}-${pointIndex}`;
        return {
          year: datum.year,
          x: groupX + pointJitter(seed, pointIndex),
          y: yFor(days),
          days,
          patientId: patient.patient_id,
          episodeId: patient.episode_id,
          cancerType: patient.cancer_type ?? "Unknown",
          isBenign: !!patient.is_benign,
          inferred: !!patient.diag_is_inferred,
        };
      });
  });

  function openPatient(patientId?: string | null) {
    if (!patientId) return;
    router.push(`/care/patients?patient_id=${encodeURIComponent(patientId)}`);
  }

  if (points.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary" sx={{ py: 3, textAlign: "center" }}>
        No yearly {label.toLowerCase()} referral dots available yet.
      </Typography>
    );
  }

  return (
    <Box>
      <Box
        role="group"
        aria-label={`${label} yearly scatter plot. Each dot is a referral, grouped by year.`}
        sx={{ width: "100%", overflowX: "auto" }}
      >
        <svg viewBox={`0 0 ${width} ${height}`} width="100%">
          {tickValues.map((tick) => {
            const y = yFor(tick);
            return (
              <g key={tick}>
                <line
                  x1={margin.left}
                  x2={width - margin.right}
                  y1={y}
                  y2={y}
                  stroke={AXIS_COLOUR}
                  strokeDasharray={tick === 0 ? undefined : "4 4"}
                />
                <text x={margin.left - 8} y={y + 4} textAnchor="end" fontSize={10} fill={TEXT_COLOUR}>
                  {tick}
                </text>
              </g>
            );
          })}

          {yearData.map((datum, index) => {
            const band = plotWidth / yearData.length;
            const groupX = margin.left + band * index + band / 2;
            return (
              <g key={datum.year}>
                <line
                  x1={groupX}
                  x2={groupX}
                  y1={margin.top}
                  y2={height - margin.bottom}
                  stroke="#E5E7EB"
                />
                <text x={groupX} y={height - 22} textAnchor="middle" fontSize={12} fill={TEXT_COLOUR}>
                  {datum.year}
                </text>
              </g>
            );
          })}

          {points.map((point) => (
            <circle
              key={`${point.year}-${point.episodeId}`}
              cx={point.x}
              cy={point.y}
              r={4}
              fill={point.isBenign ? BENIGN_COLOUR : CANCER_COLOUR}
              fillOpacity={0.68}
              stroke="white"
              strokeWidth={0.8}
              tabIndex={point.patientId ? 0 : undefined}
              role={point.patientId ? "button" : undefined}
              aria-label={`${point.year} ${label}: ${point.days} ${unit}, ${point.cancerType}`}
              onClick={() => openPatient(point.patientId)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  openPatient(point.patientId);
                }
              }}
              style={{ cursor: point.patientId ? "pointer" : "default" }}
            >
              <title>
                {`${point.year} - ${point.cancerType}: ${point.days} ${unit}${
                  point.isBenign ? " (benign/excluded)" : ""
                }${point.inferred ? " (inferred)" : ""}`}
              </title>
            </circle>
          ))}
        </svg>
      </Box>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block", textAlign: "center", mt: 0.5 }}>
        Each dot represents one referral grouped by year. Click a dot to open the patient record.
      </Typography>
    </Box>
  );
}
