/**
 * Recommendation rows and chapter sections for RecommendationPickerDialog.
 *
 * Atlas: DI-EB716E68
 */
"use client";

import { useState } from "react";
import Box from "@mui/material/Box";
import Checkbox from "@mui/material/Checkbox";
import Chip from "@mui/material/Chip";
import Collapse from "@mui/material/Collapse";
import Stack from "@mui/material/Stack";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Typography from "@mui/material/Typography";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import BuildIcon from "@mui/icons-material/Build";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import {
  pickAttachRule,
  type RecMode,
  type RecSelection,
  type SelectionMap,
} from "./recommendationPickerSelection";
import { RuleStatusChip } from "./recommendationPickerStatus";

export interface RuleEntry {
  rule_id: string;
  status: string;
  name: string;
  created_at?: string | null;
}

export interface RecEntry {
  rec_id: string;
  rec_title: string;
  verbatim: string;
  is_normative: boolean;
  section_title: string;
  rules: RuleEntry[];
}

export interface ChapterEntry {
  chapter_id: string;
  chapter_title: string;
  order: number;
  recommendations: RecEntry[];
}

interface RecRowProps {
  rec: RecEntry;
  sel: RecSelection;
  onChange: (patch: Partial<RecSelection>) => void;
  attachMode?: boolean;
  compiledRuleIds?: ReadonlySet<string>;
}

export function RecRow({
  rec,
  sel,
  onChange,
  attachMode = false,
  compiledRuleIds,
}: RecRowProps) {
  const [expanded, setExpanded] = useState(false);
  const hasRule = rec.rules.length > 0;
  const preview = rec.verbatim ? rec.verbatim.slice(0, 120) : "(no text stored)";
  // Attach mode shows the rule that would be attached (prefer approved).
  const attachRule = attachMode ? pickAttachRule(rec.rules) : null;
  const inCompiled =
    !!attachRule && !!compiledRuleIds?.has(attachRule.rule_id);

  return (
    <Box sx={{ py: 0.75, borderBottom: "1px solid", borderColor: "grey.100" }}>
      <Stack direction="row" spacing={1} alignItems="flex-start">
        <Checkbox
          size="small"
          checked={sel.checked}
          onChange={(e) => onChange({ checked: e.target.checked })}
          sx={{ mt: -0.25, flexShrink: 0 }}
          inputProps={{ "aria-label": `Select recommendation ${rec.rec_title}` }}
        />

        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Stack
            direction="row"
            spacing={0.75}
            alignItems="center"
            flexWrap="wrap"
            sx={{ mb: 0.3 }}
          >
            {rec.rec_title && (
              <Chip
                label={rec.rec_title}
                size="small"
                sx={{
                  height: 18,
                  fontSize: "0.68rem",
                  fontFamily: "monospace",
                  bgcolor: "grey.100",
                }}
              />
            )}
            {attachMode && attachRule ? (
              <RuleStatusChip
                rule={attachRule}
                attachMode
                inCompiledBitmap={inCompiled}
              />
            ) : null}
            {!attachMode
              ? rec.rules.map((r) => <RuleStatusChip key={r.rule_id} rule={r} />)
              : null}
            {!rec.is_normative && (
              <Chip
                label="cross-ref"
                size="small"
                color="warning"
                sx={{ height: 16, fontSize: "0.62rem" }}
              />
            )}
          </Stack>

          <Stack direction="row" spacing={0.5} alignItems="flex-start">
            <Box
              sx={{
                cursor: rec.verbatim ? "pointer" : "default",
                pt: 0.1,
                flexShrink: 0,
              }}
              onClick={() => rec.verbatim && setExpanded((v) => !v)}
            >
              {rec.verbatim ? (
                expanded ? (
                  <ExpandMoreIcon sx={{ fontSize: 14, color: "text.secondary" }} />
                ) : (
                  <ChevronRightIcon sx={{ fontSize: 14, color: "text.secondary" }} />
                )
              ) : (
                <Box sx={{ width: 14 }} />
              )}
            </Box>
            <Typography
              variant="body2"
              sx={{
                fontSize: "0.8rem",
                lineHeight: 1.5,
                cursor: rec.verbatim ? "pointer" : "default",
              }}
              onClick={() => rec.verbatim && setExpanded((v) => !v)}
            >
              {expanded ? rec.verbatim : preview}
              {rec.verbatim && rec.verbatim.length > 120 && !expanded ? "..." : ""}
            </Typography>
          </Stack>

          {sel.checked && attachMode && hasRule ? (
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{ mt: 0.75, display: "block", fontSize: "0.68rem" }}
            >
              Existing rule can score whether the test case should fire
            </Typography>
          ) : null}

          {sel.checked && !attachMode && (
            <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 0.75 }}>
              <ToggleButtonGroup
                size="small"
                exclusive
                value={sel.mode}
                onChange={(_, v) => v && onChange({ mode: v as RecMode })}
                aria-label="How to create this rule"
              >
                <ToggleButton
                  value="ai"
                  sx={{ py: 0.25, px: 1, fontSize: "0.72rem", textTransform: "none" }}
                >
                  <AutoAwesomeIcon sx={{ fontSize: 13, mr: 0.5 }} />
                  AI draft
                </ToggleButton>
                <ToggleButton
                  value="hand"
                  sx={{ py: 0.25, px: 1, fontSize: "0.72rem", textTransform: "none" }}
                >
                  <BuildIcon sx={{ fontSize: 13, mr: 0.5 }} />
                  Build by hand
                </ToggleButton>
              </ToggleButtonGroup>
              {hasRule && (
                <Typography
                  variant="caption"
                  color="warning.main"
                  sx={{ fontSize: "0.68rem" }}
                >
                  Has existing rule - will add another
                </Typography>
              )}
            </Stack>
          )}
        </Box>
      </Stack>
    </Box>
  );
}

