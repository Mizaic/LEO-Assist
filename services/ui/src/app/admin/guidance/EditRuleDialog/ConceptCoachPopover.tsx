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
 * Concept-expansion coach popover.
 *
 * Triggered from a chip whose preferred_term matches a vague pattern
 * (for example "symptoms of lung cancer", "CXR indicative of malignancy").
 * The popover offers a curated list of specific SNOMED concepts the
 * reviewer can add as siblings of the vague chip, plus the option to
 * replace the vague chip altogether.
 *
 * The deterministic suggestions come from the lookup in
 * ``vaguePhrases.ts``. Phase 4 / DI-LEO-AI-155 will extend this
 * popover with an LLM-backed expander for unknown topics.
 */

import { useEffect, useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Divider from "@mui/material/Divider";
import FormControlLabel from "@mui/material/FormControlLabel";
import Popover from "@mui/material/Popover";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import LightbulbOutlinedIcon from "@mui/icons-material/LightbulbOutlined";

import type { ConceptSuggestion, VaguePhraseMatch } from "./vaguePhrases";
import { suggestConceptsForTopic } from "./vaguePhrases";
import type { LogicCriterion } from "./types";

interface Props {
  open: boolean;
  anchorEl: HTMLElement | null;
  vagueTerm: string;
  match: VaguePhraseMatch;
  onClose: () => void;
  onAddCriteria: (criteria: LogicCriterion[], replaceVague: boolean) => void;
  onSearchMore: (topic: string) => void;
}

function suggestionToCriterion(s: ConceptSuggestion): LogicCriterion {
  return {
    snomed_concept_id: s.snomed_concept_id,
    preferred_term: s.preferred_term,
    term: s.preferred_term,
    semantic_tag: undefined,
  };
}

export default function ConceptCoachPopover({
  open,
  anchorEl,
  vagueTerm,
  match,
  onClose,
  onAddCriteria,
  onSearchMore,
}: Props) {
  const suggestions = useMemo(
    () => suggestConceptsForTopic(match.topic),
    [match.topic],
  );
  const [picked, setPicked] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (open) setPicked(new Set());
  }, [open, match.topic]);

  function togglePick(id: string) {
    setPicked((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function pickAll() {
    setPicked(new Set(suggestions.map((s) => s.snomed_concept_id)));
  }

  function handleAdd(replaceVague: boolean) {
    const chosen = suggestions.filter((s) => picked.has(s.snomed_concept_id));
    if (chosen.length === 0) return;
    onAddCriteria(chosen.map(suggestionToCriterion), replaceVague);
    onClose();
  }

  const hasSuggestions = suggestions.length > 0;

  return (
    <Popover
      open={open}
      anchorEl={anchorEl}
      onClose={onClose}
      anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      transformOrigin={{ vertical: "top", horizontal: "center" }}
      slotProps={{
        paper: {
          sx: {
            width: 380,
            maxHeight: "70vh",
            borderRadius: 1.5,
            boxShadow: 6,
            overflow: "hidden",
            display: "flex",
            flexDirection: "column",
          },
          "aria-label": "Concept expansion coach",
        },
      }}
    >
      <Box
        sx={{
          p: 1.5,
          bgcolor: "warning.50",
          borderBottom: "1px solid",
          borderColor: "warning.100",
        }}
      >
        <Stack direction="row" spacing={1} alignItems="flex-start">
          <LightbulbOutlinedIcon fontSize="small" sx={{ color: "warning.dark", mt: 0.25 }} />
          <Box sx={{ flex: 1 }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
              This phrase is vague
            </Typography>
            <Typography variant="caption" color="text.secondary">
              &ldquo;{vagueTerm}&rdquo;
            </Typography>
            <Typography variant="body2" sx={{ mt: 0.5, lineHeight: 1.45 }}>
              {match.reason}
            </Typography>
          </Box>
        </Stack>
      </Box>
      {hasSuggestions ? (
        <>
          <Box sx={{ px: 1.5, pt: 1, pb: 0.5 }}>
            <Stack direction="row" alignItems="center" spacing={1}>
              <Typography variant="caption" color="text.secondary" sx={{ flex: 1 }}>
                Tick the symptoms that apply for {match.topic}, then add them.
              </Typography>
              <Button
                size="small"
                onClick={pickAll}
                aria-label="Tick every suggestion"
                sx={{ textTransform: "none", fontSize: "0.72rem" }}
              >
                Tick all
              </Button>
            </Stack>
          </Box>
          <Box
            sx={{
              flex: 1,
              overflowY: "auto",
              px: 1.5,
              py: 0.5,
              display: "flex",
              flexDirection: "column",
            }}
            role="list"
            aria-label="Suggested concepts"
          >
            {suggestions.map((s) => (
              <FormControlLabel
                key={s.snomed_concept_id}
                control={
                  <Checkbox
                    size="small"
                    checked={picked.has(s.snomed_concept_id)}
                    onChange={() => togglePick(s.snomed_concept_id)}
                    inputProps={{
                      "aria-label": `Add ${s.preferred_term}`,
                    }}
                  />
                }
                label={
                  <Box>
                    <Typography variant="body2" sx={{ fontWeight: 500 }}>
                      {s.preferred_term}
                    </Typography>
                    {s.rationale && (
                      <Typography variant="caption" color="text.secondary">
                        {s.rationale}
                      </Typography>
                    )}
                  </Box>
                }
                sx={{ alignItems: "flex-start", py: 0.25, m: 0 }}
              />
            ))}
          </Box>
        </>
      ) : (
        <Box sx={{ p: 1.5 }}>
          <Typography variant="body2" color="text.secondary">
            We do not have a suggestion list for &ldquo;{match.topic}&rdquo;
            yet. Search for the specific symptoms you want to look for and add
            each one as a separate pill.
          </Typography>
        </Box>
      )}
      <Divider />
      <Stack
        direction="row"
        spacing={1}
        sx={{
          p: 1.25,
          bgcolor: "background.paper",
          flexWrap: "wrap",
          rowGap: 1,
        }}
      >
        <Button
          size="small"
          variant="text"
          onClick={() => onSearchMore(match.topic ?? vagueTerm)}
          sx={{ textTransform: "none" }}
        >
          Search for more
        </Button>
        <Box sx={{ flex: 1 }} />
        <Button size="small" onClick={onClose} sx={{ textTransform: "none" }}>
          Cancel
        </Button>
        {hasSuggestions && (
          <>
            <Button
              size="small"
              variant="outlined"
              onClick={() => handleAdd(false)}
              disabled={picked.size === 0}
              sx={{ textTransform: "none" }}
              aria-label="Add the ticked symptoms next to the vague phrase"
            >
              Add ticked
            </Button>
            <Button
              size="small"
              variant="contained"
              onClick={() => handleAdd(true)}
              disabled={picked.size === 0}
              sx={{ textTransform: "none" }}
              aria-label="Replace the vague phrase with the ticked symptoms"
            >
              Replace vague phrase
            </Button>
          </>
        )}
      </Stack>
    </Popover>
  );
}
