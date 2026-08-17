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
import { color, typography } from "@leo/design-system/tokens";
import CloseIcon from "@mui/icons-material/Close";

export function GuardDialogTitleBar({
  titleId,
  title,
  badge,
  onClose,
}: {
  titleId: string;
  title: string;
  badge?: string;
  onClose: () => void;
}) {
  const { reducedMotion } = useMotion();
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 10,
        padding: "14px 52px 14px 20px",
        position: "relative",
      }}
    >
      <h2 id={titleId} style={titleStyle()}>
        {title}
      </h2>
      {badge ? (
        <span
          style={{
            fontSize: 11,
            fontWeight: 600,
            color: color.text.secondary,
            background: color.surface.alt,
            borderRadius: 999,
            padding: "3px 8px",
          }}
        >
          {badge}
        </span>
      ) : null}
      <fm.button
        type="button"
        aria-label="Close"
        onClick={onClose}
        whileTap={tapScale(reducedMotion)}
        transition={springOrInstant(reducedMotion, springs.press)}
        style={closeBtnStyle()}
      >
        <CloseIcon />
      </fm.button>
    </div>
  );
}

function titleStyle() {
  return {
    margin: 0,
    fontFamily: typography.fontFamily.heading,
    fontSize: 22,
    fontWeight: 700,
    letterSpacing: typography.letterSpacing.display,
    color: color.text.primary,
  };
}

function closeBtnStyle() {
  return {
    position: "absolute" as const,
    right: 12,
    top: 10,
    border: 0,
    background: "transparent",
    cursor: "pointer" as const,
    padding: 6,
    color: color.text.primary,
  };
}
