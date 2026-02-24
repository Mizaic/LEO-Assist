"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const W = 384;
const H = 384;
const PLAYER_W = 32;
const PLAYER_H = 16;
const BULLET_R = 2;
const ALIEN_W = 20;
const ALIEN_H = 14;
const ALIEN_COLS = 8;
const ALIEN_ROWS = 4;
const ALIEN_GAP = 8;
const MOVE_SPEED = 4;
const BULLET_SPEED = 6;
const ALIEN_STEP_X = 12;
const ALIEN_DROP_Y = 14;

interface Bullet {
  x: number;
  y: number;
}

interface Alien {
  x: number;
  y: number;
  alive: boolean;
  row: number;
}

function initAliens(): Alien[] {
  const aliens: Alien[] = [];
  const totalW = ALIEN_COLS * (ALIEN_W + ALIEN_GAP) - ALIEN_GAP;
  const ox = (W - totalW) / 2;
  for (let r = 0; r < ALIEN_ROWS; r++) {
    for (let c = 0; c < ALIEN_COLS; c++) {
      aliens.push({
        x: ox + c * (ALIEN_W + ALIEN_GAP),
        y: 30 + r * (ALIEN_H + ALIEN_GAP),
        alive: true,
        row: r,
      });
    }
  }
  return aliens;
}

export default function SpaceInvaders() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [score, setScore] = useState(0);
  const [gameOver, setGameOver] = useState(false);

  const stateRef = useRef({
    px: W / 2 - PLAYER_W / 2,
    bullets: [] as Bullet[],
    aliens: initAliens(),
    alienDir: 1,
    alienTick: 0,
    keys: new Set<string>(),
    alive: true,
  });

  const reset = useCallback(() => {
    const s = stateRef.current;
    s.px = W / 2 - PLAYER_W / 2;
    s.bullets = [];
    s.aliens = initAliens();
    s.alienDir = 1;
    s.alienTick = 0;
    s.alive = true;
    setScore(0);
    setGameOver(false);
  }, []);

  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (["ArrowLeft", "ArrowRight", " "].includes(e.key)) e.preventDefault();
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

    let lastShot = 0;

    const tick = () => {
      const s = stateRef.current;
      if (!s.alive) return;

      if (s.keys.has("ArrowLeft")) s.px = Math.max(0, s.px - MOVE_SPEED);
      if (s.keys.has("ArrowRight")) s.px = Math.min(W - PLAYER_W, s.px + MOVE_SPEED);

      const now = Date.now();
      if (s.keys.has(" ") && now - lastShot > 250) {
        s.bullets.push({ x: s.px + PLAYER_W / 2, y: H - PLAYER_H - 8 });
        lastShot = now;
      }

      s.bullets = s.bullets
        .map((b) => ({ ...b, y: b.y - BULLET_SPEED }))
        .filter((b) => b.y > 0);

      s.alienTick++;
      if (s.alienTick % 30 === 0) {
        const liveAliens = s.aliens.filter((a) => a.alive);
        const minX = Math.min(...liveAliens.map((a) => a.x));
        const maxX = Math.max(...liveAliens.map((a) => a.x + ALIEN_W));

        if ((s.alienDir > 0 && maxX + ALIEN_STEP_X > W) || (s.alienDir < 0 && minX - ALIEN_STEP_X < 0)) {
          s.alienDir *= -1;
          for (const a of s.aliens) a.y += ALIEN_DROP_Y;
        } else {
          for (const a of s.aliens) a.x += s.alienDir * ALIEN_STEP_X;
        }
      }

      for (const b of s.bullets) {
        for (const a of s.aliens) {
          if (!a.alive) continue;
          if (b.x > a.x && b.x < a.x + ALIEN_W && b.y > a.y && b.y < a.y + ALIEN_H) {
            a.alive = false;
            b.y = -100;
            setScore((p) => p + (ALIEN_ROWS - a.row) * 10);
          }
        }
      }

      if (s.aliens.some((a) => a.alive && a.y + ALIEN_H >= H - PLAYER_H - 10)) {
        s.alive = false;
        setGameOver(true);
        return;
      }
      if (!s.aliens.some((a) => a.alive)) {
        s.aliens = initAliens();
        s.alienDir = 1;
        s.alienTick = 0;
      }

      ctx.fillStyle = "#0f172a";
      ctx.fillRect(0, 0, W, H);

      const rowColors = ["#ef4444", "#f59e0b", "#22c55e", "#6366f1"];
      for (const a of s.aliens) {
        if (!a.alive) continue;
        ctx.fillStyle = rowColors[a.row % rowColors.length];
        ctx.fillRect(a.x, a.y, ALIEN_W, ALIEN_H);
        ctx.fillStyle = "#0f172a";
        ctx.fillRect(a.x + 4, a.y + 4, 4, 4);
        ctx.fillRect(a.x + ALIEN_W - 8, a.y + 4, 4, 4);
      }

      ctx.fillStyle = "#38bdf8";
      ctx.fillRect(s.px, H - PLAYER_H - 4, PLAYER_W, PLAYER_H);
      ctx.fillRect(s.px + PLAYER_W / 2 - 2, H - PLAYER_H - 10, 4, 8);

      ctx.fillStyle = "#fbbf24";
      for (const b of s.bullets) {
        ctx.beginPath();
        ctx.arc(b.x, b.y, BULLET_R, 0, Math.PI * 2);
        ctx.fill();
      }
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
      <p style={{ color: "#64748b", fontSize: 12 }}>
        Arrow keys to move &middot; Space to shoot
      </p>
    </div>
  );
}
