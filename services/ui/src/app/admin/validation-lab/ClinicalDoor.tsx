/**
 * Clinical complaint door: open a real PipelineRun without enqueue.
 *
 * Atlas: DI-562F2C9E / DI-238DA59A / DI-287FFFD0 / DI-ED5A9AC3 / DO-4FD76836
 */
"use client";

import { useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";

import { ClinicalNcrPanel } from "./ClinicalNcrPanel";
import { LookupPanel } from "./ClinicalPatientPicker";
import { useClinicalDoor } from "./clinicalDoorState";
import { useNcrInvestigation } from "./useNcrInvestigation";
import { displayTitle, glassPanel, pressable, statusTone } from "./clinicalDoorChrome";
import type { ClinicalPipelineRun } from "./labFindingsApi";
import type { RunReviewTarget } from "./RunReviewLightbox";
import { caseLabel } from "./ncrInvestigationCases";
import type { ProductNcr } from "./ncrDraft";

interface Props {
  onBack: () => void;
  onReview: (target: RunReviewTarget) => void;
}

export default function ClinicalDoor({ onBack, onReview }: Props) {
  const door = useClinicalDoor(onReview);
  const [linkedNcr, setLinkedNcr] = useState<ProductNcr | null>(null);
  const inv = useNcrInvestigation(linkedNcr?.id, door);
  return (
    <Box
      data-testid="validation-lab-clinical-door"
      sx={{ maxWidth: 760, mx: "auto", pb: 4 }}
    >
      <DoorHeader onBack={onBack} />
      {door.error ? (
        <Alert severity="error" sx={{ mb: 2 }}>
          {door.error}
        </Alert>
      ) : null}
      {!linkedNcr ? (
        <ClinicalNcrPanel
          runId=""
          why=""
          onLinked={setLinkedNcr}
        />
      ) : (
        <CaseAfterNcr
          ncr={linkedNcr}
          onChangeNcr={() => {
            setLinkedNcr(null);
            door.onClearInvestigation();
          }}
          door={door}
          onOpenReview={() => {
            inv.logReview();
            door.onOpen();
          }}
        />
      )}
    </Box>
  );
}

function CaseAfterNcr({
  ncr,
  onChangeNcr,
  door,
  onOpenReview,
}: {
  ncr: ProductNcr;
  onChangeNcr: () => void;
  door: ReturnType<typeof useClinicalDoor>;
  onOpenReview: () => void;
}) {
  return (
    <Box data-testid="validation-lab-clinical-after-ncr">
      <LinkedNcrBar ncr={ncr} onChange={onChangeNcr} />
      <InvestigationCases
        cases={door.linkedCases}
        active={door.picked}
        onSelect={door.onSelectCase}
        onRemove={door.onRemoveCase}
      />
      <LookupPanel
        query={door.query}
        onQuery={door.setQuery}
        searchMode={door.searchMode}
        onSearchMode={door.setSearchMode}
        busy={door.busy}
        searched={door.searched}
        rows={door.rows}
        recent={door.recent}
        frequent={door.frequent}
        patients={door.patients}
        onFind={door.onFind}
        onPick={door.onPick}
      />
      {door.picked ? (
        <Box sx={{ mt: 2 }}>
          <WhyOpened
            picked={door.picked}
            why={door.why}
            onWhy={door.setWhy}
            onBack={door.onBackPick}
            onOpen={onOpenReview}
          />
        </Box>
      ) : null}
    </Box>
  );
}

function LinkedNcrBar({
  ncr,
  onChange,
}: {
  ncr: ProductNcr;
  onChange: () => void;
}) {
  return (
    <Stack
      direction="row"
      spacing={1}
      alignItems="center"
      sx={{ ...glassPanel, p: 1.5, mb: 2 }}
      data-testid="validation-lab-ncr-linked"
    >
      <Typography sx={{ fontWeight: 600, flex: 1 }}>
        NCR: {ncr.title}
      </Typography>
      <Button size="small" onClick={onChange} sx={pressable}>
        Change NCR
      </Button>
    </Stack>
  );
}

function DoorHeader({ onBack }: { onBack: () => void }) {
  return (
    <>
      <Button
        size="small"
        onClick={onBack}
        startIcon={<ChevronLeftIcon />}
        sx={{ mb: 2, ...pressable }}
      >
        Back to start
      </Button>
      <Typography sx={{ ...displayTitle, mb: 0.75 }}>
        Investigate a non-conformance
      </Typography>
      <Typography
        variant="body2"
        color="text.secondary"
        sx={{ mb: 3, maxWidth: 520, lineHeight: 1.55 }}
      >
        Start with the product non-conformance. Then add one or more
        patients or referral numbers. Those stay in LEO. Atlas gets a
        note with numbers removed. This does not start a new job.
      </Typography>
    </>
  );
}

function InvestigationCases({
  cases,
  active,
  onSelect,
  onRemove,
}: {
  cases: ClinicalPipelineRun[];
  active: ClinicalPipelineRun | null;
  onSelect: (row: ClinicalPipelineRun) => void;
  onRemove: (row: ClinicalPipelineRun) => void;
}) {
  if (cases.length === 0) {
    return (
      <Typography
        variant="body2"
        color="text.secondary"
        sx={{ mb: 2 }}
        data-testid="validation-lab-ncr-cases-empty"
      >
        Add one or more cases with an NHS number or referral number
        (UBRN). They stay in this investigation. Atlas gets a note
        with numbers removed.
      </Typography>
    );
  }
  return (
    <Stack spacing={1} sx={{ mb: 2 }} data-testid="validation-lab-ncr-cases">
      <Typography variant="body2" sx={{ fontWeight: 600 }}>
        Cases in this investigation
      </Typography>
      {cases.map((row) => (
        <Stack
          key={row.run_id || row.patient_id}
          direction="row"
          spacing={1}
          alignItems="center"
        >
          <Button
            size="small"
            variant={
              active && active.run_id === row.run_id ? "contained" : "outlined"
            }
            onClick={() => onSelect(row)}
            sx={{ ...pressable, flex: 1, justifyContent: "flex-start" }}
          >
            {caseLabel(row)}
          </Button>
          <Button size="small" onClick={() => onRemove(row)} sx={pressable}>
            Remove
          </Button>
        </Stack>
      ))}
    </Stack>
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
    <Stack
      spacing={2}
      data-testid="validation-lab-clinical-why"
      sx={{ ...glassPanel, p: { xs: 2, sm: 2.5 } }}
    >
      <Stack direction="row" spacing={1} alignItems="center">
        <Typography sx={{ fontWeight: 700, letterSpacing: "-0.01em" }}>
          {picked.patient_name || picked.patient_id}
        </Typography>
        {picked.status ? (
          <Chip
            size="small"
            label={picked.status}
            color={statusTone(picked.status)}
            variant="outlined"
          />
        ) : null}
      </Stack>
      <Typography variant="body2" color="text.secondary">
        Run {picked.run_id}. Status {picked.status}.
      </Typography>
      <Typography variant="body2" sx={{ fontWeight: 600 }}>
        Why did you open this?
      </Typography>
      <TextField
        value={why}
        onChange={(e) => onWhy(e.target.value)}
        fullWidth
        multiline
        minRows={3}
        placeholder="A short note for the review log"
        inputProps={{ "aria-label": "Why did you open this?" }}
      />
      <Stack direction="row" spacing={1}>
        <Button variant="contained" onClick={onOpen} sx={pressable}>
          Open review
        </Button>
        <Button onClick={onBack} sx={pressable}>
          Pick another
        </Button>
      </Stack>
    </Stack>
  );
}
