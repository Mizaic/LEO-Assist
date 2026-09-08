/**
 * Clinical door matching, recent, frequent, and all-patient lists.
 *
 * Atlas: DI-238DA59A / DO-4FD76836
 *
 * Atlas trace:
 *   DO: DO-158BE606
 *   DI: DI-2289D095
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-158BE606")
 */
"use client";

import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import AddCircleOutlineIcon from "@mui/icons-material/AddCircleOutline";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";

import type { ClinicalPipelineRun } from "./labFindingsApi";
import { investigationKey } from "./ncrInvestigationCases";
import {
  glassPanel,
  matchLabel,
  pressable,
  sectionLabel,
  shortDate,
  statusTone,
} from "./clinicalDoorChrome";

export function UsedAndAllLists({
  recent,
  frequent,
  patients,
  onPick,
  linkedCases = [],
}: {
  recent: ClinicalPipelineRun[];
  frequent: ClinicalPipelineRun[];
  patients: ClinicalPipelineRun[];
  onPick: (row: ClinicalPipelineRun) => void;
  linkedCases?: ClinicalPipelineRun[];
}) {
  const linkedKeys = new Set(linkedCases.map(investigationKey));
  return (
    <>
      {/* Recently used: compact rows with instant add / already-added checkmark */}
      {recent.length > 0 ? (
        <Box data-testid="validation-lab-clinical-recent">
          <Typography sx={{ ...sectionLabel, mb: 1.25 }}>Recently used</Typography>
          <Stack
            spacing={0.5}
            sx={{
              ...glassPanel,
              p: 1,
              borderRadius: "16px",
            }}
          >
            {recent.map((row) => (
              <CompactPatientRow
                key={`${row.patient_id}-${row.run_id}-${row.nhs_number}`}
                row={row}
                onPick={onPick}
                alreadyAdded={linkedKeys.has(investigationKey(row))}
              />
            ))}
          </Stack>
        </Box>
      ) : null}
      <PatientSection
        title="Frequently used"
        testId="validation-lab-clinical-frequent"
        emptyText="Patients you open often will show here."
        rows={frequent}
        onPick={onPick}
        linkedCases={linkedCases}
      />
      <PatientSection
        title="All patients"
        testId="validation-lab-clinical-all-patients"
        emptyText="No patients with a pipeline run yet."
        rows={patients}
        onPick={onPick}
        linkedCases={linkedCases}
        scroll
      />
    </>
  );
}

function CompactPatientRow({
  row,
  onPick,
  alreadyAdded,
}: {
  row: ClinicalPipelineRun;
  onPick: (row: ClinicalPipelineRun) => void;
  alreadyAdded: boolean;
}) {
  const label = [
    row.patient_name || row.patient_id || "Patient",
    row.nhs_number ? `NHS ${row.nhs_number}` : "",
    row.ubrn ? `Referral ${row.ubrn}` : "",
    shortDate(row.created_at),
  ].filter(Boolean).join(" -- ");
  return (
    <Stack
      direction="row"
      alignItems="center"
      justifyContent="space-between"
      spacing={1}
      sx={{
        px: 1,
        py: 0.75,
        borderRadius: "10px",
        cursor: alreadyAdded ? "default" : "pointer",
        transition: "background 140ms ease-out",
        "@media (hover: hover) and (pointer: fine)": {
          "&:hover": {
            bgcolor: alreadyAdded ? "transparent" : "action.hover",
          },
        },
      }}
      onClick={alreadyAdded ? undefined : () => onPick(row)}
    >
      <Typography
        variant="body2"
        sx={{
          flex: 1,
          color: alreadyAdded ? "text.secondary" : "text.primary",
          lineHeight: 1.4,
        }}
      >
        {label}
      </Typography>
      {alreadyAdded ? (
        <CheckCircleIcon
          sx={{ fontSize: 18, color: "success.main", flexShrink: 0 }}
          aria-label="Already in investigation"
        />
      ) : (
        <IconButton
          size="small"
          onClick={() => onPick(row)}
          aria-label={`Add ${row.patient_name || row.patient_id}`}
          sx={{
            ...pressable,
            p: 0.5,
            color: "primary.main",
          }}
        >
          <AddCircleOutlineIcon sx={{ fontSize: 18 }} />
        </IconButton>
      )}
    </Stack>
  );
}

