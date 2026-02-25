"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Leaderboard from "./Leaderboard";

const CELL = 16;
const COLS = 24;
const ROWS = 24;
const W = COLS * CELL;
const H = ROWS * CELL;
const BASE_TICK = 120;
const MIN_TICK = 50;
const COMBO_WINDOW = 3_000;
const MAX_COMBO = 5;
const FOOD_PER_LEVEL = 10;
const PU_INTERVAL = 15_000;
const PU_LIFETIME = 8_000;
const PARTICLE_MS = 300;
const UI_SYNC_MS = 250;

type Pt = [number, number];
type Dir = "up" | "down" | "left" | "right";
type PUKind = "speed" | "slow" | "ghost" | "double" | "diamond";

const DIR_VEC: Record<Dir, Pt> = {
  up: [0, -1],
  down: [0, 1],
  left: [-1, 0],
  right: [1, 0],
};
const OPP: Record<Dir, Dir> = {
  up: "down",
  down: "up",
  left: "right",
  right: "left",
};
const KEYS: Record<string, Dir> = {
  ArrowUp: "up",
  ArrowDown: "down",
  ArrowLeft: "left",
  ArrowRight: "right",
  w: "up",
  W: "up",
  s: "down",
  S: "down",
  a: "left",
  A: "left",
  d: "right",
  D: "right",
};

interface PUDef {
  kind: PUKind;
  label: string;
  color: string;
  dur: number;
}
const PU_DEFS: PUDef[] = [
  { kind: "speed", label: "S", color: "#3b82f6", dur: 6_000 },
  { kind: "slow", label: "W", color: "#eab308", dur: 6_000 },
  { kind: "ghost", label: "G", color: "#a855f7", dur: 8_000 },
  { kind: "double", label: "2", color: "#f59e0b", dur: 10_000 },
  { kind: "diamond", label: "D", color: "#06b6d4", dur: 0 },
];
const puDef = (k: PUKind) => PU_DEFS.find((d) => d.kind === k)!;

interface Effect {
  kind: PUKind;
  label: string;
  color: string;
  end: number;
}
interface PUItem {
  kind: PUKind;
  pos: Pt;
  born: number;
}
interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  born: number;
  color: string;
}

interface GS {
  snake: Pt[];
  dir: Dir;
  nextDir: Dir;
  food: Pt;
  alive: boolean;
  score: number;
  level: number;
  eaten: number;
  combo: number;
  maxCombo: number;
  lastEat: number;
  pu: PUItem | null;
  lastPuTime: number;
  fx: Effect[];
  particles: Particle[];
  acc: number;
  prev: number;
}

/* ── helpers ── */

function freeCell(snake: Pt[], extra: Pt[]): Pt {
  const occ = new Set<string>();
  for (const p of snake) occ.add(`${p[0]},${p[1]}`);
  for (const p of extra) occ.add(`${p[0]},${p[1]}`);
  let c: Pt;
  do {
    c = [~~(Math.random() * COLS), ~~(Math.random() * ROWS)];
  } while (occ.has(`${c[0]},${c[1]}`));
  return c;
}

function burst(cx: number, cy: number, color: string, now: number): Particle[] {
  const n = 6 + ~~(Math.random() * 3);
  return Array.from({ length: n }, (_, i) => {
    const a = (Math.PI * 2 * i) / n + (Math.random() - 0.5) * 0.5;
    const v = 50 + Math.random() * 70;
    return {
      x: cx * CELL + CELL / 2,
      y: cy * CELL + CELL / 2,
      vx: Math.cos(a) * v,
      vy: Math.sin(a) * v,
      born: now,
      color,
    };
  });
}

function effectiveTickMs(s: GS): number {
  let ms = BASE_TICK - s.eaten * 2 - (s.level - 1) * 2;
  ms = Math.max(ms, MIN_TICK);
  if (s.fx.some((e) => e.kind === "speed")) ms /= 1.5;
  if (s.fx.some((e) => e.kind === "slow")) ms *= 2;
  return Math.max(Math.round(ms), 25);
}

