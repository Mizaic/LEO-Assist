"use client";
/**
 * AI-assisted rule drafting button.
 *
 * Calls POST /api/guidance/rules/review/{ruleId}/ai-redraft and
 * surfaces the proposed logic_tree for the reviewer to accept or
 * discard. Shown in two places:
 *   - Empty state: large primary CTA "Draft from NICE text"
 *   - Non-empty editor header: small secondary "Regenerate AI draft"
 *
 * Advisory only: no writes until the reviewer saves.
 *
 * Atlas trace: DO-D6CE2AA5 / DI-A3107424
 */

import { useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Typography from "@mui/material/Typography";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";

import { AI_DRAFT } from "./copy";
import type { EditableLogicNode } from "./types";

interface Props {
  ruleId: string;
  /** Called with the proposed logic tree when the AI draft succeeds. */
  onDraft: (tree: EditableLogicNode) => void;
  /** Render as a large primary CTA (empty state) or small secondary button. */
  variant: "primary-cta" | "secondary";
}

export default function AIDraftButton({ ruleId, onDraft, variant }: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleClick() {
    if (!ruleId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/guidance/rules/review/${ruleId}/ai-redraft`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        const msg =
          (body as { detail?: string }).detail ||
          `Server error (${res.status})`;
        setError(typeof msg === "string" ? msg : AI_DRAFT.errorLabel);
        return;
      }
      const data = (await res.json()) as { logic_tree: EditableLogicNode };
      onDraft(data.logic_tree);
    } catch {
      setError(AI_DRAFT.errorLabel);
    } finally {
      setLoading(false);
    }
  }

  if (variant === "primary-cta") {
    return (
      <Box sx={{ mt: 2, textAlign: "center" }}>
        <Button
          variant="outlined"
          startIcon={
            loading ? (
              <CircularProgress size={16} color="inherit" />
            ) : (
              <AutoAwesomeIcon fontSize="small" />
            )
          }
          disabled={loading || !ruleId}
          onClick={handleClick}
          aria-label={AI_DRAFT.emptyCtaLabel}
          sx={{
            borderRadius: 999,
            textTransform: "none",
            fontWeight: 600,
            px: 2.5,
            color: "primary.main",
            borderColor: "primary.main",
            "&:hover": { bgcolor: "primary.50" },
          }}
        >
          {loading ? AI_DRAFT.loadingLabel : AI_DRAFT.emptyCtaLabel}
        </Button>
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ display: "block", mt: 0.75 }}
        >
          {AI_DRAFT.emptyCtaSubtitle}
        </Typography>
        {error && (
          <Alert severity="error" sx={{ mt: 1, textAlign: "left" }}>
            {error}
          </Alert>
        )}
      </Box>
    );
  }

  return (
    <Box>
      <Button
        size="small"
        variant="outlined"
        startIcon={
          loading ? (
            <CircularProgress size={13} color="inherit" />
          ) : (
            <AutoAwesomeIcon sx={{ fontSize: 14 }} />
          )
        }
        disabled={loading || !ruleId}
        onClick={handleClick}
        aria-label={AI_DRAFT.regenerateAria}
        sx={{
          textTransform: "none",
          fontSize: "0.78rem",
          borderRadius: 1.5,
          color: "text.secondary",
          borderColor: "divider",
          "&:hover": { borderColor: "primary.main", color: "primary.main", bgcolor: "primary.50" },
        }}
      >
        {loading ? AI_DRAFT.loadingLabel : AI_DRAFT.regenerateLabel}
      </Button>
      {error && (
        <Alert severity="error" sx={{ mt: 0.5, py: 0.25, fontSize: "0.78rem" }}>
          {error}
        </Alert>
      )}
    </Box>
  );
}
