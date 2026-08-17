/**
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
import { color, typography } from "@leo/design-system/tokens";
import CloseIcon from "@mui/icons-material/Close";

export function ContextDialogTitleBar({
  titleId,
  title,
  onClose,
}: {
  titleId: string;
  title: string;
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
      <h2
        id={titleId}
        style={{
          margin: 0,
          fontFamily: typography.fontFamily.heading,
          fontSize: 22,
          fontWeight: 700,
          letterSpacing: typography.letterSpacing.display,
          color: color.text.primary,
        }}
      >
        {title}
      </h2>
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
        Context
      </span>
      <fm.button
        type="button"
        aria-label="Close"
        onClick={onClose}
        whileTap={tapScale(reducedMotion)}
        transition={springOrInstant(reducedMotion, springs.press)}
        style={{
          position: "absolute",
          right: 12,
          top: 10,
          border: 0,
          background: "transparent",
          cursor: "pointer",
          padding: 6,
          color: color.text.primary,
        }}
      >
        <CloseIcon />
      </fm.button>
    </div>
  );
}
