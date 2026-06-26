/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2C03CA0E
 *   DI: DI-3F771AFB
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C03CA0E")
 */
"use client";

/**
 * Tab 3 -- prompt sandbox (encounter text + assemble prompt + live LLM run).
 * Extracted from prompts/[id]/page.tsx (Phase 4b decomposition).
 */

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import FormControl from "@mui/material/FormControl";
import FormControlLabel from "@mui/material/FormControlLabel";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import ScienceIcon from "@mui/icons-material/Science";

import { SandboxCostTable } from "./SandboxCostTable";
import {
  categoryColor,
  type PresetItem,
  type SandboxProvider,
  type SandboxResult,
  type SandboxTier,
} from "./types";

interface SandboxTabProps {
  presets: PresetItem[];
  sandboxText: string;
  sandboxPresetId: string;
  sandboxProvider: SandboxProvider;
  sandboxTier: SandboxTier;
  sandboxDryRun: boolean;
  sandboxRunning: boolean;
  sandboxError: string | null;
  sandboxResult: SandboxResult | null;
  onSandboxText: (next: string) => void;
  onSandboxPresetId: (next: string) => void;
  onSandboxProvider: (next: SandboxProvider) => void;
  onSandboxTier: (next: SandboxTier) => void;
  onSandboxDryRun: (next: boolean) => void;
  onClearError: () => void;
  onRun: () => void;
}

export function SandboxTab(props: SandboxTabProps) {
  return (
    <Box sx={{ pt: 2 }}>
      <Alert severity="info" sx={{ mb: 2 }} icon={<ScienceIcon />}>
        <Typography variant="body2" fontWeight={600} gutterBottom>
          Prompt sandbox
        </Typography>
        <Typography variant="body2">
          Paste encounter text below. The AI assembles the full prompt using
          this config -- showing which core examples go into the system prompt
          and which examples the RAG selector picks for the user message.
          Toggle &ldquo;Call the LLM&rdquo; to get a live response.
        </Typography>
      </Alert>

      <SandboxControls {...props} />

      <TextField
        fullWidth
        multiline
        minRows={5}
        size="small"
        label="Encounter text (paste clinical note here)"
        placeholder={
          "[s0] Patient reports no chest pain.\n[s1] BP 142/88 mmHg.\n" +
          "[s2] Known T2DM, HbA1c 58 mmol/mol."
        }
        value={props.sandboxText}
        onChange={(e) => props.onSandboxText(e.target.value)}
        sx={{ mb: 2, fontFamily: "monospace" }}
        inputProps={{
          style: { fontFamily: "monospace", fontSize: "0.82rem" },
        }}
      />

      {props.sandboxError && (
        <Alert
          severity="error"
          sx={{ mb: 2 }}
          onClose={props.onClearError}
        >
          {props.sandboxError}
        </Alert>
      )}

      {props.sandboxResult && <SandboxResultPanels result={props.sandboxResult} />}
    </Box>
  );
}

function SandboxControls({
  presets,
  sandboxPresetId,
  sandboxProvider,
  sandboxTier,
  sandboxDryRun,
  sandboxRunning,
  sandboxText,
  onSandboxPresetId,
  onSandboxProvider,
  onSandboxTier,
  onSandboxDryRun,
  onRun,
}: SandboxTabProps) {
  return (
    <Paper variant="outlined" sx={{ p: 1.5, mb: 2, borderRadius: 2 }}>
      <Stack
        direction={{ xs: "column", sm: "row" }}
        spacing={1.5}
        alignItems={{ xs: "stretch", sm: "center" }}
      >
        <FormControl size="small" sx={{ minWidth: 230 }}>
          <InputLabel>Pipeline preset</InputLabel>
          <Select
            label="Pipeline preset"
            value={sandboxPresetId}
            onChange={(e) => onSandboxPresetId(e.target.value)}
          >
            <MenuItem value="__custom__">
              <em>Custom (choose below)</em>
            </MenuItem>
            {presets.map((p) => (
              <MenuItem key={p.preset_id} value={p.preset_id}>
                <Stack direction="row" spacing={0.75} alignItems="center">
                  <span>{p.name}</span>
                  {p.consensus_mode && (
                    <Chip
                      size="small"
                      label="Consensus"
                      color="info"
                      sx={{ height: 16, fontSize: "0.6rem" }}
                    />
                  )}
                  <Typography variant="caption" color="text.disabled">
                    {p.primary_model}
                  </Typography>
                </Stack>
              </MenuItem>
            ))}
          </Select>
        </FormControl>

        {sandboxPresetId === "__custom__" && (
          <>
            <FormControl size="small" sx={{ minWidth: 160 }}>
              <InputLabel>Provider</InputLabel>
              <Select
                label="Provider"
                value={sandboxProvider}
                onChange={(e) =>
                  onSandboxProvider(e.target.value as SandboxProvider)
                }
              >
                <MenuItem value="aws">AWS (Claude / Bedrock)</MenuItem>
                <MenuItem value="azure">Azure (OpenAI / GPT)</MenuItem>
              </Select>
            </FormControl>
            <FormControl size="small" sx={{ minWidth: 130 }}>
              <InputLabel>Model tier</InputLabel>
              <Select
                label="Model tier"
                value={sandboxTier}
                onChange={(e) =>
                  onSandboxTier(e.target.value as SandboxTier)
                }
              >
                <MenuItem value="small">Small (fast)</MenuItem>
                <MenuItem value="big">Big (quality)</MenuItem>
                <MenuItem value="max">Max (best)</MenuItem>
              </Select>
            </FormControl>
          </>
        )}

        <FormControlLabel
          control={
            <Switch
              size="small"
              checked={!sandboxDryRun}
              onChange={(e) => onSandboxDryRun(!e.target.checked)}
              color="warning"
            />
          }
          label={
            <Stack direction="row" alignItems="center" spacing={0.5}>
              <Typography variant="caption">Call the LLM</Typography>
              <Tooltip title="When off, shows assembled prompt only (no tokens used). When on, sends it to the model and shows the real response.">
                <InfoOutlinedIcon
                  sx={{ fontSize: 14, color: "text.disabled" }}
                />
              </Tooltip>
              {!sandboxDryRun && (
                <Chip
                  size="small"
                  label="Live"
                  color="warning"
                  sx={{ height: 16, fontSize: "0.65rem" }}
                />
              )}
            </Stack>
          }
          sx={{ m: 0 }}
        />
        <Box sx={{ flex: 1 }} />
        <Button
          variant="contained"
          color="secondary"
          startIcon={
            sandboxRunning ? (
              <CircularProgress size={16} color="inherit" />
            ) : (
              <PlayArrowIcon />
            )
          }
          onClick={onRun}
          disabled={sandboxRunning || !sandboxText.trim()}
        >
          {sandboxRunning ? "Assembling..." : "Assemble prompt"}
        </Button>
      </Stack>
    </Paper>
  );
}