function mkState(): GS {
  const snake: Pt[] = [[12, 12]];
  const now = performance.now();
  return {
    snake,
    dir: "right",
    nextDir: "right",
    food: freeCell(snake, []),
    alive: true,
    score: 0,
    level: 1,
    eaten: 0,
    combo: 0,
    maxCombo: 0,
    lastEat: 0,
    pu: null,
    lastPuTime: now,
    fx: [],
    particles: [],
    acc: 0,
    prev: now,
  };
}

/* ── component ── */

export default function SnakeGame() {
  const cvs = useRef<HTMLCanvasElement>(null);
  const gs = useRef(mkState());
  const raf = useRef(0);
  const lastUI = useRef(0);
  const prevFxLen = useRef(0);

  const [score, setScore] = useState(0);
  const [gameOver, setGameOver] = useState(false);
  const [level, setLevel] = useState(1);
  const [combo, setCombo] = useState(0);
  const [effects, setEffects] = useState<Effect[]>([]);

  const pushUI = useCallback((s: GS) => {
    setScore(s.score);
    setLevel(s.level);
    setCombo(s.combo);
    setGameOver(!s.alive);
    if (s.fx.length > 0 || prevFxLen.current > 0) {
      setEffects(s.fx.map((e) => ({ ...e })));
      prevFxLen.current = s.fx.length;
    }
  }, []);

  const restart = useCallback(() => {
    gs.current = mkState();
    pushUI(gs.current);
  }, [pushUI]);

  /* keyboard */
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      const s = gs.current;
      if (!s.alive && e.key === " ") {
        restart();
        return;
      }
      const d = KEYS[e.key];
      if (!d) return;
      e.preventDefault();
      if (d !== OPP[s.dir]) s.nextDir = d;
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [restart]);

  /* game loop (rAF with accumulator-based ticks) */
  useEffect(() => {
    const ctx = cvs.current?.getContext("2d");
    if (!ctx) return;

    /* ── game tick ── */
    function tick(s: GS, now: number) {
      if (!s.alive) return;

      s.dir = s.nextDir;
      const [dx, dy] = DIR_VEC[s.dir];
      let nx = s.snake[0][0] + dx;
      let ny = s.snake[0][1] + dy;

      const ghostOn = s.fx.some((e) => e.kind === "ghost");

      if (nx < 0 || nx >= COLS || ny < 0 || ny >= ROWS) {
        if (ghostOn) {
          nx = ((nx % COLS) + COLS) % COLS;
          ny = ((ny % ROWS) + ROWS) % ROWS;
        } else {
          s.alive = false;
          return;
        }
      }

      if (s.snake.some(([x, y]) => x === nx && y === ny)) {
        s.alive = false;
        return;
      }

      s.snake.unshift([nx, ny]);

      /* food */
      if (nx === s.food[0] && ny === s.food[1]) {
        s.eaten++;
        s.combo =
          now - s.lastEat < COMBO_WINDOW && s.lastEat > 0
            ? Math.min(s.combo + 1, MAX_COMBO)
            : 1;
        s.maxCombo = Math.max(s.maxCombo, s.combo);
        s.lastEat = now;

        let pts = s.combo;
        if (s.fx.some((e) => e.kind === "double")) pts *= 2;
        s.score += pts;
        s.level = ~~(s.eaten / FOOD_PER_LEVEL) + 1;

        s.particles.push(...burst(nx, ny, "#ef4444", now));
        const extra: Pt[] = s.pu ? [s.pu.pos] : [];
        s.food = freeCell(s.snake, extra);
      } else {
        s.snake.pop();
      }

      if (s.lastEat > 0 && now - s.lastEat > COMBO_WINDOW) s.combo = 0;

      /* power-up pickup */
      if (s.pu && nx === s.pu.pos[0] && ny === s.pu.pos[1]) {
        const def = puDef(s.pu.kind);
        s.particles.push(...burst(nx, ny, def.color, now));
        if (def.dur > 0) {
          s.fx = s.fx.filter((e) => e.kind !== s.pu!.kind);
          s.fx.push({
            kind: def.kind,
            label: def.label,
            color: def.color,
            end: now + def.dur,
          });
        } else {
          let p = 5;
          if (s.fx.some((e) => e.kind === "double")) p *= 2;
          s.score += p;
          s.particles.push(...burst(nx, ny, "#06b6d4", now));
        }
        s.pu = null;
      }

      /* power-up lifecycle */
      if (s.pu && now - s.pu.born > PU_LIFETIME) s.pu = null;
      if (!s.pu && now - s.lastPuTime > PU_INTERVAL) {
        const def = PU_DEFS[~~(Math.random() * PU_DEFS.length)];
        s.pu = {
          kind: def.kind,
          pos: freeCell(s.snake, [s.food]),
          born: now,
        };
        s.lastPuTime = now;
      }

      s.fx = s.fx.filter((e) => now < e.end);
    }

    /* ── render ── */
    function draw(s: GS, now: number) {
      ctx.fillStyle = "#0f172a";
      ctx.fillRect(0, 0, W, H);

      /* grid */
      ctx.strokeStyle = "rgba(255,255,255,0.03)";
      ctx.lineWidth = 1;
      for (let x = 0; x <= COLS; x++) {
        ctx.beginPath();
        ctx.moveTo(x * CELL + 0.5, 0);
        ctx.lineTo(x * CELL + 0.5, H);
        ctx.stroke();
      }
      for (let y = 0; y <= ROWS; y++) {
        ctx.beginPath();
        ctx.moveTo(0, y * CELL + 0.5);
        ctx.lineTo(W, y * CELL + 0.5);
        ctx.stroke();
      }

      /* food — pulsing glow */
      const pulse = 1 + 0.18 * Math.sin(now / 180);
      const foodR = (CELL / 2 - 2) * pulse;
      const fx = s.food[0] * CELL + CELL / 2;
      const fy = s.food[1] * CELL + CELL / 2;
      ctx.save();
      ctx.shadowColor = "#ef4444";
      ctx.shadowBlur = 10 + 5 * Math.sin(now / 250);
      ctx.fillStyle = "#ef4444";
      ctx.beginPath();
      ctx.arc(fx, fy, foodR, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();

      /* power-up on map */
      if (s.pu) {
        const def = puDef(s.pu.kind);
        const px = s.pu.pos[0] * CELL + CELL / 2;
        const py = s.pu.pos[1] * CELL + CELL / 2;
        const rem = PU_LIFETIME - (now - s.pu.born);
        const blink = rem < 2000 && Math.sin(now / 80) > 0;

        if (!blink) {
          ctx.save();
          ctx.shadowColor = def.color;
          ctx.shadowBlur = 8 + 5 * Math.sin(now / 200);
          ctx.fillStyle = def.color;
          ctx.beginPath();
          ctx.arc(px, py, CELL / 2 - 1, 0, Math.PI * 2);
          ctx.fill();
          ctx.shadowBlur = 0;
          ctx.fillStyle = "#fff";
          ctx.font = "bold 9px monospace";
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          ctx.fillText(def.label, px, py + 1);
          ctx.restore();
        }
      }

      /* snake */
      const ghostOn = s.fx.some((e) => e.kind === "ghost");
      const speedOn = s.fx.some((e) => e.kind === "speed");
      const len = s.snake.length;

      for (let i = len - 1; i >= 0; i--) {
        const [sx, sy] = s.snake[i];
        const cx = sx * CELL + CELL / 2;
        const cy = sy * CELL + CELL / 2;

        if (i === 0) {
          /* head */
          ctx.save();
          if (ghostOn) {
            ctx.fillStyle = "rgba(168,85,247,0.9)";
            ctx.shadowColor = "#a855f7";
            ctx.shadowBlur = 6;
          } else if (speedOn) {
            ctx.fillStyle = "#93c5fd";
            ctx.shadowColor = "#3b82f6";
            ctx.shadowBlur = 4;
          } else {
            ctx.fillStyle = "#818cf8";
          }
          ctx.beginPath();
          ctx.arc(cx, cy, CELL / 2, 0, Math.PI * 2);
          ctx.fill();
          ctx.restore();

          /* eyes */
          const [edx, edy] = DIR_VEC[s.dir];
          ctx.fillStyle = "#0f172a";
          if (edx !== 0) {
            const ex = cx + edx * 3;
            ctx.beginPath();
            ctx.arc(ex, cy - 3.5, 2, 0, Math.PI * 2);
            ctx.fill();
            ctx.beginPath();
            ctx.arc(ex, cy + 3.5, 2, 0, Math.PI * 2);
            ctx.fill();
          } else {
            const ey = cy + edy * 3;
            ctx.beginPath();
            ctx.arc(cx - 3.5, ey, 2, 0, Math.PI * 2);
            ctx.fill();
            ctx.beginPath();
            ctx.arc(cx + 3.5, ey, 2, 0, Math.PI * 2);
            ctx.fill();
          }
          /* eye highlights */
          ctx.fillStyle = "#e0e7ff";
          if (edx !== 0) {
            const ex = cx + edx * 3;
            ctx.beginPath();
            ctx.arc(ex + 0.5, cy - 4.2, 0.7, 0, Math.PI * 2);
            ctx.fill();
            ctx.beginPath();
            ctx.arc(ex + 0.5, cy + 2.8, 0.7, 0, Math.PI * 2);
            ctx.fill();
          } else {
            const ey = cy + edy * 3;
            ctx.beginPath();
            ctx.arc(cx - 4.2, ey + 0.5, 0.7, 0, Math.PI * 2);
            ctx.fill();
            ctx.beginPath();
            ctx.arc(cx + 2.8, ey + 0.5, 0.7, 0, Math.PI * 2);
            ctx.fill();
          }
        } else {
          /* body segment */
          const t = i / Math.max(len - 1, 1);
          const alpha = Math.max(0.2, 1 - t * 0.75);
          const pad = 1 + t * 0.8;
          if (ghostOn) {
            ctx.fillStyle = `rgba(168,85,247,${alpha * 0.5})`;
          } else if (speedOn) {
            ctx.fillStyle = `rgba(147,197,253,${alpha * 0.85})`;
          } else {
            ctx.fillStyle = `rgba(99,102,241,${alpha})`;
          }
          ctx.beginPath();
          ctx.arc(cx, cy, CELL / 2 - pad, 0, Math.PI * 2);
          ctx.fill();
        }
      }

      /* particles */
      for (const p of s.particles) {
        const age = now - p.born;
        const t = 1 - age / PARTICLE_MS;
        if (t <= 0) continue;
        ctx.globalAlpha = t * t;
        ctx.fillStyle = p.color;
        const dt = age / 1000;
        const sz = 3.5 * t;
        ctx.beginPath();
        ctx.arc(p.x + p.vx * dt, p.y + p.vy * dt, sz, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.globalAlpha = 1;

      /* game over overlay */
      if (!s.alive) {
        ctx.fillStyle = "rgba(15,23,42,0.88)";
        ctx.fillRect(0, 0, W, H);
        ctx.textAlign = "center";

        ctx.fillStyle = "#ef4444";
        ctx.font = "bold 30px sans-serif";
        ctx.fillText("GAME OVER", W / 2, H / 2 - 60);

        ctx.font = "bold 20px monospace";
        ctx.fillStyle = "#e2e8f0";
        ctx.fillText(`${s.score}`, W / 2, H / 2 - 18);
        ctx.font = "12px monospace";
        ctx.fillStyle = "#64748b";
        ctx.fillText("SCORE", W / 2, H / 2 - 3);

        ctx.font = "15px monospace";
        ctx.fillStyle = "#94a3b8";
        ctx.fillText(`Level ${s.level}`, W / 2, H / 2 + 28);

        if (s.maxCombo > 1) {
          ctx.fillStyle = "#fbbf24";
          ctx.fillText(`Best Combo: ${s.maxCombo}x`, W / 2, H / 2 + 50);
        }

        ctx.fillStyle = "#6366f1";
        ctx.font = "13px sans-serif";
        ctx.fillText("Press SPACE to play again", W / 2, H / 2 + 84);
      }
    }

    /* ── frame loop ── */
    function frame() {
      const s = gs.current;
      const now = performance.now();
      const dt = now - s.prev;
      s.prev = now;

      if (s.alive) {
        s.acc += dt;
        const ms = effectiveTickMs(s);
        let ticks = 0;
        while (s.acc >= ms && s.alive && ticks < 4) {
          s.acc -= ms;
          tick(s, now);
          ticks++;
        }
        if (ticks >= 4) s.acc = 0;
      }

      s.particles = s.particles.filter((p) => now - p.born < PARTICLE_MS);
      draw(s, now);

      if (now - lastUI.current > UI_SYNC_MS || !s.alive) {
        pushUI(s);
        lastUI.current = now;
      }

      raf.current = requestAnimationFrame(frame);
    }

    raf.current = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf.current);
  }, [pushUI]);

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        maxWidth: W,
        margin: "0 auto",
      }}
    >
      {/* HUD */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          width: W,
          marginBottom: 4,
          fontSize: 13,
          fontFamily: "var(--font-mono, monospace)",
          color: "#94a3b8",
        }}
      >
        <span>
          Score:{" "}
          <b style={{ color: "#e2e8f0", fontSize: 15 }}>{score}</b>
        </span>
        <span>
          Lvl <b style={{ color: "#e2e8f0" }}>{level}</b>
        </span>
        {combo > 1 && (
          <span
            style={{
              color: combo >= 4 ? "#f97316" : "#fbbf24",
              fontWeight: 700,
              textShadow:
                combo >= 4 ? "0 0 6px rgba(249,115,22,0.5)" : "none",
            }}
          >
            {combo}x
          </span>
        )}
        {gameOver && (
          <button
            onClick={restart}
            style={{
              background: "linear-gradient(135deg,#6366f1,#8b5cf6)",
              color: "#fff",
              border: "none",
              borderRadius: 6,
              padding: "4px 14px",
              fontSize: 12,
              fontWeight: 700,
              cursor: "pointer",
            }}
          >
            Again
          </button>
        )}
      </div>

      {/* Active power-up timers */}
      {effects.length > 0 && (
        <div
          style={{
            display: "flex",
            gap: 6,
            marginBottom: 4,
            width: W,
            flexWrap: "wrap",
          }}
        >
          {effects.map((e, i) => {
            const sec = Math.max(
              0,
              Math.ceil((e.end - performance.now()) / 1000),
            );
            return (
              <span
                key={`${e.kind}-${i}`}
                style={{
                  fontSize: 11,
                  fontFamily: "var(--font-mono, monospace)",
                  color: e.color,
                  background: "rgba(255,255,255,0.05)",
                  borderRadius: 4,
                  padding: "2px 8px",
                  border: `1px solid ${e.color}44`,
                }}
              >
                {e.label} {sec}s
              </span>
            );
          })}
        </div>
      )}

      <canvas
        ref={cvs}
        width={W}
        height={H}
        style={{
          borderRadius: 8,
          border: "1px solid #334155",
          display: "block",
        }}
      />

      {!gameOver && (
        <p
          style={{
            color: "#64748b",
            fontSize: 11,
            marginTop: 6,
            fontFamily: "var(--font-mono, monospace)",
          }}
        >
          Arrow keys / WASD &middot; Catch power-ups for boosts!
        </p>
      )}

      <Leaderboard
        game="snake"
        currentScore={score}
        currentLevel={level}
        gameOver={gameOver}
      />
    </div>
  );
}
