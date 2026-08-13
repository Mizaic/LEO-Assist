/**
 * Clinical complaint door: open a real PipelineRun without enqueue.
 *
 * Atlas: DI-562F2C9E / DI-238DA59A / DO-4FD76836
 */
"use client";

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import { LookupPanel } from "./ClinicalPatientPicker";
import { useClinicalDoor } from "./clinicalDoorState";
import type { ClinicalPipelineRun } from "./labFindingsApi";
import type { RunReviewTarget } from "./RunReviewLightbox";

interface Props {
  onBack: () => void;
  onReview: (target: RunReviewTarget) => void;
}

export default function ClinicalDoor({ onBack, onReview }: Props) {
  const door = useClinicalDoor(onReview);
  return (
    <Box data-testid="validation-lab-clinical-door">
      <Button size="small" onClick={onBack} sx={{ mb: 2 }}>
        Back to start
      </Button>
      <Typography variant="h6" fontWeight={700} sx={{ mb: 0.5 }}>
        Investigate a clinical complaint
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Find the patient by NHS number or referral number. This does not start a new job.
      </Typography>
      {door.error ? (
        <Alert severity="error" sx={{ mb: 2 }}>{door.error}</Alert>
      ) : null}
      {door.picked ? (
        <WhyOpened
          picked={door.picked}
          why={door.why}
          onWhy={door.setWhy}
          onBack={door.onBackPick}
          onOpen={door.onOpen}
        />
      ) : (
        <LookupPanel
          query={door.query}
          onQuery={door.setQuery}
          busy={door.busy}
          searched={door.searched}
          rows={door.rows}
          recent={door.recent}
          frequent={door.frequent}
          patients={door.patients}
          onFind={door.onFind}
          onPick={door.onPick}
        />
      )}
    </Box>
  );
}

function WhyOpened({
  picked,
  why,
  onWhy,
  onBack,
  onOpen,
}: {
  picked: ClinicalPipelineRun;
  why: string;
  onWhy: (value: string) => void;
  onBack: () => void;
  onOpen: () => void;
}) {
  return (
    <Stack spacing={2} data-testid="validation-lab-clinical-why">
      <Typography variant="body2">
        {picked.patient_name || picked.patient_id}. Run {picked.run_id}. Status{" "}
        {picked.status}.
      </Typography>
      <TextField
        label="Why did you open this?"
        value={why}
        onChange={(e) => onWhy(e.target.value)}
        fullWidth
        multiline
        minRows={3}
      />
      <Stack direction="row" spacing={1}>
        <Button variant="contained" onClick={onOpen}>
          Open review
        </Button>
        <Button onClick={onBack}>Pick another</Button>
      </Stack>
    </Stack>
  );
}
