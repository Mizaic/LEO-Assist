/**
 * LogPanel -- streaming sync output with copy-to-clipboard and Clear controls.
 *
 * Design Controls: DI-340279C1, DO-CFA1ED55.
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

  const handleCopy = () => {
    const text = lines
      .filter((l) => l.pct == null)
      .map((l) => l.msg)
      .join("\n");
    void navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <Box>
      <Stack
        direction="row"
        alignItems="center"
        justifyContent="space-between"
        sx={{ mb: 0.5 }}
      >
        <Typography variant="caption" color="text.secondary">
          Sync log
        </Typography>
        <Stack direction="row" spacing={0.5} alignItems="center">
          <Tooltip title={copied ? "Copied!" : "Copy log to clipboard"}>
            <IconButton
              size="small"
              aria-label="Copy sync log to clipboard"
              onClick={handleCopy}
              color={copied ? "success" : "default"}
            >
              <ContentCopyIcon fontSize="small" />
            </IconButton>
          </Tooltip>
          <Button
            size="small"
            variant="text"
            onClick={onClear}
            sx={{ fontSize: "0.72rem", textTransform: "none", color: "text.secondary" }}
          >
            Clear
          </Button>
        </Stack>
      </Stack>
      <Paper
        variant="outlined"
        sx={{
          p: 1.5,
          maxHeight: 360,
          overflowY: "auto",
          bgcolor: "#0F172A",
          fontFamily: "JetBrains Mono, monospace",
          fontSize: "0.72rem",
          borderRadius: 2,
        }}
        data-testid="terminology-log-panel"
      >
        {lines.map((line, i) => (
          <Box
            key={i}
            sx={{
              color:
                line.level === "error" || line.level === "critical"
                  ? "#FCA5A5"
                  : line.level === "warning"
                    ? "#FDE68A"
                    : "#CBD5E1",
              lineHeight: 1.6,
              whiteSpace: "pre-wrap",
              wordBreak: "break-all",
            }}
          >
            {line.pct != null ? (
              <Stack direction="row" alignItems="center" spacing={1}>
                <Box sx={{ flex: 1 }}>
                  <LinearProgress
                    variant="determinate"
                    value={line.pct}
                    sx={{ height: 6, borderRadius: 1 }}
                  />
                </Box>
                <Typography variant="caption" sx={{ color: "#94A3B8", minWidth: 36 }}>
                  {line.pct}%
                </Typography>
              </Stack>
            ) : (
              line.msg
            )}
          </Box>
        ))}
        <div ref={bottomRef} />
      </Paper>
    </Box>
  );
}
