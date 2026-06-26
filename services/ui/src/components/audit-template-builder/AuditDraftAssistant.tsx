"use client";

/**
 * AI Draft Assistant drawer for the audit template builder.
 *
 * Multi-phase conversational flow:
 *   idle       -> user types intent
 *   intent     -> sending; backend returns questions-available
 *   discovering -> DiscoveryCard shown; user answers MCQs
 *   planning   -> sending answers; backend returns plan-available
 *   reviewing  -> PlanCard shown; user approves or requests changes
 *   building   -> sending approved tiles; backend validates and adds
 *
 * Atlas trace:
 *   DO: DO-3775670C
 *   DI: DI-64CA7740
 */

import { useCallback, useEffect, useRef, useState } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import Drawer from "@mui/material/Drawer";
import IconButton from "@mui/material/IconButton";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";
import CloseIcon from "@mui/icons-material/Close";
import SendIcon from "@mui/icons-material/Send";

import {
  sendMessage,
  type BuildSummary,
  type DashboardPlan,
  type DraftMessage,
  type GatherRequirementsResult,
  type PlannedTile,
} from "@/lib/auditDraftChatAdapter";
import {
  BuildReport,
  DiscoveryCard,
  PendingBubble,
  PlanCard,
  TextBubble,
  UserBubble,
} from "./AuditDraftSubComponents";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type AssistantPhase =
  | "idle"
  | "intent"
  | "discovering"
  | "planning"
  | "reviewing"
  | "building";

type MessageItem =
  | { kind: "user"; content: string }
  | { kind: "assistant-text"; content: string; pending?: boolean }
  | { kind: "discovery"; result: GatherRequirementsResult }
  | { kind: "plan"; plan: DashboardPlan }
  | { kind: "build-report"; summary: BuildSummary };

export interface AuditDraftAssistantProps {
  open: boolean;
  onClose: () => void;
  tiles: { metric_id: string; label: string }[];
  onAddTile: (
    metric_id: string,
    label: string,
    tile_type: string,
    section?: string,
    storyHeadline?: string,
    highlightKey?: string,
  ) => void;
}