function SandboxResultPanels({ result }: { result: SandboxResult }) {
  return (
    <Stack spacing={2}>
      <SandboxCostTable result={result} />
      {result.selectedDynamicExamples.length > 0 && (
        <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 2 }}>
          <Typography
            variant="caption"
            fontWeight={700}
            color="text.secondary"
            sx={{ display: "block", mb: 1 }}
          >
            RAG-SELECTED DYNAMIC EXAMPLES (placed in user message)
          </Typography>
          <Stack spacing={0.75}>
            {result.selectedDynamicExamples.map((ex, i) => (
              <Stack
                key={i}
                direction="row"
                spacing={0.75}
                alignItems="center"
                flexWrap="wrap"
                useFlexGap
              >
                <Chip
                  size="small"
                  label={`#${i + 1}`}
                  sx={{ height: 18, fontSize: "0.62rem" }}
                />
                {ex.category && (
                  <Chip
                    size="small"
                    label={ex.category}
                    color={categoryColor(ex.category)}
                    sx={{ height: 18, fontSize: "0.62rem" }}
                  />
                )}
                {ex.description && (
                  <Typography
                    variant="caption"
                    color="text.secondary"
                    fontStyle="italic"
                  >
                    {ex.description}
                  </Typography>
                )}
                {ex._similarity_score !== undefined && (
                  <Chip
                    size="small"
                    label={`score: ${ex._similarity_score.toFixed(3)}`}
                    variant="outlined"
                    sx={{ height: 18, fontSize: "0.62rem" }}
                  />
                )}
              </Stack>
            ))}
          </Stack>
        </Paper>
      )}

      <CodeBlockPaper
        label="ASSEMBLED SYSTEM PROMPT (static cacheable prefix)"
        body={result.systemPrompt}
      />
      <CodeBlockPaper
        label="USER MESSAGE (dynamic examples + encounter)"
        body={result.userMessage}
      />

      {result.llmResponse !== null && (
        <Paper
          variant="outlined"
          sx={{
            p: 1.5,
            borderRadius: 2,
            borderColor: result.llmResponse.startsWith("[LLM")
              ? "warning.main"
              : "success.main",
          }}
        >
          <Typography
            variant="caption"
            fontWeight={700}
            color={
              result.llmResponse.startsWith("[LLM")
                ? "warning.main"
                : "success.main"
            }
            sx={{ display: "block", mb: 0.75 }}
          >
            LLM RESPONSE
          </Typography>
          <CodeBox text={result.llmResponse} maxHeight={400} />
        </Paper>
      )}
    </Stack>
  );
}

function CodeBlockPaper({ label, body }: { label: string; body: string }) {
  return (
    <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 2 }}>
      <Typography
        variant="caption"
        fontWeight={700}
        color="text.secondary"
        sx={{ display: "block", mb: 0.75 }}
      >
        {label}
      </Typography>
      <CodeBox text={body} />
    </Paper>
  );
}

function CodeBox({
  text,
  maxHeight = 320,
}: {
  text: string;
  maxHeight?: number;
}) {
  return (
    <Box
      component="pre"
      sx={{
        fontFamily: "monospace",
        fontSize: "0.72rem",
        whiteSpace: "pre-wrap",
        wordBreak: "break-word",
        maxHeight,
        overflow: "auto",
        bgcolor: "grey.50",
        p: 1,
        borderRadius: 1,
        m: 0,
      }}
    >
      {text}
    </Box>
  );
}
