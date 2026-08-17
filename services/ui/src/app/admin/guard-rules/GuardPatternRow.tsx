/**
 * Atlas trace:
 *   Implements: DO-6413D5BC
 *   DI: DI-34712A9A, DI-C5A523A7
 */
"use client";

import { motion as fm } from "framer-motion";
import {
  springOrInstant,
  springs,
  tapScale,
  useMotion,
} from "@leo/design-system";
import { color, elevation, typography } from "@leo/design-system/tokens";

import { humanizePattern } from "./humanizePattern";
import type { NerGuardRule } from "./types";

export function GuardPatternRow({
  rule,
  selected,
  onSelect,
}: {
  rule: NerGuardRule;
  selected: boolean;
  onSelect: (rule: NerGuardRule) => void;
}) {
  const { reducedMotion } = useMotion();
  const label = rule.summary || humanizePattern(rule.pattern) || "(no pattern)";
  return (
    <fm.button
      type="button"
      onClick={() => onSelect(rule)}
      aria-current={selected ? "true" : undefined}
      whileTap={tapScale(reducedMotion)}
      transition={springOrInstant(reducedMotion, springs.press)}
      style={rowStyle(selected)}
    >
      {selected ? <SelectedRail /> : null}
      <span
        style={{
          flex: 1,
          fontSize: 13,
          color: color.text.primary,
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        }}
      >
        {label}
      </span>
      <span
        style={{
          fontSize: 11,
          fontWeight: 600,
          color: color.text.secondary,
          background: color.surface.alt,
          borderRadius: 999,
          padding: "2px 8px",
          flexShrink: 0,
        }}
      >
        {rule.source === "builtin" ? "Built-in" : "Added"}
      </span>
    </fm.button>
  );
}

function rowStyle(selected: boolean) {
  return {
    display: "flex" as const,
    position: "relative" as const,
    alignItems: "center",
    gap: 8,
    width: "100%",
    textAlign: "left" as const,
    border: "none",
    borderRadius: 8,
    padding: "8px 10px 8px 14px",
    margin: "2px 0",
    cursor: "pointer" as const,
    background: selected ? color.surface.raised : "transparent",
    boxShadow: selected ? elevation.card : "none",
    fontFamily: typography.fontFamily.body,
  };
}

function SelectedRail() {
  return (
    <span
      aria-hidden="true"
      style={{
        position: "absolute",
        left: 0,
        top: 6,
        bottom: 6,
        width: 3,
        borderRadius: 999,
        background: color.brand.primary,
      }}
    />
  );
}
