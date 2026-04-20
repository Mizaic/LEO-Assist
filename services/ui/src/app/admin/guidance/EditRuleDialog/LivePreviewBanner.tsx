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
 * Sticky one-line preview banner above the editor canvas.
 *
 * Replaces the always-visible right-hand LivePreviewPane column.
 * The banner keeps the user oriented at every keystroke without
 * stealing canvas width: a single line summarising "If patient
 * matches X, the system will: Y" plus a [Preview] button that
 * slides out the full LivePreviewPane as a right-side drawer
 * for users who want the full plain-English mirror.
 *
 * On step 4 (save) the button label switches to "See before / after"
 * to telegraph the diff view inside the drawer.
 *
 * Design Controls: UN-LEO-AI-094 (v2), DI-LEO-AI-512 (v2),
 *                  R-LEO-AI-509 (v2), VT-LEO-AI-511 (v2).
 */

import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import VisibilityRoundedIcon from "@mui/icons-material/VisibilityRounded";
import VisibilityOffRoundedIcon from "@mui/icons-material/VisibilityOffRounded";

import { STRENGTH_LABELS, friendlyTerm } from "./copy";
import type { RuleSummary } from "./treeToSentence";
import type { LogicCriterion } from "./types";

interface Props {
  summary: RuleSummary;
  strength: string;
  action: LogicCriterion | null;
  /** True on step 4 -- changes the button label to telegraph the diff. */
  showDiffMode: boolean;
  /** Whether the inline preview panel is currently open. The button
   *  becomes a toggle so the affordance stays symmetric. */
  previewOpen: boolean;
  onOpenPreview: () => void;
  onClosePreview: () => void;
}

const ONE_LINE_FALLBACK = "Add a symptom or sign to start the rule.";

export default function LivePreviewBanner({
  summary,
  strength,
  action,
  showDiffMode,
  previewOpen,
  onOpenPreview,
  onClosePreview,
}: Props) {
  const oneLineRule = compactRuleSentence(summary) || ONE_LINE_FALLBACK;
  const strengthLabel =
    STRENGTH_LABELS.find((o) => o.value === strength)?.label ??
    "Not specified yet";
  const procedure = friendlyTerm(action?.preferred_term);
  const systemReady = Boolean(procedure);

  return (
    <Box
      role="status"
      aria-live="polite"
      aria-label="Live one-line preview of this rule"
      sx={{
        display: "flex",
        flexDirection: { xs: "column", md: "row" },
        alignItems: { xs: "stretch", md: "center" },
        gap: 1,
        px: { xs: 1.5, md: 2.5 },
        py: 1,
        bgcolor: "primary.50",
        borderBottom: "1px solid",
        borderColor: "primary.100",
      }}
    >
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography
          variant="caption"
          sx={{
            display: "block",
            fontWeight: 700,
            letterSpacing: 0.5,
            textTransform: "uppercase",
            color: "primary.dark",
            fontSize: "0.65rem",
            lineHeight: 1.1,
          }}
        >
          Live preview
        </Typography>
        <Typography
          variant="body2"
          sx={{
            fontWeight: 500,
            lineHeight: 1.4,
            color: "text.primary",
            mt: 0.25,
            display: "-webkit-box",
            WebkitLineClamp: 2,
            WebkitBoxOrient: "vertical",
            overflow: "hidden",
          }}
        >
          <Box component="span" sx={{ color: "text.secondary" }}>
            If patient matches:&nbsp;
          </Box>
          {oneLineRule}
          <Box component="span" sx={{ color: "text.secondary" }}>
            {" "}&middot; system will:&nbsp;
          </Box>
          <Box
            component="span"
            sx={{
              fontWeight: 700,
              color: systemReady ? "success.dark" : "warning.dark",
            }}
          >
            {strengthLabel}
            {procedure ? ` -- ${procedure}` : ""}
          </Box>
        </Typography>
      </Box>
      <Stack
        direction="row"
        spacing={1}
        alignItems="center"
        sx={{ flexShrink: 0 }}
      >
        <Button
          size="small"
          variant={previewOpen ? "contained" : "outlined"}
          color="primary"
          startIcon={
            previewOpen ? (
              <VisibilityOffRoundedIcon fontSize="small" />
            ) : (
              <VisibilityRoundedIcon fontSize="small" />
            )
          }
          onClick={previewOpen ? onClosePreview : onOpenPreview}
          aria-label={
            previewOpen
              ? "Hide the full preview panel"
              : showDiffMode
                ? "See full before and after preview"
                : "See full live preview"
          }
          aria-pressed={previewOpen}
          sx={{
            borderRadius: 999,
            bgcolor: previewOpen ? undefined : "background.paper",
            textTransform: "none",
            fontWeight: 600,
          }}
        >
          {previewOpen
            ? "Hide preview"
            : showDiffMode
              ? "See before / after"
              : "See full preview"}
        </Button>
      </Stack>
    </Box>
  );
}

/**
 * Render a RuleSummary as a single short clause for the banner.
 *
 * The full SummaryCard renders a structured layered view; the banner
 * shows a single clamped line. We start from the lead sentence and,
 * if there are pathway alternatives, append a "; or ..." tail with
 * each pathway's headline so the user sees they exist without having
 * to open the full preview.
 */
function compactRuleSentence(summary: RuleSummary | undefined | null): string {
  if (!summary) return "";
  const lead = (summary.lead ?? "").trim();
  const pathwayTails = (summary.pathways ?? [])
    .map((p) => (p.headline ?? "").trim())
    .filter((h) => h.length > 0);
  const joined =
    pathwayTails.length === 0
      ? lead
      : `${lead}${lead ? "; " : ""}${pathwayTails.join("; or ")}`;
  return clamp(joined, 220);
}

function clamp(s: string, n: number): string {
  if (s.length <= n) return s;
  return `${s.slice(0, n - 1).trimEnd()}...`;
}
