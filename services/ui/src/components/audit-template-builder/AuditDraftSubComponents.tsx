"use client";

/**
 * AI Draft Assistant -- sub-components.
 *
 * DiscoveryCard  -- multiple-choice question list rendered as a chat bubble.
 * PlanCard       -- proposed tile plan with Approve / Request changes actions.
 * BuildReport    -- summary of tiles added during the build phase.
 *
 * Atlas trace:  DO-3775670C / DI-64CA7740
 */

import { motion as fm, useReducedMotion } from "framer-motion";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Typography from "@mui/material/Typography";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import StarIcon from "@mui/icons-material/Star";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";

import type {
  BuildSummary,
  DashboardPlan,
  GatherRequirementsResult,
  PlannedTile,
} from "@/lib/auditDraftChatAdapter";

// ---------------------------------------------------------------------------
// Bubble wrapper
// ---------------------------------------------------------------------------

export function AssistantBubble({ children }: { children: React.ReactNode }) {
  const reduced = useReducedMotion();
  return (
    <fm.div
      initial={{ opacity: 0, x: reduced ? 0 : -16, scale: reduced ? 1 : 0.97 }}
      animate={{ opacity: 1, x: 0, scale: 1 }}
      transition={{ duration: reduced ? 0 : 0.22, ease: "easeOut" }}
      style={{ display: "flex", justifyContent: "flex-start", marginBottom: 16 }}
    >
      <Paper
        variant="outlined"
        sx={{ maxWidth: "95%", p: 1.5, borderRadius: 2, bgcolor: "grey.50" }}
      >
        {children}
      </Paper>
    </fm.div>
  );
}

export function UserBubble({ content }: { content: string }) {
  const reduced = useReducedMotion();
  return (
    <fm.div
      initial={{ opacity: 0, x: reduced ? 0 : 16, scale: reduced ? 1 : 0.97 }}
      animate={{ opacity: 1, x: 0, scale: 1 }}
      transition={{ duration: reduced ? 0 : 0.22, ease: "easeOut" }}
      style={{ display: "flex", justifyContent: "flex-end", marginBottom: 12 }}
    >
      <Box
        sx={{
          maxWidth: "85%",
          px: 1.5,
          py: 1,
          borderRadius: 2,
          bgcolor: "primary.main",
          color: "primary.contrastText",
          fontSize: 13,
          lineHeight: 1.5,
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
        }}
      >
        {content}
      </Box>
    </fm.div>
  );
}

export function PendingBubble() {
  const reduced = useReducedMotion();
  return (
    <AssistantBubble>
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
        {[0, 1, 2].map((i) => (
          <fm.span
            key={i}
            animate={reduced ? {} : { y: [0, -4, 0] }}
            transition={{ repeat: Infinity, duration: 0.8, delay: i * 0.15, ease: "easeInOut" }}
            style={{
              display: "inline-block",
              width: 6,
              height: 6,
              borderRadius: "50%",
              background: "currentColor",
              opacity: 0.6,
            }}
          />
        ))}
        <Typography variant="caption" sx={{ ml: 0.5 }}>Thinking</Typography>
      </Box>
    </AssistantBubble>
  );
}

export function TextBubble({ content }: { content: string }) {
  return (
    <AssistantBubble>
      <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", lineHeight: 1.6 }}>
        {content}
      </Typography>
    </AssistantBubble>
  );
}

// ---------------------------------------------------------------------------
// DiscoveryCard
// ---------------------------------------------------------------------------

interface DiscoveryCardProps {
  result: GatherRequirementsResult;
  answers: Record<string, string>;
  onChange: (questionId: string, optionId: string) => void;
  onContinue: () => void;
  disabled?: boolean;
}

export function DiscoveryCard({
  result,
  answers,
  onChange,
  onContinue,
  disabled,
}: DiscoveryCardProps) {
  const allAnswered = result.questions.every((q) => Boolean(answers[q.id]));

  return (
    <AssistantBubble>
      <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
        {result.intent_summary}
      </Typography>
      <Typography variant="caption" color="text.secondary" sx={{ mb: 1.5, display: "block" }}>
        Answer these questions to build your dashboard plan.
      </Typography>

      <Stack spacing={2}>
        {result.questions.map((q) => (
          <Box key={q.id}>
            <Typography variant="caption" fontWeight={600} sx={{ mb: 0.5, display: "block" }}>
              {q.question}
            </Typography>
            <ToggleButtonGroup
              exclusive
              value={answers[q.id] ?? null}
              onChange={(_, val) => val && onChange(q.id, val)}
              size="small"
              disabled={disabled}
              sx={{ flexWrap: "wrap", gap: 0.5 }}
            >
              {q.options.map((opt) => (
                <ToggleButton
                  key={opt.id}
                  value={opt.id}
                  sx={{
                    fontSize: 11,
                    px: 1,
                    py: 0.5,
                    border: "1px solid",
                    borderColor: "divider",
                    borderRadius: "6px !important",
                    lineHeight: 1.3,
                    textTransform: "none",
                  }}
                >
                  {opt.recommended && (
                    <StarIcon sx={{ fontSize: 10, mr: 0.4, color: "warning.main" }} />
                  )}
                  {opt.label}
                </ToggleButton>
              ))}
            </ToggleButtonGroup>
          </Box>
        ))}
      </Stack>

      <Button
        variant="contained"
        size="small"
        sx={{ mt: 2 }}
        disabled={!allAnswered || disabled}
        onClick={onContinue}
      >
        Continue
      </Button>
    </AssistantBubble>
  );
}

