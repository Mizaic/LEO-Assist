/**
 * LogPanel -- streaming sync output with copy-to-clipboard and Clear controls.
 *
 * Design Controls: DI-340279C1, DO-CFA1ED55.
 *
 * Atlas trace:
 *   DO: DO-CD075278
 *   DI: DI-B5EEBC4C
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-CD075278")
 */
"use client";

import { useEffect, useRef, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import IconButton from "@mui/material/IconButton";
import LinearProgress from "@mui/material/LinearProgress";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import { color, elevation, typography } from "@leo/design-system/tokens";

export interface LogLine {
  msg: string;
  level?: string;
  pct?: number;
}

interface Props {
  lines: LogLine[];
  onClear: () => void;
}

export function LogPanel({ lines, onClear }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [lines]);

  if (lines.length === 0) return null;

  return (
    <Box>
      <LogToolbar copied={copied} onCopy={() => copyLines(lines, setCopied)} onClear={onClear} />
      <Paper variant="outlined" sx={logPaperSx} data-testid="terminology-log-panel">
        {lines.map((line, i) => (
          <LogRow key={i} line={line} />
        ))}
        <div ref={bottomRef} />
      </Paper>
    </Box>
  );
}

function copyLines(lines: LogLine[], setCopied: (next: boolean) => void) {
  const text = lines
    .filter((l) => l.pct == null)
    .map((l) => l.msg)
    .join("\n");
  void navigator.clipboard.writeText(text).then(() => {
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  });
}

function LogToolbar({
  copied,
  onCopy,
  onClear,
}: {
  copied: boolean;
  onCopy: () => void;
  onClear: () => void;
}) {
  return (
    <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 0.5 }}>
      <Typography variant="caption" sx={{ color: color.text.secondary }}>
        Sync log
      </Typography>
      <Stack direction="row" spacing={0.5} alignItems="center">
        <Tooltip title={copied ? "Copied!" : "Copy log to clipboard"}>
          <IconButton
            size="small"
            aria-label="Copy sync log to clipboard"
            onClick={onCopy}
            sx={{ color: copied ? color.status.success : color.text.secondary }}
          >
            <ContentCopyIcon fontSize="small" />
          </IconButton>
        </Tooltip>
        <Button
          size="small"
          variant="text"
          onClick={onClear}
          sx={{ fontSize: "0.72rem", textTransform: "none", color: color.text.secondary }}
        >
          Clear
        </Button>
      </Stack>
    </Stack>
  );
}

function LogRow({ line }: { line: LogLine }) {
  if (line.pct != null) {
    return (
      <Stack direction="row" alignItems="center" spacing={1} sx={{ py: 0.25 }}>
        <Box sx={{ flex: 1 }}>
          <LinearProgress
            variant="determinate"
            value={line.pct}
            sx={{
              height: 6,
              borderRadius: 1,
              bgcolor: color.surface.alt,
              "& .MuiLinearProgress-bar": { bgcolor: color.brand.primary },
            }}
          />
        </Box>
        <Typography variant="caption" sx={{ color: color.text.secondary, minWidth: 36 }}>
          {line.pct}%
        </Typography>
      </Stack>
    );
  }
  return (
    <Box
      sx={{
        color: lineColor(line.level),
        lineHeight: 1.6,
        whiteSpace: "pre-wrap",
        wordBreak: "break-all",
        fontFamily: typography.fontFamily.mono,
        fontSize: "0.72rem",
      }}
    >
      {line.msg}
    </Box>
  );
}

function lineColor(level?: string): string {
  if (level === "error" || level === "critical") return color.status.danger;
  if (level === "warning") return color.status.warning;
  return color.text.primary;
}

const logPaperSx = {
  p: 1.5,
  maxHeight: 360,
  overflowY: "auto",
  bgcolor: color.surface.raised,
  border: "1px solid " + color.text.secondary,
  borderRadius: 2,
  boxShadow: elevation.card,
};
