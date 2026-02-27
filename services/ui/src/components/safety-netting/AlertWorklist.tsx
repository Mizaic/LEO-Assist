"use client";

import { useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Chip from "@mui/material/Chip";
import Table from "@mui/material/Table";
import TableHead from "@mui/material/TableHead";
import TableBody from "@mui/material/TableBody";
import TableRow from "@mui/material/TableRow";
import TableCell from "@mui/material/TableCell";
import Collapse from "@mui/material/Collapse";
import IconButton from "@mui/material/IconButton";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import PersonOutlineIcon from "@mui/icons-material/PersonOutline";
import type { SafetyNetAlert } from "@/lib/analyticsApi";

const SEVERITY_COLORS: Record<string, "error" | "warning" | "info" | "default"> = {
  critical: "error",
  high: "error",
  medium: "warning",
  low: "info",
};

const SEVERITY_ORDER: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3 };

interface PatientGroup {
  patientId: string;
  alerts: SafetyNetAlert[];
  worstSeverity: string;
}

function groupByPatient(alerts: SafetyNetAlert[]): PatientGroup[] {
  const map = new Map<string, SafetyNetAlert[]>();
  for (const a of alerts) {
    const key = a.patient_id ?? "Unknown";
    const list = map.get(key);
    if (list) {
      list.push(a);
    } else {
      map.set(key, [a]);
    }
  }
  return Array.from(map.entries())
    .map(([patientId, patientAlerts]) => ({
      patientId,
      alerts: patientAlerts,
      worstSeverity: patientAlerts.reduce(
        (worst, a) =>
          (SEVERITY_ORDER[a.severity] ?? 99) < (SEVERITY_ORDER[worst] ?? 99)
            ? a.severity
            : worst,
        "low",
      ),
    }))
    .sort(
      (a, b) =>
        (SEVERITY_ORDER[a.worstSeverity] ?? 99) -
        (SEVERITY_ORDER[b.worstSeverity] ?? 99),
    );
}

export type ViewMode = "grouped" | "flat";

interface AlertWorklistProps {
  alerts: SafetyNetAlert[];
  selectedId: string | null;
  onSelect: (alert: SafetyNetAlert) => void;
  viewMode?: ViewMode;
}