// ---------------------------------------------------------------------------
// PlanCard
// ---------------------------------------------------------------------------

interface PlanCardProps {
  plan: DashboardPlan;
  onApprove: () => void;
  onRevise: (prompt: string) => void;
  disabled?: boolean;
}

function TileRow({ tile }: { tile: PlannedTile }) {
  return (
    <Box sx={{ py: 0.75, borderBottom: "1px solid", borderColor: "grey.200" }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, mb: 0.25 }}>
        <Chip label={tile.tile_type} size="small" variant="outlined" sx={{ fontSize: 10 }} />
        <Typography variant="caption" fontWeight={600}>
          {tile.label}
        </Typography>
      </Box>
      <Typography variant="caption" color="text.secondary">
        {tile.reason}
      </Typography>
      {tile.story_headline && (
        <Typography
          variant="caption"
          color="primary"
          sx={{ display: "block", fontStyle: "italic", mt: 0.25 }}
        >
          &ldquo;{tile.story_headline}&rdquo;
        </Typography>
      )}
    </Box>
  );
}

export function PlanCard({ plan, onApprove, onRevise, disabled }: PlanCardProps) {
  const sections = [...new Set(plan.tiles.map((t) => t.section ?? "General"))];

  return (
    <AssistantBubble>
      <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
        Dashboard plan
      </Typography>
      <Typography variant="caption" color="text.secondary" sx={{ mb: 1.5, display: "block" }}>
        {plan.rationale}
      </Typography>

      {plan.warnings.length > 0 && (
        <Box sx={{ mb: 1.5 }}>
          {plan.warnings.map((w) => (
            <Box key={w} sx={{ display: "flex", alignItems: "flex-start", gap: 0.5, mb: 0.5 }}>
              <WarningAmberIcon sx={{ fontSize: 13, color: "warning.main", mt: 0.1 }} />
              <Typography variant="caption" color="warning.dark">{w}</Typography>
            </Box>
          ))}
        </Box>
      )}

      {sections.map((section) => (
        <Box key={section} sx={{ mb: 1.5 }}>
          <Typography
            variant="overline"
            color="text.secondary"
            sx={{ display: "block", mb: 0.5 }}
          >
            {section}
          </Typography>
          {plan.tiles
            .filter((t) => (t.section ?? "General") === section)
            .map((t) => <TileRow key={t.metric_id} tile={t} />)}
        </Box>
      ))}

      <Divider sx={{ my: 1 }} />
      <Box sx={{ display: "flex", gap: 1 }}>
        <Button
          variant="contained"
          size="small"
          disabled={disabled}
          onClick={onApprove}
        >
          Approve
        </Button>
        <Button
          variant="outlined"
          size="small"
          disabled={disabled}
          onClick={() => onRevise("Please revise the plan")}
        >
          Request changes
        </Button>
      </Box>
    </AssistantBubble>
  );
}

// ---------------------------------------------------------------------------
// BuildReport
// ---------------------------------------------------------------------------

interface BuildReportProps {
  summary: BuildSummary;
}

export function BuildReport({ summary }: BuildReportProps) {
  return (
    <AssistantBubble>
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, mb: 1 }}>
        <CheckCircleOutlineIcon sx={{ color: "success.main", fontSize: 18 }} />
        <Typography variant="subtitle2">
          {summary.added} tile{summary.added !== 1 ? "s" : ""} added to your template
        </Typography>
      </Box>

      {summary.skipped.length > 0 && (
        <Box>
          <Typography variant="caption" color="text.secondary" fontWeight={600}>
            Skipped ({summary.skipped.length}):
          </Typography>
          {summary.skipped.map((s) => (
            <Typography key={s.metric_id} variant="caption" color="warning.dark" display="block">
              {s.metric_id} -- {s.reason}
            </Typography>
          ))}
        </Box>
      )}

      {summary.warnings.map((w) => (
        <Typography key={w} variant="caption" color="text.secondary" display="block">
          {w}
        </Typography>
      ))}
    </AssistantBubble>
  );
}
