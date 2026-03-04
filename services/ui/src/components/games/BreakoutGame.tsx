"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Leaderboard from "./Leaderboard";

/* ── Canvas & Layout ────────────────────────────────────── */
const W = 384;
const H = 384;
const PADDLE_H = 10;
const PADDLE_Y = H - 24;
const PW_DEF = 64;
const PW_WIDE = 100;
const BALL_R = 5;
const BRICK_ROWS = 6;
const BRICK_COLS = 8;
const BRICK_GAP = 3;
const BRICK_W = 44;
const BRICK_H = 14;
const BRICK_OX =
  (W - (BRICK_COLS * BRICK_W + (BRICK_COLS - 1) * BRICK_GAP)) / 2;
const BRICK_OY = 44;

/* ── Tuning ─────────────────────────────────────────────── */
const PAD_SPD = 6;
const BASE_SPEED = 4;
const SPEED_INC = 0.3;
const MAX_SPEED = 8;
const PU_CHANCE = 0.15;
const PU_FALL = 1.8;
const LASER_SPD = 7;
const TRAIL_LEN = 4;

/* ── Row palette (top→bottom) ───────────────────────────── */
const ROW_CLR = [
  "#a855f7",
  "#6366f1",
  "#3b82f6",
  "#22c55e",
  "#eab308",
  "#ef4444",
];
const ROW_PTS = [60, 50, 40, 30, 20, 10];

/* ── Power-ups ──────────────────────────────────────────── */
type PU = "W" | "M" | "L" | "S" | "+" | "F";
const PU_ALL: PU[] = ["W", "M", "L", "S", "+", "F"];
const PU_CLR: Record<PU, string> = {
  W: "#ef4444",
  M: "#3b82f6",
  L: "#22c55e",
  S: "#eab308",
  "+": "#a855f7",
  F: "#f59e0b",
};
const PU_TAG: Record<PU, string> = {
  W: "WIDE",
  M: "MULTI",
  L: "LASER",
  S: "STICK",
  "+": "LIFE",
  F: "FIRE",
};
const PU_MS: Partial<Record<PU, number>> = {
  W: 10_000,
  L: 8_000,
  S: 10_000,
  F: 5_000,
};

/* ── Types ──────────────────────────────────────────────── */
interface Brick {
  x: number;
  y: number;
  alive: boolean;
  row: number;
  hp: number;
  maxHp: number;
  color: string;
  pts: number;
  gold: boolean;
}
interface Ball {
  x: number;
  y: number;
  vx: number;
  vy: number;
  trail: { x: number; y: number }[];
  stuck: boolean;
  off: number;
}
interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  t: number;
  maxT: number;
  color: string;
  sz: number;
}
interface Drop {
  x: number;
  y: number;
  type: PU;
  rot: number;
}
interface APU {
  type: PU;
  end: number;
}
interface Laser {
  x: number;
  y: number;
}
interface GS {
  px: number;
  pw: number;
  balls: Ball[];
  bricks: Brick[];
  parts: Particle[];
  drops: Drop[];
  apus: APU[];
  lasers: Laser[];
  lives: number;
  lvl: number;
  score: number;
  destroyed: number;
  over: boolean;
  launched: boolean;
  flash: number;
  lvlFlash: number;
  keys: Set<string>;
  spaceQ: boolean;
  sticky: boolean;
  fire: boolean;
  laserOn: boolean;
  laserCD: number;
}

/* ── Helpers ────────────────────────────────────────────── */

function buildBricks(lvl: number): Brick[] {
  const out: Brick[] = [];
  const p2 = Math.min(0.08 + lvl * 0.07, 0.55);
  const pg = lvl >= 3 ? Math.min((lvl - 2) * 0.04, 0.12) : 0;
  for (let r = 0; r < BRICK_ROWS; r++) {
    for (let c = 0; c < BRICK_COLS; c++) {
      const isGold = Math.random() < pg;
      const is2 = !isGold && Math.random() < p2;
      out.push({
        x: BRICK_OX + c * (BRICK_W + BRICK_GAP),
        y: BRICK_OY + r * (BRICK_H + BRICK_GAP),
        alive: true,
        row: r,
        hp: 0,
        maxHp: isGold ? Infinity : is2 ? 2 : 1,
        color: isGold ? "#c9a227" : ROW_CLR[r],
        pts: isGold ? 0 : ROW_PTS[r],
        gold: isGold,
      });
    }
  }
  return out;
}

