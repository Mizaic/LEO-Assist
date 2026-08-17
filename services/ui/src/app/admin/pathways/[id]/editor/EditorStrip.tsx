/**
 * Atlas trace:
 *   DO: DO-5D885390
 *   DI: DI-693FFEEA
 */
"use client";

import type { CSSProperties, ReactNode } from "react";
import { motion as fm } from "framer-motion";
import {
  springOrInstant,
  springs,
  tapScale,
  useMotion,
  useReducedTransparency,
} from "@leo/design-system";
import { color, elevation, frostStyle, typography } from "@leo/design-system/tokens";

export function useEditorStripStyle(): CSSProperties {
  const reducedTransparency = useReducedTransparency();
  return {
    margin: "8px 16px 0",
    borderRadius: 12,
    border: "1px solid " + color.text.secondary,
    boxShadow: elevation.card,
    fontFamily: typography.fontFamily.body,
    overflow: "hidden",
    ...frostStyle(reducedTransparency, "light"),
  };
}

export function EditorAccordionHeader({
  title,
  open,
  onToggle,
  icon,
  trailing,
}: {
  title: string;
  open: boolean;
  onToggle: () => void;
  icon?: ReactNode;
  trailing?: ReactNode;
}) {
  const { reducedMotion } = useMotion();
  return (
    <fm.button
      type="button"
      onClick={onToggle}
      title={open ? "Hide " + title : "Show " + title}
      whileTap={tapScale(reducedMotion)}
      transition={springOrInstant(reducedMotion, springs.press)}
      style={{
        width: "100%",
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "10px 14px",
        border: 0,
        background: "transparent",
        cursor: "pointer",
        fontFamily: typography.fontFamily.body,
        color: color.text.primary,
        textAlign: "left",
      }}
    >
      {icon}
      <span style={{ flex: 1, fontWeight: 700, fontSize: 14 }}>{title}</span>
      {trailing}
      <span
        style={{
          fontSize: 12,
          fontWeight: 700,
          color: color.brand.primary,
          flexShrink: 0,
        }}
      >
        {open ? "Hide" : "Show"}
      </span>
    </fm.button>
  );
}

export function EditorAccordionBody({
  open,
  children,
}: {
  open: boolean;
  children: ReactNode;
}) {
  const { reducedMotion } = useMotion();
  if (!open) return null;
  return (
    <fm.div
      initial={reducedMotion ? false : { opacity: 0, y: -6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={springOrInstant(reducedMotion, springs.ui)}
      style={{ padding: "0 14px 14px" }}
    >
      {children}
    </fm.div>
  );
}
