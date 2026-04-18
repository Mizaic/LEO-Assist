"use client";

/**
 * SBAR generation playground.
 *
 * Lets an admin reviewer assemble a payload that mirrors the
 * production `sbar_requested` queue contract (DI-LEO-AI-186), submit it
 * via the Core API enqueue endpoint, and watch the four-stage
 * orchestrator progress over SSE (DI-LEO-AI-191/194).
 *
 * Refactored to use four shared primitives so reviewers no longer have
 * to remember any Neo4j ids:
 *   - PatientFinder              (DI-LEO-AI-230)
 *   - SummarisationContextSelect (DI-LEO-AI-231)
 *   - BackgroundSourcePicker     (DI-LEO-AI-232)
 *   - GuidelinePicker            (DI-LEO-AI-233)
 *
 * Risks addressed:
 *   - R-LEO-AI-185: clearly labels every result as "test only -- not for
 *     clinical use" so reviewers do not mistake playground output for
 *     production guidance.
 *   - R-LEO-AI-NEW patient mismatch: PatientFinder always shows NHS
 *     number and date of birth on every row.
 */
import { useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import Alert from "@mui/material/Alert";
import LinearProgress from "@mui/material/LinearProgress";
import Chip from "@mui/material/Chip";
import Paper from "@mui/material/Paper";
import {
  type SbarBackgroundSourceInput,
  type SbarSituationArtifactInput,
  type SbarStageName,
  useSbarStream,
} from "@/hooks/useSbarStream";

import {
  PatientFinder,
  type SelectedPatient,
} from "@/components/sbar-playground/PatientFinder";
import {
  BackgroundSourcePicker,
  type SelectedBackgroundSource,
} from "@/components/sbar-playground/BackgroundSourcePicker";
import { GuidelinePicker } from "@/components/sbar-playground/GuidelinePicker";
import {
  SummarisationContextSelect,
  type SummarisationContextValue,
} from "@/components/sbar-playground/SummarisationContextSelect";

const STAGE_LABELS: Record<SbarStageName, string> = {
  situation: "Situation",
  background: "Background",
  assessment: "Assessment",
  recommendation: "Recommendation",
};

// QSIR-aligned framing -- give the reviewer a tight 500-char box for a
// "what is the worry today?" note. Mirrors the backend `concern` cap.
const CONCERN_MAX_CHARS = 500;

function backgroundSourceToInput(
  source: SelectedBackgroundSource,
): SbarBackgroundSourceInput {
  if (source.type === "encounter") {
    return { type: "encounter", id: source.id };
  }
  if (source.type === "document_reference") {
    return { type: "document_reference", id: source.id };
  }
  return { type: "chunk", id: source.id };
}

export default function SbarPlayground() {
  const [patient, setPatient] = useState<SelectedPatient | null>(null);
  const [patientFinderOpen, setPatientFinderOpen] = useState(false);

  const [context, setContext] = useState<SummarisationContextValue | null>(
    null,
  );
  const [concern, setConcern] = useState("");

  const [sources, setSources] = useState<SelectedBackgroundSource[]>([]);
  const [sourcePickerOpen, setSourcePickerOpen] = useState(false);

  const [guidelineCodes, setGuidelineCodes] = useState<string[]>([]);

  const sbar = useSbarStream();

  const sourceCounts = useMemo(() => {
    const counts = { encounter: 0, document_reference: 0, chunk: 0 };
    for (const s of sources) counts[s.type] += 1;
    return counts;
  }, [sources]);

  const canSubmit =
    patient !== null &&
    context !== null &&
    sources.length > 0 &&
    !sbar.running;

  const onSubmit = () => {
    if (!patient || !context) return;

    const artifacts: SbarSituationArtifactInput[] = [
      { type: "patient_context", id: patient.id },
      { type: "summarisation_context", context_value: context },
    ];

    sbar.start({
      patientId: patient.id,
      artifacts,
      background: sources.map(backgroundSourceToInput),
      guidelineIds: guidelineCodes,
      concern: concern.trim() || undefined,
    });
  };

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 3 }}>
      <Alert severity="info" data-testid="sbar-test-only-banner">
        <strong>Test only.</strong> Output from this playground is for
        prompt and pipeline testing. It must not be used for clinical
        decision-making.
      </Alert>

      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack spacing={3}>
          <Typography variant="h6">Set up the summary</Typography>

          {/* 1. Patient ------------------------------------------------ */}
          <Stack spacing={1}>
            <Typography variant="subtitle2">1. Pick the patient</Typography>
            {patient ? (
              <Stack
                direction="row"
                spacing={1}
                alignItems="center"
                data-testid="sbar-selected-patient"
              >
                <Chip
                  color="primary"
                  variant="outlined"
                  label={
                    patient.displayName ?? `Patient ${patient.id.slice(0, 8)}`
                  }
                />
                {patient.nhsNumber && (
                  <Chip
                    size="small"
                    variant="outlined"
                    label={`NHS ${patient.nhsNumber}`}
                  />
                )}
                {patient.dob && (
                  <Chip
                    size="small"
                    variant="outlined"
                    label={`DOB ${patient.dob}`}
                  />
                )}
                <Button
                  size="small"
                  onClick={() => setPatientFinderOpen(true)}
                  data-testid="sbar-change-patient"
                >
                  Change
                </Button>
              </Stack>
            ) : (
              <Box>
                <Button
                  variant="outlined"
                  onClick={() => setPatientFinderOpen(true)}
                  data-testid="sbar-pick-patient"
                >
                  Find a patient
                </Button>
                <Typography
                  component="span"
                  variant="caption"
                  color="text.secondary"
                  sx={{ ml: 1 }}
                >
                  Search by name or NHS number, or filter by health needs.
                </Typography>
              </Box>
            )}
          </Stack>

          {/* 2. Reason for summary ------------------------------------ */}
          <Stack spacing={1}>
            <Typography variant="subtitle2">2. Why are we summarising?</Typography>
            <SummarisationContextSelect
              value={context}
              onChange={setContext}
            />
          </Stack>

          {/* 3. Concern ----------------------------------------------- */}
          <Stack spacing={1}>
            <Typography variant="subtitle2">
              3. What is the worry today? (optional)
            </Typography>
            <TextField
              multiline
              minRows={2}
              maxRows={6}
              fullWidth
              size="small"
              value={concern}
              onChange={(e) =>
                setConcern(e.target.value.slice(0, CONCERN_MAX_CHARS))
              }
              placeholder="One or two short sentences. For example: 'breathless and oxygen has dropped'."
              helperText={`${concern.length} / ${CONCERN_MAX_CHARS}`}
              inputProps={{
                "data-testid": "sbar-concern",
                maxLength: CONCERN_MAX_CHARS,
              }}
            />
          </Stack>

          {/* 4. Background -------------------------------------------- */}
          <Stack spacing={1}>
            <Typography variant="subtitle2">
              4. Pick the records to read
            </Typography>
            {patient ? (
              <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
                <Button
                  variant="outlined"
                  onClick={() => setSourcePickerOpen(true)}
                  data-testid="sbar-pick-sources"
                >
                  {sources.length === 0
                    ? "Pick records"
                    : `Change picks (${sources.length})`}
                </Button>
                {sources.length > 0 && (
                  <>
                    {sourceCounts.encounter > 0 && (
                      <Chip
                        size="small"
                        variant="outlined"
                        label={`${sourceCounts.encounter} encounters`}
                      />
                    )}
                    {sourceCounts.document_reference > 0 && (
                      <Chip
                        size="small"
                        variant="outlined"
                        label={`${sourceCounts.document_reference} documents`}
                      />
                    )}
                    {sourceCounts.chunk > 0 && (
                      <Chip
                        size="small"
                        variant="outlined"
                        label={`${sourceCounts.chunk} chunks`}
                      />
                    )}
                    <Button
                      size="small"
                      color="inherit"
                      onClick={() => setSources([])}
                      data-testid="sbar-clear-sources"
                    >
                      Clear
                    </Button>
                  </>
                )}
              </Stack>
            ) : (
              <Typography variant="body2" color="text.secondary">
                Pick a patient first.
              </Typography>
            )}
          </Stack>

          {/* 5. Guidelines -------------------------------------------- */}
          <Stack spacing={1}>
            <Typography variant="subtitle2">
              5. Guidelines (optional)
            </Typography>
            <GuidelinePicker
              value={guidelineCodes}
              onChange={setGuidelineCodes}
            />
          </Stack>

          {/* Submit --------------------------------------------------- */}
          <Box>
            <Button
              variant="contained"
              onClick={onSubmit}
              disabled={!canSubmit}
              data-testid="sbar-submit"
            >
              Generate SBAR
            </Button>
            {sbar.running && (
              <Button
                sx={{ ml: 1 }}
                variant="text"
                onClick={sbar.cancel}
                data-testid="sbar-cancel"
              >
                Cancel
              </Button>
            )}
          </Box>
        </Stack>
      </Paper>

      {/* Pickers -------------------------------------------------------- */}
      <PatientFinder
        open={patientFinderOpen}
        onClose={() => setPatientFinderOpen(false)}
        onSelect={(p) => {
          setPatient(p);
          setSources([]);
          setPatientFinderOpen(false);
        }}
      />
      {patient && (
        <BackgroundSourcePicker
          open={sourcePickerOpen}
          patientId={patient.id}
          initialSelected={sources}
          onClose={() => setSourcePickerOpen(false)}
          onConfirm={(next) => {
            setSources(next);
            setSourcePickerOpen(false);
          }}
        />
      )}

      {/* Errors / progress / final -------------------------------------- */}
      {sbar.error && (
        <Alert severity="error" data-testid="sbar-error">
          {sbar.error}
        </Alert>
      )}

      {(sbar.running || sbar.runId) && (
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Stack spacing={2}>
            <Stack direction="row" alignItems="center" spacing={1}>
              <Typography variant="h6">Progress</Typography>
              {sbar.runId && (
                <Chip size="small" label={`run ${sbar.runId.slice(0, 8)}`} />
              )}
              {sbar.assessmentId && (
                <Chip
                  size="small"
                  variant="outlined"
                  label={`assessment ${sbar.assessmentId.slice(0, 8)}`}
                />
              )}
            </Stack>
            {sbar.running && <LinearProgress />}
            {sbar.status && (
              <Typography variant="body2" color="text.secondary">
                {sbar.status}
              </Typography>
            )}
            <Stack spacing={1}>
              {(Object.keys(STAGE_LABELS) as SbarStageName[]).map((stage) => {
                const s = sbar.stages[stage];
                return (
                  <Box key={stage} data-testid={`sbar-stage-${stage}`}>
                    <Stack direction="row" spacing={1} alignItems="center">
                      <Chip
                        size="small"
                        label={STAGE_LABELS[stage]}
                        color={
                          s.status === "completed"
                            ? "success"
                            : s.status === "running"
                              ? "primary"
                              : s.status === "failed"
                                ? "error"
                                : "default"
                        }
                      />
                      {typeof s.ruleCount === "number" && (
                        <Chip
                          size="small"
                          variant="outlined"
                          label={`${s.ruleCount} rules`}
                        />
                      )}
                      {typeof s.actionCount === "number" && (
                        <Chip
                          size="small"
                          variant="outlined"
                          label={`${s.actionCount} actions`}
                        />
                      )}
                    </Stack>
                    {s.preview && (
                      <Typography
                        variant="body2"
                        sx={{
                          mt: 0.5,
                          ml: 0.5,
                          color: "text.secondary",
                          whiteSpace: "pre-wrap",
                        }}
                      >
                        {s.preview}
                      </Typography>
                    )}
                  </Box>
                );
              })}
            </Stack>
          </Stack>
        </Paper>
      )}

      {sbar.finalContent && (
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Typography variant="h6" gutterBottom>
            SBAR (final)
          </Typography>
          <Box
            data-testid="sbar-final-content"
            sx={{
              fontFamily:
                "ui-monospace, SFMono-Regular, Menlo, monospace",
              whiteSpace: "pre-wrap",
              fontSize: "0.875rem",
              lineHeight: 1.5,
            }}
          >
            {sbar.finalContent}
          </Box>
        </Paper>
      )}
    </Box>
  );
}
