/**
 * Show-more control for paged clinician lists.
 *
 * Atlas trace:
 *   DO: DO-5D3EA371
 *   DI: DI-357A7468
 */
"use client";

import { motion as fm } from "framer-motion";
import {
  color,
  radius,
  springOrInstant,
  springs,
  tapScale,
  typography,
  useMotion,
} from "@leo/design-system";
import { RECORD_PAGE_SIZE } from "./recordPage";

interface Props {
  remaining: number;
  pageSize?: number;
  onShowMore: () => void;
}

export function RecordShowMore({
  remaining,
  pageSize = RECORD_PAGE_SIZE,
  onShowMore,
}: Props) {
  const { reducedMotion } = useMotion();
  if (remaining <= 0) return null;
  const next = Math.min(pageSize, remaining);
  const label = `Show ${next} more`;
  return (
    <fm.button
      type="button"
      data-testid="record-show-more"
      aria-label={label}
      onClick={onShowMore}
      whileTap={tapScale(reducedMotion)}
      transition={springOrInstant(reducedMotion, springs.press)}
      style={{
        appearance: "none",
        border: "1px solid " + color.brand.primary,
        background: color.surface.raised,
        color: color.brand.primary,
        fontFamily: typography.fontFamily.body,
        fontSize: 13,
        fontWeight: 700,
        padding: "8px 14px",
        borderRadius: radius.pill,
        cursor: "pointer",
        minHeight: 36,
      }}
    >
      {label}
    </fm.button>
  );
}
