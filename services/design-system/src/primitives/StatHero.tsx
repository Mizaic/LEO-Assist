"use client";

import type { ReactNode } from "react";

import { useMotion } from "../motion";

export interface StatTile {
  id: string;
  label: string;
  value: string | number;
  hint?: string;
  delta?: {
    value: string;
    direction: "up" | "down" | "flat";
    // When true, 'up' is shown in red and 'down' in green. For metrics
    // where lower-is-better (e.g. waiting times) pass invert=true.
    invert?: boolean;
  };
  icon?: ReactNode;
}

export interface StatHeroProps {
  stats: StatTile[];
  maxTiles?: number;
}

function deltaColor(
  direction: StatTile["delta"] extends infer D
    ? D extends { direction: infer X }
      ? X
      : never
    : never,
  invert: boolean,
): string {
  if (direction === "flat") return "rgba(15, 23, 42, 0.5)";
  const goodIsUp = !invert;
  const isGood =
    (direction === "up" && goodIsUp) || (direction === "down" && !goodIsUp);
  return isGood ? "#0f7b3c" : "#b4262b";
}

function arrow(direction: "up" | "down" | "flat"): string {
  if (direction === "up") return "\u2191";
  if (direction === "down") return "\u2193";
  return "\u2192";
}

export function StatHero({ stats, maxTiles = 5 }: StatHeroProps) {
  const { reducedMotion } = useMotion();
  const visible = stats.slice(0, maxTiles);
  const transitionMs = reducedMotion ? 0 : 160;

  return (
    <section
      aria-label="Key numbers"
      data-testid="stat-hero"
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(" + visible.length + ", minmax(0, 1fr))",
        gap: 12,
        marginBottom: 16,
      }}
    >
      {visible.map((s) => {
        const invert = s.delta?.invert ?? false;
        const color = s.delta ? deltaColor(s.delta.direction, invert) : "";
        return (
          <div
            key={s.id}
            data-testid={"stat-tile-" + s.id}
            style={{
              background: "var(--mui-palette-background-paper, #ffffff)",
              border: "1px solid rgba(15, 23, 42, 0.08)",
              borderRadius: 12,
              padding: "12px 16px",
              minHeight: 88,
              transition: "box-shadow " + transitionMs + "ms ease-out",
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                color: "rgba(15, 23, 42, 0.6)",
                fontSize: 12,
                fontWeight: 500,
                letterSpacing: 0.2,
                textTransform: "uppercase",
              }}
            >
              {s.icon ?? null}
              <span>{s.label}</span>
            </div>
            <div
              style={{
                fontSize: 28,
                fontWeight: 600,
                lineHeight: 1.1,
                marginTop: 6,
              }}
            >
              {s.value}
            </div>
            <div
              style={{
                marginTop: 4,
                fontSize: 12,
                color: "rgba(15, 23, 42, 0.5)",
                display: "flex",
                gap: 6,
                alignItems: "baseline",
              }}
            >
              {s.delta ? (
                <span style={{ color }}>
                  {arrow(s.delta.direction)} {s.delta.value}
                </span>
              ) : null}
              {s.hint ? <span>{s.hint}</span> : null}
            </div>
          </div>
        );
      })}
    </section>
  );
}
