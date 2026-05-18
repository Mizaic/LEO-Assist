/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-EF5F7455
 *   DI: DI-38AE4EA1
 *   Risk: R-E00F9C3C
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-EF5F7455")
 */
"use client";

/**
 * One cancer-type row inside the CancerStageEvolutionDialog.
 *
 * Layout:
 *   | Label + 2018 published estimate | 2018 cell | YYYY cell | YYYY cell | YYYY cell |
 *
 * Each cell is a small stacked bar (early / late / unstaged) for that
 * cancer type in that calendar year. Cells with no data render an
 * explicit "No data" placeholder; cancer types whose published 2018
 * baseline is null (e.g. brain, leukaemia, lymphoma, myeloma,
 * haematological) render a single "Stage convention N/A" note instead
 * of zero bars (R-E00F9C3C mitigation).
 *
 * A delta chip on the right shows current-year early% minus 2018
 * baseline early% in pp when both are available.
 */

import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import {
  cancerTypeLabel,
  resolveBaseline2019,
  FALLBACK_NATIONAL_2019,
} from "@/lib/cancerTypeKeys";

const C_EARLY = "#16A34A";
const C_LATE = "#EA580C";
const C_GREY = "#CBD5E1";
const C_BENCH18 = "#92400E";

const CELL_TRACK_H = 14;
const LOW_SAMPLE_THRESHOLD = 5;

export interface PerTypeYearCell {
  yearLabel: string;
  earlyPct: number | null;
  latePct: number | null;
  totalN: number;
  /**
   * When true, the cell is the 2018 NCDA published baseline for this cancer
   * type. Only the green early-stage segment is drawn; late and unstaged are
   * not published in the baseline so the rest of the bar is hatched grey
   * and the n badge is suppressed.
   */
  isBaseline?: boolean;
}

export interface CancerStagePerTypeRowProps {
  cancerKey: string;
  baselineEarlyPct: number | null;
  cells: PerTypeYearCell[];
  bm:
    | Record<
        string,
        { practice?: number | null; alliance?: number | null; national?: number | null }
      >
    | null
    | undefined;
}

interface CellProps {
  cell: PerTypeYearCell;
}

