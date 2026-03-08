"use client";

import Box from "@mui/material/Box";
import InputBase from "@mui/material/InputBase";
import Typography from "@mui/material/Typography";

interface WiringPillProps {
  label: string;
  type?: string;
  required?: boolean;
  connected: boolean;
  editable?: boolean;
  onLabelChange?: (value: string) => void;
}

export function WiringPill({
  label,
  type,
  required,
  connected,
  editable,
  onLabelChange,
}: WiringPillProps) {
  const bg = connected ? "success.50" : required ? "error.50" : "grey.50";
  const border = connected ? "success.200" : required ? "error.200" : "grey.200";
  const dot = connected ? "success.main" : required ? "error.main" : "grey.400";
  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, px: 1, py: 0.4, borderRadius: 1, bgcolor: bg, border: "1px solid", borderColor: border }}>
      <Box sx={{ width: 8, height: 8, borderRadius: "50%", bgcolor: dot, flexShrink: 0 }} />
      {editable ? (
        <InputBase
          value={label}
          onChange={(e) => onLabelChange?.(e.target.value)}
          placeholder="entities[].field"
          sx={{ flex: 1, fontFamily: "monospace", fontSize: "0.72rem" }}
        />
      ) : (
        <Typography variant="caption" sx={{ flex: 1, fontFamily: "monospace", fontSize: "0.72rem", fontWeight: required ? 700 : 400 }}>
          {label}{required ? " *" : ""}
        </Typography>
      )}
      {type && (
        <Typography variant="caption" sx={{ fontSize: "0.58rem", color: "info.main", whiteSpace: "nowrap" }}>
          {type}
        </Typography>
      )}
    </Box>
  );
}

