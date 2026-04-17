"use client";

import { useId, useRef, useState } from "react";
import Box from "@mui/material/Box";
import Popover from "@mui/material/Popover";
import Typography from "@mui/material/Typography";
import { lookupTerm } from "@/lib/glossary";

interface GlossaryTermProps {
  termId: string;
  children?: React.ReactNode;
}

/**
 * Renders an underlined phrase whose click opens a plain-language popover
 * sourced from lib/glossary. Unknown termIds render the fallback children
 * without an affordance. See DI-LEO-AI-121 / VT-LEO-AI-116 TC-005.
 */
export default function GlossaryTerm({
  termId,
  children,
}: GlossaryTermProps) {
  const entry = lookupTerm(termId);
  const titleId = useId();
  const anchorRef = useRef<HTMLButtonElement | null>(null);
  const [open, setOpen] = useState(false);

  if (!entry) {
    return <>{children ?? termId}</>;
  }

  const visible = children ?? entry.clinicalTerm;

  return (
    <>
      <Box
        component="button"
        type="button"
        ref={anchorRef}
        onClick={() => setOpen(true)}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={`What is ${entry.clinicalTerm}?`}
        sx={{
          background: "none",
          border: "none",
          padding: 0,
          color: "primary.main",
          textDecoration: "underline dotted",
          cursor: "pointer",
          font: "inherit",
        }}
      >
        {visible}
      </Box>
      <Popover
        open={open}
        anchorEl={anchorRef.current}
        onClose={() => setOpen(false)}
        anchorOrigin={{ vertical: "bottom", horizontal: "left" }}
        slotProps={{
          paper: {
            role: "dialog",
            "aria-labelledby": titleId,
            sx: { maxWidth: 320, p: 2 },
          },
        }}
      >
        <Typography id={titleId} variant="h6" component="h3" sx={{ mb: 0.5 }}>
          {entry.clinicalTerm}
        </Typography>
        <Typography variant="body2">{entry.plainLanguage}</Typography>
      </Popover>
    </>
  );
}
