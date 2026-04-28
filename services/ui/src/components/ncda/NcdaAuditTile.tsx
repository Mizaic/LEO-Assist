/**
 * NCDA audit-findings tile (Stage 9b).
 *
 * Surfaces open ncda_label_audit rows for reviewer triage. Reviewer actions
 * (mark_correct, relabel, delete_milestone, add_to_read_code_lookup) write
 * back via the audit API; Stage 2 tidy migration blocks on any open
 * severity='high' row.
 */
"use client";

import * as React from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";

import {
  NCDA_AUDIT_FINDING_LABELS,
  NCDA_AUDIT_SEVERITY_LABELS,
  NCDA_REVIEWER_ACTIONS,
  NcdaAuditFindingKey,
  NcdaSeverityKey,
} from "@/lib/ncdaLabels";

export interface NcdaAuditFinding {
  patient_id: string;
  episode_id: string | null;
  encounter_id: string;
  current_milestone: string | null;
  suggested_role: string | null;
  suggested_outcome: string | null;
  finding_type: NcdaAuditFindingKey;
  severity: NcdaSeverityKey;
  rationale: string;
  supporting_quote: string | null;
  status: string;
}

const SEVERITY_COLOR: Record<string, "error" | "warning" | "info" | "default"> = {
  high: "error",
  medium: "warning",
  low: "info",
  info: "default",
};

export type ReviewerAction = keyof typeof NCDA_REVIEWER_ACTIONS;

export interface NcdaAuditTileProps {
  findings: NcdaAuditFinding[];
  onAction?: (
    finding: NcdaAuditFinding,
    action: ReviewerAction,
  ) => void | Promise<void>;
}

export function NcdaAuditTile({ findings, onAction }: NcdaAuditTileProps) {
  const [severityFilter, setSeverityFilter] = React.useState<string>("all");
  const filtered = React.useMemo(
    () => findings.filter((f) => severityFilter === "all" || f.severity === severityFilter),
    [findings, severityFilter],
  );

  return (
    <Box data-testid="ncda-audit-tile" sx={{ p: 2 }}>
      <Stack direction="row" alignItems="center" spacing={2} mb={2}>
        <Typography variant="h6">Audit findings</Typography>
        <Chip label={`${filtered.length} open`} size="small" />
        <Box sx={{ flex: 1 }} />
        <Select
          size="small"
          value={severityFilter}
          onChange={(e) => setSeverityFilter(String(e.target.value))}
          data-testid="ncda-audit-severity-filter"
        >
          <MenuItem value="all">All severities</MenuItem>
          <MenuItem value="high">{NCDA_AUDIT_SEVERITY_LABELS.high}</MenuItem>
          <MenuItem value="medium">{NCDA_AUDIT_SEVERITY_LABELS.medium}</MenuItem>
          <MenuItem value="low">{NCDA_AUDIT_SEVERITY_LABELS.low}</MenuItem>
          <MenuItem value="info">{NCDA_AUDIT_SEVERITY_LABELS.info}</MenuItem>
        </Select>
      </Stack>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>Severity</TableCell>
            <TableCell>What went wrong</TableCell>
            <TableCell>Current label</TableCell>
            <TableCell>Suggested label</TableCell>
            <TableCell>Why</TableCell>
            <TableCell>Actions</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {filtered.map((f) => (
            <TableRow key={`${f.patient_id}:${f.encounter_id}:${f.finding_type}`}>
              <TableCell>
                <Chip
                  label={NCDA_AUDIT_SEVERITY_LABELS[f.severity]}
                  color={SEVERITY_COLOR[f.severity]}
                  size="small"
                />
              </TableCell>
              <TableCell>{NCDA_AUDIT_FINDING_LABELS[f.finding_type]}</TableCell>
              <TableCell>
                <Typography variant="body2">{f.current_milestone ?? "-"}</Typography>
              </TableCell>
              <TableCell>
                <Typography variant="body2">
                  {f.suggested_role ?? "-"}
                  {f.suggested_outcome ? ` (${f.suggested_outcome})` : ""}
                </Typography>
              </TableCell>
              <TableCell>
                <Typography variant="body2" color="text.secondary">
                  {f.rationale}
                </Typography>
                {f.supporting_quote && (
                  <Typography variant="caption" color="text.secondary">
                    "{f.supporting_quote}"
                  </Typography>
                )}
              </TableCell>
              <TableCell>
                <Stack direction="row" spacing={1}>
                  {(Object.keys(NCDA_REVIEWER_ACTIONS) as ReviewerAction[]).map(
                    (action) => (
                      <Button
                        key={action}
                        size="small"
                        variant="outlined"
                        onClick={() => onAction?.(f, action)}
                        data-testid={`ncda-audit-action-${action}`}
                      >
                        {NCDA_REVIEWER_ACTIONS[action]}
                      </Button>
                    ),
                  )}
                </Stack>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Box>
  );
}

export default NcdaAuditTile;
