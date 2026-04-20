/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-9539333E
 *   DI: DI-29EEE9C3
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-9539333E")
 */
"use client";

import { useEffect, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";

interface PageIntroProps {
  screenId: string;
  why: string;
  how: string;
  what: string;
  headingLevel?: 1 | 2;
}

/**
 * Tells the user, in plain language, why they are on this page, how to do
 * the task, and what will happen next. Per-screen collapse is persisted in
 * localStorage under 'leo-pageintro-<screenId>'. See DI-LEO-AI-121.
 */
export default function PageIntro({
  screenId,
  why,
  how,
  what,
  headingLevel = 1,
}: PageIntroProps) {
  const storageKey = `leo-pageintro-${screenId}`;
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(storageKey);
      if (raw === "collapsed") setCollapsed(true);
    } catch {
      /* ignore */
    }
  }, [storageKey]);

  const toggle = () => {
    const next = !collapsed;
    setCollapsed(next);
    try {
      window.localStorage.setItem(
        storageKey,
        next ? "collapsed" : "expanded",
      );
    } catch {
      /* ignore */
    }
  };

  const headingVariant = headingLevel === 1 ? "h4" : "h5";
  const headingTag: "h1" | "h2" = headingLevel === 1 ? "h1" : "h2";

  return (
    <Box
      component="section"
      aria-labelledby={`${screenId}-intro-title`}
      sx={{
        bgcolor: "background.paper",
        border: "1px solid",
        borderColor: "divider",
        borderRadius: 2,
        p: 2,
        mb: 2,
      }}
    >
      <Stack
        direction="row"
        alignItems="center"
        justifyContent="space-between"
        spacing={1}
      >
        <Typography
          id={`${screenId}-intro-title`}
          variant={headingVariant}
          component={headingTag}
          sx={{ m: 0 }}
        >
          {why}
        </Typography>
        <Button
          size="small"
          onClick={toggle}
          aria-expanded={!collapsed}
          aria-controls={`${screenId}-intro-body`}
          startIcon={collapsed ? <ExpandMoreIcon /> : <ExpandLessIcon />}
        >
          {collapsed ? "Show details" : "Hide details"}
        </Button>
      </Stack>
      {!collapsed && (
        <Box id={`${screenId}-intro-body`} sx={{ mt: 1.5 }}>
          <Typography variant="body1" sx={{ mb: 1 }}>
            <Box component="strong" sx={{ fontWeight: 700 }}>
              How:
            </Box>{" "}
            {how}
          </Typography>
          <Typography variant="body1">
            <Box component="strong" sx={{ fontWeight: 700 }}>
              What happens next:
            </Box>{" "}
            {what}
          </Typography>
        </Box>
      )}
    </Box>
  );
}
