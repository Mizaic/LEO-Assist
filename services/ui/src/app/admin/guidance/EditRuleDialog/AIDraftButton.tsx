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
 * Atlas trace: DI-42246DA7 / DO-F8C56339
 */

import { useState } from "react";
import { motion as fm } from "framer-motion";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Typography from "@mui/material/Typography";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";

import { useMotion } from "@leo/design-system";

import { AI_DRAFT } from "./copy";
import type { EditableLogicNode } from "./types";
import { bounceInteraction } from "../motionPresets";

/** Sparkle icon that twinkles on idle hover-bait, and spins gently while generating. */
function SparkleIcon({ loading, reducedMotion, small }: {
  loading: boolean;
  reducedMotion: boolean;
  small: boolean;
}) {
  const icon = small
    ? <AutoAwesomeIcon sx={{ fontSize: 14 }} />
    : <AutoAwesomeIcon fontSize="small" />;
  if (reducedMotion) return icon;
  return (
    <fm.div
      style={{ display: "flex" }}
      animate={
        loading
          ? { rotate: [0, 360], scale: [1, 1.2, 1] }
          : { rotate: [0, 12, -8, 0], scale: [1, 1.2, 1] }
      }
      transition={
        loading
          ? { duration: 1.1, repeat: Infinity, ease: "linear" }
          : { duration: 1.8, repeat: Infinity, repeatDelay: 1.5, ease: "easeInOut" }
      }
    >
      {icon}
    </fm.div>
  );
}

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
  const { reducedMotion } = useMotion();
  const spring = bounceInteraction(reducedMotion || loading || !ruleId);
  const generatingGlow =
    loading && !reducedMotion
      ? {
          animate: {
            boxShadow: [
              "0 0 0 rgba(37,99,235,0)",
              "0 0 14px rgba(37,99,235,0.45)",
              "0 0 0 rgba(37,99,235,0)",
            ],
          },
          transition: { duration: 1.3, repeat: Infinity, ease: "easeInOut" },
        }
      : {};

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
        <fm.div style={{ display: "inline-block", borderRadius: 999 }} {...spring} {...generatingGlow}>
          <Button
            variant="outlined"
            startIcon={<SparkleIcon loading={loading} reducedMotion={reducedMotion} small={false} />}
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
        </fm.div>
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
      <fm.div style={{ display: "inline-block", borderRadius: 6 }} {...spring} {...generatingGlow}>
        <Button
          size="small"
          variant="outlined"
          startIcon={<SparkleIcon loading={loading} reducedMotion={reducedMotion} small />}
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
      </fm.div>
      {error && (
        <Alert severity="error" sx={{ mt: 0.5, py: 0.25, fontSize: "0.78rem" }}>
          {error}
        </Alert>
      )}
    </Box>
  );
}
