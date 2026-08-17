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
import type { CSSProperties } from "react";
import CircularProgress from "@mui/material/CircularProgress";
import Tooltip from "@mui/material/Tooltip";
import AutoFixHighIcon from "@mui/icons-material/AutoFixHigh";
import { motion as fm } from "framer-motion";
import {
  ProgressiveReveal,
  springOrInstant,
  springs,
  tapScale,
  useMotion,
} from "@leo/design-system";
import { color, radius, typography } from "@leo/design-system/tokens";

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
    <div style={{ paddingTop: 8 }}>
      <InstructionsToolbar
        improving={improving}
        canImprove={Boolean(systemPrompt)}
        onAiImprove={onAiImprove}
      />
      {loaded ? (
        <MarkdownEditor
          ref={editorRef as React.Ref<MarkdownEditorHandle>}
          initialContent={systemPrompt}
          mode={isNew ? "create" : "edit"}
          onChange={onEditorChange}
          placeholder="Type the extraction rules here..."
          minHeight={400}
        />
      ) : null}
      {aiSuggestion ? (
        <AiSuggestionPanel
          current={systemPrompt}
          suggestion={aiSuggestion}
          onAccept={onAcceptSuggestion}
          onDismiss={onDismissSuggestion}
        />
      ) : null}
    </div>
  );
}

function InstructionsToolbar({
  improving,
  canImprove,
  onAiImprove,
}: {
  improving: boolean;
  canImprove: boolean;
  onAiImprove: () => void;
}) {
  const disabled = improving || !canImprove;
  const { reducedMotion } = useMotion();
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "flex-start",
        marginBottom: 8,
        gap: 12,
      }}
    >
      <ProgressiveReveal summary="How to write instructions">
        <p style={{ margin: "6px 0 0", fontSize: 14, color: color.text.secondary }}>
          Write the rules the AI follows -- scope, semantic tags, assertion
          logic. Do not include examples or output format here; manage those
          in the other tabs.
        </p>
      </ProgressiveReveal>
      <Tooltip title="Use the AI assistant to review and improve these instructions.">
        <fm.button
          type="button"
          onClick={onAiImprove}
          disabled={disabled}
          whileTap={disabled ? undefined : tapScale(reducedMotion)}
          transition={springOrInstant(reducedMotion, springs.press)}
          style={improveBtn(disabled)}
        >
          {improving ? <CircularProgress size={14} color="inherit" /> : <AutoFixHighIcon sx={{ fontSize: 16 }} />}
          {improving ? "Thinking..." : "AI improve"}
        </fm.button>
      </Tooltip>
    </div>
  );
}

function AiSuggestionPanel({
  current,
  suggestion,
  onAccept,
  onDismiss,
}: {
  current: string;
  suggestion: string;
  onAccept: (suggestion: string) => void;
  onDismiss: () => void;
}) {
  return (
    <ProgressiveReveal summary="AI suggestion" defaultOpen>
      <div style={{ display: "grid", gap: 12, gridTemplateColumns: "1fr 1fr" }}>
        <ComparePane title="Current" text={current} />
        <ComparePane title="Suggestion" text={suggestion} />
      </div>
      <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 12 }}>
        <button type="button" onClick={onDismiss} style={ghostBtn()}>
          Dismiss
        </button>
        <button type="button" onClick={() => onAccept(suggestion)} style={primaryBtn()}>
          Use suggestion
        </button>
      </div>
    </ProgressiveReveal>
  );
}

function ComparePane({ title, text }: { title: string; text: string }) {
  return (
    <div>
      <p style={{ margin: "0 0 6px", fontSize: 12, fontWeight: 600, color: color.text.secondary }}>
        {title}
      </p>
      <pre style={comparePre()}>{text}</pre>
    </div>
  );
}

function improveBtn(disabled: boolean): CSSProperties {
  if (disabled) {
    return {
      display: "inline-flex",
      alignItems: "center",
      gap: 6,
      flexShrink: 0,
      border: "1px solid " + color.text.secondary,
      borderRadius: radius.sm,
      padding: "6px 12px",
      background: color.surface.divider,
      color: color.text.secondary,
      fontWeight: 600,
      fontFamily: typography.fontFamily.body,
      cursor: "not-allowed",
    };
  }
  return {
    display: "inline-flex",
    alignItems: "center",
    gap: 6,
    flexShrink: 0,
    border: "1px solid " + color.text.secondary,
    borderRadius: radius.sm,
    padding: "6px 12px",
    background: color.surface.raised,
    color: color.brand.primary,
    fontWeight: 600,
    fontFamily: typography.fontFamily.body,
    cursor: "pointer",
  };
}

function comparePre(): CSSProperties {
  return {
    fontFamily: typography.fontFamily.mono,
    fontSize: 12,
    whiteSpace: "pre-wrap",
    wordBreak: "break-word",
    maxHeight: 280,
    overflow: "auto",
    background: color.surface.alt,
    padding: 8,
    borderRadius: radius.sm,
    margin: 0,
    border: "1px solid " + color.text.secondary,
    color: color.text.primary,
  };
}

function ghostBtn(): CSSProperties {
  return {
    border: "1px solid " + color.text.secondary,
    background: color.surface.raised,
    borderRadius: radius.sm,
    padding: "6px 12px",
    fontWeight: 600,
    cursor: "pointer",
    fontFamily: typography.fontFamily.body,
  };
}

function primaryBtn(): CSSProperties {
  return {
    border: 0,
    background: color.brand.primary,
    color: color.brand.onBrand,
    borderRadius: radius.sm,
    padding: "6px 12px",
    fontWeight: 600,
    cursor: "pointer",
    fontFamily: typography.fontFamily.body,
  };
}
