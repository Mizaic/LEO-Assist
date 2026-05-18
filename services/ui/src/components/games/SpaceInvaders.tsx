/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2E8544FD
 *   DI: DI-C65FD45B
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2E8544FD")
 */
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Leaderboard from "./Leaderboard";

const W = 384;
const H = 384;

const SHIP_W = 28;
const SHIP_H = 14;
const SHIP_Y = H - 30;
const MOVE_SPD = 4;
const BASE_FIRE_CD = 250;

const A_ROWS = 5;
const A_COLS = 8;
const A_W = 22;
const A_H = 14;
const A_GAPX = 8;
const A_GAPY = 6;
const A_STEPX = 8;
const A_DROPY = 12;
const A_BASE_TICK = 45;

const BUL_SPD = 7;
const BUL_W = 2;
const BUL_H = 8;

const BOMB_SPD = 2.5;
const BOMB_W = 3;
const BOMB_H = 7;

const UFO_W = 30;
const UFO_H = 10;
const UFO_SPD = 1.5;
const UFO_INTERVAL = 20_000;
const UFO_Y = 20;

const PU_SZ = 14;
const PU_FALL = 1.5;
const PU_CHANCE = 0.1;
const PU_DUR = 8000;

const BG = "#0f172a";
const ROW_CLR = ["#ef4444", "#f59e0b", "#22c55e", "#3b82f6", "#a855f7"];
const ROW_PTS = [10, 20, 30, 40, 50];
const STAR_N = 80;

type PUKind = "T" | "R" | "S" | "B" | "L";
const PU_CLR: Record<PUKind, string> = {
  T: "#ef4444",
  R: "#3b82f6",
  S: "#22c55e",
  B: "#eab308",
  L: "#a855f7",
};
const PU_LBL: Record<PUKind, string> = {
  T: "TRIPLE",
  R: "RAPID",
  S: "SHIELD",
  B: "BOMB",
  L: "+LIFE",
};
const PU_ALL: PUKind[] = ["T", "R", "S", "B", "L"];

interface Bul {
  x: number;
  y: number;
  dx: number;
}
interface Bmb {
  x: number;
  y: number;
}
interface Al {
  x: number;
  y: number;
  alive: boolean;
  row: number;
  col: number;
}
interface UFOState {
  on: boolean;
  x: number;
  dir: number;
  pts: number;
  trail: number[];
}
interface FallingPU {
  x: number;
  y: number;
  t: PUKind;
  age: number;
}
interface ActivePU {
  t: PUKind;
  until: number;
}
interface Part {
  x: number;
  y: number;
  vx: number;
  vy: number;
  life: number;
  max: number;
  clr: string;
  r: number;
}
interface Star {
  x: number;
  y: number;
  spd: number;
  r: number;
  b: number;
}
interface Popup {
  x: number;
  y: number;
  txt: string;
  life: number;
  clr: string;
}

interface GState {
  px: number;
  lives: number;
  score: number;
  level: number;
  killed: number;
  buls: Bul[];
  bombs: Bmb[];
  aliens: Al[];
  aDir: number;
  aTick: number;
  ufo: UFOState;
  ufoTimer: number;
  fpu: FallingPU[];
  apu: ActivePU[];
  shield: boolean;
  parts: Part[];
  stars: Star[];
  popups: Popup[];
  shakeEnd: number;
  keys: Set<string>;
  alive: boolean;
  lastShot: number;
  frame: number;
  invuln: number;
}

function mkAliens(level: number): Al[] {
  const out: Al[] = [];
  const gridW = A_COLS * (A_W + A_GAPX) - A_GAPX;
  const ox = (W - gridW) / 2;
  const extraY = Math.min((level - 1) * A_DROPY, 80);
  for (let r = 0; r < A_ROWS; r++) {
    for (let c = 0; c < A_COLS; c++) {
      out.push({
        x: ox + c * (A_W + A_GAPX),
        y: 36 + r * (A_H + A_GAPY) + extraY,
        alive: true,
        row: r,
        col: c,
      });
    }
  }
  return out;
}

function mkStars(): Star[] {
  return Array.from({ length: STAR_N }, () => ({
    x: Math.random() * W,
    y: Math.random() * H,
    spd: 0.15 + Math.random() * 0.4,
    r: 0.4 + Math.random() * 1,
    b: 0.25 + Math.random() * 0.75,
  }));
}

