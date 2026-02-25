"use client";

import { useState } from "react";
import type { PipelineRunResponse } from "@/lib/types";
import type { WorkerState } from "@/hooks/usePipelineStream";
import ProgressViz from "./games/ProgressViz";
import SnakeGame from "./games/SnakeGame";
import SpaceInvaders from "./games/SpaceInvaders";
import BreakoutGame from "./games/BreakoutGame";
import LeaderboardTab from "./games/LeaderboardTab";
import Dialog from "@mui/material/Dialog";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Tabs from "@mui/material/Tabs";
import Tab from "@mui/material/Tab";
import IconButton from "@mui/material/IconButton";
import Button from "@mui/material/Button";
import LinearProgress from "@mui/material/LinearProgress";
import CloseIcon from "@mui/icons-material/Close";
import MinimizeIcon from "@mui/icons-material/Minimize";
import { keyframes } from "@mui/system";

type ModalTab = "progress" | "snake" | "invaders" | "breakout" | "leaderboard";

interface Props {
  running: boolean;
  status: string | null;
  live: PipelineRunResponse | null;
  result: PipelineRunResponse | null;
  error: string | null;
  workerStates: Record<number, WorkerState>;
  onClose: () => void;
  onMinimize: () => void;
}

const TAB_META: { id: ModalTab; label: string; icon: string }[] = [
  { id: "progress", label: "Progress", icon: "📊" },
  { id: "snake", label: "Snake", icon: "🐍" },
  { id: "invaders", label: "Invaders", icon: "👾" },
  { id: "breakout", label: "Breakout", icon: "🧱" },
  { id: "leaderboard", label: "Scores", icon: "🏆" },
];

const pulse = keyframes`
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
`;

function StatChip({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <Box
      sx={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        px: 1.75,
        py: 0.75,
        bgcolor: "rgba(255,255,255,0.06)",
        borderRadius: 2,
        minWidth: 80,
      }}
    >
      <Typography
        sx={{ fontSize: 22, fontWeight: 700, color, fontFamily: "var(--font-mono)" }}
      >
        {value}
      </Typography>
      <Typography sx={{ fontSize: 11, color: "#94a3b8" }}>{label}</Typography>
    </Box>
  );
}

