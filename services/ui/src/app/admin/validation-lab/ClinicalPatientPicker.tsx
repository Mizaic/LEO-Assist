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
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Typography from "@mui/material/Typography";

import { PatientSection, UsedAndAllLists } from "./ClinicalPatientLists";
import type {
  ClinicalPipelineRun,
  ClinicalSearchMode,
} from "./labFindingsApi";
import { glassPanel, pressable } from "./clinicalDoorChrome";

export interface LookupPanelProps {
  query: string;
  onQuery: (value: string) => void;
  searchMode: ClinicalSearchMode;
  onSearchMode: (mode: ClinicalSearchMode) => void;
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
    <Stack spacing={3}>
      <LookupFields
        query={props.query}
        onQuery={props.onQuery}
        searchMode={props.searchMode}
        onSearchMode={props.onSearchMode}
        busy={props.busy}
        onFind={props.onFind}
      />
      {props.searched && props.rows.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          {emptyCopy(props.searchMode)}
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

function emptyCopy(mode: ClinicalSearchMode): string {
  if (mode === "letters") return "No letter contains those words.";
  return "No pipeline run for that name, NHS number, or referral number.";
}

function LookupFields({
  query,
  onQuery,
  searchMode,
  onSearchMode,
  busy,
  onFind,
}: {
  query: string;
  onQuery: (value: string) => void;
  searchMode: ClinicalSearchMode;
  onSearchMode: (mode: ClinicalSearchMode) => void;
  busy: boolean;
  onFind: () => void;
}) {
  const letters = searchMode === "letters";
  return (
    <Box sx={{ ...glassPanel, p: { xs: 2, sm: 2.5 } }}>
      <SearchModeToggle value={searchMode} onChange={onSearchMode} />
      <Stack
        direction={{ xs: "column", sm: "row" }}
        spacing={1.5}
        alignItems={{ sm: "flex-start" }}
      >
        <TextField
          label={
            letters
              ? "Words from the letter"
              : "Name, NHS number, or referral number"
          }
          helperText={
            letters
              ? "Type at least 3 letters. This does not start a new job."
              : "The referral number is also called UBRN."
          }
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
          disabled={busy || !query.trim() || (letters && query.trim().length < 3)}
          onClick={onFind}
          sx={{ minWidth: 112, height: 56, borderRadius: "14px", ...pressable }}
        >
          {busy ? "Finding..." : "Find"}
        </Button>
      </Stack>
    </Box>
  );
}

function SearchModeToggle({
  value,
  onChange,
}: {
  value: ClinicalSearchMode;
  onChange: (mode: ClinicalSearchMode) => void;
}) {
  return (
    <ToggleButtonGroup
      exclusive
      size="small"
      value={value}
      onChange={(_, next) => next && onChange(next)}
      aria-label="Search patients or letters"
      data-testid="validation-lab-clinical-search-mode"
      sx={{ mb: 1.5 }}
    >
      <ToggleButton value="patient" sx={{ textTransform: "none", px: 1.5 }}>
        Patient
      </ToggleButton>
      <ToggleButton value="letters" sx={{ textTransform: "none", px: 1.5 }}>
        In letters
      </ToggleButton>
    </ToggleButtonGroup>
  );
}
