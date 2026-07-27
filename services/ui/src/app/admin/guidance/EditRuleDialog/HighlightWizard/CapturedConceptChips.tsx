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
 * "Captured so far" row content for a CONCEPT leaf built from several
 * synonym seeds ("Add another code that means the same"). Rendering
 * ten findings as one packed "one of: a, b, c, ..." sentence is hard
 * to scan and hides how much has actually been captured -- this shows
 * each finding as its own chip instead, with the list collapsed to a
 * handful plus a "+N more" toggle so a big synonym set still fits in
 * one row.
 */
import { useState } from "react";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";

import { STEP_PREREQUISITES } from "./copy";

const DEFAULT_VISIBLE_COUNT = 4;

export interface CapturedConceptChipsProps {
  /** Each already-captured finding's own plain-English term. */
  terms: string[];
  /** How many chips to show before collapsing behind "+N more". */
  visibleCount?: number;
}

export default function CapturedConceptChips({
  terms,
  visibleCount = DEFAULT_VISIBLE_COUNT,
}: CapturedConceptChipsProps) {
  const [expanded, setExpanded] = useState(false);
  const shown = expanded ? terms : terms.slice(0, visibleCount);
  const hiddenCount = terms.length - shown.length;

  return (
    <Stack spacing={0.5}>
      <Typography variant="body2" color="text.secondary">
        {STEP_PREREQUISITES.oneOfPrefix}
      </Typography>
      <Stack direction="row" spacing={0.5} flexWrap="wrap" sx={{ rowGap: 0.5 }}>
        {shown.map((term, index) => (
          <Chip key={`${term}-${index}`} label={term} size="small" variant="outlined" />
        ))}
        {hiddenCount > 0 && (
          <Chip
            label={STEP_PREREQUISITES.showMoreLabel(hiddenCount)}
            size="small"
            onClick={() => setExpanded(true)}
            clickable
          />
        )}
      </Stack>
      {expanded && terms.length > visibleCount && (
        <Button
          size="small"
          onClick={() => setExpanded(false)}
          sx={{ alignSelf: "flex-start", minWidth: 0, px: 0.5 }}
        >
          {STEP_PREREQUISITES.showLessLabel}
        </Button>
      )}
    </Stack>
  );
}
