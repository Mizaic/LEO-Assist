/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-3AD4D385
 *   DI: DI-9DCBC4BA
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-3AD4D385")
 */
"use client";

import { useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Collapse from "@mui/material/Collapse";
import Typography from "@mui/material/Typography";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import type { RunResult } from "@/lib/researchApi";

interface Props {
  result: RunResult | null;
}

export default function MethodExplainer({ result }: Props) {
  const [open, setOpen] = useState(false);

  if (!result?.method_plain) return null;

  return (
    <Box sx={{ mt: 1 }}>
      <Button
        size="small"
        variant="text"
        startIcon={<InfoOutlinedIcon fontSize="small" />}
        onClick={() => setOpen((o) => !o)}
        sx={{ textTransform: "none", fontSize: "0.8125rem", px: 0 }}
        aria-expanded={open}
        aria-controls="method-explainer-content"
      >
        {open ? "Hide" : "How did we work this out?"}
      </Button>

      <Collapse in={open} id="method-explainer-content">
        <Box
          sx={{
            mt: 1.5,
            p: 2,
            borderRadius: 1,
            bgcolor: "action.hover",
            border: "1px solid",
            borderColor: "divider",
          }}
        >
          <Typography variant="body2" sx={{ mb: 1.5, lineHeight: 1.6 }}>
            {result.method_plain}
          </Typography>
          {result.method_technical && (
            <Typography
              variant="caption"
              sx={{ color: "text.secondary", lineHeight: 1.5 }}
            >
              {result.method_technical}
            </Typography>
          )}
        </Box>
      </Collapse>
    </Box>
  );
}
