/**
 * Row and header primitives for RunPickerGrid.
 *
 * Atlas trace:
 *   DO: DO-158BE606
 *   DI: DI-2289D095
 */
"use client";

import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import AddCircleOutlineIcon from "@mui/icons-material/AddCircleOutline";
import ArrowDownwardIcon from "@mui/icons-material/ArrowDownward";
import ArrowUpwardIcon from "@mui/icons-material/ArrowUpward";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import UnfoldMoreIcon from "@mui/icons-material/UnfoldMore";

import type { ClinicalPipelineRun } from "./labFindingsApi";
import { investigationKey } from "./ncrInvestigationCases";
import { pressable, shortDate, statusTone } from "./clinicalDoorChrome";

export type SortCol = "created_at" | "status";
export type SortDir = "asc" | "desc";

export function GridSortHeader({
  col,
  label,
  current,
  dir,
  onSort,
}: {
  col: SortCol;
  label: string;
  current: SortCol;
  dir: SortDir;
  onSort: (col: SortCol) => void;
}) {
  const active = col === current;
  return (
    <th
      style={TH_BASE}
      aria-sort={active ? (dir === "asc" ? "ascending" : "descending") : "none"}
    >
      <button
        type="button"
        onClick={() => onSort(col)}
        style={SORT_BTN}
        aria-label={`Sort by ${label}`}
      >
        {label}
        {active ? (
          dir === "asc" ? (
            <ArrowUpwardIcon sx={{ fontSize: 12, ml: 0.5 }} />
          ) : (
            <ArrowDownwardIcon sx={{ fontSize: 12, ml: 0.5 }} />
          )
        ) : (
          <UnfoldMoreIcon sx={{ fontSize: 12, ml: 0.5, opacity: 0.35 }} />
        )}
      </button>
    </th>
  );
}

export function RunDataRow({
  row,
  index,
  indent,
  linkedKeys,
  onPick,
}: {
  row: ClinicalPipelineRun;
  index: number;
  indent: boolean;
  linkedKeys: Set<string>;
  onPick: (row: ClinicalPipelineRun) => void;
}) {
  const added = linkedKeys.has(investigationKey(row));
  const even = index % 2 === 0;
  return (
    <tr
      data-testid={`run-row-${row.run_id}`}
      style={{
        background: even ? "#FFFFFF" : "#F9FAFB",
        transition: "background 120ms ease-out",
        cursor: added ? "default" : "pointer",
      }}
      onClick={added ? undefined : () => onPick(row)}
    >
      <td style={{ ...TD, color: "#6B7280", fontSize: 12 }}>
        {shortDate(row.created_at)}
      </td>
      <td style={TD}>
        <Typography variant="body2" sx={{ fontWeight: indent ? 400 : 600, pl: indent ? 2 : 0, color: added ? "text.secondary" : "text.primary" }}>
          {row.patient_name || row.patient_id || "—"}
        </Typography>
      </td>
      <td style={{ ...TD, color: "#6B7280", fontSize: 13, fontVariantNumeric: "tabular-nums" }}>
        {row.nhs_number || "—"}
      </td>
      <td style={{ ...TD, color: "#6B7280", fontSize: 13, fontVariantNumeric: "tabular-nums" }}>
        {row.ubrn || "—"}
      </td>
      <td style={TD}>
        {row.status ? (
          <Chip size="small" label={row.status} color={statusTone(row.status)} variant="outlined"
            sx={{ fontSize: 11, height: 20 }} />
        ) : null}
      </td>
      <td style={{ ...TD, textAlign: "right" }}>
        {added ? (
          <CheckCircleIcon sx={{ fontSize: 18, color: "success.main" }} aria-label="Already in investigation" />
        ) : (
          <IconButton
            size="small"
            aria-label={`Add ${row.patient_name || row.patient_id}`}
            sx={{ ...pressable, p: 0.5, color: "primary.main" }}
            onClick={(e) => { e.stopPropagation(); onPick(row); }}
          >
            <AddCircleOutlineIcon sx={{ fontSize: 18 }} />
          </IconButton>
        )}
      </td>
    </tr>
  );
}

export function NhsGroupRows({
  group,
  expandedNhs,
  onToggle,
  linkedKeys,
  onPick,
}: {
  group: { nhsKey: string; patientName: string; runs: ClinicalPipelineRun[] };
  expandedNhs: string | null;
  onToggle: (key: string) => void;
  linkedKeys: Set<string>;
  onPick: (row: ClinicalPipelineRun) => void;
}) {
  const expanded = expandedNhs === group.nhsKey;
  const firstRun = group.runs[0];
  const allAdded = group.runs.every((r) => linkedKeys.has(investigationKey(r)));
  return (
    <>
      {/* Patient summary row */}
      <tr
        data-testid={`nhs-group-${group.nhsKey}`}
        style={{
          background: "#EFF6FF",
          cursor: "pointer",
          borderTop: "2px solid #DBEAFE",
        }}
        onClick={() => onToggle(group.nhsKey)}
      >
        <td style={{ ...TD, color: "#6B7280", fontSize: 12 }}>
          {shortDate(firstRun.created_at)}
        </td>
        <td style={TD}>
          <Stack direction="row" alignItems="center" spacing={0.75}>
            <ChevronRightIcon
              sx={{
                fontSize: 16,
                color: "primary.main",
                transition: "transform 180ms ease-out",
                transform: expanded ? "rotate(90deg)" : "rotate(0deg)",
              }}
            />
            <Typography variant="body2" sx={{ fontWeight: 700, color: "primary.dark" }}>
              {group.patientName}
            </Typography>
            <Chip size="small" label={`${group.runs.length} runs`}
              sx={{ fontSize: 10, height: 18, bgcolor: "#DBEAFE", color: "#1E40AF", border: "none" }} />
          </Stack>
        </td>
        <td style={{ ...TD, color: "#6B7280", fontSize: 13, fontVariantNumeric: "tabular-nums" }}>
          {firstRun.nhs_number || "—"}
        </td>
        <td style={TD} colSpan={2} />
        <td style={{ ...TD, textAlign: "right" }}>
          {allAdded ? (
            <CheckCircleIcon sx={{ fontSize: 18, color: "success.main" }} aria-label="All added" />
          ) : null}
        </td>
      </tr>
      {/* Individual runs when expanded */}
      {expanded &&
        group.runs.map((run, i) => (
          <RunDataRow
            key={investigationKey(run)}
            row={run}
            index={i}
            indent
            linkedKeys={linkedKeys}
            onPick={onPick}
          />
        ))}
    </>
  );
}

const TH_BASE: React.CSSProperties = {
  textAlign: "left",
  fontSize: 11,
  fontWeight: 700,
  textTransform: "uppercase",
  letterSpacing: "0.05em",
  color: "#6B7280",
  padding: "8px 12px",
  borderBottom: "1px solid #E5E7EB",
  background: "#F9FAFB",
  position: "sticky",
  top: 0,
  zIndex: 1,
  whiteSpace: "nowrap",
};

const SORT_BTN: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  background: "none",
  border: "none",
  padding: 0,
  cursor: "pointer",
  fontSize: "inherit",
  fontWeight: "inherit",
  textTransform: "inherit",
  letterSpacing: "inherit",
  color: "inherit",
  fontFamily: "inherit",
};

const TD: React.CSSProperties = {
  padding: "10px 12px",
  borderBottom: "1px solid #F3F4F6",
  fontSize: 13,
  verticalAlign: "middle",
};
