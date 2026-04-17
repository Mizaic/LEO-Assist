"use client";

import type { ReactNode } from "react";
import { AnimatePresence, motion as fm } from "framer-motion";

import { color } from "../tokens/color";
import { radius } from "../tokens/spacing";
import { typography } from "../tokens/typography";
import { useMotion } from "../motion";

export interface ReviewListItem {
  id: string;
  title: ReactNode;
  meta?: ReactNode;
  // Left-side chips (e.g. assertion, tag). Keep short -- 1-3 words each.
  chips?: ReactNode;
  // Right-side action cluster (e.g. "Mark gold" + menu).
  actions?: ReactNode;
  // Optional tone that tints a left-edge accent (e.g. "danger" for
  // "needs review"). Maps to design-system tokens.
  tone?: "neutral" | "positive" | "warning" | "danger";
  onSelect?: () => void;
  selected?: boolean;
}

export interface ReviewListCardProps {
  items: ReviewListItem[];
  emptyState?: ReactNode;
  // How many ms between items animating in (default 40 ms, 0 if reduced-motion).
  staggerMs?: number;
}

/**
 * ReviewListCard -- motion-aware list container used by Training Data
 * and AI Instructions. Each row animates in with a short y-translate +
 * opacity fade; exit reverses. Honours prefers-reduced-motion.
 *
 * Design Controls: DI-LEO-AI-142, DO-LEO-AI-139, VT-LEO-AI-141.
 */

function toneToAccent(tone: ReviewListItem["tone"]): string {
  if (tone === "positive") return color.status.success;
  if (tone === "warning") return color.status.warning;
  if (tone === "danger") return color.status.danger;
  return color.surface.divider;
}

function row(item: ReviewListItem, reducedMotion: boolean, idx: number, step: number) {
  const accent = toneToAccent(item.tone);
  const isInteractive = typeof item.onSelect === "function";
  const Tag = isInteractive ? fm.button : fm.div;
  const initial = reducedMotion ? false : { opacity: 0, y: 6 };
  const animate = { opacity: 1, y: 0 };
  const exit = reducedMotion ? undefined : { opacity: 0, y: -6 };
  const delay = reducedMotion ? 0 : (step * idx) / 1000;

  return (
    <Tag
      key={item.id}
      type={isInteractive ? "button" : undefined}
      onClick={item.onSelect}
      data-testid={"review-list-item-" + item.id}
      layout
      initial={initial}
      animate={animate}
      exit={exit}
      transition={{ duration: reducedMotion ? 0 : 0.18, ease: "easeOut", delay }}
      style={{
        position: "relative",
        display: "grid",
        gridTemplateColumns: "1fr auto",
        gap: 16,
        alignItems: "center",
        width: "100%",
        textAlign: "left",
        font: "inherit",
        fontFamily: typography.fontFamily.body,
        padding: "14px 16px 14px 20px",
        background: item.selected ? color.surface.alt : color.surface.raised,
        border: "1px solid " + color.surface.divider,
        borderRadius: radius.md,
        cursor: isInteractive ? "pointer" : "default",
      }}
    >
      <span
        aria-hidden="true"
        style={{
          position: "absolute",
          left: 0,
          top: 10,
          bottom: 10,
          width: 3,
          borderRadius: radius.sm,
          background: accent,
        }}
      />
      <div style={{ minWidth: 0 }}>
        <div
          style={{
            fontSize: 14,
            fontWeight: 500,
            color: color.text.primary,
            lineHeight: 1.45,
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          {item.title}
        </div>
        {item.meta ? (
          <div
            style={{
              marginTop: 4,
              fontSize: 12,
              color: color.text.caption,
              display: "flex",
              gap: 10,
              flexWrap: "wrap",
            }}
          >
            {item.meta}
          </div>
        ) : null}
        {item.chips ? (
          <div style={{ marginTop: 8, display: "flex", gap: 6, flexWrap: "wrap" }}>
            {item.chips}
          </div>
        ) : null}
      </div>
      {item.actions ? (
        <div
          style={{ display: "inline-flex", gap: 6, alignItems: "center" }}
          onClick={(e) => e.stopPropagation()}
        >
          {item.actions}
        </div>
      ) : null}
    </Tag>
  );
}

export function ReviewListCard({
  items,
  emptyState,
  staggerMs = 40,
}: ReviewListCardProps) {
  const { reducedMotion } = useMotion();
  const step = reducedMotion ? 0 : staggerMs;

  if (items.length === 0 && emptyState) {
    return (
      <div
        data-testid="review-list-empty"
        style={{
          padding: 32,
          textAlign: "center",
          fontFamily: typography.fontFamily.body,
          color: color.text.caption,
          border: "1px dashed " + color.surface.divider,
          borderRadius: radius.md,
          background: color.surface.raised,
        }}
      >
        {emptyState}
      </div>
    );
  }

  return (
    <div
      data-testid="review-list-card"
      style={{ display: "flex", flexDirection: "column", gap: 8 }}
    >
      <AnimatePresence initial={!reducedMotion}>
        {items.map((item, idx) => row(item, reducedMotion, idx, step))}
      </AnimatePresence>
    </div>
  );
}