function StageCell({ cell }: CellProps) {
  const { earlyPct, latePct, totalN, isBaseline } = cell;
  const early = earlyPct ?? 0;
  const late = latePct ?? 0;
  const hasAny = isBaseline
    ? earlyPct != null
    : totalN > 0 && (earlyPct != null || latePct != null);

  if (!hasAny) {
    return (
      <Box
        sx={{
          display: "flex",
          flexDirection: "column",
          alignItems: "stretch",
          gap: 0.25,
          minWidth: 0,
        }}
      >
        <Box
          sx={{
            height: CELL_TRACK_H,
            borderRadius: "4px",
            border: "1px dashed",
            borderColor: "divider",
            bgcolor: "action.hover",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <Typography
            component="span"
            sx={{
              fontSize: "0.6rem",
              color: "text.disabled",
              fontStyle: "italic",
              lineHeight: 1,
            }}
          >
            No data
          </Typography>
        </Box>
        <Typography
          component="span"
          sx={{
            fontSize: "0.6rem",
            color: "text.disabled",
            textAlign: "center",
          }}
        >
          n = 0
        </Typography>
      </Box>
    );
  }

  const isLowSample = totalN > 0 && totalN < LOW_SAMPLE_THRESHOLD;

  return (
    <Box
      sx={{
        display: "flex",
        flexDirection: "column",
        alignItems: "stretch",
        gap: 0.25,
        minWidth: 0,
      }}
    >
      <Box sx={{ position: "relative", height: CELL_TRACK_H }}>
        <Box
          sx={{
            position: "absolute",
            inset: 0,
            bgcolor: C_GREY,
            borderRadius: "4px",
            backgroundImage: isBaseline
              ? `repeating-linear-gradient(45deg, ${C_GREY} 0, ${C_GREY} 3px, #E2E8F0 3px, #E2E8F0 6px)`
              : undefined,
          }}
        />
        {!isBaseline && late > 0 && (
          <Box
            sx={{
              position: "absolute",
              top: 0,
              left: `${early}%`,
              width: `${late}%`,
              height: "100%",
              bgcolor: C_LATE,
              opacity: 0.85,
            }}
          />
        )}
        {early > 0 && (
          <Box
            sx={{
              position: "absolute",
              top: 0,
              left: 0,
              width: `${early}%`,
              height: "100%",
              bgcolor: isBaseline ? C_BENCH18 : C_EARLY,
              borderRadius: isBaseline ? "4px" : "4px 0 0 4px",
              opacity: 0.85,
              zIndex: 1,
            }}
          />
        )}
      </Box>
      <Box
        sx={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
          gap: 0.5,
        }}
      >
        <Typography
          component="span"
          sx={{
            fontSize: "0.7rem",
            fontWeight: 700,
            color: isBaseline ? C_BENCH18 : C_EARLY,
          }}
        >
          {earlyPct != null ? `${Math.round(early)}%` : "--"}
        </Typography>
        {!isBaseline && (
          <Typography
            component="span"
            sx={{
              fontSize: "0.6rem",
              color: isLowSample ? "text.disabled" : "text.secondary",
              fontStyle: isLowSample ? "italic" : "normal",
            }}
          >
            n = {totalN}
          </Typography>
        )}
      </Box>
    </Box>
  );
}

interface DeltaProps {
  baseline: number | null;
  current: number | null;
}

function DeltaChip({ baseline, current }: DeltaProps) {
  if (baseline == null || current == null) return null;
  const diff = Math.round((current - baseline) * 10) / 10;
  if (diff === 0) {
    return (
      <Typography
        component="span"
        sx={{
          fontSize: "0.7rem",
          fontWeight: 700,
          color: "text.secondary",
        }}
      >
        0pp
      </Typography>
    );
  }
  const positive = diff > 0;
  return (
    <Typography
      component="span"
      sx={{
        fontSize: "0.7rem",
        fontWeight: 700,
        color: positive ? "success.main" : "error.main",
      }}
    >
      {positive ? `+${diff}` : diff}pp
    </Typography>
  );
}

export default function CancerStagePerTypeRow({
  cancerKey,
  baselineEarlyPct,
  cells,
  bm,
}: CancerStagePerTypeRowProps) {
  const label = cancerTypeLabel(cancerKey);
  const resolvedBaseline = baselineEarlyPct ?? resolveBaseline2019(cancerKey, bm);
  const conventionApplies = !(
    cancerKey in FALLBACK_NATIONAL_2019 && FALLBACK_NATIONAL_2019[cancerKey] === null
  );

  const currentCell = cells[cells.length - 1];
  const currentEarly = currentCell?.earlyPct ?? null;

  const totalAcrossYears = cells.reduce((acc, c) => acc + (c.totalN ?? 0), 0);

  if (!conventionApplies) {
    return (
      <Box
        role="row"
        aria-label={`${label} stage row -- staging convention not applicable`}
        sx={{
          display: "grid",
          gridTemplateColumns: "minmax(160px, 1.4fr) repeat(4, minmax(80px, 1fr)) 70px",
          alignItems: "center",
          gap: 1.25,
          py: 1,
          px: 1,
          borderTop: "1px solid",
          borderColor: "divider",
        }}
      >
        <Box>
          <Typography
            component="span"
            sx={{ fontWeight: 700, fontSize: "0.85rem", color: "text.primary" }}
          >
            {label}
          </Typography>
          <Typography
            component="div"
            sx={{ fontSize: "0.65rem", color: "text.disabled", fontStyle: "italic" }}
          >
            Stage convention N/A
          </Typography>
        </Box>
        <Box
          sx={{
            gridColumn: "2 / span 4",
            color: "text.disabled",
            fontStyle: "italic",
            fontSize: "0.72rem",
            textAlign: "center",
          }}
        >
          Stage at diagnosis is not published or routinely captured for this
          cancer type.
        </Box>
        <Box />
      </Box>
    );
  }

  return (
    <Box
      role="row"
      aria-label={`${label} stage row`}
      sx={{
        display: "grid",
        gridTemplateColumns: "minmax(160px, 1.4fr) repeat(4, minmax(80px, 1fr)) 70px",
        alignItems: "center",
        gap: 1.25,
        py: 1,
        px: 1,
        borderTop: "1px solid",
        borderColor: "divider",
      }}
    >
      <Box>
        <Typography
          component="span"
          sx={{ fontWeight: 700, fontSize: "0.85rem", color: "text.primary" }}
        >
          {label}
        </Typography>
        {resolvedBaseline != null && (
          <Typography
            component="div"
            sx={{
              fontSize: "0.65rem",
              color: C_BENCH18,
              fontWeight: 600,
            }}
          >
            2018 baseline {resolvedBaseline}% early
          </Typography>
        )}
        {totalAcrossYears > 0 && (
          <Typography
            component="div"
            sx={{ fontSize: "0.62rem", color: "text.disabled" }}
          >
            {totalAcrossYears} cases across shown years
          </Typography>
        )}
      </Box>

      {cells.map((cell, idx) => (
        <StageCell key={`${cancerKey}-${cell.yearLabel}-${idx}`} cell={cell} />
      ))}

      <Box
        sx={{
          textAlign: "right",
          minWidth: 0,
        }}
      >
        <DeltaChip baseline={resolvedBaseline} current={currentEarly} />
        <Typography
          component="div"
          sx={{ fontSize: "0.6rem", color: "text.disabled" }}
        >
          vs 2018
        </Typography>
      </Box>
    </Box>
  );
}
