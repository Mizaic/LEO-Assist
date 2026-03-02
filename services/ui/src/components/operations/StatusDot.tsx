"use client";

import Box from "@mui/material/Box";

const COLORS: Record<string, string> = {
  ok: "#16a34a",
  warn: "#d97706",
  error: "#dc2626",
  neutral: "#94a3b8",
  processing: "#1F3A8A",
};

interface Props {
  variant?: keyof typeof COLORS;
  size?: number;
  label?: string;
}

export default function StatusDot({ variant = "neutral", size = 8, label }: Props) {
  const color = COLORS[variant] ?? COLORS.neutral;
  return (
    <Box
      component="span"
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      sx={{
        display: "inline-block",
        width: size,
        height: size,
        borderRadius: "50%",
        bgcolor: color,
        flexShrink: 0,
      }}
    />
  );
}
