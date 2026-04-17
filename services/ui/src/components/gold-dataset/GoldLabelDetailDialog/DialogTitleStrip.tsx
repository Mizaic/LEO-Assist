/**
 * DialogTitleStrip -- Wave E Phase 2a-iv
 *
 * The compact header strip that sits above the sentence in the
 * gold-label review dialog. Replaces the loud "Review this example"
 * MUI DialogTitle with a calm two-line strip plus a small
 * ToolbarActions cluster on the right.
 *
 * Visual rules (per DI-LEO-AI-145):
 *   - Title weight is 16px / 600, sub-line is 12px / muted.
 *   - The status pill summarises work-remaining at a glance
 *     (uncoded count + suggestions count) so the reviewer sees
 *     scope before reading the sentence.
 *   - Right cluster contains: copy, guidelines toggle, shortcuts
 *     toggle, close. All ghost-style icons; no big primary
 *     buttons live in the header.
 *   - No bottom divider -- the next section already provides
 *     visual separation through its surface tone.
 */
"use client";

import type { ReactNode } from "react";

import Box from "@mui/material/Box";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import CloseIcon from "@mui/icons-material/Close";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import KeyboardIcon from "@mui/icons-material/Keyboard";
import MenuBookIcon from "@mui/icons-material/MenuBook";

interface DialogTitleStripProps {
  title: string;
  uncodedCount: number;
  suggestionCount: number;
  hasGuidelines: boolean;
  guidelinesOpen: boolean;
  shortcutsOpen: boolean;
  copied: boolean;
  onCopySentence: () => void;
  onToggleGuidelines: () => void;
  onToggleShortcuts: () => void;
  onClose: () => void;
}

function StatusPill({
  uncoded,
  suggestions,
}: {
  uncoded: number;
  suggestions: number;
}): ReactNode {
  if (uncoded === 0 && suggestions === 0) {
    return (
      <Box
        component="span"
        data-testid="dialog-status-pill"
        data-tone="ready"
        sx={{
          display: "inline-flex",
          alignItems: "center",
          gap: 0.5,
          height: 20,
          px: 0.85,
          borderRadius: 1,
          bgcolor: "#ECFDF5",
          color: "#047857",
          border: "1px solid #A7F3D0",
          fontSize: "0.68rem",
          fontWeight: 600,
        }}
      >
        Ready to mark gold
      </Box>
    );
  }
  const parts: string[] = [];
  if (uncoded > 0) parts.push(`${uncoded} need code`);
  if (suggestions > 0) parts.push(`${suggestions} suggested`);
  return (
    <Box
      component="span"
      data-testid="dialog-status-pill"
      data-tone={uncoded > 0 && suggestions === 0 ? "warning" : "info"}
      sx={{
        display: "inline-flex",
        alignItems: "center",
        gap: 0.5,
        height: 20,
        px: 0.85,
        borderRadius: 1,
        bgcolor: uncoded > 0 && suggestions === 0 ? "#FEF3C7" : "#EFF6FF",
        color: uncoded > 0 && suggestions === 0 ? "#92400E" : "#1D4ED8",
        border:
          "1px solid " +
          (uncoded > 0 && suggestions === 0 ? "#FDE68A" : "#BFDBFE"),
        fontSize: "0.68rem",
        fontWeight: 600,
      }}
    >
      {parts.join(" - ")}
    </Box>
  );
}

export default function DialogTitleStrip(props: DialogTitleStripProps) {
  const {
    title,
    uncodedCount,
    suggestionCount,
    hasGuidelines,
    guidelinesOpen,
    shortcutsOpen,
    copied,
    onCopySentence,
    onToggleGuidelines,
    onToggleShortcuts,
    onClose,
  } = props;
  return (
    <Box
      data-testid="dialog-title-strip"
      sx={{
        px: 2.25,
        pt: 1.75,
        pb: 1.25,
        display: "flex",
        alignItems: "flex-start",
        gap: 1.5,
      }}
    >
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography
          component="h2"
          sx={{
            fontSize: "1rem",
            fontWeight: 600,
            color: "text.primary",
            lineHeight: 1.3,
            mb: 0.4,
          }}
        >
          {title}
        </Typography>
        <Stack
          direction="row"
          alignItems="center"
          spacing={1}
          flexWrap="wrap"
          useFlexGap
          sx={{ rowGap: 0.5 }}
        >
          <Typography
            sx={{
              fontSize: "0.75rem",
              color: "text.secondary",
              lineHeight: 1.3,
            }}
          >
            Check the terms and codes, then mark it as gold.
          </Typography>
          <StatusPill uncoded={uncodedCount} suggestions={suggestionCount} />
        </Stack>
      </Box>
      <Stack direction="row" spacing={0.25} sx={{ flexShrink: 0 }}>
        <Tooltip title={copied ? "Copied!" : "Copy sentence"}>
          <IconButton
            size="small"
            onClick={onCopySentence}
            data-testid="dialog-copy-button"
            sx={{ color: copied ? "success.main" : "text.secondary" }}
          >
            <ContentCopyIcon sx={{ fontSize: 18 }} />
          </IconButton>
        </Tooltip>
        {hasGuidelines && (
          <Tooltip title="Annotation guidelines">
            <IconButton
              size="small"
              onClick={onToggleGuidelines}
              data-testid="dialog-guidelines-toggle"
              aria-pressed={guidelinesOpen}
              sx={{
                color: guidelinesOpen ? "primary.main" : "text.secondary",
              }}
            >
              <MenuBookIcon sx={{ fontSize: 18 }} />
            </IconButton>
          </Tooltip>
        )}
        <Tooltip title="Keyboard shortcuts">
          <IconButton
            size="small"
            onClick={onToggleShortcuts}
            data-testid="dialog-shortcuts-toggle"
            aria-pressed={shortcutsOpen}
            sx={{
              color: shortcutsOpen ? "primary.main" : "text.secondary",
            }}
          >
            <KeyboardIcon sx={{ fontSize: 18 }} />
          </IconButton>
        </Tooltip>
        <Tooltip title="Close">
          <IconButton
            size="small"
            onClick={onClose}
            data-testid="dialog-close-button"
            sx={{ color: "text.secondary" }}
          >
            <CloseIcon sx={{ fontSize: 18 }} />
          </IconButton>
        </Tooltip>
      </Stack>
    </Box>
  );
}