interface ChapterSectionProps {
  chapter: ChapterEntry;
  selection: SelectionMap;
  onChangeRec: (recId: string, patch: Partial<RecSelection>) => void;
  attachMode?: boolean;
  compiledRuleIds?: ReadonlySet<string>;
}

export function ChapterSection({
  chapter,
  selection,
  onChangeRec,
  attachMode = false,
  compiledRuleIds,
}: ChapterSectionProps) {
  const normative = chapter.recommendations.filter((r) => r.is_normative);
  const [open, setOpen] = useState(true);
  const checkedCount = normative.filter((r) => selection[r.rec_id]?.checked).length;

  return (
    <Box sx={{ mb: 1 }}>
      <Stack
        direction="row"
        alignItems="center"
        spacing={0.5}
        sx={{
          cursor: "pointer",
          p: 0.75,
          borderRadius: 1,
          bgcolor: "grey.50",
          "&:hover": { bgcolor: "grey.100" },
        }}
        onClick={() => setOpen((v) => !v)}
      >
        {open ? (
          <ExpandMoreIcon fontSize="small" color="primary" />
        ) : (
          <ChevronRightIcon fontSize="small" />
        )}
        <Typography
          variant="body2"
          sx={{ fontWeight: 600, flex: 1, fontSize: "0.82rem" }}
        >
          {chapter.chapter_title || chapter.chapter_id}
        </Typography>
        <Chip
          label={`${checkedCount}/${normative.length} selected`}
          size="small"
          color={checkedCount > 0 ? "primary" : "default"}
          variant="outlined"
          sx={{ height: 18, fontSize: "0.65rem" }}
        />
      </Stack>

      <Collapse in={open}>
        <Box sx={{ pl: 1, mt: 0.25 }}>
          {normative.length === 0 ? (
            <Typography
              variant="caption"
              color="text.disabled"
              sx={{ pl: 1, py: 0.5, display: "block" }}
            >
              No normative recommendations in this chapter.
            </Typography>
          ) : (
            normative.map((rec) => (
              <RecRow
                key={rec.rec_id}
                rec={rec}
                sel={selection[rec.rec_id] ?? { checked: false, mode: "ai" }}
                onChange={(patch) => onChangeRec(rec.rec_id, patch)}
                attachMode={attachMode}
                compiledRuleIds={compiledRuleIds}
              />
            ))
          )}
        </Box>
      </Collapse>
    </Box>
  );
}
