/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-30A82196
 *   DI: DI-85B110A5
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-30A82196")
 */
"use client";

import Link from "next/link";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import Step from "@mui/material/Step";
import StepLabel from "@mui/material/StepLabel";
import Stepper from "@mui/material/Stepper";
import Typography from "@mui/material/Typography";
import CloseIcon from "@mui/icons-material/Close";
import type { SafetyNetAlert } from "@/lib/analyticsApi";
import type { PathwayRisk } from "@/lib/pathwayRisk";
import type { SafetyNetWorklistRow } from "@/components/safety-netting/PatientPathwayWorklist";
import { daysBetween } from "@/lib/pathwayRisk";
import { useDemoMode } from "@/context/DemoModeContext";
import { maskBirthDate, maskPatientId } from "@/lib/demoMode";

const SEVERITY_COLORS: Record<string, "error" | "warning" | "info"> = {
  critical: "error",
  high: "error",
  alert: "error",
  warning: "warning",
  medium: "warning",
  low: "info",
};

const PATHWAY_STEPS = ["Referred", "Booked / First Seen", "Diagnostics", "Outcome"] as const;

function safeDate(value?: string): string {
  return value?.slice(0, 10) ?? "-";
}

function daysOnPathway(referralDate?: string, lastEncounterDate?: string): string {
  if (!referralDate) return "-";
  const end = (lastEncounterDate ?? new Date().toISOString()).slice(0, 10);
  return `${daysBetween(referralDate.slice(0, 10), end)} days`;
}

function fdsDeadline(referralDate?: string): string {
  if (!referralDate) return "-";
  const d = new Date(referralDate);
  d.setDate(d.getDate() + 28);
  return d.toISOString().slice(0, 10);
}

function rttDeadline(referralDate?: string): string {
  if (!referralDate) return "-";
  const d = new Date(referralDate);
  d.setDate(d.getDate() + 62);
  return d.toISOString().slice(0, 10);
}

/** Returns how many steps are *completed* (i.e. the active step index for MUI Stepper). */
function completedStepCount(risk: PathwayRisk): number {
  switch (risk.nextExpectedMilestone) {
    case "presentation":
    case "referral":
      return 0; // nothing done yet
    case "first_clinic":
      return 1; // Referred done
    case "diagnosis":
      return 2; // Referred + Booked done
    case "treatment_decision":
    case "first_treatment":
      return 3; // Referred + Booked + Diagnostics done
    default:
      return 4; // all done
  }
}

export default function PathwayDetailPanel({
  row,
  onClose,
  onActionAlert,
  actionLoading,
}: {
  row: SafetyNetWorklistRow;
  onClose: () => void;
  onActionAlert: (alertId: string, actioned: boolean) => void;
  actionLoading: boolean;
}) {
  const { isDemoMode } = useDemoMode();
  const outstanding = row.alerts.filter((a) => !a.actioned);
  const worst = outstanding[0] ?? row.alerts[0];
  const activeStep = completedStepCount(row.risk);

  return (
    <Box
      sx={{
        width: 380,
        flexShrink: 0,
        borderLeft: "1px solid",
        borderColor: "divider",
        bgcolor: "background.paper",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}
    >
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          px: 2,
          py: 1.5,
          borderBottom: "1px solid",
          borderColor: "divider",
        }}
      >
        <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
          {isDemoMode ? maskPatientId(row.patient_id) : row.patient_id}
        </Typography>
        <IconButton aria-label="Close" size="small" onClick={onClose}>
          <CloseIcon fontSize="small" />
        </IconButton>
      </Box>

      <Box sx={{ p: 2, overflow: "auto", flex: 1 }}>
        <Typography variant="caption" color="text.secondary">
          {`DOB: ${
            isDemoMode ? maskBirthDate(row.birth_date) : safeDate(row.birth_date)
          } ${row.gender ? `· ${row.gender}` : ""}`}
        </Typography>

        {worst && (
          <Alert severity={SEVERITY_COLORS[worst.severity] ?? "warning"} sx={{ mt: 1.5, mb: 2 }}>
            {worst.description}
          </Alert>
        )}

        <Typography variant="subtitle2" sx={{ mb: 1 }}>
          Pathway Progress
        </Typography>
        <Stepper activeStep={activeStep} orientation="vertical" sx={{ mb: 2 }}>
          {PATHWAY_STEPS.map((label) => (
            <Step key={label}>
              <StepLabel>{label}</StepLabel>
            </Step>
          ))}
        </Stepper>

        <Typography variant="subtitle2" sx={{ mb: 1 }}>
          Referral Details
        </Typography>
        <DetailRow label="Cancer Site" value={row.condition_type ?? "-"} />
        <DetailRow label="Referred" value={safeDate(row.referral_date)} />
        <DetailRow
          label="Days on Pathway"
          value={daysOnPathway(row.referral_date, row.last_encounter_date)}
        />
        <DetailRow label="FDS Deadline" value={fdsDeadline(row.referral_date)} />
        <DetailRow label="62-day Target" value={rttDeadline(row.referral_date)} />
        <DetailRow label="Last Activity" value={safeDate(row.last_encounter_date)} />

        <Divider sx={{ my: 1.5 }} />

        <Typography variant="subtitle2" sx={{ mb: 1 }}>
          Linked Alerts
        </Typography>
        {row.alerts.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            No linked alerts
          </Typography>
        ) : (
          <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
            {row.alerts.map((alert) => (
              <Box key={alert.id} sx={{ border: "1px solid", borderColor: "divider", borderRadius: 1.5, p: 1 }}>
                <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.5 }}>
                  <Chip
                    size="small"
                    color={SEVERITY_COLORS[alert.severity] ?? "default"}
                    label={alert.severity}
                    sx={{ textTransform: "capitalize" }}
                  />
                  {alert.actioned && <Chip size="small" label="Actioned" color="success" variant="outlined" />}
                </Box>
                <Typography variant="body2" sx={{ fontSize: "0.85rem" }}>
                  {alert.description}
                </Typography>
              </Box>
            ))}
          </Box>
        )}
      </Box>

      <Box sx={{ p: 2, borderTop: "1px solid", borderColor: "divider", display: "flex", flexDirection: "column", gap: 1 }}>
        <Button
          variant="contained"
          disabled={actionLoading || outstanding.length === 0}
          onClick={() => {
            const first = outstanding[0];
            if (first) onActionAlert(first.id, true);
          }}
        >
          Record Action Taken
        </Button>
        <Button variant="outlined" color="warning" component={Link} href="/admin/console">
          Escalate to Lead
        </Button>
        <Button
          variant="outlined"
          component={Link}
          href={`/care/patients/${row.patient_id}`}
        >
          Add Clinical Note
        </Button>
        <Button variant="outlined" component={Link} href={`/pathways?id=${row.episode_id}`}>
          View Audit Trail
        </Button>
      </Box>
    </Box>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <Box sx={{ display: "flex", justifyContent: "space-between", py: 0.4, gap: 1.5, minWidth: 0 }}>
      <Typography
        variant="caption"
        color="text.secondary"
        sx={{ flexShrink: 0, whiteSpace: "nowrap" }}
      >
        {label}
      </Typography>
      <Typography
        variant="caption"
        sx={{
          fontWeight: 600,
          textAlign: "right",
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
          minWidth: 0,
        }}
      >
        {value}
      </Typography>
    </Box>
  );
}