function mkBall(px: number, pw: number): Ball {
  return {
    x: px + pw / 2,
    y: PADDLE_Y - BALL_R,
    vx: 0,
    vy: 0,
    trail: [],
    stuck: true,
    off: pw / 2,
  };
}

function launchBall(b: Ball, s: GS) {
  const spd = Math.min(BASE_SPEED + (s.lvl - 1) * SPEED_INC, MAX_SPEED);
  const hitNorm = (b.x - s.px - s.pw / 2) / (s.pw / 2);
  const clamped = Math.max(-0.8, Math.min(0.8, hitNorm));
  const jitter = (Math.random() - 0.5) * 0.15;
  const ang = (clamped + jitter) * (Math.PI / 3);
  b.vx = spd * Math.sin(ang);
  b.vy = -spd * Math.cos(ang);
  b.stuck = false;
}

function burst(x: number, y: number, color: string): Particle[] {
  const n = 4 + Math.floor(Math.random() * 3);
  return Array.from({ length: n }, (_, i) => {
    const a = (Math.PI * 2 * i) / n + Math.random() * 0.5;
    const v = 1.5 + Math.random() * 2;
    const life = 22 + Math.random() * 15;
    return {
      x,
      y,
      vx: Math.cos(a) * v,
      vy: Math.sin(a) * v,
      t: life,
      maxT: life,
      color,
      sz: 2 + Math.random() * 2,
    };
  });
}

function init(): GS {
  const px = W / 2 - PW_DEF / 2;
  return {
    px,
    pw: PW_DEF,
    balls: [mkBall(px, PW_DEF)],
    bricks: buildBricks(1),
    parts: [],
    drops: [],
    apus: [],
    lasers: [],
    lives: 3,
    lvl: 1,
    score: 0,
    destroyed: 0,
    over: false,
    launched: false,
    flash: 0,
    lvlFlash: 0,
    keys: new Set(),
    spaceQ: false,
    sticky: false,
    fire: false,
    laserOn: false,
    laserCD: 0,
  };
}

/* ── Component ──────────────────────────────────────────── */

