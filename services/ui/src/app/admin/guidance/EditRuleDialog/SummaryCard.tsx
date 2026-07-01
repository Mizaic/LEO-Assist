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
import VisibilityRoundedIcon from "@mui/icons-material/VisibilityRounded";

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
        position: "relative",
        borderRadius: 2,
        bgcolor: "background.paper",
        border: "1px solid",
        borderColor: "primary.100",
        overflow: "hidden",
        boxShadow:
          "0 1px 2px rgba(15, 23, 42, 0.04), 0 4px 12px rgba(15, 23, 42, 0.04)",
      }}
    >
      <Box
        aria-hidden
        sx={{
          height: 4,
          width: "100%",
          background:
            "linear-gradient(90deg, var(--mui-palette-primary-main, #1976d2) 0%, var(--mui-palette-info-main, #0288d1) 100%)",
        }}
      />
      <Box sx={{ p: 1.75 }}>
        <Stack
          direction="row"
          alignItems="center"
          justifyContent="space-between"
          spacing={1}
          sx={{ mb: expanded ? 1 : 0 }}
        >
          <Stack direction="row" alignItems="center" spacing={0.75}>
            <VisibilityRoundedIcon
              sx={{ fontSize: 16, color: "primary.main" }}
            />
            <Typography
              variant="overline"
              sx={{
                display: "block",
                color: "primary.dark",
                letterSpacing: 0.5,
                lineHeight: 1,
              }}
            >
              What this rule means
            </Typography>
          </Stack>
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
              sx={{
                mt: 0.25,
                lineHeight: 1.6,
                color: "text.primary",
                fontWeight: 500,
              }}
            >
              {summary.lead}
            </Typography>
            {summary.pathways && summary.pathways.length > 0 && (
              <Stack spacing={1} sx={{ mt: 1.5 }}>
                {summary.pathways.map((p, i) => (
                  <Box
                    key={`${i}-${p.headline}`}
                    sx={{
                      position: "relative",
                      p: 1.25,
                      pl: 1.5,
                      borderRadius: 1.5,
                      bgcolor: "primary.50",
                      border: "1px solid",
                      borderColor: "primary.100",
                      "&::before": {
                        content: '""',
                        position: "absolute",
                        left: 0,
                        top: 8,
                        bottom: 8,
                        width: 3,
                        borderRadius: 2,
                        bgcolor: "primary.main",
                      },
                    }}
                  >
                    <Typography
                      variant="subtitle2"
                      sx={{
                        fontWeight: 700,
                        color: "primary.dark",
                        lineHeight: 1.3,
                      }}
                    >
                      {p.connector ? `${p.connector}  ` : ""}
                      {p.headline}
                    </Typography>
                    <Box
                      component="ul"
                      sx={{
                        m: 0,
                        mt: 0.5,
                        pl: 2.25,
                        "& li": { mb: 0.25 },
                        "& li::marker": { color: "primary.main" },
                      }}
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
    </Box>
  );
}
