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
 * Redesigned Wave E: onboarding Alert removed, selects replaced with
 * FilterBar chips + SegmentedTabs, result labels sentence-cased with
 * copy-to-clipboard buttons.
 */

import { useCallback, useMemo, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import IconButton from "@mui/material/IconButton";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";

import {
  FilterBar,
  SegmentedTabs,
  type FilterChip,
} from "@leo/design-system";

import { SandboxCostTable } from "./SandboxCostTable";
import {
  categoryColor,
  type PresetItem,
  type SandboxDynamicExample,
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
        <Alert severity="error" sx={{ mb: 2 }} onClose={props.onClearError}>
          {props.sandboxError}
        </Alert>
      )}

      {props.sandboxResult && (
        <SandboxResultPanels result={props.sandboxResult} />
      )}
    </Box>
  );
}

function ModeAndRunRow({
  sandboxDryRun,
  sandboxRunning,
  sandboxText,
  onSandboxDryRun,
  onRun,
}: Pick<
  SandboxTabProps,
  | "sandboxDryRun"
  | "sandboxRunning"
  | "sandboxText"
  | "onSandboxDryRun"
  | "onRun"
>) {
  return (
    <Stack
      direction="row"
      spacing={1.5}
      alignItems="center"
      justifyContent="space-between"
    >
      <SegmentedTabs
        tabs={[
          { id: "dry", label: "Dry run" },
          { id: "live", label: "Live" },
        ]}
        value={sandboxDryRun ? "dry" : "live"}
        onChange={(id) => onSandboxDryRun(id === "dry")}
        aria-label="Run mode"
      />
      <Tooltip title="Assemble the full prompt. The AI shows which core examples go into the system prompt and which the RAG selector picks. Enable Live to call the model.">
        <span>
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
        </span>
      </Tooltip>
    </Stack>
  );
}

function CustomSelector({
  sandboxProvider,
  sandboxTier,
  onSandboxProvider,
  onSandboxTier,
}: Pick<
  SandboxTabProps,
  "sandboxProvider" | "sandboxTier" | "onSandboxProvider" | "onSandboxTier"
>) {
  return (
    <Stack
      direction="row"
      spacing={2}
      alignItems="center"
      flexWrap="wrap"
      useFlexGap
    >
      <Typography variant="caption" color="text.secondary">
        Provider:
      </Typography>
      <SegmentedTabs
        tabs={[
          { id: "aws", label: "AWS" },
          { id: "azure", label: "Azure" },
        ]}
        value={sandboxProvider}
        onChange={(id) => onSandboxProvider(id as SandboxProvider)}
        aria-label="LLM provider"
        dense
      />
      <Typography variant="caption" color="text.secondary">
        Tier:
      </Typography>
      <SegmentedTabs
        tabs={[
          { id: "small", label: "Small" },
          { id: "big", label: "Big" },
          { id: "max", label: "Max" },
        ]}
        value={sandboxTier}
        onChange={(id) => onSandboxTier(id as SandboxTier)}
        aria-label="Model tier"
        dense
      />
    </Stack>
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
  const [presetSearch, setPresetSearch] = useState("");

  const presetChips = useMemo<FilterChip[]>(
    () => [
      {
        id: "__custom__",
        label: "Custom",
        active: sandboxPresetId === "__custom__",
        onToggle: () => onSandboxPresetId("__custom__"),
      },
      ...presets
        .filter((p) =>
          p.name.toLowerCase().includes(presetSearch.toLowerCase()),
        )
        .map((p) => ({
          id: p.preset_id,
          label: p.name,
          active: sandboxPresetId === p.preset_id,
          onToggle: () => onSandboxPresetId(p.preset_id),
        })),
    ],
    [presets, sandboxPresetId, presetSearch, onSandboxPresetId],
  );

  return (
    <Paper variant="outlined" sx={{ p: 1.5, mb: 2, borderRadius: 2 }}>
      <Stack spacing={1.5}>
        <FilterBar
          search={presetSearch}
          onSearchChange={setPresetSearch}
          searchPlaceholder="Filter presets..."
          aria-label="Pipeline preset"
          chips={presetChips}
        />
        {sandboxPresetId === "__custom__" && (
          <CustomSelector
            sandboxProvider={sandboxProvider}
            sandboxTier={sandboxTier}
            onSandboxProvider={onSandboxProvider}
            onSandboxTier={onSandboxTier}
          />
        )}
        <ModeAndRunRow
          sandboxDryRun={sandboxDryRun}
          sandboxRunning={sandboxRunning}
          sandboxText={sandboxText}
          onSandboxDryRun={onSandboxDryRun}
          onRun={onRun}
        />
      </Stack>
    </Paper>
  );
}

function DynamicExampleRow({
  ex,
  i,
}: {
  ex: SandboxDynamicExample;
  i: number;
}) {
  return (
    <Stack
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
  );
}

function DynamicExamplesPanel({
  examples,
}: {
  examples: SandboxDynamicExample[];
}) {
  return (
    <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 2 }}>
      <Typography
        variant="caption"
        fontWeight={700}
        color="text.secondary"
        sx={{ display: "block", mb: 1 }}
      >
        Selected examples (dynamic, in user message)
      </Typography>
      <Stack spacing={0.75}>
        {examples.map((ex, i) => (
          <DynamicExampleRow key={i} ex={ex} i={i} />
        ))}
      </Stack>
    </Paper>
  );
}

function LlmResponsePanel({ response }: { response: string }) {
  const isWarn = response.startsWith("[LLM");
  const toneColor = isWarn ? "warning.main" : "success.main";
  return (
    <Paper
      variant="outlined"
      sx={{ p: 1.5, borderRadius: 2, borderColor: toneColor }}
    >
      <Typography
        variant="caption"
        fontWeight={700}
        color={toneColor}
        sx={{ display: "block", mb: 0.75 }}
      >
        LLM response
      </Typography>
      <CodeBox text={response} maxHeight={400} />
    </Paper>
  );
}

function SandboxResultPanels({ result }: { result: SandboxResult }) {
  return (
    <Stack spacing={2}>
      <SandboxCostTable result={result} />
      {result.selectedDynamicExamples.length > 0 && (
        <DynamicExamplesPanel examples={result.selectedDynamicExamples} />
      )}
      <CodeBlockPaper
        label="Assembled system prompt (cached prefix)"
        body={result.systemPrompt}
      />
      <CodeBlockPaper
        label="User message (examples + encounter)"
        body={result.userMessage}
      />
      {result.llmResponse !== null && (
        <LlmResponsePanel response={result.llmResponse} />
      )}
    </Stack>
  );
}

function CodeBlockPaper({ label, body }: { label: string; body: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(body).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    }).catch(() => {});
  }, [body]);

  return (
    <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 2 }}>
      <Stack
        direction="row"
        justifyContent="space-between"
        alignItems="center"
        sx={{ mb: 0.75 }}
      >
        <Typography
          variant="caption"
          fontWeight={700}
          color="text.secondary"
        >
          {label}
        </Typography>
        <Tooltip title={copied ? "Copied!" : "Copy to clipboard"}>
          <IconButton
            size="small"
            onClick={handleCopy}
            aria-label="Copy to clipboard"
          >
            <ContentCopyIcon sx={{ fontSize: 14 }} />
          </IconButton>
        </Tooltip>
      </Stack>
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
