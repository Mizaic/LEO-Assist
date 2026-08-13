/**
 * Left pane: letter, chunks, and source highlight.
 *
 * Atlas: DI-C953EF73 / DO-4FD76836
 */
"use client";

import Box from "@mui/material/Box";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import Typography from "@mui/material/Typography";
import { useState } from "react";

interface Props {
  referralText: string;
  openedBecause?: string;
  highlight?: string;
  gpNote?: string;
  pmhText?: string;
}

export default function LetterPane({
  referralText,
  openedBecause,
  highlight,
  gpNote,
  pmhText,
}: Props) {
  const [tab, setTab] = useState(0);
  const letter = referralText || "No letter text on this run.";
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
        {tab === 0 ? <HighlightedText text={letter} needle={highlight} /> : null}
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

function HighlightedText({ text, needle }: { text: string; needle?: string }) {
  const q = (needle || "").trim();
  if (!q) {
    return <Typography variant="body2">{text}</Typography>;
  }
  const idx = text.toLowerCase().indexOf(q.toLowerCase());
  if (idx < 0) {
    return <Typography variant="body2">{text}</Typography>;
  }
  const before = text.slice(0, idx);
  const match = text.slice(idx, idx + q.length);
  const after = text.slice(idx + q.length);
  return (
    <Typography variant="body2" component="div">
      {before}
      <Box
        component="mark"
        sx={{ bgcolor: "#FEF08A", px: 0.25 }}
        data-testid="validation-lab-letter-highlight"
      >
        {match}
      </Box>
      {after}
    </Typography>
  );
}
