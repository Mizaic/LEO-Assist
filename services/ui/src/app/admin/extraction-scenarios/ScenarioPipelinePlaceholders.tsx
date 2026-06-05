/**
 * Placeholder editors for downstream pipeline expectations.
 */

"use client";

import Accordion from "@mui/material/Accordion";
import AccordionDetails from "@mui/material/AccordionDetails";
import AccordionSummary from "@mui/material/AccordionSummary";
import FormControlLabel from "@mui/material/FormControlLabel";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";

import { arrayToCommaList, commaListToArray, listToLines, linesToList } from "./phraseHelpers";
import type { ExpectedAnalysis, ExpectedSbar } from "./types";

interface Props {
  expectedAnalysis: ExpectedAnalysis;
  expectedSbar: ExpectedSbar;
  onAnalysisChange: (next: ExpectedAnalysis) => void;
  onSbarChange: (next: ExpectedSbar) => void;
}

export default function ScenarioPipelinePlaceholders({
  expectedAnalysis,
  expectedSbar,
  onAnalysisChange,
  onSbarChange,
}: Props) {
  return (
    <Stack spacing={1}>
      <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
        Downstream pipeline placeholders
      </Typography>
      <Typography variant="caption" color="text.secondary">
        Optional ground truth for terminology coding, roaring-bitmap analysis, and SBAR
        output. Validation against these fields is not wired yet.
      </Typography>

      <Accordion defaultExpanded={false} disableGutters data-testid="expected-analysis-panel">
        <AccordionSummary expandIcon={<ExpandMoreIcon fontSize="small" />}>
          <Typography variant="body2" sx={{ fontWeight: 600 }}>
            Expected analysis (bitmap / rules)
          </Typography>
        </AccordionSummary>
        <AccordionDetails>
          <Stack spacing={1.5}>
            <TextField
              label="Matched rule IDs"
              value={arrayToCommaList(expectedAnalysis.matched_rule_ids)}
              onChange={(e) =>
                onAnalysisChange({
                  ...expectedAnalysis,
                  matched_rule_ids: commaListToArray(e.target.value),
                })
              }
              fullWidth
              size="small"
              helperText="Comma-separated AppropriatenessRule ids that should fire."
              inputProps={{ "data-testid": "expected-analysis-rule-ids" }}
            />
            <FormControlLabel
              control={
                <Switch
                  data-testid="expected-analysis-no-rules"
                  checked={expectedAnalysis.expect_no_rules_fired}
                  onChange={(e) =>
                    onAnalysisChange({
                      ...expectedAnalysis,
                      expect_no_rules_fired: e.target.checked,
                    })
                  }
                />
              }
              label="Expect no rules to fire"
            />
            <TextField
              label="Expected action priority"
              value={expectedAnalysis.expected_action_priority ?? ""}
              onChange={(e) =>
                onAnalysisChange({
                  ...expectedAnalysis,
                  expected_action_priority: e.target.value.trim() || null,
                })
              }
              fullWidth
              size="small"
              placeholder="2ww, urgent, routine"
              inputProps={{ "data-testid": "expected-analysis-action-priority" }}
            />
            <TextField
              label="Reviewer notes"
              value={expectedAnalysis.reviewer_notes}
              onChange={(e) =>
                onAnalysisChange({
                  ...expectedAnalysis,
                  reviewer_notes: e.target.value,
                })
              }
              fullWidth
              size="small"
              multiline
              minRows={2}
              inputProps={{ "data-testid": "expected-analysis-notes" }}
            />
          </Stack>
        </AccordionDetails>
      </Accordion>

      <Accordion defaultExpanded={false} disableGutters data-testid="expected-sbar-panel">
        <AccordionSummary expandIcon={<ExpandMoreIcon fontSize="small" />}>
          <Typography variant="body2" sx={{ fontWeight: 600 }}>
            Expected SBAR output
          </Typography>
        </AccordionSummary>
        <AccordionDetails>
          <Stack spacing={1.5}>
            <TextField
              label="Situation"
              value={expectedSbar.situation_md}
              onChange={(e) =>
                onSbarChange({ ...expectedSbar, situation_md: e.target.value })
              }
              fullWidth
              size="small"
              multiline
              minRows={2}
              inputProps={{ "data-testid": "expected-sbar-situation" }}
            />
            <TextField
              label="Background"
              value={expectedSbar.background_md}
              onChange={(e) =>
                onSbarChange({ ...expectedSbar, background_md: e.target.value })
              }
              fullWidth
              size="small"
              multiline
              minRows={2}
              inputProps={{ "data-testid": "expected-sbar-background" }}
            />
            <TextField
              label="Recommendation"
              value={expectedSbar.recommendation_md}
              onChange={(e) =>
                onSbarChange({ ...expectedSbar, recommendation_md: e.target.value })
              }
              fullWidth
              size="small"
              multiline
              minRows={2}
              inputProps={{ "data-testid": "expected-sbar-recommendation" }}
            />
            <TextField
              label="Matched rule IDs"
              value={arrayToCommaList(expectedSbar.matched_rule_ids)}
              onChange={(e) =>
                onSbarChange({
                  ...expectedSbar,
                  matched_rule_ids: commaListToArray(e.target.value),
                })
              }
              fullWidth
              size="small"
              helperText="Rules the recommendation section should cite."
              inputProps={{ "data-testid": "expected-sbar-rule-ids" }}
            />
            <TextField
              label="Required phrases"
              value={listToLines(expectedSbar.required_phrases)}
              onChange={(e) =>
                onSbarChange({
                  ...expectedSbar,
                  required_phrases: linesToList(e.target.value),
                })
              }
              fullWidth
              size="small"
              multiline
              minRows={2}
              helperText="One phrase per line."
              inputProps={{ "data-testid": "expected-sbar-required-phrases" }}
            />
            <TextField
              label="Banned phrases"
              value={listToLines(expectedSbar.banned_phrases)}
              onChange={(e) =>
                onSbarChange({
                  ...expectedSbar,
                  banned_phrases: linesToList(e.target.value),
                })
              }
              fullWidth
              size="small"
              multiline
              minRows={2}
              helperText="One phrase per line."
              inputProps={{ "data-testid": "expected-sbar-banned-phrases" }}
            />
            <TextField
              label="Expected action priority"
              value={expectedSbar.expected_action_priority ?? ""}
              onChange={(e) =>
                onSbarChange({
                  ...expectedSbar,
                  expected_action_priority: e.target.value.trim() || null,
                })
              }
              fullWidth
              size="small"
              inputProps={{ "data-testid": "expected-sbar-action-priority" }}
            />
            <TextField
              label="Reviewer focus"
              value={expectedSbar.reviewer_focus}
              onChange={(e) =>
                onSbarChange({ ...expectedSbar, reviewer_focus: e.target.value })
              }
              fullWidth
              size="small"
              multiline
              minRows={2}
              inputProps={{ "data-testid": "expected-sbar-reviewer-focus" }}
            />
          </Stack>
        </AccordionDetails>
      </Accordion>
    </Stack>
  );
}
