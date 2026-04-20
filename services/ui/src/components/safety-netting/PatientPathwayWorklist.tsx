/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-B1116B14
 *   DI: DI-35494904
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-B1116B14")
 */
"use client";

import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import type { SafetyNetWorklistItem } from "@/lib/analyticsApi";
import type { Milestone, PathwayRisk } from "@/lib/pathwayRisk";
import PathwayProgressBar from "@/components/safety-netting/PathwayProgressBar";

export interface SafetyNetWorklistRow extends SafetyNetWorklistItem {
  risk: PathwayRisk;
  normalizedMilestones: Milestone[];
}

const RAG_COLOR: Record<string, string> = {
  breached: "#dc2626",
  "at-risk": "#d97706",
  "on-track": "#16a34a",
  completed: "#6b7280",
  unknown: "#9ca3af",
};

function compactDate(value?: string): string {
  if (!value) return "\u2014";
  return value.slice(0, 10);
}

function shortBreachLabel(b: {
  target: { label: string };
  daysElapsed: number | null;
  daysRemaining: number | null;
  achieved: boolean;
  breached: boolean;
}): string {
  if (b.achieved && b.breached) return `${b.daysElapsed}d (breached)`;
  if (b.achieved)
    return `${b.daysElapsed}d / ${b.target.label.match(/\d+/)?.[0] ?? ""}d`;
  const remaining = b.daysRemaining ?? 0;
  if (remaining < 0 && Math.abs(remaining) > 365) return "Stale \u2013 review";
  if (remaining < 0) return `${Math.abs(remaining)}d overdue`;
  return `${remaining}d left`;
}

const COL = {
  rag: "3.5%",
  patient: "14%",
  site: "13%",
  pathway: "20%",
  fds: "13%",
  action: "24.5%",
  lastActivity: "12%",
} as const;

const HEADER_SX = {
  fontWeight: 700,
  fontSize: "0.7rem",
  letterSpacing: "0.06em",
  textTransform: "uppercase" as const,
  color: "text.secondary",
  whiteSpace: "nowrap" as const,
  borderBottom: "2px solid",
  borderColor: "divider",
  py: 1.25,
};

export default function PatientPathwayWorklist({
  rows,
  selectedEpisodeId,
  onSelect,
}: {
  rows: SafetyNetWorklistRow[];
  selectedEpisodeId: string | null;
  onSelect: (row: SafetyNetWorklistRow) => void;
}) {
  if (rows.length === 0) {
    return (
      <Box sx={{ p: 4, textAlign: "center" }}>
        <Typography color="text.secondary">
          No pathways match your filters.
        </Typography>
      </Box>
    );
  }

  return (
    <Box sx={{ overflow: "auto", height: "100%" }}>
      <Table size="small" sx={{ tableLayout: "fixed", width: "100%" }}>
        <TableHead>
          <TableRow
            sx={{
              position: "sticky",
              top: 0,
              bgcolor: "background.paper",
              zIndex: 2,
            }}
          >
            <TableCell sx={{ ...HEADER_SX, width: COL.rag, pl: 2.5, pr: 0 }}>
              RAG
            </TableCell>
            <TableCell sx={{ ...HEADER_SX, width: COL.patient }}>
              Patient
            </TableCell>
            <TableCell sx={{ ...HEADER_SX, width: COL.site }}>
              Cancer Site
            </TableCell>
            <TableCell sx={{ ...HEADER_SX, width: COL.pathway }}>
              Pathway
            </TableCell>
            <TableCell sx={{ ...HEADER_SX, width: COL.fds }}>FDS</TableCell>
            <TableCell sx={{ ...HEADER_SX, width: COL.action }}>
              Action Required
            </TableCell>
            <TableCell
              sx={{ ...HEADER_SX, width: COL.lastActivity, pr: 2.5 }}
            >
              Last Activity
            </TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((row, idx) => {
            const fds = row.risk.breaches.find(
              (b) => b.target.label === "28-day FDS",
            );
            const outstanding = row.alerts.filter((a) => !a.actioned);
            const hasAction = outstanding.length > 0;
            const actionText =
              outstanding[0]?.description ?? "No action required";
            const isSelected = selectedEpisodeId === row.episode_id;
            const zebra = idx % 2 === 1;

            const chipColor = fds?.breached
              ? "#dc2626"
              : fds?.achieved
                ? "#16a34a"
                : "#64748b";
            const chipBg = fds?.breached
              ? "#fef2f2"
              : fds?.achieved
                ? "#f0fdf4"
                : "#f8fafc";

            return (
              <TableRow
                key={row.episode_id}
                hover
                selected={isSelected}
                onClick={() => onSelect(row)}
                sx={{
                  cursor: "pointer",
                  bgcolor: isSelected
                    ? "action.selected"
                    : zebra
                      ? "grey.50"
                      : "background.paper",
                  "&:hover": { bgcolor: "action.hover" },
                  "&.Mui-selected": { bgcolor: "action.selected" },
                }}
              >
                <TableCell sx={{ pl: 2.5, pr: 0, py: 1.5 }}>
                  <Box
                    sx={{
                      width: 10,
                      height: 10,
                      borderRadius: "50%",
                      bgcolor:
                        RAG_COLOR[row.risk.level] ?? RAG_COLOR.unknown,
                    }}
                  />
                </TableCell>
                <TableCell sx={{ py: 1.5 }}>
                  <Typography
                    variant="body2"
                    sx={{
                      fontWeight: 600,
                      fontFamily: "var(--font-mono)",
                      fontSize: "0.8rem",
                      lineHeight: 1.4,
                    }}
                  >
                    {row.patient_id}
                  </Typography>
                  <Typography
                    variant="caption"
                    color="text.secondary"
                    sx={{ fontSize: "0.72rem" }}
                  >
                    {compactDate(row.birth_date)}
                  </Typography>
                </TableCell>
                <TableCell sx={{ py: 1.5 }}>
                  <Typography
                    variant="body2"
                    sx={{
                      fontSize: "0.84rem",
                      textTransform: "capitalize",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {row.condition_type ?? "\u2014"}
                  </Typography>
                </TableCell>
                <TableCell sx={{ py: 1.5, pr: 2 }}>
                  <PathwayProgressBar milestones={row.normalizedMilestones} />
                </TableCell>
                <TableCell sx={{ py: 1.5 }}>
                  {fds ? (
                    <Chip
                      size="small"
                      label={shortBreachLabel(fds)}
                      sx={{
                        fontWeight: 600,
                        fontSize: "0.72rem",
                        maxWidth: "100%",
                        color: chipColor,
                        bgcolor: chipBg,
                        border: `1px solid ${chipColor}30`,
                      }}
                    />
                  ) : (
                    <Typography variant="caption" color="text.disabled">
                      {"\u2014"}
                    </Typography>
                  )}
                </TableCell>
                <TableCell sx={{ py: 1.5 }}>
                  <Typography
                    variant="body2"
                    sx={{
                      fontSize: "0.84rem",
                      color: hasAction ? "text.primary" : "text.disabled",
                      fontWeight: hasAction ? 500 : 400,
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {hasAction ? actionText : "\u2014"}
                  </Typography>
                </TableCell>
                <TableCell sx={{ py: 1.5, pr: 2.5 }}>
                  <Typography
                    variant="caption"
                    color="text.secondary"
                    sx={{ fontSize: "0.78rem", whiteSpace: "nowrap" }}
                  >
                    {compactDate(
                      row.last_encounter_date || row.referral_date,
                    )}
                  </Typography>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </Box>
  );
}