export default function BreakoutGame() {
  const cvs = useRef<HTMLCanvasElement>(null);
  const gs = useRef(init());
  const raf = useRef(0);

  const [score, setScore] = useState(0);
  const [level, setLevel] = useState(1);
  const [gameOver, setGameOver] = useState(false);

  const reset = useCallback(() => {
    const keys = gs.current.keys;
    gs.current = init();
    gs.current.keys = keys;
    setScore(0);
    setLevel(1);
    setGameOver(false);
  }, []);

  /* ── Keyboard ── */
  useEffect(() => {
    const dn = (e: KeyboardEvent) => {
      if (["ArrowLeft", "ArrowRight", " "].includes(e.key))
        e.preventDefault();
      if (e.key === "r" && gs.current.over) {
        reset();
        return;
      }
      gs.current.keys.add(e.key);
      if (e.key === " " && !e.repeat) gs.current.spaceQ = true;
    };
    const up = (e: KeyboardEvent) => gs.current.keys.delete(e.key);
    window.addEventListener("keydown", dn);
    window.addEventListener("keyup", up);
    return () => {
      window.removeEventListener("keydown", dn);
      window.removeEventListener("keyup", up);
    };
  }, [reset]);

  /* ── Game Loop ── */
  useEffect(() => {
    const ctx = cvs.current?.getContext("2d");
    if (!ctx) return;

    function tick() {
      raf.current = requestAnimationFrame(tick);
      const s = gs.current;
      if (!s.over) {
        step(s);
      } else {
        for (const p of s.parts) {
          p.x += p.vx;
          p.y += p.vy;
          p.vy += 0.05;
          p.t--;
        }
        s.parts = s.parts.filter((p) => p.t > 0);
        if (s.flash > 0) s.flash = Math.max(0, s.flash - 0.03);
      }
      draw(ctx!, s);
      setScore(s.score);
      setLevel(s.lvl);
      setGameOver(s.over);
    }

    /* ──── Update ──── */

    function step(s: GS) {
      /* Paddle movement */
      if (s.keys.has("ArrowLeft")) s.px = Math.max(0, s.px - PAD_SPD);
      if (s.keys.has("ArrowRight"))
        s.px = Math.min(W - s.pw, s.px + PAD_SPD);

      /* Space: launch / sticky-release */
      if (s.spaceQ) {
        if (!s.launched) {
          s.launched = true;
          for (const b of s.balls) if (b.stuck) launchBall(b, s);
        } else if (s.balls.some((b) => b.stuck)) {
          for (const b of s.balls) if (b.stuck) launchBall(b, s);
        }
        s.spaceQ = false;
      }

      /* Laser: continuous fire while held */
      if (
        s.keys.has(" ") &&
        s.laserOn &&
        s.launched &&
        s.laserCD <= 0 &&
        !s.balls.some((b) => b.stuck)
      ) {
        s.lasers.push({ x: s.px + s.pw / 2 - 3, y: PADDLE_Y - 2 });
        s.lasers.push({ x: s.px + s.pw / 2 + 3, y: PADDLE_Y - 2 });
        s.laserCD = 10;
      }
      if (s.laserCD > 0) s.laserCD--;

      /* Power-up expiry */
      const now = Date.now();
      s.apus = s.apus.filter((pu) => {
        if (now < pu.end) return true;
        switch (pu.type) {
          case "W":
            s.pw = PW_DEF;
            s.px = Math.max(0, Math.min(W - PW_DEF, s.px));
            for (const b of s.balls)
              if (b.stuck)
                b.off = Math.max(BALL_R, Math.min(PW_DEF - BALL_R, b.off));
            break;
          case "L":
            s.laserOn = false;
            break;
          case "S":
            s.sticky = false;
            for (const b of s.balls)
              if (b.stuck && s.launched) launchBall(b, s);
            break;
          case "F":
            s.fire = false;
            break;
        }
        return false;
      });

      /* Balls */
      for (const b of s.balls) {
        if (b.stuck) {
          b.x = s.px + b.off;
          b.y = PADDLE_Y - BALL_R;
          continue;
        }

        b.trail.unshift({ x: b.x, y: b.y });
        if (b.trail.length > TRAIL_LEN) b.trail.pop();

        b.x += b.vx;
        b.y += b.vy;

        /* Wall bounces */
        if (b.x - BALL_R < 0) {
          b.x = BALL_R;
          b.vx = Math.abs(b.vx);
        }
        if (b.x + BALL_R > W) {
          b.x = W - BALL_R;
          b.vx = -Math.abs(b.vx);
        }
        if (b.y - BALL_R < 0) {
          b.y = BALL_R;
          b.vy = Math.abs(b.vy);
        }

        /* Paddle bounce */
        if (
          b.vy > 0 &&
          b.y + BALL_R >= PADDLE_Y &&
          b.y + BALL_R <= PADDLE_Y + PADDLE_H + 4 &&
          b.x + BALL_R > s.px &&
          b.x - BALL_R < s.px + s.pw
        ) {
          if (s.sticky) {
            b.stuck = true;
            b.off = Math.max(BALL_R, Math.min(s.pw - BALL_R, b.x - s.px));
            b.vx = 0;
            b.vy = 0;
          } else {
            b.y = PADDLE_Y - BALL_R;
            const spd = Math.sqrt(b.vx ** 2 + b.vy ** 2);
            const hit = (b.x - s.px - s.pw / 2) / (s.pw / 2);
            const cl = Math.max(-0.9, Math.min(0.9, hit));
            const ang = cl * (Math.PI / 3);
            b.vx = spd * Math.sin(ang);
            b.vy = -spd * Math.cos(ang);
          }
        }

        /* Brick collisions */
        for (const br of s.bricks) {
          if (!br.alive) continue;
          if (
            b.x + BALL_R > br.x &&
            b.x - BALL_R < br.x + BRICK_W &&
            b.y + BALL_R > br.y &&
            b.y - BALL_R < br.y + BRICK_H
          ) {
            if (!br.gold) {
              br.hp++;
              if (br.hp >= br.maxHp) {
                br.alive = false;
                s.score += br.pts;
                s.destroyed++;
                s.parts.push(
                  ...burst(br.x + BRICK_W / 2, br.y + BRICK_H / 2, br.color),
                );
                if (Math.random() < PU_CHANCE) {
                  s.drops.push({
                    x: br.x + BRICK_W / 2,
                    y: br.y + BRICK_H / 2,
                    type: PU_ALL[Math.floor(Math.random() * PU_ALL.length)],
                    rot: 0,
                  });
                }
              }
            }
            if (!s.fire || br.gold) {
              const ol = b.x + BALL_R - br.x;
              const or_ = br.x + BRICK_W - (b.x - BALL_R);
              const ot = b.y + BALL_R - br.y;
              const ob = br.y + BRICK_H - (b.y - BALL_R);
              if (Math.min(ol, or_) < Math.min(ot, ob)) b.vx *= -1;
              else b.vy *= -1;
              break;
            }
          }
        }

        /* Enforce minimum vertical component */
        const sp = Math.sqrt(b.vx ** 2 + b.vy ** 2);
        if (sp > 0 && Math.abs(b.vy) < sp * 0.15) {
          b.vy = (b.vy < 0 ? -1 : 1) * sp * 0.2;
          b.vx =
            (b.vx < 0 ? -1 : 1) * Math.sqrt(sp ** 2 - b.vy ** 2);
        }
      }

      /* Remove fallen balls */
      s.balls = s.balls.filter((b) => b.y < H + 20);

      if (s.balls.length === 0) {
        s.lives--;
        s.flash = 1;
        if (s.lives <= 0) {
          s.over = true;
          return;
        }
        s.launched = false;
        s.balls = [mkBall(s.px, s.pw)];
        s.apus = [];
        s.pw = PW_DEF;
        s.px = Math.max(0, Math.min(W - PW_DEF, s.px));
        s.sticky = false;
        s.fire = false;
        s.laserOn = false;
        s.drops = [];
        s.lasers = [];
      }

      /* Lasers */
      for (const l of s.lasers) {
        l.y -= LASER_SPD;
        for (const br of s.bricks) {
          if (!br.alive) continue;
          if (
            l.x >= br.x &&
            l.x <= br.x + BRICK_W &&
            l.y >= br.y &&
            l.y <= br.y + BRICK_H
          ) {
            if (!br.gold) {
              br.hp++;
              if (br.hp >= br.maxHp) {
                br.alive = false;
                s.score += br.pts;
                s.destroyed++;
                s.parts.push(
                  ...burst(br.x + BRICK_W / 2, br.y + BRICK_H / 2, br.color),
                );
                if (Math.random() < PU_CHANCE) {
                  s.drops.push({
                    x: br.x + BRICK_W / 2,
                    y: br.y + BRICK_H / 2,
                    type: PU_ALL[Math.floor(Math.random() * PU_ALL.length)],
                    rot: 0,
                  });
                }
              }
            }
            l.y = -99;
            break;
          }
        }
      }
      s.lasers = s.lasers.filter((l) => l.y > -10);

      /* Power-up drops */
      for (const d of s.drops) {
        d.y += PU_FALL;
        d.rot += 0.06;
        if (
          d.y + 8 >= PADDLE_Y &&
          d.y - 8 <= PADDLE_Y + PADDLE_H &&
          d.x >= s.px &&
          d.x <= s.px + s.pw
        ) {
          applyPU(s, d.type);
          d.y = H + 999;
        }
      }
      s.drops = s.drops.filter((d) => d.y < H + 50);

      /* Particles */
      for (const p of s.parts) {
        p.x += p.vx;
        p.y += p.vy;
        p.vy += 0.05;
        p.t--;
      }
      s.parts = s.parts.filter((p) => p.t > 0);
      if (s.parts.length > 250) s.parts.splice(0, s.parts.length - 250);

      /* Flash / level-flash decay */
      if (s.flash > 0) s.flash = Math.max(0, s.flash - 0.03);
      if (s.lvlFlash > 0) s.lvlFlash--;

      /* Level clear */
      if (s.bricks.every((b) => !b.alive || b.gold)) {
        s.lvl++;
        s.bricks = buildBricks(s.lvl);
        s.launched = false;
        s.balls = [mkBall(s.px, s.pw)];
        s.apus = [];
        s.pw = PW_DEF;
        s.px = Math.max(0, Math.min(W - PW_DEF, s.px));
        s.sticky = false;
        s.fire = false;
        s.laserOn = false;
        s.drops = [];
        s.lasers = [];
        s.lvlFlash = 90;
      }
    }

    function applyPU(s: GS, type: PU) {
      const now = Date.now();
      const ms = PU_MS[type];
      switch (type) {
        case "W":
          s.pw = PW_WIDE;
          s.px = Math.max(0, Math.min(W - PW_WIDE, s.px));
          upsert(s, "W", now + ms!);
          break;
        case "M": {
          const src = s.balls.find((b) => !b.stuck) ?? s.balls[0];
          if (!src) break;
          const sp =
            Math.sqrt(src.vx ** 2 + src.vy ** 2) || BASE_SPEED;
          const a0 = Math.atan2(src.vy, src.vx);
          for (const d of [-0.4, 0.4]) {
            const a = a0 + d;
            s.balls.push({
              x: src.x,
              y: src.y,
              vx: sp * Math.cos(a),
              vy: sp * Math.sin(a),
              trail: [],
              stuck: false,
              off: 0,
            });
          }
          break;
        }
        case "L":
          s.laserOn = true;
          upsert(s, "L", now + ms!);
          break;
        case "S":
          s.sticky = true;
          upsert(s, "S", now + ms!);
          break;
        case "+":
          s.lives = Math.min(s.lives + 1, 9);
          break;
        case "F":
          s.fire = true;
          upsert(s, "F", now + ms!);
          break;
      }
    }

    function upsert(s: GS, type: PU, end: number) {
      const e = s.apus.find((a) => a.type === type);
      if (e) e.end = Math.max(e.end, end);
      else s.apus.push({ type, end });
    }

    /* ──── Draw ──── */

    function draw(c: CanvasRenderingContext2D, s: GS) {
      c.fillStyle = "#0f172a";
      c.fillRect(0, 0, W, H);

      /* Subtle background grid */
      c.fillStyle = "#1e293b";
      for (let gx = 0; gx < W; gx += 24)
        for (let gy = 0; gy < H; gy += 24) c.fillRect(gx, gy, 1, 1);

      /* Bricks */
      for (const br of s.bricks) {
        if (!br.alive) continue;
        if (br.gold) {
          const gr = c.createLinearGradient(br.x, br.y, br.x, br.y + BRICK_H);
          gr.addColorStop(0, "#f5d060");
          gr.addColorStop(0.5, "#c9a227");
          gr.addColorStop(1, "#a88620");
          c.fillStyle = gr;
        } else {
          c.fillStyle = br.color;
          if (br.maxHp === 2 && br.hp === 1) c.globalAlpha = 0.55;
        }
        c.beginPath();
        c.roundRect(br.x, br.y, BRICK_W, BRICK_H, 2);
        c.fill();
        c.globalAlpha = 1;

        if (br.maxHp === 2 && br.hp === 0) {
          c.strokeStyle = "rgba(255,255,255,0.45)";
          c.lineWidth = 1;
          c.strokeRect(br.x + 0.5, br.y + 0.5, BRICK_W - 1, BRICK_H - 1);
        }
        if (br.gold) {
          c.strokeStyle = "#f5d060";
          c.lineWidth = 1.5;
          c.strokeRect(br.x + 0.5, br.y + 0.5, BRICK_W - 1, BRICK_H - 1);
        }
      }

      /* Particles */
      for (const p of s.parts) {
        c.globalAlpha = p.t / p.maxT;
        c.fillStyle = p.color;
        c.fillRect(p.x - p.sz / 2, p.y - p.sz / 2, p.sz, p.sz);
      }
      c.globalAlpha = 1;

      /* Lasers */
      c.save();
      c.shadowColor = "#22c55e";
      c.shadowBlur = 6;
      c.fillStyle = "#4ade80";
      for (const l of s.lasers) c.fillRect(l.x, l.y, 2, 8);
      c.restore();

      /* Power-up drops */
      for (const d of s.drops) {
        c.save();
        c.translate(d.x, d.y);
        c.rotate(d.rot);
        c.shadowColor = PU_CLR[d.type];
        c.shadowBlur = 12;
        c.fillStyle = PU_CLR[d.type];
        c.beginPath();
        c.arc(0, 0, 8, 0, Math.PI * 2);
        c.fill();
        c.shadowBlur = 0;
        c.fillStyle = "#fff";
        c.font = "bold 9px sans-serif";
        c.textAlign = "center";
        c.textBaseline = "middle";
        c.fillText(d.type, 0, 0.5);
        c.restore();
      }

      /* Ball trails */
      const trailClr = s.fire ? "#f97316" : "#fbbf24";
      for (const b of s.balls) {
        for (let i = 0; i < b.trail.length; i++) {
          c.globalAlpha = (TRAIL_LEN - i) / (TRAIL_LEN * 2.5);
          c.fillStyle = trailClr;
          c.beginPath();
          c.arc(
            b.trail[i].x,
            b.trail[i].y,
            BALL_R * (1 - i * 0.12),
            0,
            Math.PI * 2,
          );
          c.fill();
        }
      }
      c.globalAlpha = 1;

      /* Balls */
      for (const b of s.balls) {
        c.save();
        if (s.fire) {
          c.shadowColor = "#ff6b00";
          c.shadowBlur = 14;
          c.fillStyle = "#ff8c00";
        } else {
          c.fillStyle = "#fbbf24";
        }
        c.beginPath();
        c.arc(b.x, b.y, BALL_R, 0, Math.PI * 2);
        c.fill();
        c.restore();
      }

      /* Paddle */
      c.save();
      if (s.apus.length > 0) {
        const cols = s.apus.map((a) => PU_CLR[a.type]);
        c.shadowColor = cols[Math.floor(Date.now() / 200) % cols.length];
        c.shadowBlur = 12;
      }
      c.fillStyle = "#e2e8f0";
      c.beginPath();
      c.roundRect(s.px, PADDLE_Y, s.pw, PADDLE_H, 4);
      c.fill();
      c.restore();

      if (s.laserOn) {
        c.fillStyle = "#4ade80";
        c.fillRect(s.px + 3, PADDLE_Y + 1, 3, 3);
        c.fillRect(s.px + s.pw - 6, PADDLE_Y + 1, 3, 3);
      }

      /* ── HUD ── */
      c.font = "bold 11px 'Segoe UI', system-ui, sans-serif";
      c.textBaseline = "top";

      c.fillStyle = "#94a3b8";
      c.textAlign = "left";
      c.fillText(`Score ${s.score}`, 8, 8);

      c.fillStyle = "#e2e8f0";
      c.textAlign = "center";
      c.fillText(`Level ${s.lvl}`, W / 2, 8);

      c.fillStyle = "#fbbf24";
      for (let i = 0; i < s.lives; i++) {
        c.beginPath();
        c.arc(W - 14 - i * 14, 14, 4, 0, Math.PI * 2);
        c.fill();
      }

      /* Active power-up timers */
      const now = Date.now();
      let ax = 8;
      c.font = "bold 7px 'Segoe UI', sans-serif";
      c.textBaseline = "top";
      for (const pu of s.apus) {
        const dur = PU_MS[pu.type] || 10_000;
        const frac = Math.max(0, (pu.end - now) / dur);

        c.fillStyle = PU_CLR[pu.type];
        c.globalAlpha = 0.25;
        c.beginPath();
        c.roundRect(ax, 25, 36, 12, 3);
        c.fill();

        c.globalAlpha = 0.7;
        if (frac > 0) {
          c.beginPath();
          c.roundRect(ax, 25, 36 * frac, 12, 3);
          c.fill();
        }

        c.globalAlpha = 1;
        c.fillStyle = "#fff";
        c.textAlign = "left";
        c.fillText(PU_TAG[pu.type], ax + 4, 27.5);
        ax += 40;
      }

      /* Screen flash */
      if (s.flash > 0) {
        c.fillStyle = `rgba(239,68,68,${s.flash * 0.3})`;
        c.fillRect(0, 0, W, H);
      }

      /* Level-up flash */
      if (s.lvlFlash > 0) {
        const a = Math.min(1, s.lvlFlash / 30);
        c.globalAlpha = a;
        c.fillStyle = "#fbbf24";
        c.font = "bold 30px 'Segoe UI', system-ui, sans-serif";
        c.textAlign = "center";
        c.textBaseline = "middle";
        c.fillText(`Level ${s.lvl}`, W / 2, H / 2);
        c.globalAlpha = 1;
      }

      /* Launch prompt */
      if (!s.launched && !s.over) {
        const pulse = 0.5 + 0.5 * Math.sin(Date.now() / 400);
        c.globalAlpha = 0.5 + pulse * 0.5;
        c.fillStyle = "#94a3b8";
        c.font = "13px 'Segoe UI', system-ui, sans-serif";
        c.textAlign = "center";
        c.textBaseline = "middle";
        c.fillText("Press SPACE to launch", W / 2, H / 2 + 50);
        c.globalAlpha = 1;
      }

      /* Game-over overlay */
      if (s.over) {
        c.fillStyle = "rgba(15,23,42,0.85)";
        c.fillRect(0, 0, W, H);

        c.fillStyle = "#ef4444";
        c.font = "bold 28px 'Segoe UI', system-ui, sans-serif";
        c.textAlign = "center";
        c.textBaseline = "middle";
        c.fillText("GAME OVER", W / 2, H / 2 - 45);

        c.fillStyle = "#e2e8f0";
        c.font = "15px 'Segoe UI', system-ui, sans-serif";
        c.fillText(`Score: ${s.score}`, W / 2, H / 2 - 8);
        c.fillText(`Level: ${s.lvl}`, W / 2, H / 2 + 16);

        c.fillStyle = "#94a3b8";
        c.fillText(`Bricks destroyed: ${s.destroyed}`, W / 2, H / 2 + 40);

        c.fillStyle = "#64748b";
        c.font = "12px 'Segoe UI', system-ui, sans-serif";
        c.fillText("Press R or click Restart", W / 2, H / 2 + 70);
      }
    }

    raf.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf.current);
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
        ref={cvs}
        width={W}
        height={H}
        style={{ borderRadius: 8, border: "1px solid #334155" }}
      />
      {gameOver && (
        <button
          type="button"
          aria-label="Restart game"
          onClick={reset}
          style={{
            background: "linear-gradient(135deg,#6366f1,#8b5cf6)",
            color: "#fff",
            border: "none",
            borderRadius: 8,
            padding: "8px 24px",
            fontSize: 14,
            fontWeight: 600,
            cursor: "pointer",
          }}
        >
          Restart
        </button>
      )}
      <p style={{ color: "#64748b", fontSize: 11, margin: 0 }}>
        ← → Move · Space Launch / Fire · R Restart
      </p>
      <Leaderboard
        game="breakout"
        currentScore={score}
        currentLevel={level}
        gameOver={gameOver}
      />
    </div>
  );
}
