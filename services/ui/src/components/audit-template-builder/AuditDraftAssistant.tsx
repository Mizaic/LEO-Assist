"use client";

/**
 * AI Draft Assistant drawer for the audit template builder.
 *
 * Renders a 400 px right-anchored MUI Drawer with:
 *   - Suggestion chips for common NHS QI intents
 *   - Scrollable message list (user / assistant bubbles)
 *   - TextField + Send button for free-text prompts
 *
 * On `tool-input-available` SSE events the `onAddTile` callback is fired
 * once per tile so the parent can add them to the tile grid.
 *
 * Atlas trace:
 *   DO: DO-3775670C
 *   DI: DI-64CA7740
 */

import { useCallback, useRef, useState, useEffect } from "react";
import Drawer from "@mui/material/Drawer";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import IconButton from "@mui/material/IconButton";
import TextField from "@mui/material/TextField";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import Tooltip from "@mui/material/Tooltip";
import CloseIcon from "@mui/icons-material/Close";
import SendIcon from "@mui/icons-material/Send";
import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";

import {
  sendMessage,
  type DraftMessage,
  type TileSuggestion,
} from "@/lib/auditDraftChatAdapter";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Message {
  role: "user" | "assistant";
  content: string;
  pending?: boolean;
}

export interface AuditDraftAssistantProps {
  open: boolean;
  onClose: () => void;
  tiles: { metric_id: string; label: string }[];
  onAddTile: (
    metric_id: string,
    label: string,
    tile_type: string,
    section?: string,
  ) => void;
}

// ---------------------------------------------------------------------------
// Suggestion chips
// ---------------------------------------------------------------------------

const SUGGESTIONS = [
  "Draft NCDA audit dashboard",
  "28-day faster diagnosis tiles",
  "Referral quality metrics",
  "Safety netting overview",
  "Board cancer report",
  "Primary care coding quality",
];

// ---------------------------------------------------------------------------
// Bubble component
// ---------------------------------------------------------------------------

function Bubble({ msg }: { msg: Message }) {
  const isUser = msg.role === "user";
  return (
    <Box
      sx={{
        display: "flex",
        justifyContent: isUser ? "flex-end" : "flex-start",
        mb: 1.5,
      }}
    >
      <Box
        sx={{
          maxWidth: "85%",
          px: 1.5,
          py: 1,
          borderRadius: 2,
          bgcolor: isUser ? "primary.main" : "grey.100",
          color: isUser ? "primary.contrastText" : "text.primary",
          fontSize: 13,
          lineHeight: 1.5,
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
        }}
      >
        {msg.pending ? (
          <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
            <CircularProgress size={12} color="inherit" />
            <span>Thinking...</span>
          </Box>
        ) : (
          msg.content
        )}
      </Box>
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function AuditDraftAssistant({
  open,
  onClose,
  tiles,
  onAddTile,
}: AuditDraftAssistantProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const scrollToBottom = useCallback(() => {
    requestAnimationFrame(() => {
      if (scrollRef.current) {
        scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
      }
    });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  const handleSend = useCallback(
    async (text: string) => {
      if (!text.trim() || loading) return;
      setInput("");
      setLoading(true);

      const userMsg: Message = { role: "user", content: text.trim() };
      const pendingMsg: Message = {
        role: "assistant",
        content: "",
        pending: true,
      };
      setMessages((prev) => [...prev, userMsg, pendingMsg]);

      const history: DraftMessage[] = messages.map((m) => ({
        role: m.role,
        content: m.content,
      }));

      abortRef.current = new AbortController();
      let assistantText = "";

      await sendMessage({
        userText: text.trim(),
        history,
        currentTiles: tiles,
        existingMetricIds: tiles.map((t) => t.metric_id),
        signal: abortRef.current.signal,
        onText: (delta) => {
          assistantText += delta;
          setMessages((prev) => {
            const next = [...prev];
            const last = next[next.length - 1];
            if (last?.role === "assistant") {
              next[next.length - 1] = {
                ...last,
                content: assistantText,
                pending: false,
              };
            }
            return next;
          });
        },
        onTiles: (suggestions: TileSuggestion[]) => {
          suggestions.forEach((s) => {
            onAddTile(s.metric_id, s.label, s.tile_type, s.section);
          });
        },
        onFinish: () => {
          setLoading(false);
        },
        onError: (message) => {
          setMessages((prev) => {
            const next = [...prev];
            const last = next[next.length - 1];
            if (last?.role === "assistant" && last.pending) {
              next[next.length - 1] = {
                ...last,
                content: `Error: ${message}`,
                pending: false,
              };
            }
            return next;
          });
          setLoading(false);
        },
      });
    },
    [loading, messages, tiles, onAddTile],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        void handleSend(input);
      }
    },
    [handleSend, input],
  );

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      variant="persistent"
      PaperProps={{ sx: { width: 400, display: "flex", flexDirection: "column" } }}
    >
      {/* Header */}
      <Box
        sx={{
          px: 2,
          py: 1.5,
          display: "flex",
          alignItems: "center",
          gap: 1,
          borderBottom: "1px solid",
          borderColor: "divider",
          flexShrink: 0,
        }}
      >
        <AutoAwesomeOutlinedIcon fontSize="small" color="primary" />
        <Typography variant="subtitle2" sx={{ flex: 1 }}>
          AI Draft Assistant
        </Typography>
        <Tooltip title="Close">
          <IconButton size="small" onClick={onClose}>
            <CloseIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </Box>

      {/* Suggestion chips (only when no messages yet) */}
      {messages.length === 0 && (
        <Box sx={{ px: 2, pt: 2, pb: 1, flexShrink: 0 }}>
          <Typography variant="caption" color="text.secondary" gutterBottom>
            Try a suggestion:
          </Typography>
          <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5, mt: 0.5 }}>
            {SUGGESTIONS.map((s) => (
              <Chip
                key={s}
                label={s}
                size="small"
                variant="outlined"
                clickable
                onClick={() => void handleSend(s)}
                disabled={loading}
              />
            ))}
          </Box>
        </Box>
      )}

      <Divider sx={{ flexShrink: 0 }} />

      {/* Message list */}
      <Box
        ref={scrollRef}
        sx={{ flex: 1, overflowY: "auto", px: 2, py: 1.5 }}
      >
        {messages.length === 0 && (
          <Typography
            variant="body2"
            color="text.secondary"
            sx={{ textAlign: "center", mt: 4 }}
          >
            Describe the report you need and I will suggest tiles.
          </Typography>
        )}
        {messages.map((m, i) => (
          <Bubble key={i} msg={m} />
        ))}
      </Box>

      <Divider sx={{ flexShrink: 0 }} />

      {/* Input area */}
      <Box
        sx={{
          px: 2,
          py: 1.5,
          display: "flex",
          alignItems: "flex-end",
          gap: 1,
          flexShrink: 0,
        }}
      >
        <TextField
          multiline
          maxRows={4}
          size="small"
          placeholder="Describe the dashboard you need..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={loading}
          fullWidth
          sx={{ fontSize: 13 }}
        />
        <Tooltip title="Send (Enter)">
          <span>
            <IconButton
              color="primary"
              onClick={() => void handleSend(input)}
              disabled={!input.trim() || loading}
            >
              {loading ? <CircularProgress size={20} /> : <SendIcon />}
            </IconButton>
          </span>
        </Tooltip>
      </Box>
    </Drawer>
  );
}
