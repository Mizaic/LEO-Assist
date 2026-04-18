"use client";

/**
 * SBAR generation playground.
 *
 * Lets an admin reviewer assemble a payload that mirrors the
 * production `sbar_requested` queue contract (DI-LEO-AI-186), submit it
 * via the Core API enqueue endpoint, and watch the four-stage
 * orchestrator progress over SSE (DI-LEO-AI-191/194).
 *
 * Risks addressed:
 *   - R-LEO-AI-185: clearly labels every result as "test only -- not for
 *     clinical use" so reviewers do not mistake playground output for
 *     production guidance.
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
import IconButton from "@mui/material/IconButton";
import Select from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import DeleteIcon from "@mui/icons-material/Delete";
import AddIcon from "@mui/icons-material/Add";
import {
  type SbarBackgroundSourceInput,
  type SbarSituationArtifactInput,
  type SbarStageName,
  useSbarStream,
} from "@/hooks/useSbarStream";

type SituationKind = SbarSituationArtifactInput["type"];
type BackgroundKind = SbarBackgroundSourceInput["type"];

const SITUATION_KINDS: Array<{ value: SituationKind; label: string }> = [
  { value: "patient_context", label: "Patient context node" },
  { value: "referral_request", label: "Referral request" },
  { value: "procedure_request", label: "Procedure request" },
  { value: "fixed_text", label: "Fixed text (e.g. NCDA, clinic name)" },
];

const BACKGROUND_KINDS: Array<{ value: BackgroundKind; label: string }> = [
  { value: "encounter", label: "Encounter" },
  { value: "document_reference", label: "Document reference" },
  { value: "chunk", label: "Chunk (e.g. referral letter section)" },
];

const STAGE_LABELS: Record<SbarStageName, string> = {
  situation: "Situation",
  background: "Background",
  assessment: "Assessment",
  recommendation: "Recommendation",
};

function newRow<T>(initial: T): T {
  return { ...initial };
}

export default function SbarPlayground() {
  const [patientId, setPatientId] = useState("");
  const [artifacts, setArtifacts] = useState<SbarSituationArtifactInput[]>([
    { type: "patient_context", id: "" },
  ]);
  const [background, setBackground] = useState<SbarBackgroundSourceInput[]>([
    { type: "encounter", id: "" },
  ]);
  const [guidelines, setGuidelines] = useState("");
  const sbar = useSbarStream();

  const guidelineIds = useMemo(
    () =>
      guidelines
        .split(/[,\s]+/)
        .map((s) => s.trim())
        .filter(Boolean),
    [guidelines],
  );

  const canSubmit =
    patientId.trim().length > 0 &&
    !sbar.running &&
    background.some((b) => b.id.trim().length > 0);

  const onSubmit = () => {
    sbar.start({
      patientId: patientId.trim(),
      artifacts: artifacts
        .map(normaliseArtifact)
        .filter((a) => Boolean(a.id || a.text)),
      background: background
        .map((b) => ({ ...b, id: b.id.trim() }))
        .filter((b) => b.id.length > 0),
      guidelineIds,
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
        <Stack spacing={2}>
          <Typography variant="h6">Input</Typography>

          <TextField
            label="Patient id"
            value={patientId}
            onChange={(e) => setPatientId(e.target.value)}
            required
            inputProps={{ "data-testid": "sbar-patient-id" }}
            helperText="The :Patient.id this Assessment will be linked to."
          />

          <Stack spacing={1}>
            <Typography variant="subtitle1">Situation artefacts</Typography>
            {artifacts.map((art, idx) => (
              <ArtifactRow
                key={idx}
                value={art}
                onChange={(next) =>
                  setArtifacts((prev) => prev.map((a, i) => (i === idx ? next : a)))
                }
                onRemove={() =>
                  setArtifacts((prev) => prev.filter((_, i) => i !== idx))
                }
              />
            ))}
            <Button
              startIcon={<AddIcon />}
              onClick={() =>
                setArtifacts((prev) => [
                  ...prev,
                  newRow<SbarSituationArtifactInput>({
                    type: "patient_context",
                    id: "",
                  }),
                ])
              }
              data-testid="sbar-add-artifact"
            >
              Add artefact
            </Button>
          </Stack>

          <Stack spacing={1}>
            <Typography variant="subtitle1">Background sources</Typography>
            {background.map((bg, idx) => (
              <BackgroundRow
                key={idx}
                value={bg}
                onChange={(next) =>
                  setBackground((prev) =>
                    prev.map((b, i) => (i === idx ? next : b)),
                  )
                }
                onRemove={() =>
                  setBackground((prev) => prev.filter((_, i) => i !== idx))
                }
              />
            ))}
            <Button
              startIcon={<AddIcon />}
              onClick={() =>
                setBackground((prev) => [
                  ...prev,
                  newRow<SbarBackgroundSourceInput>({
                    type: "encounter",
                    id: "",
                  }),
                ])
              }
              data-testid="sbar-add-background"
            >
              Add background
            </Button>
          </Stack>

          <TextField
            label="Guideline ids (optional, comma or space separated)"
            value={guidelines}
            onChange={(e) => setGuidelines(e.target.value)}
            helperText="Empty means evaluate against all loaded guidelines."
            inputProps={{ "data-testid": "sbar-guideline-ids" }}
          />

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

function normaliseArtifact(
  art: SbarSituationArtifactInput,
): SbarSituationArtifactInput {
  if (art.type === "fixed_text") {
    return { type: "fixed_text", text: (art.text ?? art.id ?? "").trim() };
  }
  return { type: art.type, id: (art.id ?? "").trim() };
}

function ArtifactRow({
  value,
  onChange,
  onRemove,
}: {
  value: SbarSituationArtifactInput;
  onChange: (next: SbarSituationArtifactInput) => void;
  onRemove: () => void;
}) {
  const isFixedText = value.type === "fixed_text";
  return (
    <Stack direction="row" spacing={1} alignItems="center">
      <FormControl size="small" sx={{ minWidth: 220 }}>
        <InputLabel>Type</InputLabel>
        <Select
          label="Type"
          value={value.type}
          onChange={(e) =>
            onChange({ ...value, type: e.target.value as SituationKind })
          }
        >
          {SITUATION_KINDS.map((k) => (
            <MenuItem key={k.value} value={k.value}>
              {k.label}
            </MenuItem>
          ))}
        </Select>
      </FormControl>
      <TextField
        size="small"
        fullWidth
        label={isFixedText ? "Text" : "Node id"}
        value={isFixedText ? (value.text ?? "") : (value.id ?? "")}
        onChange={(e) =>
          onChange(
            isFixedText
              ? { ...value, text: e.target.value }
              : { ...value, id: e.target.value },
          )
        }
      />
      <IconButton aria-label="Remove artefact" onClick={onRemove} size="small">
        <DeleteIcon fontSize="small" />
      </IconButton>
    </Stack>
  );
}

function BackgroundRow({
  value,
  onChange,
  onRemove,
}: {
  value: SbarBackgroundSourceInput;
  onChange: (next: SbarBackgroundSourceInput) => void;
  onRemove: () => void;
}) {
  return (
    <Stack direction="row" spacing={1} alignItems="center">
      <FormControl size="small" sx={{ minWidth: 220 }}>
        <InputLabel>Type</InputLabel>
        <Select
          label="Type"
          value={value.type}
          onChange={(e) =>
            onChange({ ...value, type: e.target.value as BackgroundKind })
          }
        >
          {BACKGROUND_KINDS.map((k) => (
            <MenuItem key={k.value} value={k.value}>
              {k.label}
            </MenuItem>
          ))}
        </Select>
      </FormControl>
      <TextField
        size="small"
        fullWidth
        label="Node id"
        value={value.id}
        onChange={(e) => onChange({ ...value, id: e.target.value })}
      />
      <IconButton
        aria-label="Remove background source"
        onClick={onRemove}
        size="small"
      >
        <DeleteIcon fontSize="small" />
      </IconButton>
    </Stack>
  );
}