const SUGGESTIONS = [
  "Draft NCDA audit dashboard",
  "28-day faster diagnosis tiles",
  "Referral quality metrics",
  "Safety netting overview",
  "Board cancer report",
  "Primary care coding quality",
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getHistory(items: MessageItem[]): DraftMessage[] {
  return items.flatMap((m) => {
    if (m.kind === "user") return [{ role: "user" as const, content: m.content }];
    if (m.kind === "assistant-text" && !m.pending) {
      return [{ role: "assistant" as const, content: m.content }];
    }
    return [];
  });
}

function replaceLast<T>(arr: T[], updater: (item: T) => T): T[] {
  if (arr.length === 0) return arr;
  return [...arr.slice(0, -1), updater(arr[arr.length - 1])];
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
  const [phase, setPhase] = useState<AssistantPhase>("idle");
  const [items, setItems] = useState<MessageItem[]>([]);
  const [input, setInput] = useState("");
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [pendingPlan, setPendingPlan] = useState<DashboardPlan | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const loading =
    phase === "intent" || phase === "planning" || phase === "building";

  const scrollToBottom = useCallback(() => {
    requestAnimationFrame(() => {
      if (scrollRef.current) {
        scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
      }
    });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [items, scrollToBottom]);

  useEffect(() => {
    if (!open) {
      abortRef.current?.abort();
    }
  }, [open]);

  // -- Phase: intent (user sends initial message) ---------------------------

  const handleSendIntent = useCallback(
    async (text: string) => {
      if (!text.trim() || loading) return;
      setInput("");
      setPhase("intent");

      const history = getHistory(items);
      const newItems: MessageItem[] = [
        ...items,
        { kind: "user", content: text.trim() },
        { kind: "assistant-text", content: "", pending: true },
      ];
      setItems(newItems);

      abortRef.current = new AbortController();

      await sendMessage({
        phase: "intent",
        userText: text.trim(),
        history,
        currentTiles: tiles,
        existingMetricIds: tiles.map((t) => t.metric_id),
        signal: abortRef.current.signal,
        onText: (delta) => {
          setItems((prev) =>
            replaceLast(prev, (m) =>
              m.kind === "assistant-text"
                ? { ...m, content: m.content + delta, pending: false }
                : m,
            ),
          );
        },
        onQuestions: (result) => {
          setItems((prev) => [
            ...prev.filter((m) => !(m.kind === "assistant-text" && m.pending)),
            { kind: "discovery", result },
          ]);
          setPhase("discovering");
        },
        onFinish: () => {
          if (phase !== "discovering") setPhase("discovering");
        },
        onError: (msg) => {
          setItems((prev) =>
            replaceLast(prev, (m) =>
              m.kind === "assistant-text"
                ? { ...m, content: `Error: ${msg}`, pending: false }
                : m,
            ),
          );
          setPhase("idle");
        },
      });
    },
    [loading, items, tiles, phase],
  );

  // -- Phase: planning (submit discovery answers) ---------------------------

  const handleSubmitAnswers = useCallback(async () => {
    setPhase("planning");
    setItems((prev) => [
      ...prev,
      { kind: "assistant-text", content: "", pending: true },
    ]);

    const history = getHistory(items);
    abortRef.current = new AbortController();

    await sendMessage({
      phase: "discover",
      history,
      answers,
      currentTiles: tiles,
      existingMetricIds: tiles.map((t) => t.metric_id),
      signal: abortRef.current.signal,
      onText: (delta) => {
        setItems((prev) =>
          replaceLast(prev, (m) =>
            m.kind === "assistant-text"
              ? { ...m, content: m.content + delta, pending: false }
              : m,
          ),
        );
      },
      onPlan: (plan) => {
        setPendingPlan(plan);
        setItems((prev) => [
          ...prev.filter((m) => !(m.kind === "assistant-text" && m.pending)),
          { kind: "plan", plan },
        ]);
        setPhase("reviewing");
      },
      onFinish: () => {
        if (phase !== "reviewing") setPhase("reviewing");
      },
      onError: (msg) => {
        setItems((prev) =>
          replaceLast(prev, (m) =>
            m.kind === "assistant-text"
              ? { ...m, content: `Error: ${msg}`, pending: false }
              : m,
          ),
        );
        setPhase("discovering");
      },
    });
  }, [items, answers, tiles, phase]);

  // -- Phase: building (user approved the plan) -----------------------------

  const handleApprove = useCallback(async () => {
    if (!pendingPlan) return;
    setPhase("building");

    abortRef.current = new AbortController();
    let added = 0;

    await sendMessage({
      phase: "build",
      history: [],
      approvedTiles: pendingPlan.tiles,
      signal: abortRef.current.signal,
      onTileAdded: (tile: PlannedTile) => {
        onAddTile(
          tile.metric_id,
          tile.label,
          tile.tile_type,
          tile.section,
          tile.story_headline,
          tile.highlight_key,
        );
        added++;
      },
      onBuildComplete: (summary: BuildSummary) => {
        setItems((prev) => [...prev, { kind: "build-report", summary }]);
        setPhase("idle");
        setPendingPlan(null);
        setAnswers({});
      },
      onFinish: () => {
        if (phase !== "idle") setPhase("idle");
      },
      onError: (msg) => {
        setItems((prev) => [
          ...prev,
          { kind: "assistant-text", content: `Build error: ${msg}` },
        ]);
        setPhase("idle");
      },
    });
    void added; // used via onTileAdded
  }, [pendingPlan, onAddTile, phase]);

  // -- Phase: revise --------------------------------------------------------

  const handleRevise = useCallback(
    async (revisionText: string) => {
      setPhase("planning");
      setItems((prev) => [
        ...prev,
        { kind: "user", content: revisionText },
        { kind: "assistant-text", content: "", pending: true },
      ]);

      const history = getHistory(items);
      abortRef.current = new AbortController();

      await sendMessage({
        phase: "discover",
        userText: revisionText,
        history,
        answers,
        currentTiles: tiles,
        existingMetricIds: tiles.map((t) => t.metric_id),
        signal: abortRef.current.signal,
        onPlan: (plan) => {
          setPendingPlan(plan);
          setItems((prev) => [
            ...prev.filter((m) => !(m.kind === "assistant-text" && m.pending)),
            { kind: "plan", plan },
          ]);
          setPhase("reviewing");
        },
        onFinish: () => {
          if (phase !== "reviewing") setPhase("reviewing");
        },
        onError: (msg) => {
          setItems((prev) =>
            replaceLast(prev, (m) =>
              m.kind === "assistant-text"
                ? { ...m, content: `Error: ${msg}`, pending: false }
                : m,
            ),
          );
          setPhase("reviewing");
        },
      });
    },
    [items, answers, tiles, phase],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        void handleSendIntent(input);
      }
    },
    [handleSendIntent, input],
  );

  const showInput = phase !== "reviewing";
  const showSuggestions = phase === "idle" && items.length === 0;

  // -- Render ----------------------------------------------------------------

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      variant="persistent"
      PaperProps={{ sx: { width: 420, display: "flex", flexDirection: "column" } }}
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

      {/* Suggestion chips */}
      {showSuggestions && (
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
                onClick={() => void handleSendIntent(s)}
              />
            ))}
          </Box>
        </Box>
      )}

      <Divider sx={{ flexShrink: 0 }} />

      {/* Message list */}
      <Box ref={scrollRef} sx={{ flex: 1, overflowY: "auto", px: 2, py: 1.5 }}>
        {items.length === 0 && (
          <Typography
            variant="body2"
            color="text.secondary"
            sx={{ textAlign: "center", mt: 4 }}
          >
            Describe the report you need and I will guide you through building it.
          </Typography>
        )}

        {items.map((item, i) => {
          if (item.kind === "user") return <UserBubble key={i} content={item.content} />;
          if (item.kind === "assistant-text") {
            if (item.pending) return <PendingBubble key={i} />;
            return <TextBubble key={i} content={item.content} />;
          }
          if (item.kind === "discovery") {
            return (
              <DiscoveryCard
                key={i}
                result={item.result}
                answers={answers}
                onChange={(qId, optId) => setAnswers((a) => ({ ...a, [qId]: optId }))}
                onContinue={() => void handleSubmitAnswers()}
                disabled={phase !== "discovering"}
              />
            );
          }
          if (item.kind === "plan") {
            return (
              <PlanCard
                key={i}
                plan={item.plan}
                onApprove={() => void handleApprove()}
                onRevise={(txt) => void handleRevise(txt)}
                disabled={phase !== "reviewing"}
              />
            );
          }
          if (item.kind === "build-report") {
            return <BuildReport key={i} summary={item.summary} />;
          }
          return null;
        })}
      </Box>

      <Divider sx={{ flexShrink: 0 }} />

      {/* Input area (hidden during reviewing) */}
      {showInput && (
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
                onClick={() => void handleSendIntent(input)}
                disabled={!input.trim() || loading}
              >
                {loading ? <CircularProgress size={20} /> : <SendIcon />}
              </IconButton>
            </span>
          </Tooltip>
        </Box>
      )}
    </Drawer>
  );
}
