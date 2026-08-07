/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-42246DA7")
 */
"use client";

/**
 * The two "fewer than 2 rows" states Step 2 (StepPathwaySplit) can
 * land on -- split out of that file to keep it under the repo's
 * 500-LOC file-length limit. They are deliberately NOT the same
 * component: showing `NoSplitState`'s "we couldn't find more than one
 * situation" copy after the REVIEWER's own merge collapsed everything
 * down to one row would be a flat contradiction (there WAS more than
 * one -- the reviewer just combined them). See `MergedToOneState`'s
 * doc comment.
 */
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";

import { STEP_PATHWAY_SPLIT, WIZARD_TOOLTIPS } from "./copy";

const EMPTY_STATE_BOX_SX = {
  p: 2,
  borderRadius: 1.5,
  border: "1px dashed",
  borderColor: "divider",
  textAlign: "center",
} as const;

export function NoSplitState({
  onNoSplit,
  onAgeLabBands,
}: {
  onNoSplit: () => void;
  onAgeLabBands?: () => void;
}) {
  return (
    <Box sx={EMPTY_STATE_BOX_SX}>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
        {STEP_PATHWAY_SPLIT.noSplitBody}
      </Typography>
      <Stack
        direction="column"
        spacing={1}
        alignItems="center"
        sx={{ rowGap: 1 }}
      >
        {onAgeLabBands && (
          <Tooltip title={STEP_PATHWAY_SPLIT.ageLabBandsHint}>
            <Button variant="contained" size="small" onClick={onAgeLabBands}>
              {STEP_PATHWAY_SPLIT.ageLabBandsLabel}
            </Button>
          </Tooltip>
        )}
        <Tooltip title={WIZARD_TOOLTIPS.noSplit}>
          <Button variant="outlined" size="small" onClick={onNoSplit}>
            {STEP_PATHWAY_SPLIT.noSplitConfirmLabel}
          </Button>
        </Tooltip>
      </Stack>
    </Box>
  );
}

/** Reached only by the reviewer's OWN merge action (never on first
 *  load) -- explains what just happened and offers a way back, unlike
 *  `NoSplitState`'s "we couldn't find" framing which would be untrue
 *  here. See StepPathwaySplit's `preMergeSnapshot` doc comment. */
export function MergedToOneState({
  onUndo,
  onNoSplit,
}: {
  onUndo: () => void;
  onNoSplit: () => void;
}) {
  return (
    <Box sx={EMPTY_STATE_BOX_SX}>
      <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 0.5 }}>
        {STEP_PATHWAY_SPLIT.mergedToOneTitle}
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
        {STEP_PATHWAY_SPLIT.mergedToOneBody}
      </Typography>
      <Stack direction="row" spacing={1} justifyContent="center" flexWrap="wrap" sx={{ rowGap: 1 }}>
        <Tooltip title={WIZARD_TOOLTIPS.undoMerge}>
          <Button variant="outlined" size="small" onClick={onUndo}>
            {STEP_PATHWAY_SPLIT.undoMergeLabel}
          </Button>
        </Tooltip>
        <Tooltip title={WIZARD_TOOLTIPS.noSplit}>
          <Button variant="contained" size="small" onClick={onNoSplit}>
            {STEP_PATHWAY_SPLIT.noSplitConfirmLabel}
          </Button>
        </Tooltip>
      </Stack>
    </Box>
  );
}
