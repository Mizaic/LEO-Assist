"use client";

import type { ReactNode } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

type MiniHitlStatus = "completed" | "halted" | "error" | "running" | "idle";

export interface MiniHitlCardProps {
  title: string;
  subtitle: string;
  headline: string;
  status: MiniHitlStatus;
  /** Clinical content — rendered below the headline in a dark probe-style panel */
  children?: ReactNode;
  onRunToHere: () => void;
  onInspectJson: () => void;
}

function statusMeta(status: MiniHitlStatus): { label: string; color: "success" | "error" | "warning" | "info" | "default" } {
  if (status === "completed") return { label: "Passed", color: "success" };
  if (status === "halted") return { label: "Halted", color: "error" };
  if (status === "error") return { label: "Error", color: "warning" };
  if (status === "running") return { label: "Running", color: "info" };
  return { label: "Awaiting run", color: "default" };
}

export default function MiniHitlCard({
  title,
  subtitle,
  headline,
  status,
  children,
  onRunToHere,
  onInspectJson,
}: MiniHitlCardProps) {
  const meta = statusMeta(status);

  return (
    <Stack spacing={1.1}>
      {/* Header: label + status badge */}
      <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={1}>
        <Typography variant="body2" fontWeight={700} noWrap>
          {title}
        </Typography>
        <Chip size="small" color={meta.color} label={meta.label} sx={{ height: 18, fontSize: "0.62rem" }} />
      </Stack>

      {/* Step + source context */}
      <Typography variant="caption" color="text.secondary" sx={{ lineHeight: 1.3 }}>
        {subtitle}
      </Typography>

      {/* Strategy headline — short human-readable summary */}
      <Box sx={{ bgcolor: "grey.50", border: "1px solid", borderColor: "divider", borderRadius: 1.5, px: 1, py: 0.75 }}>
        <Typography variant="caption" sx={{ fontSize: "0.68rem" }}>
          {headline}
        </Typography>
      </Box>

      {/* Clinical content slot */}
      {children && (
        <Box
          sx={{
            bgcolor: "#11111b",
            borderRadius: 1.5,
            p: 1,
            maxHeight: 300,
            overflowY: "auto",
            /* thin scrollbar so it doesn't eat width */
            "&::-webkit-scrollbar": { width: 4 },
            "&::-webkit-scrollbar-thumb": { bgcolor: "#313244", borderRadius: 2 },
          }}
        >
          {children}
        </Box>
      )}

      <Divider />
      <Stack direction="row" spacing={0.75}>
        <Button
          size="small"
          variant="outlined"
          onClick={onRunToHere}
          sx={{ textTransform: "none", minWidth: 0, fontSize: "0.7rem", px: 1 }}
        >
          Run to here
        </Button>
        <Button
          size="small"
          variant="text"
          onClick={onInspectJson}
          sx={{ textTransform: "none", minWidth: 0, fontSize: "0.7rem", px: 1 }}
        >
          Inspect JSON
        </Button>
      </Stack>
    </Stack>
  );
}