function rnd(a: number, b: number) {
  return a + Math.random() * (b - a);
}
function rndI(a: number, b: number) {
  return Math.floor(rnd(a, b + 1));
}
function hitTest(
  ax: number,
  ay: number,
  aw: number,
  ah: number,
  bx: number,
  by: number,
  bw: number,
  bh: number,
) {
  return ax < bx + bw && ax + aw > bx && ay < by + bh && ay + ah > by;
}

function mkState(): GState {
  return {
    px: W / 2 - SHIP_W / 2,
    lives: 3,
    score: 0,
    level: 1,
    killed: 0,
    buls: [],
    bombs: [],
    aliens: mkAliens(1),
    aDir: 1,
    aTick: 0,
    ufo: { on: false, x: 0, dir: 1, pts: 0, trail: [] },
    ufoTimer: 0,
    fpu: [],
    apu: [],
    shield: false,
    parts: [],
    stars: mkStars(),
    popups: [],
    shakeEnd: 0,
    keys: new Set(),
    alive: true,
    lastShot: 0,
    frame: 0,
    invuln: 0,
  };
}

export default function SpaceInvaders() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [score, setScore] = useState(0);
  const [gameOver, setGameOver] = useState(false);
  const [level, setLevel] = useState(1);
  const [lives, setLives] = useState(3);
  const [killed, setKilled] = useState(0);

  const gs = useRef<GState>(mkState());

  const reset = useCallback(() => {
    Object.assign(gs.current, mkState());
    setScore(0);
    setGameOver(false);
    setLevel(1);
    setLives(3);
    setKilled(0);
  }, []);

  /* ── Keyboard ── */
  useEffect(() => {
    const dn = (e: KeyboardEvent) => {
      const k = e.key;
      if (
        ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", " "].includes(k)
      )
        e.preventDefault();
      gs.current.keys.add(k);
      if (k === " " && !gs.current.alive) reset();
    };
    const up = (e: KeyboardEvent) => gs.current.keys.delete(e.key);
    window.addEventListener("keydown", dn);
    window.addEventListener("keyup", up);
    return () => {
      window.removeEventListener("keydown", dn);
      window.removeEventListener("keyup", up);
    };
  }, [reset]);

  /* ── Game loop ── */
  useEffect(() => {
    const cvs = canvasRef.current;
    if (!cvs) return;
    const ctx = cvs.getContext("2d")!;

    /* ════════════════════ DRAW ════════════════════ */
    function draw(s: GState, now: number) {
      ctx.fillStyle = BG;
      ctx.fillRect(0, 0, W, H);

      ctx.save();

      if (s.shakeEnd > now) {
        ctx.translate(rnd(-4, 4), rnd(-4, 4));
      }

      /* Stars */
      for (const st of s.stars) {
        ctx.globalAlpha = st.b;
        ctx.fillStyle = "#e2e8f0";
        ctx.beginPath();
        ctx.arc(st.x, st.y, st.r, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.globalAlpha = 1;

      /* UFO */
      if (s.ufo.on) {
        for (let i = 0; i < s.ufo.trail.length; i++) {
          ctx.globalAlpha = (i / s.ufo.trail.length) * 0.2;
          ctx.fillStyle = "#ef4444";
          ctx.beginPath();
          ctx.ellipse(
            s.ufo.trail[i] + UFO_W / 2,
            UFO_Y + UFO_H / 2,
            UFO_W / 2,
            UFO_H / 2,
            0,
            0,
            Math.PI * 2,
          );
          ctx.fill();
        }
        ctx.globalAlpha = 1;
        ctx.fillStyle = "#ef4444";
        ctx.beginPath();
        ctx.ellipse(
          s.ufo.x + UFO_W / 2,
          UFO_Y + UFO_H / 2,
          UFO_W / 2,
          UFO_H / 2,
          0,
          0,
          Math.PI * 2,
        );
        ctx.fill();
        ctx.fillStyle = "#fca5a5";
        ctx.beginPath();
        ctx.ellipse(s.ufo.x + UFO_W / 2, UFO_Y + 2, 7, 4, 0, Math.PI, 0);
        ctx.fill();
        ctx.fillStyle = "#fbbf24";
        ctx.font = "bold 8px monospace";
        ctx.textAlign = "center";
        ctx.textBaseline = "bottom";
        ctx.fillText(`${s.ufo.pts}`, s.ufo.x + UFO_W / 2, UFO_Y - 1);
      }

      /* Aliens */
      for (const a of s.aliens) {
        if (!a.alive) continue;
        const clr = ROW_CLR[a.row];
        const f = s.frame;
        ctx.fillStyle = clr;

        if (a.row <= 1) {
          ctx.fillRect(a.x + 4, a.y, A_W - 8, A_H);
          ctx.fillRect(a.x, a.y + 3, A_W, A_H - 6);
          ctx.fillStyle = BG;
          ctx.fillRect(a.x + 5, a.y + 4, 3, 3);
          ctx.fillRect(a.x + A_W - 8, a.y + 4, 3, 3);
          ctx.fillStyle = clr;
          if (f % 30 < 15) {
            ctx.fillRect(a.x, a.y + A_H - 2, 3, 3);
            ctx.fillRect(a.x + A_W - 3, a.y + A_H - 2, 3, 3);
          } else {
            ctx.fillRect(a.x + 2, a.y + A_H, 3, 2);
            ctx.fillRect(a.x + A_W - 5, a.y + A_H, 3, 2);
          }
        } else if (a.row === 2) {
          ctx.fillRect(a.x + 2, a.y + 2, A_W - 4, A_H - 4);
          ctx.fillRect(a.x + 6, a.y, A_W - 12, A_H);
          ctx.fillStyle = BG;
          ctx.fillRect(a.x + 6, a.y + 4, 3, 4);
          ctx.fillRect(a.x + A_W - 9, a.y + 4, 3, 4);
          ctx.fillStyle = clr;
          const cp = f % 30 < 15 ? -1 : 1;
          ctx.fillRect(a.x - 1 + cp, a.y + 4, 3, 3);
          ctx.fillRect(a.x + A_W - 2 - cp, a.y + 4, 3, 3);
        } else {
          ctx.fillRect(a.x + 2, a.y, A_W - 4, A_H);
          ctx.fillRect(a.x, a.y + 2, A_W, A_H - 4);
          ctx.fillStyle = BG;
          ctx.fillRect(a.x + 4, a.y + 3, 4, 4);
          ctx.fillRect(a.x + A_W - 8, a.y + 3, 4, 4);
          ctx.fillStyle = "#fff";
          ctx.fillRect(a.x + 5, a.y + 4, 2, 2);
          ctx.fillRect(a.x + A_W - 7, a.y + 4, 2, 2);
        }
      }

      /* Alien bombs */
      for (const b of s.bombs) {
        ctx.fillStyle = "#f87171";
        const zig = (s.frame + Math.floor(b.y)) % 6 < 3 ? -1 : 1;
        ctx.fillRect(b.x - BOMB_W / 2, b.y, BOMB_W, BOMB_H);
        ctx.fillRect(b.x - BOMB_W / 2 + zig, b.y + 2, BOMB_W, 3);
        ctx.globalAlpha = 0.25;
        ctx.beginPath();
        ctx.arc(b.x, b.y + BOMB_H, 3, 0, Math.PI * 2);
        ctx.fill();
        ctx.globalAlpha = 1;
      }

      /* Player bullets */
      for (const b of s.buls) {
        ctx.fillStyle = "#fbbf24";
        ctx.fillRect(b.x - BUL_W / 2, b.y - BUL_H / 2, BUL_W, BUL_H);
        ctx.globalAlpha = 0.35;
        ctx.fillRect(b.x - BUL_W, b.y, BUL_W * 2, 4);
        ctx.globalAlpha = 1;
      }

      /* Falling power-ups */
      for (const p of s.fpu) {
        const pulse = 0.6 + Math.sin(p.age * 0.12) * 0.4;
        const c = PU_CLR[p.t];
        ctx.globalAlpha = 0.15 * pulse;
        ctx.fillStyle = c;
        ctx.beginPath();
        ctx.arc(p.x + PU_SZ / 2, p.y + PU_SZ / 2, PU_SZ, 0, Math.PI * 2);
        ctx.fill();
        ctx.globalAlpha = 0.85 + pulse * 0.15;
        ctx.fillStyle = c;
        ctx.beginPath();
        ctx.arc(
          p.x + PU_SZ / 2,
          p.y + PU_SZ / 2,
          PU_SZ / 2,
          0,
          Math.PI * 2,
        );
        ctx.fill();
        ctx.globalAlpha = 1;
        ctx.fillStyle = "#fff";
        ctx.font = "bold 9px monospace";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(p.t, p.x + PU_SZ / 2, p.y + PU_SZ / 2 + 1);
      }

      /* Player ship */
      if (s.alive) {
        const blink = s.invuln > now && s.frame % 8 < 4;
        if (!blink) {
          const px = s.px;
          const py = SHIP_Y;

          const fl = 4 + Math.sin(s.frame * 0.5) * 2;
          const jitter = s.frame % 3;
          ctx.fillStyle = "#f97316";
          ctx.beginPath();
          ctx.moveTo(px + SHIP_W / 2 - 5, py + SHIP_H);
          ctx.lineTo(px + SHIP_W / 2, py + SHIP_H + fl + jitter);
          ctx.lineTo(px + SHIP_W / 2 + 5, py + SHIP_H);
          ctx.fill();
          ctx.fillStyle = "#fbbf24";
          ctx.beginPath();
          ctx.moveTo(px + SHIP_W / 2 - 2, py + SHIP_H);
          ctx.lineTo(px + SHIP_W / 2, py + SHIP_H + fl * 0.55);
          ctx.lineTo(px + SHIP_W / 2 + 2, py + SHIP_H);
          ctx.fill();

          ctx.fillStyle = "#38bdf8";
          ctx.beginPath();
          ctx.moveTo(px, py + SHIP_H);
          ctx.lineTo(px + 3, py + 4);
          ctx.lineTo(px + SHIP_W / 2, py);
          ctx.lineTo(px + SHIP_W - 3, py + 4);
          ctx.lineTo(px + SHIP_W, py + SHIP_H);
          ctx.closePath();
          ctx.fill();

          ctx.fillStyle = "#7dd3fc";
          ctx.fillRect(px + 4, py + 7, 5, 2);
          ctx.fillRect(px + SHIP_W - 9, py + 7, 5, 2);

          ctx.fillStyle = "#bae6fd";
          ctx.beginPath();
          ctx.arc(px + SHIP_W / 2, py + 5, 3, 0, Math.PI * 2);
          ctx.fill();

          if (s.shield) {
            ctx.strokeStyle = "#22c55e";
            ctx.lineWidth = 1.5;
            ctx.globalAlpha = 0.35 + Math.sin(s.frame * 0.08) * 0.2;
            ctx.beginPath();
            ctx.arc(
              px + SHIP_W / 2,
              py + SHIP_H / 2,
              SHIP_W * 0.78,
              0,
              Math.PI * 2,
            );
            ctx.stroke();
            ctx.globalAlpha = 0.07;
            ctx.fillStyle = "#22c55e";
            ctx.fill();
            ctx.globalAlpha = 1;
            ctx.lineWidth = 1;
          }
        }
      }

      /* Particles */
      for (const p of s.parts) {
        ctx.globalAlpha = Math.max(0, p.life / p.max);
        ctx.fillStyle = p.clr;
        ctx.beginPath();
        ctx.arc(p.x, p.y, Math.max(0.2, p.r * (p.life / p.max)), 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.globalAlpha = 1;

      /* Score popups */
      for (const p of s.popups) {
        ctx.globalAlpha = Math.max(0, p.life / 35);
        ctx.fillStyle = p.clr;
        ctx.font = "bold 10px monospace";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(p.txt, p.x, p.y);
      }
      ctx.globalAlpha = 1;

      ctx.restore();

      /* ── HUD (unaffected by shake) ── */
      ctx.textBaseline = "top";
      ctx.font = "bold 11px monospace";

      ctx.fillStyle = "#e2e8f0";
      ctx.textAlign = "left";
      ctx.fillText(`SCORE ${s.score}`, 8, 5);

      ctx.textAlign = "center";
      ctx.fillStyle = "#94a3b8";
      ctx.fillText(`LV ${s.level}`, W / 2, 5);

      for (let i = 0; i < s.lives; i++) {
        const lx = W - 14 - i * 16;
        const ly = 5;
        ctx.fillStyle = "#38bdf8";
        ctx.beginPath();
        ctx.moveTo(lx - 5, ly + 9);
        ctx.lineTo(lx - 2, ly + 3);
        ctx.lineTo(lx, ly);
        ctx.lineTo(lx + 2, ly + 3);
        ctx.lineTo(lx + 5, ly + 9);
        ctx.closePath();
        ctx.fill();
      }

      /* Active power-up bar */
      if (s.apu.length > 0) {
        ctx.font = "bold 7px monospace";
        ctx.textAlign = "left";
        ctx.textBaseline = "top";
        let bx = 8;
        for (const ap of s.apu) {
          const rem =
            ap.t === "S" ? Infinity : Math.max(0, ap.until - now);
          const label =
            ap.t === "S" ? "ON" : `${Math.ceil(rem / 1000)}s`;
          const c = PU_CLR[ap.t];
          const barW = 44;

          ctx.fillStyle = c;
          ctx.globalAlpha = 0.2;
          ctx.fillRect(bx, 18, barW, 11);

          if (ap.t !== "S") {
            const pct = Math.min(1, rem / PU_DUR);
            ctx.globalAlpha = 0.45;
            ctx.fillRect(bx, 18, barW * pct, 11);
          } else {
            ctx.globalAlpha = 0.35;
            ctx.fillRect(bx, 18, barW, 11);
          }

          ctx.globalAlpha = 1;
          ctx.fillStyle = "#fff";
          ctx.fillText(`${PU_LBL[ap.t]} ${label}`, bx + 3, 20);
          bx += barW + 4;
        }
        ctx.globalAlpha = 1;
      }

      /* Game over overlay */
      if (!s.alive) {
        ctx.fillStyle = "rgba(15, 23, 42, 0.82)";
        ctx.fillRect(0, 0, W, H);

        ctx.textAlign = "center";
        ctx.textBaseline = "middle";

        ctx.fillStyle = "#ef4444";
        ctx.font = "bold 30px monospace";
        ctx.fillText("GAME OVER", W / 2, H / 2 - 55);

        ctx.fillStyle = "#e2e8f0";
        ctx.font = "bold 18px monospace";
        ctx.fillText(`Score: ${s.score}`, W / 2, H / 2 - 15);

        ctx.fillStyle = "#94a3b8";
        ctx.font = "14px monospace";
        ctx.fillText(
          `Level ${s.level}  \u00b7  ${s.killed} aliens`,
          W / 2,
          H / 2 + 15,
        );

        ctx.fillStyle = "#64748b";
        ctx.font = "11px monospace";
        ctx.fillText("Press SPACE or click Play Again", W / 2, H / 2 + 50);
      }
    }

    /* ════════════════════ TICK ════════════════════ */
    const tick = () => {
      const s = gs.current;
      const now = Date.now();
      s.frame++;

      /* Stars scroll always */
      for (const st of s.stars) {
        st.y += st.spd;
        if (st.y > H) {
          st.y = 0;
          st.x = Math.random() * W;
        }
      }

      /* Particles update always (death explosions keep going) */
      for (let i = s.parts.length - 1; i >= 0; i--) {
        const p = s.parts[i];
        p.x += p.vx;
        p.y += p.vy;
        p.vy += 0.04;
        p.life--;
        if (p.life <= 0) s.parts.splice(i, 1);
      }

      /* Score popups float up */
      for (let i = s.popups.length - 1; i >= 0; i--) {
        s.popups[i].y -= 0.6;
        s.popups[i].life--;
        if (s.popups[i].life <= 0) s.popups.splice(i, 1);
      }

      if (!s.alive) {
        draw(s, now);
        return;
      }

      /* ── Player movement ── */
      if (s.keys.has("ArrowLeft")) s.px = Math.max(0, s.px - MOVE_SPD);
      if (s.keys.has("ArrowRight"))
        s.px = Math.min(W - SHIP_W, s.px + MOVE_SPD);

      /* ── Shooting ── */
      const rapid = s.apu.some((p) => p.t === "R" && p.until > now);
      const triple = s.apu.some((p) => p.t === "T" && p.until > now);
      const cd = rapid ? Math.floor(BASE_FIRE_CD / 3) : BASE_FIRE_CD;
      if (s.keys.has(" ") && now - s.lastShot >= cd) {
        const cx = s.px + SHIP_W / 2;
        const by = SHIP_Y - 2;
        s.buls.push({ x: cx, y: by, dx: 0 });
        if (triple) {
          s.buls.push({ x: cx - 6, y: by + 2, dx: -1.5 });
          s.buls.push({ x: cx + 6, y: by + 2, dx: 1.5 });
        }
        s.lastShot = now;
      }

      /* ── Move bullets ── */
      for (let i = s.buls.length - 1; i >= 0; i--) {
        const b = s.buls[i];
        b.x += b.dx;
        b.y -= BUL_SPD;
        if (b.y < -10 || b.x < -10 || b.x > W + 10) s.buls.splice(i, 1);
      }

      /* ── Alien movement ── */
      const live = s.aliens.filter((a) => a.alive);
      const aliveN = live.length;
      const total = A_ROWS * A_COLS;
      const speedUp = 1 + (s.level - 1) * 0.18;
      const interval = Math.max(
        3,
        Math.floor((aliveN / total) * A_BASE_TICK / speedUp),
      );

      s.aTick++;
      if (aliveN > 0 && s.aTick >= interval) {
        s.aTick = 0;
        const minX = Math.min(...live.map((a) => a.x));
        const maxX = Math.max(...live.map((a) => a.x + A_W));
        if (
          (s.aDir > 0 && maxX + A_STEPX > W - 2) ||
          (s.aDir < 0 && minX - A_STEPX < 2)
        ) {
          s.aDir *= -1;
          for (const a of s.aliens) if (a.alive) a.y += A_DROPY;
        } else {
          for (const a of s.aliens) if (a.alive) a.x += s.aDir * A_STEPX;
        }
      }

      /* ── Alien bombs ── */
      const bombRate = 0.008 + s.level * 0.003;
      const maxBombs = 3 + s.level;
      if (
        s.bombs.length < maxBombs &&
        Math.random() < bombRate &&
        aliveN > 0
      ) {
        const bottomPerCol = new Map<number, Al>();
        for (const a of s.aliens) {
          if (!a.alive) continue;
          const prev = bottomPerCol.get(a.col);
          if (!prev || a.y > prev.y) bottomPerCol.set(a.col, a);
        }
        const bottoms = [...bottomPerCol.values()];
        if (bottoms.length > 0) {
          const src = bottoms[rndI(0, bottoms.length - 1)];
          s.bombs.push({ x: src.x + A_W / 2, y: src.y + A_H });
        }
      }

      /* Move bombs */
      const bombSpd = BOMB_SPD + s.level * 0.15;
      for (let i = s.bombs.length - 1; i >= 0; i--) {
        s.bombs[i].y += bombSpd;
        if (s.bombs[i].y > H + 10) s.bombs.splice(i, 1);
      }

      /* ── UFO ── */
      s.ufoTimer += 1000 / 60;
      if (!s.ufo.on && s.ufoTimer >= UFO_INTERVAL) {
        const dir = Math.random() < 0.5 ? 1 : -1;
        s.ufo = {
          on: true,
          x: dir > 0 ? -UFO_W : W,
          dir,
          pts: [100, 150, 200, 250, 300][rndI(0, 4)],
          trail: [],
        };
        s.ufoTimer = 0;
      }
      if (s.ufo.on) {
        s.ufo.trail.push(s.ufo.x);
        if (s.ufo.trail.length > 18) s.ufo.trail.shift();
        s.ufo.x += s.ufo.dir * UFO_SPD;
        if (s.ufo.x < -UFO_W - 20 || s.ufo.x > W + 20) s.ufo.on = false;
      }

      /* ── Move falling power-ups ── */
      for (let i = s.fpu.length - 1; i >= 0; i--) {
        s.fpu[i].y += PU_FALL;
        s.fpu[i].age++;
        if (s.fpu[i].y > H + 10) s.fpu.splice(i, 1);
      }

      /* ── Bullet vs alien ── */
      outer: for (let bi = s.buls.length - 1; bi >= 0; bi--) {
        const b = s.buls[bi];
        for (const a of s.aliens) {
          if (!a.alive) continue;
          if (
            hitTest(
              b.x - BUL_W / 2,
              b.y - BUL_H / 2,
              BUL_W,
              BUL_H,
              a.x,
              a.y,
              A_W,
              A_H,
            )
          ) {
            a.alive = false;
            s.buls.splice(bi, 1);
            const pts = ROW_PTS[a.row];
            s.score += pts;
            s.killed++;

            const clr = ROW_CLR[a.row];
            const n = rndI(8, 12);
            for (let i = 0; i < n; i++) {
              const ang = (Math.PI * 2 * i) / n + rnd(-0.4, 0.4);
              const spd = rnd(0.8, 3);
              s.parts.push({
                x: a.x + A_W / 2,
                y: a.y + A_H / 2,
                vx: Math.cos(ang) * spd,
                vy: Math.sin(ang) * spd,
                life: rndI(20, 40),
                max: 40,
                clr,
                r: rnd(1, 3),
              });
            }

            s.popups.push({
              x: a.x + A_W / 2,
              y: a.y,
              txt: `+${pts}`,
              life: 35,
              clr,
            });

            if (Math.random() < PU_CHANCE) {
              s.fpu.push({
                x: a.x + A_W / 2 - PU_SZ / 2,
                y: a.y,
                t: PU_ALL[rndI(0, 4)],
                age: 0,
              });
            }
            continue outer;
          }
        }
      }

      /* ── Bullet vs UFO ── */
      if (s.ufo.on) {
        for (let bi = s.buls.length - 1; bi >= 0; bi--) {
          const b = s.buls[bi];
          if (
            hitTest(
              b.x - BUL_W / 2,
              b.y - BUL_H / 2,
              BUL_W,
              BUL_H,
              s.ufo.x,
              UFO_Y,
              UFO_W,
              UFO_H,
            )
          ) {
            const pts = s.ufo.pts;
            s.score += pts;
            s.buls.splice(bi, 1);

            for (let i = 0; i < 15; i++) {
              const ang = rnd(0, Math.PI * 2);
              const spd = rnd(1.5, 4);
              s.parts.push({
                x: s.ufo.x + UFO_W / 2,
                y: UFO_Y + UFO_H / 2,
                vx: Math.cos(ang) * spd,
                vy: Math.sin(ang) * spd,
                life: rndI(25, 45),
                max: 45,
                clr: "#ef4444",
                r: rnd(1.5, 3.5),
              });
            }

            s.popups.push({
              x: s.ufo.x + UFO_W / 2,
              y: UFO_Y,
              txt: `+${pts}`,
              life: 40,
              clr: "#fbbf24",
            });

            s.ufo.on = false;
            break;
          }
        }
      }

      /* ── Bomb vs player ── */
      if (now > s.invuln) {
        for (let i = s.bombs.length - 1; i >= 0; i--) {
          const b = s.bombs[i];
          if (
            hitTest(
              b.x - BOMB_W / 2,
              b.y,
              BOMB_W,
              BOMB_H,
              s.px,
              SHIP_Y,
              SHIP_W,
              SHIP_H,
            )
          ) {
            s.bombs.splice(i, 1);
            if (s.shield) {
              s.shield = false;
              s.apu = s.apu.filter((p) => p.t !== "S");
              for (let j = 0; j < 12; j++) {
                const ang = rnd(0, Math.PI * 2);
                s.parts.push({
                  x: s.px + SHIP_W / 2,
                  y: SHIP_Y + SHIP_H / 2,
                  vx: Math.cos(ang) * rnd(1, 2.5),
                  vy: Math.sin(ang) * rnd(1, 2.5),
                  life: 25,
                  max: 25,
                  clr: "#22c55e",
                  r: 2,
                });
              }
            } else {
              s.lives--;
              s.invuln = now + 2000;
              s.shakeEnd = now + 300;
              setLives(s.lives);
              if (s.lives <= 0) {
                s.alive = false;
                for (let j = 0; j < 24; j++) {
                  const ang = rnd(0, Math.PI * 2);
                  const spd = rnd(1, 4.5);
                  s.parts.push({
                    x: s.px + SHIP_W / 2,
                    y: SHIP_Y + SHIP_H / 2,
                    vx: Math.cos(ang) * spd,
                    vy: Math.sin(ang) * spd,
                    life: rndI(30, 60),
                    max: 60,
                    clr: "#38bdf8",
                    r: rnd(1.5, 4),
                  });
                }
                setScore(s.score);
                setGameOver(true);
                setKilled(s.killed);
                setLevel(s.level);
                draw(s, now);
                return;
              }
            }
            break;
          }
        }
      }

      /* ── Aliens reach player ── */
      if (s.aliens.some((a) => a.alive && a.y + A_H >= SHIP_Y - 2)) {
        s.alive = false;
        setScore(s.score);
        setGameOver(true);
        setKilled(s.killed);
        setLevel(s.level);
        draw(s, now);
        return;
      }

      /* ── Player catches power-up ── */
      for (let i = s.fpu.length - 1; i >= 0; i--) {
        const p = s.fpu[i];
        if (
          hitTest(
            p.x,
            p.y,
            PU_SZ,
            PU_SZ,
            s.px - 3,
            SHIP_Y - 3,
            SHIP_W + 6,
            SHIP_H + 6,
          )
        ) {
          s.fpu.splice(i, 1);
          switch (p.t) {
            case "T":
            case "R": {
              const idx = s.apu.findIndex((a) => a.t === p.t);
              if (idx >= 0) s.apu[idx].until = now + PU_DUR;
              else s.apu.push({ t: p.t, until: now + PU_DUR });
              break;
            }
            case "S":
              s.shield = true;
              if (!s.apu.some((a) => a.t === "S"))
                s.apu.push({ t: "S", until: now + 999_999_999 });
              break;
            case "B": {
              let bonus = 0;
              for (const a of s.aliens) {
                if (!a.alive) continue;
                a.alive = false;
                bonus += ROW_PTS[a.row];
                s.killed++;
                const clr = ROW_CLR[a.row];
                for (let j = 0; j < 5; j++) {
                  const ang = rnd(0, Math.PI * 2);
                  s.parts.push({
                    x: a.x + A_W / 2,
                    y: a.y + A_H / 2,
                    vx: Math.cos(ang) * rnd(0.5, 2),
                    vy: Math.sin(ang) * rnd(0.5, 2),
                    life: rndI(15, 30),
                    max: 30,
                    clr,
                    r: rnd(1, 2.5),
                  });
                }
              }
              s.score += bonus;
              s.shakeEnd = now + 250;
              if (bonus > 0) {
                s.popups.push({
                  x: W / 2,
                  y: H / 2,
                  txt: `BOOM +${bonus}`,
                  life: 50,
                  clr: "#eab308",
                });
              }
              break;
            }
            case "L":
              s.lives = Math.min(s.lives + 1, 9);
              setLives(s.lives);
              s.popups.push({
                x: s.px + SHIP_W / 2,
                y: SHIP_Y - 10,
                txt: "+1 UP",
                life: 40,
                clr: "#a855f7",
              });
              break;
          }
        }
      }

      /* ── All aliens dead → next level ── */
      if (!s.aliens.some((a) => a.alive)) {
        s.level++;
        s.aliens = mkAliens(s.level);
        s.aDir = 1;
        s.aTick = 0;
        s.bombs = [];
        setLevel(s.level);
      }

      /* ── Expire timed power-ups ── */
      s.apu = s.apu.filter((p) => {
        if (p.t === "S") return s.shield;
        return p.until > now;
      });

      /* ── Sync display state ── */
      setScore(s.score);
      setKilled(s.killed);

      draw(s, now);
    };

    const id = setInterval(tick, 1000 / 60);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 8,
      }}
    >
      <canvas
        ref={canvasRef}
        width={W}
        height={H}
        style={{ borderRadius: 8, border: "1px solid #334155" }}
        tabIndex={0}
      />
      {gameOver ? (
        <button
          type="button"
          aria-label="Play again"
          onClick={reset}
          style={{
            background: "linear-gradient(135deg, #6366f1, #8b5cf6)",
            color: "#fff",
            border: "none",
            borderRadius: 8,
            padding: "8px 24px",
            fontSize: 14,
            fontWeight: 700,
            cursor: "pointer",
            letterSpacing: 0.5,
          }}
        >
          Play Again
        </button>
      ) : (
        <p style={{ color: "#64748b", fontSize: 12, margin: 0 }}>
          Arrow keys to move &middot; Space to shoot
        </p>
      )}
      <Leaderboard
        game="invaders"
        currentScore={score}
        currentLevel={level}
        gameOver={gameOver}
      />
    </div>
  );
}
