/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-BCA9B190
 *   DI: DI-C5A523A7
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-BCA9B190")
 */
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

// Density for the list. "comfortable" is the airy default; "compact"
// tightens vertical padding for power-users clearing dense review
// queues. Consumers typically read this from useDensity() so the
// setting flows from the user's Settings toggle.
export type ReviewListDensity = "comfortable" | "compact";

export interface ReviewListCardProps {
  items: ReviewListItem[];
  emptyState?: ReactNode;
  // How many ms between items animating in (default 40 ms, 0 if reduced-motion).
  staggerMs?: number;
  density?: ReviewListDensity;
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

function row(
  item: ReviewListItem,
  reducedMotion: boolean,
  idx: number,
  step: number,
  density: ReviewListDensity,
) {
  const accent = toneToAccent(item.tone);
  const isInteractive = typeof item.onSelect === "function";
  const initial = reducedMotion ? false : { opacity: 0, y: 6 };
  const animate = { opacity: 1, y: 0 };
  const exit = reducedMotion ? undefined : { opacity: 0, y: -6 };
  const delay = reducedMotion ? 0 : (step * idx) / 1000;
  const rowPadding =
    density === "compact" ? "8px 12px 8px 16px" : "14px 16px 14px 20px";
  const rowGap = density === "compact" ? 12 : 16;

  // The row uses a div with role="button" rather than a real <button>
  // element so that nested action buttons in the `actions` slot
  // (e.g. "Mark gold" + a kebab menu) remain valid HTML. Keyboard
  // activation is wired up through onKeyDown.
  const onKeyDown = isInteractive
    ? (event: React.KeyboardEvent<HTMLDivElement>) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          item.onSelect?.();
        }
      }
    : undefined;

  return (
    <fm.div
      key={item.id}
      role={isInteractive ? "button" : undefined}
      tabIndex={isInteractive ? 0 : undefined}
      onClick={item.onSelect}
      onKeyDown={onKeyDown}
      data-testid={"review-list-item-" + item.id}
      data-density={density}
      layoutId={"review-list-item-layout-" + item.id}
      initial={initial}
      animate={animate}
      exit={exit}
      transition={{ duration: reducedMotion ? 0 : 0.18, ease: "easeOut", delay }}
      style={{
        position: "relative",
        display: "grid",
        gridTemplateColumns: "1fr auto",
        gap: rowGap,
        alignItems: "center",
        width: "100%",
        textAlign: "left",
        font: "inherit",
        fontFamily: typography.fontFamily.body,
        padding: rowPadding,
        background: item.selected ? color.surface.alt : color.surface.raised,
        border: "1px solid " + color.surface.divider,
        borderRadius: radius.md,
        cursor: isInteractive ? "pointer" : "default",
        outlineOffset: 2,
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
    </fm.div>
  );
}

export function ReviewListCard({
  items,
  emptyState,
  staggerMs = 40,
  density = "comfortable",
}: ReviewListCardProps) {
  const { reducedMotion } = useMotion();
  const step = reducedMotion ? 0 : staggerMs;
  const listGap = density === "compact" ? 6 : 8;

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
      data-density={density}
      style={{ display: "flex", flexDirection: "column", gap: listGap }}
    >
      <AnimatePresence initial={!reducedMotion}>
        {items.map((item, idx) => row(item, reducedMotion, idx, step, density))}
      </AnimatePresence>
    </div>
  );
}
