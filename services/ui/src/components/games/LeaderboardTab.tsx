"use client";

import { useEffect, useState } from "react";
import type { GameName, GameScore } from "@/lib/api";
import { fetchLeaderboard } from "@/lib/api";

const MEDAL = ["🥇", "🥈", "🥉"];

const GAMES: { id: GameName; label: string; icon: string; color: string }[] = [
  { id: "snake", label: "Snake", icon: "🐍", color: "#22c55e" },
  { id: "invaders", label: "Space Invaders", icon: "👾", color: "#6366f1" },
  { id: "breakout", label: "Breakout", icon: "🧱", color: "#f59e0b" },
];

function GameBoard({ game }: { game: (typeof GAMES)[number] }) {
  const [scores, setScores] = useState<GameScore[]>([]);

  useEffect(() => {
    fetchLeaderboard(game.id, 10).then(setScores).catch(() => {});
  }, [game.id]);

  return (
    <div
      style={{
        flex: 1,
        minWidth: 160,
        background: "rgba(255,255,255,0.03)",
        borderRadius: 10,
        border: `1px solid ${game.color}33`,
        padding: "12px 14px",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          marginBottom: 10,
          paddingBottom: 8,
          borderBottom: `1px solid ${game.color}22`,
        }}
      >
        <span style={{ fontSize: 18 }}>{game.icon}</span>
        <span
          style={{
            fontFamily: "var(--font-mono, monospace)",
            fontSize: 13,
            fontWeight: 700,
            color: game.color,
          }}
        >
          {game.label}
        </span>
      </div>

      {scores.length === 0 ? (
        <div
          style={{
            textAlign: "center",
            padding: "16px 0",
            color: "#475569",
            fontSize: 12,
            fontFamily: "var(--font-mono, monospace)",
          }}
        >
          No scores yet
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          {scores.map((s, i) => (
            <div
              key={s.id}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 6,
                padding: "4px 0",
                fontFamily: "var(--font-mono, monospace)",
                fontSize: 11,
                color: i < 3 ? "#e2e8f0" : "#94a3b8",
                fontWeight: i < 3 ? 600 : 400,
              }}
            >
              <span style={{ width: 22, textAlign: "center", flexShrink: 0 }}>
                {i < 3 ? MEDAL[i] : `${i + 1}.`}
              </span>
              <span
                style={{
                  flex: 1,
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
              >
                {s.player}
              </span>
              <span
                style={{
                  color: game.color,
                  fontWeight: 700,
                  flexShrink: 0,
                }}
              >
                {s.score.toLocaleString()}
              </span>
              <span style={{ color: "#475569", fontSize: 9, flexShrink: 0 }}>
                L{s.level}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function LeaderboardTab() {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 16,
        width: 560,
        maxWidth: "92vw",
      }}
    >
      <div
        style={{
          fontFamily: "var(--font-mono, monospace)",
          fontSize: 18,
          fontWeight: 700,
          color: "#e2e8f0",
          letterSpacing: 1,
        }}
      >
        🏆 HIGH SCORES
      </div>
      <div
        style={{
          display: "flex",
          gap: 12,
          width: "100%",
          flexWrap: "wrap",
        }}
      >
        {GAMES.map((g) => (
          <GameBoard key={g.id} game={g} />
        ))}
      </div>
      <div
        style={{
          fontSize: 11,
          color: "#475569",
          fontFamily: "var(--font-mono, monospace)",
          textAlign: "center",
        }}
      >
        Scores are saved to the database. Play while you wait!
      </div>
    </div>
  );
}
