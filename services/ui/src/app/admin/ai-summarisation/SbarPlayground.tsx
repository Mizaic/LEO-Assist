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
import MarkdownEditor from "@/components/markdown-editor/MarkdownEditor";
import {
  SbarFinalDialog,
  STAGE_LABELS,
  STAGE_THEME,
} from "@/components/sbar-final";

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

// STAGE_LABELS, STAGE_THEME, splitFinalSbar are sourced from the
// shared sbar-final module so other applications can render the same
// SBAR view without depending on the playground.

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
  const [finalDialogOpen, setFinalDialogOpen] = useState(false);

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

      {/* Per-stage friendly errors (DI-LEO-AI-516). Sits above the
          progress card so a partial-failure SBAR cannot be confused
          with a complete one. Wording is plain English (reading age
          9-11) -- raw AWS / Bedrock strings are translated server
          side by libs/sbar/error_messages. */}
      {sbar.errors.length > 0 && (
        <Alert severity="warning" data-testid="sbar-errors-alert">
          <Stack spacing={0.5}>
            <Typography variant="subtitle2">
              {sbar.errors.length === 1
                ? "1 section did not finish."
                : `${sbar.errors.length} sections did not finish.`}
            </Typography>
            {sbar.errors.map((e, i) => (
              <Typography
                key={`${e.stage}-${i}`}
                variant="body2"
                data-testid={`sbar-error-row-${e.stage}`}
              >
                <strong>{STAGE_LABELS[e.stage] ?? e.stage}:</strong>{" "}
                {e.message}
              </Typography>
            ))}
          </Stack>
        </Alert>
      )}

      {/* Notices (e.g. background shrinker trim notice). Info, not
          warning -- the SBAR still ran. */}
      {sbar.notices.length > 0 && (
        <Alert severity="info" data-testid="sbar-notices-alert">
          <Stack spacing={0.5}>
            {sbar.notices.map((n, i) => (
              <Typography
                key={`${n.stage}-${n.code}-${i}`}
                variant="body2"
                data-testid={`sbar-notice-row-${n.stage}`}
              >
                <strong>{STAGE_LABELS[n.stage] ?? n.stage}:</strong>{" "}
                {n.message}
              </Typography>
            ))}
          </Stack>
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
              <Stack
                direction="row"
                alignItems="center"
                spacing={1}
                flexWrap="wrap"
              >
                {!sbar.running && sbar.finalContent ? (
                  <Button
                    variant="contained"
                    color={sbar.errors.length === 0 ? "success" : "warning"}
                    size="small"
                    onClick={() => setFinalDialogOpen(true)}
                    data-testid="sbar-view-full-button"
                  >
                    {sbar.errors.length === 0
                      ? "View full SBAR"
                      : `View full SBAR (${sbar.errors.length} ${sbar.errors.length === 1 ? "section did not finish" : "sections did not finish"})`}
                  </Button>
                ) : (
                  <Typography variant="body2" color="text.secondary">
                    {sbar.status}
                  </Typography>
                )}
                {!sbar.running && sbar.finalContent && (
                  <Typography variant="caption" color="text.secondary">
                    {sbar.status === "Done."
                      ? "Click to open the full SBAR in a dialog."
                      : null}
                  </Typography>
                )}
              </Stack>
            )}
            <Stack spacing={1.5}>
              {(Object.keys(STAGE_LABELS) as SbarStageName[]).map((stage) => {
                const s = sbar.stages[stage];
                const theme = STAGE_THEME[stage];
                return (
                  <Box
                    key={stage}
                    data-testid={`sbar-stage-${stage}`}
                    sx={{
                      borderRadius: 1.5,
                      overflow: "hidden",
                      border: "1px solid",
                      borderColor: "divider",
                      borderLeft: `4px solid ${theme.accent}`,
                      bgcolor: "background.paper",
                    }}
                  >
                    <Stack
                      direction="row"
                      spacing={1}
                      alignItems="center"
                      sx={{ px: 1.5, py: 1, bgcolor: theme.tint }}
                    >
                      <Typography
                        variant="subtitle2"
                        sx={{ color: theme.ink, fontWeight: 700 }}
                      >
                        {STAGE_LABELS[stage]}
                      </Typography>
                      <Chip
                        size="small"
                        label={s.status ?? "queued"}
                        color={
                          s.status === "completed"
                            ? "success"
                            : s.status === "running"
                              ? "primary"
                              : s.status === "failed"
                                ? "error"
                                : "default"
                        }
                        sx={{ height: 20, fontSize: "0.65rem" }}
                      />
                      {typeof s.ruleCount === "number" && (
                        <Chip
                          size="small"
                          variant="outlined"
                          label={`${s.ruleCount} rules`}
                          sx={{ height: 20, fontSize: "0.65rem" }}
                        />
                      )}
                      {typeof s.actionCount === "number" && (
                        <Chip
                          size="small"
                          variant="outlined"
                          label={`${s.actionCount} actions`}
                          sx={{ height: 20, fontSize: "0.65rem" }}
                        />
                      )}
                      {s.partProgress &&
                        s.partProgress.partTotal > 1 &&
                        s.status === "running" && (
                          <Chip
                            size="small"
                            color="info"
                            label={`part ${s.partProgress.partIndex} of ${s.partProgress.partTotal}`}
                            sx={{ height: 20, fontSize: "0.65rem" }}
                            data-testid={`sbar-stage-${stage}-part-progress`}
                          />
                        )}
                    </Stack>
                    {s.preview && (
                      <Box
                        sx={{
                          px: 1,
                          py: 0.5,
                          "& .md-editor": {
                            border: "none",
                            background: "transparent",
                          },
                          "& .md-editor .tiptap": {
                            padding: "8px 8px",
                            fontSize: "0.85rem",
                          },
                        }}
                      >
                        <MarkdownEditor
                          mode="view"
                          initialContent={s.preview}
                          minHeight={0}
                        />
                      </Box>
                    )}
                  </Box>
                );
              })}
            </Stack>
          </Stack>
        </Paper>
      )}

      <SbarFinalDialog
        open={finalDialogOpen && !!sbar.finalContent}
        onClose={() => setFinalDialogOpen(false)}
        markdown={sbar.finalContent ?? ""}
        subtitle={
          [
            sbar.runId ? `run ${sbar.runId.slice(0, 8)}` : null,
            sbar.assessmentId
              ? `assessment ${sbar.assessmentId.slice(0, 8)}`
              : null,
          ]
            .filter(Boolean)
            .join("  --  ") || undefined
        }
      />
    </Box>
  );
}
