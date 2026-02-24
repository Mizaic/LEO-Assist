"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const W = 384;
const H = 384;
const PADDLE_W = 64;
const PADDLE_H = 10;
const BALL_R = 5;
const BRICK_ROWS = 5;
const BRICK_COLS = 8;
const BRICK_W = W / BRICK_COLS - 4;
const BRICK_H = 14;
const BRICK_PAD = 4;

interface Brick {
  x: number;
  y: number;
  alive: boolean;
  row: number;
}

function initBricks(): Brick[] {
  const bricks: Brick[] = [];
  for (let r = 0; r < BRICK_ROWS; r++) {
    for (let c = 0; c < BRICK_COLS; c++) {
      bricks.push({
        x: c * (BRICK_W + BRICK_PAD) + BRICK_PAD / 2,
        y: 30 + r * (BRICK_H + BRICK_PAD),
        alive: true,
        row: r,
      });
    }
  }
  return bricks;
}

export default function BreakoutGame() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [score, setScore] = useState(0);
  const [gameOver, setGameOver] = useState(false);

  const stateRef = useRef({
    px: W / 2 - PADDLE_W / 2,
    bx: W / 2,
    by: H - 50,
    vx: 3,
    vy: -3,
    bricks: initBricks(),
    alive: true,
    keys: new Set<string>(),
  });

  const reset = useCallback(() => {
    const s = stateRef.current;
    s.px = W / 2 - PADDLE_W / 2;
    s.bx = W / 2;
    s.by = H - 50;
    s.vx = 3;
    s.vy = -3;
    s.bricks = initBricks();
    s.alive = true;
    setScore(0);
    setGameOver(false);
  }, []);

  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (["ArrowLeft", "ArrowRight"].includes(e.key)) e.preventDefault();
      stateRef.current.keys.add(e.key);
    };
    const up = (e: KeyboardEvent) => stateRef.current.keys.delete(e.key);
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
    };
  }, []);

  useEffect(() => {
    const ctx = canvasRef.current?.getContext("2d");
    if (!ctx) return;

    const tick = () => {
      const s = stateRef.current;
      if (!s.alive) return;

      if (s.keys.has("ArrowLeft")) s.px = Math.max(0, s.px - 5);
      if (s.keys.has("ArrowRight")) s.px = Math.min(W - PADDLE_W, s.px + 5);

      s.bx += s.vx;
      s.by += s.vy;

      if (s.bx - BALL_R <= 0 || s.bx + BALL_R >= W) s.vx *= -1;
      if (s.by - BALL_R <= 0) s.vy *= -1;

      if (
        s.by + BALL_R >= H - PADDLE_H - 6 &&
        s.bx >= s.px &&
        s.bx <= s.px + PADDLE_W
      ) {
        s.vy = -Math.abs(s.vy);
        const hitPos = (s.bx - s.px) / PADDLE_W - 0.5;
        s.vx = hitPos * 6;
      }

      if (s.by > H) {
        s.alive = false;
        setGameOver(true);
        return;
      }

      for (const brick of s.bricks) {
        if (!brick.alive) continue;
        if (
          s.bx + BALL_R > brick.x &&
          s.bx - BALL_R < brick.x + BRICK_W &&
          s.by + BALL_R > brick.y &&
          s.by - BALL_R < brick.y + BRICK_H
        ) {
          brick.alive = false;
          s.vy *= -1;
          setScore((p) => p + (BRICK_ROWS - brick.row) * 10);
          break;
        }
      }

      if (!s.bricks.some((b) => b.alive)) {
        s.bricks = initBricks();
        s.by = H - 50;
        s.vy = -Math.abs(s.vy);
      }

      ctx.fillStyle = "#0f172a";
      ctx.fillRect(0, 0, W, H);

      const rowColors = ["#ef4444", "#f59e0b", "#22c55e", "#3b82f6", "#a855f7"];
      for (const b of s.bricks) {
        if (!b.alive) continue;
        ctx.fillStyle = rowColors[b.row % rowColors.length];
        ctx.fillRect(b.x, b.y, BRICK_W, BRICK_H);
      }

      ctx.fillStyle = "#e2e8f0";
      ctx.fillRect(s.px, H - PADDLE_H - 6, PADDLE_W, PADDLE_H);

      ctx.fillStyle = "#fbbf24";
      ctx.beginPath();
      ctx.arc(s.bx, s.by, BALL_R, 0, Math.PI * 2);
      ctx.fill();
    };

    const id = setInterval(tick, 1000 / 60);
    return () => clearInterval(id);
  }, []);

  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }}>
      <div style={{ display: "flex", justifyContent: "space-between", width: W, fontSize: 14 }}>
        <span style={{ color: "#94a3b8", fontFamily: "var(--font-mono)" }}>
          Score: {score}
        </span>
        {gameOver && (
          <button
            onClick={reset}
            style={{
              background: "#4f46e5",
              color: "#fff",
              border: "none",
              borderRadius: 6,
              padding: "4px 14px",
              fontSize: 13,
              cursor: "pointer",
            }}
          >
            Play Again
          </button>
        )}
      </div>
      <canvas
        ref={canvasRef}
        width={W}
        height={H}
        style={{ borderRadius: 8, border: "1px solid #334155" }}
      />
      {gameOver && (
        <p style={{ color: "#ef4444", fontSize: 16, fontWeight: 600 }}>
          Game Over!
        </p>
      )}
      <p style={{ color: "#64748b", fontSize: 12 }}>Arrow keys to move paddle</p>
    </div>
  );
}
