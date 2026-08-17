/**
 * Compact Context Rule category card -- title and type only.
 *
 * Atlas trace:
 *   Implements: DO-CFA1ED55
 *   DI: DI-340279C1, DI-C5A523A7
 */
"use client";

import { motion as fm } from "framer-motion";
import {
  springOrInstant,
  springs,
  tapScale,
  useMotion,
} from "@leo/design-system";
import { color, elevation, radius, typography } from "@leo/design-system/tokens";

import type { CategoryCopy } from "./categoryCopy";
import type { ContextRule } from "./types";

interface ContextCategoryCardProps {
  copy: CategoryCopy;
  rules: ContextRule[];
  index: number;
  onOpen: () => void;
}

function sourceType(rules: ContextRule[]): string {
  const hasBuiltin = rules.some((rule) => rule.source === "builtin");
  const hasAdded = rules.some((rule) => rule.source !== "builtin");
  if (hasBuiltin && hasAdded) return "Built-in + added";
  if (hasAdded) return "Added";
  return "Built-in";
}

export default function ContextCategoryCard({
  copy,
  rules,
  index,
  onOpen,
}: ContextCategoryCardProps) {
  const { reducedMotion } = useMotion();
  const countLabel = rules.length === 1 ? "1 phrase" : `${rules.length} phrases`;
  const enter = springOrInstant(reducedMotion, springs.ui);
  return (
    <fm.div
      initial={reducedMotion ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        ...enter,
        delay: reducedMotion ? 0 : Math.min(index, 12) * 0.04,
      }}
      style={{ height: "100%" }}
    >
      <fm.button
        type="button"
        onClick={onOpen}
        data-testid={`context-category-card-${copy.key}`}
        aria-label={`Open ${copy.title} details`}
        whileTap={tapScale(reducedMotion)}
        transition={springOrInstant(reducedMotion, springs.press)}
        style={cardStyle()}
      >
        <span
          aria-hidden="true"
          style={{
            position: "absolute",
            left: 0,
            top: 14,
            bottom: 14,
            width: 3,
            borderRadius: 999,
            background: copy.accent,
          }}
        />
        <span
          style={{
            fontFamily: typography.fontFamily.heading,
            fontSize: 16,
            fontWeight: 700,
            lineHeight: 1.2,
            letterSpacing: typography.letterSpacing.display,
            color: color.text.primary,
          }}
        >
          {copy.title}
        </span>
        <span style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
          <MetaChip label={countLabel} />
          <MetaChip label={sourceType(rules)} />
        </span>
      </fm.button>
    </fm.div>
  );
}

function cardStyle() {
  return {
    position: "relative" as const,
    display: "flex",
    flexDirection: "column" as const,
    justifyContent: "center",
    gap: 10,
    width: "100%",
    height: "100%",
    minHeight: 104,
    textAlign: "left" as const,
    background: color.surface.raised,
    border: 0,
    boxShadow: elevation.card,
    borderRadius: radius.md,
    padding: "18px 18px 18px 22px",
    cursor: "pointer" as const,
    fontFamily: typography.fontFamily.body,
  };
}

function MetaChip({ label }: { label: string }) {
  return (
    <span
      style={{
        fontSize: 12,
        fontWeight: 600,
        color: color.text.secondary,
        background: color.surface.alt,
        borderRadius: 999,
        padding: "3px 8px",
      }}
    >
      {label}
    </span>
  );
}
