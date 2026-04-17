/**
 * SuggestionsPanel -- Wave E Phase 2a-iv
 *
 * Collapsible "Recommended links" panel for the gold-label review
 * dialog. Replaces the legacy info-tinted box that lived above the
 * Terms list with two competing affordances (per-row Accept and
 * a global Accept-all).
 *
 * Design rules (DI-LEO-AI-145):
 *   - One header with the count + a single right-aligned action
 *     ("Accept all"). Per-row Accept/Reject still exist inside but
 *     are demoted to small tertiary buttons.
 *   - Collapsible: open by default ONLY when there are suggestions.
 *   - Quiet info surface (#F1F5F9), no saturated blue border. The
 *     primary action surface in the dialog is the entity list, not
 *     this panel.
 */
"use client";

import { useState } from "react";

import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Collapse from "@mui/material/Collapse";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";

import { AnimatePresence, motion } from "framer-motion";

import type { Entity } from "../goldDatasetTypes";

export interface RelationSuggestion {
  sourceIdx: number;
  targetIdx: number;
  type: string;
  confidence: number;
  reason: string;
}

interface SuggestionsPanelProps {
  suggestions: RelationSuggestion[];
  entities: Entity[];
  rejectedKeys: Record<string, string>;
  saving: boolean;
  onAccept: (suggestion: RelationSuggestion) => void;
  onReject: (suggestion: RelationSuggestion, reason: string) => void;
  onUndoReject: (suggestion: RelationSuggestion) => void;
  onAcceptAll: () => void;
}

function suggestionKey(s: RelationSuggestion): string {
  return `${s.sourceIdx}:${s.type}:${s.targetIdx}`;
}

export default function SuggestionsPanel(props: SuggestionsPanelProps) {
  const {
    suggestions,
    entities,
    rejectedKeys,
    saving,
    onAccept,
    onReject,
    onUndoReject,
    onAcceptAll,
  } = props;
  const [open, setOpen] = useState(true);

  if (suggestions.length === 0) return null;

  const activeCount = suggestions.filter((s) => !rejectedKeys[suggestionKey(s)]).length;

  return (
    <Box
      data-testid="suggestions-panel"
      sx={{
        mb: 2,
        borderRadius: 2,
        border: "1px solid",
        borderColor: "divider",
        bgcolor: "#F8FAFC",
        overflow: "hidden",
      }}
    >
      <Stack
        direction="row"
        alignItems="center"
        spacing={1}
        sx={{ px: 1.5, py: 0.85 }}
      >
        <IconButton
          size="small"
          onClick={() => setOpen((v) => !v)}
          aria-label={open ? "Collapse suggestions" : "Expand suggestions"}
          data-testid="suggestions-toggle"
          sx={{ color: "text.secondary" }}
        >
          {open ? (
            <ExpandLessIcon sx={{ fontSize: 18 }} />
          ) : (
            <ExpandMoreIcon sx={{ fontSize: 18 }} />
          )}
        </IconButton>
        <Typography
          sx={{
            flex: 1,
            fontSize: "0.78rem",
            fontWeight: 600,
            color: "text.primary",
            letterSpacing: "0.01em",
          }}
        >
          Recommended links ({activeCount})
        </Typography>
        {activeCount > 0 && (
          <Button
            size="small"
            variant="contained"
            disabled={saving}
            onClick={onAcceptAll}
            data-testid="suggestions-accept-all"
            sx={{
              height: 26,
              fontSize: "0.72rem",
              textTransform: "none",
              px: 1.25,
              boxShadow: "none",
            }}
          >
            Accept all
          </Button>
        )}
      </Stack>
      <Collapse in={open} mountOnEnter>
        <Box sx={{ px: 1.5, pb: 1, pt: 0 }}>
          <AnimatePresence initial={false}>
            {suggestions.map((suggestion) => {
              const key = suggestionKey(suggestion);
              const rejected = rejectedKeys[key];
              const source = entities[suggestion.sourceIdx];
              const target = entities[suggestion.targetIdx];
              return (
                <motion.div
                  key={key}
                  layout
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -4 }}
                  transition={{ duration: 0.18, ease: "easeOut" }}
                  data-testid={`suggestion-row-${key}`}
                >
                  <Stack
                    direction="row"
                    spacing={0.75}
                    alignItems="center"
                    flexWrap="wrap"
                    useFlexGap
                    sx={{
                      py: 0.6,
                      borderTop: "1px solid",
                      borderColor: "divider",
                    }}
                  >
                    <Box
                      component="span"
                      sx={{
                        height: 18,
                        px: 0.65,
                        bgcolor: "#EFF6FF",
                        color: "#1D4ED8",
                        border: "1px solid #BFDBFE",
                        borderRadius: 0.75,
                        fontSize: "0.62rem",
                        fontWeight: 700,
                        display: "inline-flex",
                        alignItems: "center",
                      }}
                    >
                      {Math.round(suggestion.confidence * 100)}%
                    </Box>
                    <Typography
                      sx={{ fontSize: "0.78rem", color: "text.primary" }}
                    >
                      {source?.text ?? "Source"}
                      <Box
                        component="span"
                        sx={{ mx: 0.5, color: "text.disabled" }}
                      >
                        {"->"}
                      </Box>
                      {target?.text ?? "Target"}
                    </Typography>
                    <Typography
                      sx={{ fontSize: "0.7rem", color: "text.secondary" }}
                    >
                      ({suggestion.type})
                    </Typography>
                    <Box sx={{ flex: 1 }} />
                    {!rejected ? (
                      <>
                        <Button
                          size="small"
                          variant="text"
                          onClick={() => onAccept(suggestion)}
                          disabled={saving}
                          data-testid={`suggestion-accept-${key}`}
                          sx={{
                            minHeight: 22,
                            fontSize: "0.7rem",
                            px: 1,
                            textTransform: "none",
                          }}
                        >
                          Accept
                        </Button>
                        <Button
                          size="small"
                          variant="text"
                          color="inherit"
                          onClick={() => onReject(suggestion, "not relevant")}
                          disabled={saving}
                          data-testid={`suggestion-reject-${key}`}
                          sx={{
                            minHeight: 22,
                            fontSize: "0.7rem",
                            px: 1,
                            textTransform: "none",
                            color: "text.secondary",
                          }}
                        >
                          Reject
                        </Button>
                      </>
                    ) : (
                      <Button
                        size="small"
                        variant="text"
                        color="inherit"
                        onClick={() => onUndoReject(suggestion)}
                        disabled={saving}
                        data-testid={`suggestion-undo-${key}`}
                        sx={{
                          minHeight: 22,
                          fontSize: "0.7rem",
                          px: 1,
                          textTransform: "none",
                          color: "text.disabled",
                        }}
                      >
                        Undo reject
                      </Button>
                    )}
                  </Stack>
                </motion.div>
              );
            })}
          </AnimatePresence>
        </Box>
      </Collapse>
    </Box>
  );
}
