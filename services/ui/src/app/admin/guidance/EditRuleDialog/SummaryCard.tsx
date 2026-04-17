"use client";

/**
 * Plain-English rule summary shown above the editor.
 *
 * Renders the deterministic ``RuleSummary`` produced by
 * ``treeToSentence``. The summary updates live as the reviewer
 * edits the tree, so they can read the rule in their own words
 * without parsing the indented logic blocks.
 *
 * The body is collapsible (default expanded) so the reviewer can
 * fold it away once they've read it and reclaim screen space for
 * the editor below.
 */

import { useId, useState } from "react";
import Box from "@mui/material/Box";
import Collapse from "@mui/material/Collapse";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";

import type { RuleSummary } from "./treeToSentence";

interface Props {
  summary: RuleSummary;
  defaultExpanded?: boolean;
}

export default function SummaryCard({ summary, defaultExpanded = true }: Props) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const bodyId = useId();

  return (
    <Box
      role="region"
      aria-label="Plain English summary of this rule"
      sx={{
        p: 1.75,
        borderRadius: 1.5,
        bgcolor: "primary.50",
        border: "1px solid",
        borderColor: "primary.100",
      }}
    >
      <Stack
        direction="row"
        alignItems="center"
        justifyContent="space-between"
        spacing={1}
      >
        <Typography
          variant="overline"
          sx={{ display: "block", color: "primary.dark", letterSpacing: 0.5 }}
        >
          What this rule means
        </Typography>
        <IconButton
          size="small"
          onClick={() => setExpanded((prev) => !prev)}
          aria-expanded={expanded}
          aria-controls={bodyId}
          aria-label={
            expanded
              ? "Hide plain English summary"
              : "Show plain English summary"
          }
          sx={{
            color: "primary.dark",
            transition: "transform 150ms ease",
            transform: expanded ? "rotate(0deg)" : "rotate(-90deg)",
          }}
        >
          <ExpandMoreIcon fontSize="small" />
        </IconButton>
      </Stack>
      <Collapse in={expanded} unmountOnExit={false}>
        <Box id={bodyId}>
          <Typography
            variant="body1"
            sx={{ mt: 0.25, lineHeight: 1.55, color: "text.primary" }}
          >
            {summary.lead}
          </Typography>
          {summary.pathways && summary.pathways.length > 0 && (
            <Stack spacing={1} sx={{ mt: 1.25 }}>
              {summary.pathways.map((p, i) => (
                <Box
                  key={`${i}-${p.headline}`}
                  sx={{
                    p: 1,
                    borderRadius: 1,
                    bgcolor: "background.paper",
                    border: "1px solid",
                    borderColor: "primary.100",
                  }}
                >
                  <Typography
                    variant="subtitle2"
                    sx={{ fontWeight: 700, color: "primary.dark" }}
                  >
                    {p.connector ? `${p.connector}  ` : ""}
                    {p.headline}
                  </Typography>
                  <Box
                    component="ul"
                    sx={{ m: 0, pl: 2.5, "& li": { mb: 0.25 } }}
                  >
                    {p.conditions.map((c, j) => (
                      <li key={j}>
                        <Typography variant="body2" sx={{ lineHeight: 1.5 }}>
                          {c}
                        </Typography>
                      </li>
                    ))}
                  </Box>
                </Box>
              ))}
            </Stack>
          )}
        </Box>
      </Collapse>
    </Box>
  );
}
