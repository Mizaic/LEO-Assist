"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const CELL = 16;
const COLS = 24;
const ROWS = 24;
const W = COLS * CELL;
const H = ROWS * CELL;
const TICK_MS = 100;

type Pt = [number, number];
type Dir = "up" | "down" | "left" | "right";

const DIRS: Record<Dir, Pt> = {
  up: [0, -1],
  down: [0, 1],
  left: [-1, 0],
  right: [1, 0],
};

function randomFood(snake: Pt[]): Pt {
  const set = new Set(snake.map(([x, y]) => `${x},${y}`));
  let pt: Pt;
  do {
    pt = [Math.floor(Math.random() * COLS), Math.floor(Math.random() * ROWS)];
  } while (set.has(`${pt[0]},${pt[1]}`));
  return pt;
}

export default function SnakeGame() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [score, setScore] = useState(0);
  const [gameOver, setGameOver] = useState(false);

  const stateRef = useRef({
    snake: [[12, 12]] as Pt[],
    dir: "right" as Dir,
    nextDir: "right" as Dir,
    food: [6, 6] as Pt,
    alive: true,
  });

  const reset = useCallback(() => {
    const s = stateRef.current;
    s.snake = [[12, 12]];
    s.dir = "right";
    s.nextDir = "right";
    s.food = randomFood(s.snake);
    s.alive = true;
    setScore(0);
    setGameOver(false);
  }, []);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const s = stateRef.current;
      const map: Record<string, Dir> = {
        ArrowUp: "up",
        ArrowDown: "down",
        ArrowLeft: "left",
        ArrowRight: "right",
        w: "up",
        s: "down",
        a: "left",
        d: "right",
      };
      const nd = map[e.key];
      if (!nd) return;
      e.preventDefault();
      const opp: Record<Dir, Dir> = { up: "down", down: "up", left: "right", right: "left" };
      if (opp[nd] !== s.dir) s.nextDir = nd;
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  useEffect(() => {
    const ctx = canvasRef.current?.getContext("2d");
    if (!ctx) return;

    const tick = () => {
      const s = stateRef.current;
      if (!s.alive) return;

      s.dir = s.nextDir;
      const [dx, dy] = DIRS[s.dir];
      const head = s.snake[0];
      const nx = head[0] + dx;
      const ny = head[1] + dy;

      if (nx < 0 || nx >= COLS || ny < 0 || ny >= ROWS) {
        s.alive = false;
        setGameOver(true);
        return;
      }
      if (s.snake.some(([x, y]) => x === nx && y === ny)) {
        s.alive = false;
        setGameOver(true);
        return;
      }

      s.snake.unshift([nx, ny]);
      if (nx === s.food[0] && ny === s.food[1]) {
        s.food = randomFood(s.snake);
        setScore((prev) => prev + 1);
      } else {
        s.snake.pop();
      }

      ctx.fillStyle = "#0f172a";
      ctx.fillRect(0, 0, W, H);

      ctx.fillStyle = "#ef4444";
      ctx.beginPath();
      ctx.arc(
        s.food[0] * CELL + CELL / 2,
        s.food[1] * CELL + CELL / 2,
        CELL / 2 - 1,
        0,
        Math.PI * 2,
      );
      ctx.fill();

      for (let i = 0; i < s.snake.length; i++) {
        const [sx, sy] = s.snake[i];
        const bright = Math.max(0.3, 1 - i * 0.03);
        ctx.fillStyle = `rgba(99,102,241,${bright})`;
        ctx.fillRect(sx * CELL + 1, sy * CELL + 1, CELL - 2, CELL - 2);
      }
    };

    const id = setInterval(tick, TICK_MS);
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
      <p style={{ color: "#64748b", fontSize: 12 }}>Arrow keys or WASD to move</p>
    </div>
  );
}