export default function PipelineModal({
  running,
  status,
  live,
  result,
  error,
  workerStates,
  onClose,
  onMinimize,
}: Props) {
  const [tab, setTab] = useState<ModalTab>("progress");

  const done = !!result || !!error;
  const stats = result ?? live;

  return (
    <Dialog
      open
      fullScreen
      PaperProps={{
        sx: {
          bgcolor: "rgba(15,23,42,0.96)",
          backdropFilter: "blur(8px)",
          display: "flex",
          flexDirection: "column",
        },
      }}
    >
      {/* Top bar */}
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          px: 3,
          py: 1.5,
          borderBottom: "1px solid rgba(255,255,255,0.08)",
          flexShrink: 0,
        }}
      >
        <Box sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
          <Box
            sx={{
              width: 10,
              height: 10,
              borderRadius: "50%",
              bgcolor: running ? "#22c55e" : done ? "#6366f1" : "#64748b",
              boxShadow: running ? "0 0 8px #22c55e" : "none",
              animation: running ? `${pulse} 1.5s infinite` : "none",
            }}
          />
          <Typography
            sx={{
              color: "#e2e8f0",
              fontSize: 14,
              fontFamily: "var(--font-mono)",
              maxWidth: 500,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {status ?? "Pipeline"}
          </Typography>
        </Box>
        <Box sx={{ display: "flex", gap: 1 }}>
          <IconButton
            onClick={onMinimize}
            title="Minimize"
            size="small"
            sx={{
              bgcolor: "rgba(255,255,255,0.08)",
              border: "1px solid rgba(255,255,255,0.12)",
              color: "#94a3b8",
              width: 28,
              height: 28,
              borderRadius: 1.5,
              "&:hover": { bgcolor: "rgba(255,255,255,0.14)" },
            }}
          >
            <MinimizeIcon sx={{ fontSize: 14 }} />
          </IconButton>
          {done && (
            <IconButton
              onClick={onClose}
              title="Close"
              size="small"
              sx={{
                bgcolor: "rgba(255,255,255,0.08)",
                border: "1px solid rgba(255,255,255,0.12)",
                color: "#94a3b8",
                width: 28,
                height: 28,
                borderRadius: 1.5,
                "&:hover": { bgcolor: "rgba(255,255,255,0.14)" },
              }}
            >
              <CloseIcon sx={{ fontSize: 14 }} />
            </IconButton>
          )}
        </Box>
      </Box>

      {running && (
        <LinearProgress
          sx={{
            flexShrink: 0,
            height: 3,
            bgcolor: "rgba(255,255,255,0.05)",
            "& .MuiLinearProgress-bar": { bgcolor: "#6366f1" },
          }}
        />
      )}

      {/* Pipeline stats bar */}
      {stats && (
        <Box
          sx={{
            display: "flex",
            justifyContent: "center",
            gap: 1.5,
            py: 1,
            flexShrink: 0,
            borderBottom: "1px solid rgba(255,255,255,0.05)",
          }}
        >
          <StatChip label="Processed" value={stats.processed_encounters} color="#e2e8f0" />
          <StatChip label="Queued" value={stats.queued_for_review} color="#22c55e" />
          <StatChip label="Rejected" value={stats.rejected_hard_fail} color="#ef4444" />
          <StatChip label="Warnings" value={stats.warnings_only} color="#f59e0b" />
        </Box>
      )}

      {/* Scrollable game/content area */}
      <Box
        sx={{
          flex: 1,
          overflow: "auto",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: tab === "progress" ? "center" : "flex-start",
          py: 3,
          px: 2,
        }}
      >
        {tab === "progress" && (
          <ProgressViz status={status} live={live} workerStates={workerStates} />
        )}
        {tab === "snake" && <SnakeGame />}
        {tab === "invaders" && <SpaceInvaders />}
        {tab === "breakout" && <BreakoutGame />}
        {tab === "leaderboard" && <LeaderboardTab />}
      </Box>

      {/* Completion / error banners */}
      {done && !error && (
        <Box
          sx={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 2,
            py: 1.5,
            flexShrink: 0,
            borderTop: "1px solid rgba(34,197,94,0.2)",
            bgcolor: "rgba(34,197,94,0.06)",
          }}
        >
          <Typography sx={{ fontSize: 16, color: "#22c55e", fontWeight: 700 }}>
            Pipeline Complete
          </Typography>
          <Button
            onClick={onClose}
            variant="contained"
            sx={{
              bgcolor: "#4f46e5",
              borderRadius: 2,
              px: 2.5,
              py: 0.75,
              fontSize: 13,
              fontWeight: 600,
              textTransform: "none",
              "&:hover": { bgcolor: "#4338ca" },
            }}
          >
            View Results
          </Button>
        </Box>
      )}

      {error && (
        <Box
          sx={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 2,
            py: 1.5,
            flexShrink: 0,
            borderTop: "1px solid rgba(239,68,68,0.2)",
            bgcolor: "rgba(239,68,68,0.06)",
          }}
        >
          <Typography sx={{ color: "#ef4444", fontSize: 14, fontWeight: 600 }}>
            Error: {error}
          </Typography>
          <Button
            onClick={onClose}
            variant="contained"
            sx={{
              bgcolor: "#334155",
              borderRadius: 2,
              px: 2,
              py: 0.75,
              fontSize: 13,
              textTransform: "none",
              "&:hover": { bgcolor: "#475569" },
            }}
          >
            Close
          </Button>
        </Box>
      )}

      {/* Bottom tab bar */}
      <Box
        sx={{
          display: "flex",
          justifyContent: "center",
          px: 3,
          py: 1.25,
          borderTop: "1px solid rgba(255,255,255,0.08)",
          bgcolor: "rgba(15,23,42,0.6)",
          flexShrink: 0,
        }}
      >
        <Tabs
          value={tab}
          onChange={(_, v) => setTab(v as ModalTab)}
          sx={{
            minHeight: 0,
            "& .MuiTabs-indicator": { display: "none" },
            "& .MuiTab-root": {
              minHeight: 0,
              minWidth: 0,
              px: 2,
              py: 1,
              borderRadius: 2,
              fontSize: 12,
              color: "#94a3b8",
              textTransform: "none",
              "&.Mui-selected": {
                color: "#e2e8f0",
                bgcolor: "rgba(99,102,241,0.25)",
                border: "1px solid #6366f1",
              },
            },
          }}
        >
          {TAB_META.map((t) => (
            <Tab key={t.id} value={t.id} label={`${t.icon} ${t.label}`} />
          ))}
        </Tabs>
      </Box>
    </Dialog>
  );
}