export default function AlertWorklist({
  alerts,
  selectedId,
  onSelect,
  viewMode = "grouped",
}: AlertWorklistProps) {
  const groups = useMemo(() => groupByPatient(alerts), [alerts]);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  if (alerts.length === 0) {
    return (
      <Box sx={{ p: 4, textAlign: "center" }}>
        <Typography color="text.secondary">
          No alerts match your filters.
        </Typography>
      </Box>
    );
  }

  const toggle = (patientId: string) => {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(patientId)) {
        next.delete(patientId);
      } else {
        next.add(patientId);
      }
      return next;
    });
  };

  const allCollapsed = groups.every((g) => collapsed.has(g.patientId));

  const toggleAll = () => {
    if (allCollapsed) {
      setCollapsed(new Set());
    } else {
      setCollapsed(new Set(groups.map((g) => g.patientId)));
    }
  };

  if (viewMode === "flat") {
    return (
      <Box sx={{ overflow: "auto", height: "100%" }}>
        <Table size="small" sx={{ tableLayout: "fixed" }}>
          <TableHead>
            <TableRow sx={{ bgcolor: "background.paper" }}>
              <TableCell sx={{ width: 90 }}>Severity</TableCell>
              <TableCell sx={{ width: 180 }}>Type</TableCell>
              <TableCell>Description</TableCell>
              <TableCell sx={{ width: 100 }}>Patient</TableCell>
              <TableCell sx={{ width: 120 }}>Cancer type</TableCell>
              <TableCell sx={{ width: 50, textAlign: "center" }}>Status</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {alerts.map((alert) => (
              <TableRow
                key={alert.id}
                hover
                selected={alert.id === selectedId}
                onClick={() => onSelect(alert)}
                sx={{ cursor: "pointer" }}
              >
                <TableCell>
                  <Chip
                    label={alert.severity}
                    size="small"
                    color={SEVERITY_COLORS[alert.severity] ?? "default"}
                    sx={{ textTransform: "capitalize", minWidth: 64 }}
                  />
                </TableCell>
                <TableCell>
                  <Typography variant="body2" sx={{ fontWeight: 500, fontSize: "0.85rem" }}>
                    {alert.type}
                  </Typography>
                </TableCell>
                <TableCell>
                  <Typography
                    variant="body2"
                    sx={{
                      fontSize: "0.85rem",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {alert.description}
                  </Typography>
                </TableCell>
                <TableCell>
                  <Typography variant="caption" sx={{ fontFamily: "monospace" }}>
                    {alert.patient_id ?? "-"}
                  </Typography>
                </TableCell>
                <TableCell>
                  <Typography variant="caption" sx={{ fontSize: "0.8rem" }}>
                    {alert.condition_type ?? "-"}
                  </Typography>
                </TableCell>
                <TableCell sx={{ textAlign: "center" }}>
                  {alert.actioned && (
                    <CheckCircleIcon
                      sx={{ fontSize: 18, color: "success.main" }}
                      aria-label="actioned"
                    />
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Box>
    );
  }

  return (
    <Box sx={{ overflow: "auto", height: "100%" }}>
      <Table size="small" sx={{ tableLayout: "fixed" }}>
        <TableHead>
          <TableRow sx={{ bgcolor: "background.paper" }}>
            <TableCell sx={{ width: 44, px: 0.5 }}>
              <IconButton
                size="small"
                onClick={toggleAll}
                aria-label={allCollapsed ? "expand all patients" : "collapse all patients"}
              >
                {allCollapsed ? (
                  <ChevronRightIcon sx={{ fontSize: 18 }} />
                ) : (
                  <ExpandMoreIcon sx={{ fontSize: 18 }} />
                )}
              </IconButton>
            </TableCell>
            <TableCell sx={{ width: 90 }}>Severity</TableCell>
            <TableCell sx={{ width: 180 }}>Type</TableCell>
            <TableCell>Description</TableCell>
            <TableCell sx={{ width: 120 }}>Cancer type</TableCell>
            <TableCell sx={{ width: 50, textAlign: "center" }}>Status</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {groups.map((group) => {
            const isCollapsed = collapsed.has(group.patientId);
            const outstandingCount = group.alerts.filter((a) => !a.actioned).length;

            return (
              <PatientGroupRows
                key={group.patientId}
                group={group}
                isCollapsed={isCollapsed}
                outstandingCount={outstandingCount}
                selectedId={selectedId}
                onToggle={() => toggle(group.patientId)}
                onSelect={onSelect}
              />
            );
          })}
        </TableBody>
      </Table>
    </Box>
  );
}

function PatientGroupRows({
  group,
  isCollapsed,
  outstandingCount,
  selectedId,
  onToggle,
  onSelect,
}: {
  group: PatientGroup;
  isCollapsed: boolean;
  outstandingCount: number;
  selectedId: string | null;
  onToggle: () => void;
  onSelect: (alert: SafetyNetAlert) => void;
}) {
  return (
    <>
      <TableRow
        onClick={onToggle}
        sx={{
          bgcolor: "action.hover",
          cursor: "pointer",
          "&:hover": { bgcolor: "action.selected" },
        }}
      >
        <TableCell sx={{ px: 0.5 }}>
          <IconButton
            size="small"
            aria-label={isCollapsed ? `expand ${group.patientId}` : `collapse ${group.patientId}`}
          >
            {isCollapsed ? (
              <ChevronRightIcon sx={{ fontSize: 18 }} />
            ) : (
              <ExpandMoreIcon sx={{ fontSize: 18 }} />
            )}
          </IconButton>
        </TableCell>
        <TableCell colSpan={5}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
            <PersonOutlineIcon sx={{ fontSize: 18, color: "text.secondary" }} />
            <Typography
              variant="body2"
              sx={{ fontWeight: 600, fontFamily: "monospace", fontSize: "0.85rem" }}
            >
              {group.patientId}
            </Typography>
            <Chip
              label={`${group.alerts.length} alert${group.alerts.length !== 1 ? "s" : ""}`}
              size="small"
              variant="outlined"
              sx={{ height: 22, fontSize: "0.75rem" }}
            />
            {outstandingCount > 0 && (
              <Chip
                label={`${outstandingCount} outstanding`}
                size="small"
                color={SEVERITY_COLORS[group.worstSeverity] ?? "default"}
                sx={{ height: 22, fontSize: "0.75rem" }}
              />
            )}
          </Box>
        </TableCell>
      </TableRow>

      {!isCollapsed &&
        group.alerts.map((alert) => (
          <TableRow
            key={alert.id}
            hover
            selected={alert.id === selectedId}
            onClick={() => onSelect(alert)}
            sx={{ cursor: "pointer" }}
          >
            <TableCell />
            <TableCell>
              <Chip
                label={alert.severity}
                size="small"
                color={SEVERITY_COLORS[alert.severity] ?? "default"}
                sx={{ textTransform: "capitalize", minWidth: 64 }}
              />
            </TableCell>
            <TableCell>
              <Typography variant="body2" sx={{ fontWeight: 500, fontSize: "0.85rem" }}>
                {alert.type}
              </Typography>
            </TableCell>
            <TableCell>
              <Typography
                variant="body2"
                sx={{
                  fontSize: "0.85rem",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
              >
                {alert.description}
              </Typography>
            </TableCell>
            <TableCell>
              <Typography variant="caption" sx={{ fontSize: "0.8rem" }}>
                {alert.condition_type ?? "-"}
              </Typography>
            </TableCell>
            <TableCell sx={{ textAlign: "center" }}>
              {alert.actioned && (
                <CheckCircleIcon
                  sx={{ fontSize: 18, color: "success.main" }}
                  aria-label="actioned"
                />
              )}
            </TableCell>
          </TableRow>
        ))}
    </>
  );
}
