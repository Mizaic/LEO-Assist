/**
 * Clinical door matching, recent, frequent, and all-patient lists.
 *
 * Atlas: DI-238DA59A / DO-4FD76836
 */
"use client";

import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import type { ClinicalPipelineRun } from "./labFindingsApi";
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
}: {
  recent: ClinicalPipelineRun[];
  frequent: ClinicalPipelineRun[];
  patients: ClinicalPipelineRun[];
  onPick: (row: ClinicalPipelineRun) => void;
}) {
  return (
    <>
      <PatientSection
        title="Recently used"
        testId="validation-lab-clinical-recent"
        emptyText="Patients you open will show here."
        rows={recent}
        onPick={onPick}
      />
      <PatientSection
        title="Frequently used"
        testId="validation-lab-clinical-frequent"
        emptyText="Patients you open often will show here."
        rows={frequent}
        onPick={onPick}
      />
      <PatientSection
        title="All patients"
        testId="validation-lab-clinical-all-patients"
        emptyText="No patients with a pipeline run yet."
        rows={patients}
        onPick={onPick}
        scroll
      />
    </>
  );
}

export function PatientSection({
  title,
  testId,
  rows,
  onPick,
  emptyText,
  scroll,
}: {
  title: string;
  testId: string;
  rows: ClinicalPipelineRun[];
  onPick: (row: ClinicalPipelineRun) => void;
  emptyText?: string;
  scroll?: boolean;
}) {
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
}: {
  row: ClinicalPipelineRun;
  onPick: (row: ClinicalPipelineRun) => void;
}) {
  const why = matchLabel(row.matched_on);
  return (
    <Box
      onClick={() => onPick(row)}
      sx={{
        ...glassPanel,
        ...pressable,
        p: 2,
        borderRadius: "16px",
        "&:hover": { boxShadow: "0 14px 40px rgba(15, 23, 42, 0.12)" },
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
        <Stack direction="row" spacing={0.75}>
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
