/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 */
"use client";

import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import { SEARCH_PANEL, friendlyTerm } from "./copy";
import type { LogicCriterion, PriorConceptResolution } from "./types";

export default function PriorResolutionNudge({
  term,
  resolutions,
  onPick,
}: {
  term: string;
  resolutions: PriorConceptResolution[];
  onPick: (criterion: LogicCriterion) => void;
}) {
  const heading =
    resolutions.length === 1
      ? SEARCH_PANEL.priorResolutionOneHeading(term)
      : SEARCH_PANEL.priorResolutionManyHeading(term);
  return (
    <Box
      role="group"
      aria-label={heading}
      sx={{
        p: 1,
        borderRadius: 1.5,
        bgcolor: "primary.50",
        border: "1px solid",
        borderColor: "primary.100",
      }}
    >
      <Typography
        variant="caption"
        sx={{ fontWeight: 700, display: "block", mb: 0.5 }}
      >
        {heading}
      </Typography>
      <Stack spacing={0.5}>
        {resolutions.map((r) => {
          const friendly = friendlyTerm(r.preferred_term);
          return (
            <Stack
              key={r.snomed_concept_id}
              direction="row"
              alignItems="center"
              spacing={1}
            >
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Typography variant="body2" sx={{ fontWeight: 500 }}>
                  {friendly}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {SEARCH_PANEL.priorResolutionCount(r.count)}
                </Typography>
              </Box>
              <Button
                size="small"
                variant="outlined"
                aria-label={`Use ${friendly} (previously used for "${term}")`}
                onClick={() =>
                  onPick({
                    snomed_concept_id: r.snomed_concept_id,
                    preferred_term: r.preferred_term,
                    semantic_tag: r.semantic_tag ?? undefined,
                    term,
                  })
                }
              >
                Use this
              </Button>
            </Stack>
          );
        })}
      </Stack>
    </Box>
  );
}
