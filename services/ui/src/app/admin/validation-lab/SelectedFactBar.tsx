/**
 * Mark the selected letter or tree fact as wrong, then open the fix path.
 *
 * Atlas: DI-42EB69CA / DO-DD92B11E / VT-E8A064C9
 *
 * Atlas trace:
 *   DO: DO-DD92B11E
 *   DI: DI-42EB69CA
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-DD92B11E")
 */
"use client";

import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import InlineFixCards from "./InlineFixCards";
import { categoryLabel, type FindingCategory } from "./findingTypes";
import { fixHref, isInlineFix } from "./fixRoutes";

interface Props {
  text: string;
  readOnly?: boolean;
  fixCategory: FindingCategory | "";
  onMarkWrong: (text: string) => void;
}

export function SelectedFactBar({
  text,
  readOnly,
  fixCategory,
  onMarkWrong,
}: Props) {
  if (!text) return null;
  return (
    <Box
      sx={{ p: 1.5, borderBottom: "1px solid", borderColor: "divider" }}
      data-testid="validation-lab-selected-fact"
    >
      <Stack direction="row" spacing={1} alignItems="center">
        <Typography variant="body2" sx={{ flex: 1, fontWeight: 600 }}>
          {text}
        </Typography>
        {readOnly ? null : (
          <Button
            size="small"
            variant="outlined"
            onClick={() => onMarkWrong(text)}
            data-testid="validation-lab-mark-wrong-selected"
          >
            This is wrong
          </Button>
        )}
      </Stack>
      <FixPath category={fixCategory} target={text} />
    </Box>
  );
}

function FixPath({
  category,
  target,
}: {
  category: FindingCategory | "";
  target: string;
}) {
  if (!category) return null;
  if (isInlineFix(category)) {
    return (
      <Box sx={{ mt: 1.25 }}>
        <InlineFixCards category={category} target={target} />
      </Box>
    );
  }
  return (
    <Button
      size="small"
      variant="contained"
      href={fixHref({ category, target })}
      sx={{ mt: 1.25 }}
      data-testid="validation-lab-fix-open"
    >
      Fix {categoryLabel(category)}
    </Button>
  );
}
