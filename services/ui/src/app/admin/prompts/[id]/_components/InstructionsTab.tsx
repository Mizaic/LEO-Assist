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
 * Tab 0 -- system prompt instructions + AI improve. Extracted from
 * prompts/[id]/page.tsx (Phase 4b decomposition).
 */

import { useEffect, useRef } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import AutoFixHighIcon from "@mui/icons-material/AutoFixHigh";

import { ProgressiveReveal } from "@leo/design-system";

import MarkdownEditor, {
  type MarkdownEditorHandle,
} from "@/components/markdown-editor";

interface InstructionsTabProps {
  loaded: boolean;
  isNew: boolean;
  systemPrompt: string;
  improving: boolean;
  aiSuggestion: string | null;
  editorRef: React.RefObject<MarkdownEditorHandle | null>;
  onEditorChange: (md: string) => void;
  onAiImprove: () => void;
  onAcceptSuggestion: (suggestion: string) => void;
  onDismissSuggestion: () => void;
}

export function InstructionsTab({
  loaded,
  isNew,
  systemPrompt,
  improving,
  aiSuggestion,
  editorRef,
  onEditorChange,
  onAiImprove,
  onAcceptSuggestion,
  onDismissSuggestion,
}: InstructionsTabProps) {
  const initialisedRef = useRef(false);

  useEffect(() => {
    if (loaded && systemPrompt && !initialisedRef.current) {
      editorRef.current?.setMarkdown(systemPrompt);
      initialisedRef.current = true;
    }
  }, [loaded, systemPrompt, editorRef]);

  return (
    <Box sx={{ pt: 2 }}>
      <Stack
        direction="row"
        justifyContent="space-between"
        alignItems="flex-start"
        sx={{ mb: 1 }}
      >
        <ProgressiveReveal summary="How to write instructions">
          <Typography variant="body2" color="text.secondary" sx={{ pt: 0.5 }}>
            Write the rules the AI follows -- scope, semantic tags, assertion
            logic. Do not include examples or output format here; manage those
            in the other tabs.
          </Typography>
        </ProgressiveReveal>
        <Tooltip title="Use the AI assistant to review and improve these instructions.">
          <Button
            size="small"
            variant="outlined"
            startIcon={
              improving ? <CircularProgress size={14} /> : <AutoFixHighIcon />
            }
            onClick={onAiImprove}
            disabled={improving || !systemPrompt}
            sx={{ ml: 2, flexShrink: 0 }}
          >
            {improving ? "Thinking..." : "AI improve"}
          </Button>
        </Tooltip>
      </Stack>

      {loaded && (
        <MarkdownEditor
          ref={editorRef as React.Ref<MarkdownEditorHandle>}
          initialContent={systemPrompt}
          mode={isNew ? "create" : "edit"}
          onChange={onEditorChange}
          placeholder="Type the extraction rules here..."
          minHeight={400}
        />
      )}

      {aiSuggestion && (
        <ProgressiveReveal summary="AI suggestion" defaultOpen>
          <Box
            sx={{
              mt: 1,
              display: "flex",
              gap: 2,
              flexDirection: { xs: "column", md: "row" },
            }}
          >
            <Box sx={{ flex: 1 }}>
              <Typography
                variant="caption"
                fontWeight={600}
                color="text.secondary"
                display="block"
                sx={{ mb: 0.5 }}
              >
                Current
              </Typography>
              <Box
                component="pre"
                sx={{
                  fontFamily: "monospace",
                  fontSize: "0.78rem",
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                  maxHeight: 280,
                  overflow: "auto",
                  bgcolor: "grey.50",
                  p: 1,
                  borderRadius: 1,
                  m: 0,
                  border: "1px solid",
                  borderColor: "divider",
                }}
              >
                {systemPrompt}
              </Box>
            </Box>
            <Box sx={{ flex: 1 }}>
              <Typography
                variant="caption"
                fontWeight={600}
                color="text.secondary"
                display="block"
                sx={{ mb: 0.5 }}
              >
                Suggestion
              </Typography>
              <Box
                component="pre"
                sx={{
                  fontFamily: "monospace",
                  fontSize: "0.78rem",
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                  maxHeight: 280,
                  overflow: "auto",
                  bgcolor: "grey.50",
                  p: 1,
                  borderRadius: 1,
                  m: 0,
                  border: "1px solid",
                  borderColor: "divider",
                }}
              >
                {aiSuggestion}
              </Box>
            </Box>
          </Box>
          <Stack
            direction="row"
            spacing={1}
            justifyContent="flex-end"
            sx={{ mt: 1.5 }}
          >
            <Button size="small" variant="outlined" onClick={onDismissSuggestion}>
              Dismiss
            </Button>
            <Button
              size="small"
              variant="contained"
              onClick={() => onAcceptSuggestion(aiSuggestion)}
            >
              Use suggestion
            </Button>
          </Stack>
        </ProgressiveReveal>
      )}
    </Box>
  );
}
