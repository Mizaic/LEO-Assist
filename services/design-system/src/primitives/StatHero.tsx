"use client";

import { motion as fm } from "framer-motion";

import { MetricTile, type MetricTileProps } from "./MetricTile";
import { useMotion } from "../motion";

// StatTile retains the legacy shape consumers already use (dashboards,
// knowledge primitives). Everything it carries maps onto MetricTileProps
// so the hero is just a motion-aware grid of MetricTiles.
export interface StatTile {
  id: string;
  label: string;
  value: string | number;
  hint?: string;
  delta?: MetricTileProps["delta"];
  icon?: React.ReactNode;
  tone?: MetricTileProps["tone"];
}

export interface StatHeroProps {
  stats: StatTile[];
  maxTiles?: number;
  // Stagger between tiles on mount (default 60 ms).
  staggerMs?: number;
}

/**
 * StatHero -- row of MetricTiles that fades + lifts in with a
 * framer-motion stagger on mount. Honours prefers-reduced-motion by
 * collapsing all delays and durations to zero.
 *
 * Design Controls: DI-LEO-AI-142, DO-LEO-AI-139, VT-LEO-AI-141.
 */

export function StatHero({
  stats,
  maxTiles = 6,
  staggerMs = 60,
}: StatHeroProps) {
  const { reducedMotion } = useMotion();
  const visible = stats.slice(0, maxTiles);
  const stepSec = reducedMotion ? 0 : staggerMs / 1000;
  const columns = visible.length;

  return (
    <fm.section
      aria-label="Key numbers"
      data-testid="stat-hero"
      initial={reducedMotion ? false : "hidden"}
      animate="visible"
      variants={{
        hidden: {},
        visible: {
          transition: { staggerChildren: stepSec },
        },
      }}
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(" + columns + ", minmax(0, 1fr))",
        gap: 12,
        marginBottom: 16,
      }}
    >
      {visible.map((s) => (
        <fm.div
          key={s.id}
          variants={{
            hidden: { opacity: 0, y: reducedMotion ? 0 : 8 },
            visible: {
              opacity: 1,
              y: 0,
              transition: { duration: reducedMotion ? 0 : 0.22, ease: "easeOut" },
            },
          }}
          data-testid={"stat-tile-" + s.id + "-frame"}
        >
          <MetricTile
            id={s.id}
            label={s.label}
            value={s.value}
            hint={s.hint}
            delta={s.delta}
            icon={s.icon}
            tone={s.tone}
          />
        </fm.div>
      ))}
    </fm.section>
  );
}
