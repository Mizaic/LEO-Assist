/**
 * Left pane: letter, chunks, and source highlight.
 *
 * Atlas: DI-C953EF73 / DO-4FD76836
 *
 * Atlas trace:
 *   DO: DO-158BE606
 *   DI: DI-2289D095
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-158BE606")
 */
"use client";

import Box from "@mui/material/Box";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import Typography from "@mui/material/Typography";
import { useState } from "react";

import { LetterMarkLegend, LetterMarks } from "./LetterMarks";
import type { LetterMark } from "./letterHighlight";

interface Props {
  referralText: string;
  openedBecause?: string;
  highlights?: LetterMark[];
  gpNote?: string;
  pmhText?: string;
}

export default function LetterPane({
  referralText,
  openedBecause,
  highlights,
  gpNote,
  pmhText,
}: Props) {
  const [tab, setTab] = useState(0);
  const letter = referralText || "No letter text on this run.";
  const marks = highlights || [];
  return (
    <Box
      sx={{
        width: { xs: "100%", md: "40%" },
        minWidth: 280,
        borderRight: "1px solid",
        borderColor: "divider",
        display: "flex",
        flexDirection: "column",
        bgcolor: "#FAFAFA",
        minHeight: 0,
      }}
      data-testid="validation-lab-letter-pane"
    >
      <Tabs
        value={tab}
        onChange={(_, value) => setTab(value)}
        variant="fullWidth"
      >
        <Tab label="Letter" />
        <Tab label="GP note" />
        <Tab label="Past history" />
      </Tabs>
      <Box sx={{ flex: 1, overflow: "auto", p: 2, whiteSpace: "pre-wrap" }}>
        {openedBecause ? (
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ display: "block", mb: 1.5 }}
            data-testid="validation-lab-opened-because"
          >
            Why you opened this: {openedBecause}
          </Typography>
        ) : null}
        {tab === 0 ? (
          <Typography variant="body2" component="div">
            <LetterMarkLegend marks={marks} />
            <LetterMarks
              text={letter}
              marks={marks}
              testId="validation-lab-letter-highlight"
            />
          </Typography>
        ) : null}
        {tab === 1 ? (
          <Typography variant="body2">{gpNote || "No GP note on this case."}</Typography>
        ) : null}
        {tab === 2 ? (
          <Typography variant="body2">{pmhText || "No past history on this case."}</Typography>
        ) : null}
      </Box>
    </Box>
  );
}