export function PatientSection({
  title,
  testId,
  rows,
  onPick,
  emptyText,
  scroll,
  linkedCases,
}: {
  title: string;
  testId: string;
  rows: ClinicalPipelineRun[];
  onPick: (row: ClinicalPipelineRun) => void;
  emptyText?: string;
  scroll?: boolean;
  linkedCases?: ClinicalPipelineRun[];
}) {
  const linkedKeys = new Set((linkedCases || []).map(investigationKey));
  return (
    <Box data-testid={testId}>
      <Typography sx={{ ...sectionLabel, mb: 1.25 }}>{title}</Typography>
      {rows.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          {emptyText || "None yet."}
        </Typography>
      ) : (
        <Stack
          spacing={1.25}
          sx={scroll ? { maxHeight: 360, overflow: "auto", pr: 0.5 } : undefined}
        >
          {rows.map((row) => (
            <PatientRow
              key={`${row.patient_id}-${row.run_id}-${row.nhs_number}`}
              row={row}
              onPick={onPick}
              alreadyAdded={linkedKeys.has(investigationKey(row))}
            />
          ))}
        </Stack>
      )}
    </Box>
  );
}

function PatientRow({
  row,
  onPick,
  alreadyAdded = false,
}: {
  row: ClinicalPipelineRun;
  onPick: (row: ClinicalPipelineRun) => void;
  alreadyAdded?: boolean;
}) {
  const why = matchLabel(row.matched_on);
  return (
    <Box
      onClick={alreadyAdded ? undefined : () => onPick(row)}
      sx={{
        ...glassPanel,
        ...(!alreadyAdded && pressable),
        p: 2,
        borderRadius: "16px",
        opacity: alreadyAdded ? 0.6 : 1,
        cursor: alreadyAdded ? "default" : "pointer",
        "@media (hover: hover) and (pointer: fine)": {
          "&:hover": {
            boxShadow: alreadyAdded
              ? undefined
              : "0 14px 40px rgba(15, 23, 42, 0.12)",
          },
        },
      }}
    >
      <Stack
        direction="row"
        alignItems="center"
        justifyContent="space-between"
        spacing={1}
        sx={{ mb: 0.75 }}
      >
        <Typography sx={{ fontWeight: 700, letterSpacing: "-0.01em" }}>
          {row.patient_name || row.patient_id || "Patient"}
        </Typography>
        <Stack direction="row" spacing={0.75} alignItems="center">
          {alreadyAdded ? (
            <CheckCircleIcon
              sx={{ fontSize: 16, color: "success.main" }}
              aria-label="Already in investigation"
            />
          ) : null}
          {why ? <Chip size="small" label={why} variant="outlined" /> : null}
          {row.status ? (
            <Chip
              size="small"
              label={row.status}
              color={statusTone(row.status)}
              variant="outlined"
            />
          ) : null}
        </Stack>
      </Stack>
      <PatientMeta row={row} />
    </Box>
  );
}

function PatientMeta({ row }: { row: ClinicalPipelineRun }) {
  const bits = [
    row.nhs_number ? `NHS ${row.nhs_number}` : "",
    row.ubrn ? `Referral ${row.ubrn}` : "",
    shortDate(row.created_at),
    (row.run_count || 0) > 1 ? `${row.run_count} runs` : "",
  ].filter(Boolean);
  return (
    <>
      <Typography variant="body2" color="text.secondary" sx={{ lineHeight: 1.55 }}>
        {bits.join(" -- ")}
      </Typography>
      {row.snippet ? (
        <Typography
          variant="body2"
          color="text.secondary"
          sx={{ mt: 0.75, fontStyle: "italic", lineHeight: 1.5 }}
        >
          {row.snippet}
        </Typography>
      ) : null}
    </>
  );
}
