"use client";

/**
 * Shows the live classification prompt that will be used on the next pipeline
 * run, including any few-shot examples derived from human votes.
 *
 * The panel explains the feedback loop to the user and shows:
 *   - How many verified examples exist per class
 *   - Which examples have been selected for the prompt
 *   - The exact few-shot section that will be appended to the base prompt
 *   - A full prompt preview (collapsible)
 */

import { useState } from "react";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Collapse,
  Divider,
  Stack,
  Typography,
} from "@mui/material";
import AutoFixHighIcon from "@mui/icons-material/AutoFixHigh";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import { api } from "@/lib/api";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ExampleEntry {
  text: string;
  truncated: boolean;
  notes: string;
}

interface PromptPreview {
  base_prompt: string;
  few_shot_section: string | null;
  combined_prompt: string;
  using_few_shot: boolean;
  example_counts: Record<string, number>;
  total_examples: number;
  examples_by_class: Record<string, ExampleEntry[]>;
}

const CLASS_LABELS: Record<string, string> = {
  clinical: "Clinical",
  admin_only: "Admin only",
  document_transfer: "Document transfer",
};

const CLASS_COLORS: Record<string, "success" | "warning" | "info"> = {
  clinical: "success",
  admin_only: "warning",
  document_transfer: "info",
};

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function ClassificationPromptPanel() {
  const [preview, setPreview] = useState<PromptPreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showFullPrompt, setShowFullPrompt] = useState(false);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const data = await api.get<PromptPreview>("/pipeline/classification-prompt-preview");
      setPreview(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load prompt preview");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Box sx={{ mt: 4 }}>
      <Divider sx={{ mb: 3 }} />

      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 2 }}>
        <Stack direction="row" spacing={1} alignItems="center">
          <AutoFixHighIcon sx={{ color: "text.secondary" }} />
          <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
            Prompt Improvement
          </Typography>
          <Chip label="Automatic" size="small" color="primary" variant="outlined" sx={{ fontSize: "0.7rem" }} />
        </Stack>
        <Button
          size="small"
          variant={preview ? "text" : "contained"}
          onClick={load}
          disabled={loading}
          startIcon={loading ? <CircularProgress size={14} /> : <AutoFixHighIcon />}
        >
          {preview ? "Refresh" : "Check Live Prompt"}
        </Button>
      </Stack>

      {/* Explanation */}
      <Card sx={{ mb: 2, bgcolor: "action.hover", boxShadow: "none" }}>
        <CardContent sx={{ py: "12px !important" }}>
          <Stack direction="row" spacing={1.5} alignItems="flex-start">
            <InfoOutlinedIcon sx={{ color: "text.secondary", fontSize: 20, mt: 0.2 }} />
            <Box>
              <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.5 }}>
                How the feedback loop works
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Every time you vote on a disagreement, the correct label is stored in Neo4j.
                Before each pipeline run, the classifier automatically queries for the most
                informative confirmed examples — specifically cases where at least one model
                was <em>wrong</em>, since those sit closest to the classification boundary.
                Up to 2 examples per class are appended to the system prompt as few-shot
                demonstrations. The cache refreshes every 30 minutes, or immediately after
                each vote.
              </Typography>
            </Box>
          </Stack>
        </CardContent>
      </Card>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {preview && (
        <Card variant="outlined">
          <CardContent>
            {/* Status banner */}
            {preview.using_few_shot ? (
              <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 2, p: 1.5, bgcolor: "success.light", borderRadius: 1, opacity: 0.9 }}>
                <CheckCircleOutlineIcon sx={{ color: "success.dark", fontSize: 20 }} />
                <Typography variant="body2" sx={{ fontWeight: 600, color: "success.dark" }}>
                  Few-shot active — {preview.total_examples} verified example{preview.total_examples !== 1 ? "s" : ""} are being injected into the classification prompt
                </Typography>
              </Stack>
            ) : (
              <Alert severity="info" sx={{ mb: 2 }}>
                No few-shot examples yet. Once you have reviewed enough disagreements (at least one
                per class), examples will be automatically added to the prompt. Keep voting!
              </Alert>
            )}

            {/* Example counts per class */}
            <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600, textTransform: "uppercase", letterSpacing: 0.5, display: "block", mb: 1 }}>
              Examples selected per class
            </Typography>
            <Stack direction="row" spacing={1} flexWrap="wrap" sx={{ mb: 2 }}>
              {Object.entries(CLASS_LABELS).map(([ct, label]) => (
                <Chip
                  key={ct}
                  label={`${label}: ${preview.example_counts[ct] ?? 0}`}
                  color={preview.example_counts[ct] > 0 ? CLASS_COLORS[ct] : "default"}
                  size="small"
                  variant={preview.example_counts[ct] > 0 ? "filled" : "outlined"}
                  sx={{ fontWeight: 600 }}
                />
              ))}
            </Stack>

            {/* Example cards */}
            {preview.using_few_shot && (
              <>
                <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600, textTransform: "uppercase", letterSpacing: 0.5, display: "block", mb: 1 }}>
                  Selected examples
                </Typography>
                <Stack spacing={1.5} sx={{ mb: 2 }}>
                  {(["admin_only", "document_transfer", "clinical"] as const).map((ct) => {
                    const examples = preview.examples_by_class[ct] ?? [];
                    if (examples.length === 0) return null;
                    return examples.map((ex, i) => (
                      <Box
                        key={`${ct}-${i}`}
                        sx={{
                          p: 1.5,
                          border: "1px solid",
                          borderColor: "divider",
                          borderRadius: 1,
                          borderLeft: "3px solid",
                          borderLeftColor: ct === "clinical" ? "success.main" : ct === "admin_only" ? "warning.main" : "info.main",
                        }}
                      >
                        <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.75 }}>
                          <Chip
                            label={CLASS_LABELS[ct]}
                            size="small"
                            color={CLASS_COLORS[ct]}
                            sx={{ fontWeight: 700, fontSize: "0.7rem" }}
                          />
                          <Typography variant="caption" color="text.secondary">
                            Example {i + 1}
                            {ex.truncated ? " (truncated)" : ""}
                          </Typography>
                          {ex.notes && (
                            <Typography variant="caption" color="text.secondary" sx={{ fontStyle: "italic" }}>
                              · Reviewer: &ldquo;{ex.notes}&rdquo;
                            </Typography>
                          )}
                        </Stack>
                        <Typography
                          variant="body2"
                          sx={{
                            fontFamily: "var(--font-mono)",
                            fontSize: "0.75rem",
                            lineHeight: 1.6,
                            color: "text.secondary",
                            whiteSpace: "pre-wrap",
                            maxHeight: 100,
                            overflow: "hidden",
                          }}
                        >
                          {ex.text}
                          {ex.truncated && <span style={{ color: "#999" }}>…</span>}
                        </Typography>
                      </Box>
                    ));
                  })}
                </Stack>
              </>
            )}

            {/* Full prompt preview (collapsible) */}
            <Divider sx={{ mb: 2 }} />
            <Button
              size="small"
              variant="text"
              color="inherit"
              onClick={() => setShowFullPrompt((v) => !v)}
              endIcon={<ExpandMoreIcon sx={{ transform: showFullPrompt ? "rotate(180deg)" : "none", transition: "transform 0.2s" }} />}
              sx={{ mb: 1, textTransform: "none", fontWeight: 600 }}
            >
              {showFullPrompt ? "Hide" : "Show"} full combined prompt
            </Button>
            <Collapse in={showFullPrompt}>
              <Box
                component="pre"
                sx={{
                  p: 2,
                  bgcolor: "action.hover",
                  borderRadius: 1,
                  fontSize: "0.72rem",
                  fontFamily: "var(--font-mono)",
                  lineHeight: 1.7,
                  overflowX: "auto",
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                  color: "text.primary",
                  maxHeight: 500,
                  overflowY: "auto",
                }}
              >
                {preview.combined_prompt}
              </Box>
            </Collapse>
          </CardContent>
        </Card>
      )}
    </Box>
  );
}
