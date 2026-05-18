/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2E8544FD
 *   DI: DI-C65FD45B
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2E8544FD")
 */
"use client";

import { useCallback, useEffect, useState } from "react";
import type { GameName, GameScore } from "@/lib/api";
import { fetchLeaderboard, submitGameScore } from "@/lib/api";

const MEDAL = ["🥇", "🥈", "🥉"];
const PLAYER_KEY = "pipeline_games_player";

export function usePlayerName() {
  const [name, setNameState] = useState("");
  useEffect(() => {
    setNameState(localStorage.getItem(PLAYER_KEY) || "");
  }, []);
  const setName = useCallback((n: string) => {
    setNameState(n);
    localStorage.setItem(PLAYER_KEY, n);
  }, []);
  return [name, setName] as const;
}

interface Props {
  game: GameName;
  currentScore: number;
  currentLevel?: number;
  gameOver: boolean;
  onScoreSubmitted?: () => void;
}

export default function Leaderboard({
  game,
  currentScore,
  currentLevel = 1,
  gameOver,
  onScoreSubmitted,
}: Props) {
  const [scores, setScores] = useState<GameScore[]>([]);
  const [playerName, setPlayerName] = usePlayerName();
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [myRank, setMyRank] = useState<number | null>(null);
  const [editing, setEditing] = useState(false);

  const load = useCallback(() => {
    fetchLeaderboard(game, 10).then(setScores).catch(() => {});
  }, [game]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    setSubmitted(false);
    setMyRank(null);
  }, [gameOver]);

  const handleSubmit = async () => {
    if (!playerName.trim() || currentScore <= 0) return;
    setSubmitting(true);
    try {
      const res = await submitGameScore({
        game,
        player: playerName.trim(),
        score: currentScore,
        level: currentLevel,
      });
      setMyRank(res.rank);
      setSubmitted(true);
      load();
      onScoreSubmitted?.();
    } catch {
      /* ignore */
    } finally {
      setSubmitting(false);
    }
  };

  const nameSet = playerName.trim().length > 0;

  return (
    <div
      style={{
        width: "100%",
        marginTop: 8,
        background: "rgba(255,255,255,0.03)",
        borderRadius: 8,
        border: "1px solid rgba(255,255,255,0.08)",
        padding: "10px 14px",
      }}
    >
      {/* Player name */}
      {(!nameSet || editing) && (
        <div style={{ display: "flex", gap: 6, marginBottom: 8, alignItems: "center" }}>
          <input
            type="text"
            placeholder="Your name…"
            value={playerName}
            onChange={(e) => setPlayerName(e.target.value)}
            maxLength={30}
            aria-label="Player name"
            style={{
              flex: 1,
              background: "rgba(255,255,255,0.06)",
              border: "1px solid rgba(255,255,255,0.12)",
              borderRadius: 6,
              color: "#e2e8f0",
              padding: "5px 10px",
              fontSize: 12,
              fontFamily: "var(--font-mono, monospace)",
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && playerName.trim()) setEditing(false);
            }}
          />
          {editing && (
            <button
              type="button"
              aria-label="Save player name"
              onClick={() => setEditing(false)}
              style={{
                background: "#4f46e5",
                color: "#fff",
                border: "none",
                borderRadius: 6,
                padding: "5px 10px",
                fontSize: 11,
                cursor: "pointer",
              }}
            >
              Save
            </button>
          )}
        </div>
      )}

      {/* Submit score */}
      {gameOver && currentScore > 0 && nameSet && !submitted && (
        <button
          type="button"
          aria-label={`Submit score of ${currentScore}`}
          onClick={handleSubmit}
          disabled={submitting}
          style={{
            width: "100%",
            background: "linear-gradient(135deg, #6366f1, #8b5cf6)",
            color: "#fff",
            border: "none",
            borderRadius: 6,
            padding: "7px 0",
            fontSize: 13,
            fontWeight: 700,
            cursor: submitting ? "wait" : "pointer",
            marginBottom: 8,
            opacity: submitting ? 0.6 : 1,
          }}
        >
          {submitting ? "Submitting…" : `Submit Score: ${currentScore}`}
        </button>
      )}

      {submitted && myRank && (
        <div
          style={{
            textAlign: "center",
            marginBottom: 8,
            fontSize: 13,
            color: myRank <= 3 ? "#fbbf24" : "#22c55e",
            fontWeight: 600,
          }}
        >
          {myRank <= 3 ? `${MEDAL[myRank - 1]} Rank #${myRank}!` : `Rank #${myRank}`}
        </div>
      )}

      {/* Leaderboard table */}
      <div
        style={{
          fontSize: 11,
          fontFamily: "var(--font-mono, monospace)",
          color: "#94a3b8",
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            marginBottom: 4,
            paddingBottom: 4,
            borderBottom: "1px solid rgba(255,255,255,0.06)",
          }}
        >
          <span style={{ color: "#64748b", fontSize: 10, fontWeight: 600 }}>
            HIGH SCORES
          </span>
          {nameSet && !editing && (
            <button
              type="button"
              aria-label={`Edit player name, currently ${playerName}`}
              onClick={() => setEditing(true)}
              style={{
                background: "none",
                border: "none",
                color: "#6366f1",
                fontSize: 10,
                cursor: "pointer",
                padding: 0,
              }}
            >
              {playerName} ✏️
            </button>
          )}
        </div>
        {scores.length === 0 && (
          <div style={{ textAlign: "center", padding: "8px 0", color: "#475569" }}>
            No scores yet — be the first!
          </div>
        )}
        {scores.map((s, i) => (
          <div
            key={s.id}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              padding: "3px 0",
              color:
                s.player === playerName.trim() ? "#e2e8f0" : "#94a3b8",
              fontWeight: s.player === playerName.trim() ? 600 : 400,
            }}
          >
            <span style={{ width: 22, textAlign: "center" }}>
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
            <span style={{ color: "#fbbf24", fontWeight: 700 }}>{s.score}</span>
            <span style={{ color: "#475569", fontSize: 9 }}>L{s.level}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
