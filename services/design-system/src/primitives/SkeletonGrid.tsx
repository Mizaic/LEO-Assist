/**
 * Atlas trace:
 *   DO: DO-BCA9B190
 *   DI: DI-C5A523A7
 */
"use client";

import { useEffect, useState } from "react";

import { color } from "../tokens/color";
import { radius } from "../tokens/spacing";
import { useMotion } from "../motion/MotionProvider";

export interface SkeletonGridProps {
  columns?: 1 | 2 | 3 | 4 | 6 | 8;
  rows?: number;
  itemHeight?: number;
  gap?: number;
  "data-testid"?: string;
}

export interface SkeletonListProps {
  rows?: number;
  itemHeight?: number;
  gap?: number;
  "data-testid"?: string;
}

/**
 * SkeletonGrid -- shimmer grid of placeholder rectangles that match the
 * dimensions of the loaded card grid. Respects prefers-reduced-motion
 * (shimmer animation disabled; solid placeholder shown instead).
 *
 * SkeletonList -- single-column variant used for ReviewListCard placeholders.
 *
 * Design Controls: DI-C5A523A7, DO-BCA9B190.
 */

const SHIMMER_KEYFRAMES = `
@keyframes skeleton-shimmer {
  0%   { background-position: -400px 0; }
  100% { background-position: 400px 0; }
}
`;

let styleInjected = false;

function injectShimmerStyle() {
  if (typeof document === "undefined" || styleInjected) return;
  const el = document.createElement("style");
  el.textContent = SHIMMER_KEYFRAMES;
  document.head.appendChild(el);
  styleInjected = true;
}

function SkeletonItem({
  height,
  reducedMotion,
}: {
  height: number;
  reducedMotion: boolean;
}) {
  const shimmerStyle: React.CSSProperties = reducedMotion
    ? { background: color.surface.divider }
    : {
        background: `linear-gradient(
          90deg,
          ${color.surface.divider} 25%,
          #F1F5F9 50%,
          ${color.surface.divider} 75%
        )`,
        backgroundSize: "800px 100%",
        animation: "skeleton-shimmer 1.4s infinite linear",
      };

  return (
    <div
      aria-hidden="true"
      style={{
        borderRadius: radius.md,
        height,
        ...shimmerStyle,
      }}
    />
  );
}

export function SkeletonGrid({
  columns = 3,
  rows = 3,
  itemHeight = 120,
  gap = 12,
  "data-testid": testId = "skeleton-grid",
}: SkeletonGridProps) {
  const { reducedMotion } = useMotion();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    injectShimmerStyle();
    setMounted(true);
  }, []);

  if (!mounted) return null;

  const count = columns * rows;

  return (
    <div
      data-testid={testId}
      role="status"
      aria-label="Loading"
      style={{
        display: "grid",
        gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))`,
        gap,
        marginBottom: 16,
      }}
    >
      {Array.from({ length: count }).map((_, i) => (
        <SkeletonItem
          key={i}
          height={itemHeight}
          reducedMotion={reducedMotion}
        />
      ))}
    </div>
  );
}

export function SkeletonList({
  rows = 4,
  itemHeight = 64,
  gap = 8,
  "data-testid": testId = "skeleton-list",
}: SkeletonListProps) {
  const { reducedMotion } = useMotion();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    injectShimmerStyle();
    setMounted(true);
  }, []);

  if (!mounted) return null;

  return (
    <div
      data-testid={testId}
      role="status"
      aria-label="Loading"
      style={{ display: "flex", flexDirection: "column", gap }}
    >
      {Array.from({ length: rows }).map((_, i) => (
        <SkeletonItem
          key={i}
          height={itemHeight}
          reducedMotion={reducedMotion}
        />
      ))}
    </div>
  );
}
