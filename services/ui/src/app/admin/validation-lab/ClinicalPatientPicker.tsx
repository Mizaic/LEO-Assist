/**
 * Clinical door patient lookup, recent, frequent, and all-patient lists.
 *
 * Atlas: DI-238DA59A / DO-4FD76836
 */
"use client";

import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import type { ClinicalPipelineRun } from "./labFindingsApi";

export interface LookupPanelProps {
  query: string;
  onQuery: (value: string) => void;
  busy: boolean;
  searched: boolean;
  rows: ClinicalPipelineRun[];
  recent: ClinicalPipelineRun[];
  frequent: ClinicalPipelineRun[];
  patients: ClinicalPipelineRun[];
  onFind: () => void;
  onPick: (row: ClinicalPipelineRun) => void;
}

export function LookupPanel(props: LookupPanelProps) {
  return (
    <Stack spacing={2}>
      <LookupFields
        query={props.query}
        onQuery={props.onQuery}
        busy={props.busy}
        onFind={props.onFind}
      />
      {props.searched && props.rows.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          No pipeline run for that NHS number or referral number.
        </Typography>
      ) : null}
      {props.rows.length > 0 ? (
        <PatientSection
          title="Matching runs"
          testId="validation-lab-clinical-runs"
          rows={props.rows}
          onPick={props.onPick}
        />
      ) : null}
      <UsedAndAllLists
        recent={props.recent}
        frequent={props.frequent}
        patients={props.patients}
        onPick={props.onPick}
      />
    </Stack>
  );
}

function LookupFields({
  query,
  onQuery,
  busy,
  onFind,
}: {
  query: string;
  onQuery: (value: string) => void;
  busy: boolean;
  onFind: () => void;
}) {
  return (
    <>
      <TextField
        label="NHS number or referral number"
        helperText="The referral number is also called UBRN."
        value={query}
        onChange={(e) => onQuery(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") onFind();
        }}
        fullWidth
        data-testid="validation-lab-clinical-lookup"
      />
      <Button
        variant="contained"
        disabled={busy || !query.trim()}
        onClick={onFind}
        sx={{ alignSelf: "flex-start" }}
      >
        {busy ? "Finding..." : "Find"}
      </Button>
    </>
  );
}

function UsedAndAllLists({
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

function PatientSection({
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
      <Typography variant="subtitle2" fontWeight={700} sx={{ mb: 1 }}>
        {title}
      </Typography>
      {rows.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          {emptyText || "None yet."}
        </Typography>
      ) : (
        <Stack
          spacing={1}
          sx={scroll ? { maxHeight: 320, overflow: "auto" } : undefined}
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
  const extra = (row.run_count || 0) > 1 ? ` ${row.run_count} runs` : "";
  return (
    <Box
      onClick={() => onPick(row)}
      sx={{
        p: 1.5,
        border: "1px solid",
        borderColor: "divider",
        borderRadius: 1,
        cursor: "pointer",
      }}
    >
      <Typography variant="body2" fontWeight={700}>
        {row.patient_name || row.patient_id || "Patient"}
        {row.status ? ` -- ${row.status}` : ""}
      </Typography>
      <Typography variant="caption" color="text.secondary">
        {row.nhs_number ? `NHS ${row.nhs_number} ` : ""}
        {row.ubrn ? `UBRN ${row.ubrn} ` : ""}
        {row.created_at}
        {extra}
      </Typography>
    </Box>
  );
}
