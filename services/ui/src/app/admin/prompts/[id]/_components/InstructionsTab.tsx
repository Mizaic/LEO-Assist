"use client";

/**
 * Tab 0 -- system prompt instructions + AI improve. Extracted from
 * prompts/[id]/page.tsx (Phase 4b decomposition).
 */

import { useEffect, useRef } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import AutoFixHighIcon from "@mui/icons-material/AutoFixHigh";

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
        alignItems="center"
        sx={{ mb: 1 }}
      >
        <Typography variant="body2" color="text.secondary">
          Write the rules the AI follows -- scope, semantic tags, assertion
          logic. Do not include examples or output format here; manage those
          in the other tabs.
        </Typography>
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
        <Alert
          severity="info"
          sx={{ mt: 2 }}
          onClose={onDismissSuggestion}
          action={
            <Button
              size="small"
              onClick={() => onAcceptSuggestion(aiSuggestion)}
            >
              Use this
            </Button>
          }
        >
          <Typography
            variant="body2"
            sx={{
              whiteSpace: "pre-wrap",
              fontFamily: "monospace",
              fontSize: "0.78rem",
            }}
          >
            {aiSuggestion}
          </Typography>
        </Alert>
      )}
    </Box>
  );
}
