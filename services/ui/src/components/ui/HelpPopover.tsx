"use client";

import { useId, useRef, useState } from "react";
import IconButton from "@mui/material/IconButton";
import Popover from "@mui/material/Popover";
import Typography from "@mui/material/Typography";
import HelpOutlineIcon from "@mui/icons-material/HelpOutline";

interface HelpPopoverProps {
  title: string;
  body: string;
  triggerLabel?: string;
}

/**
 * Small "What is this?" affordance. Clicking the trigger opens an MUI
 * Popover whose role is 'dialog' with aria-labelledby bound to the title.
 * See DI-LEO-AI-121 / VT-LEO-AI-116 TC-002.
 */
export default function HelpPopover({
  title,
  body,
  triggerLabel = "What is this?",
}: HelpPopoverProps) {
  const titleId = useId();
  const anchorRef = useRef<HTMLButtonElement | null>(null);
  const [open, setOpen] = useState(false);

  return (
    <>
      <IconButton
        ref={anchorRef}
        size="small"
        aria-label={triggerLabel}
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen(true)}
      >
        <HelpOutlineIcon fontSize="small" />
      </IconButton>
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
          {title}
        </Typography>
        <Typography variant="body2">{body}</Typography>
      </Popover>
    </>
  );
}
