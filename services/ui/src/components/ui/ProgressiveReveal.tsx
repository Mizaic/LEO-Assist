"use client";

import { useId, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Collapse from "@mui/material/Collapse";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";

interface ProgressiveRevealProps {
  summary: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}

/**
 * Hides advanced controls behind a "More options" disclosure, keeping
 * simple screens simple for juniors and patients while letting experts
 * reveal detail. See DI-LEO-AI-121 / VT-LEO-AI-116 TC-004.
 */
export default function ProgressiveReveal({
  summary,
  children,
  defaultOpen = false,
}: ProgressiveRevealProps) {
  const bodyId = useId();
  const [open, setOpen] = useState(defaultOpen);
  return (
    <Box>
      <Button
        size="small"
        variant="text"
        onClick={() => setOpen((prev) => !prev)}
        aria-expanded={open}
        aria-controls={bodyId}
        startIcon={open ? <ExpandLessIcon /> : <ExpandMoreIcon />}
      >
        {summary}
      </Button>
      <Collapse in={open} unmountOnExit>
        <Box id={bodyId} sx={{ mt: 1 }}>
          {children}
        </Box>
      </Collapse>
    </Box>
  );
}
