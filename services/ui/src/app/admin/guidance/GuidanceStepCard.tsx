/**
 * Atlas trace:
 *   DO: DO-0A8B7188
 *   DI: DI-0C8FBAF7
 */
"use client";

import { motion as fm } from "framer-motion";
import { springOrInstant, springs } from "@leo/design-system";
import { color, elevation, typography } from "@leo/design-system/tokens";

export interface GuidanceStepCardProps {
  id: string;
  step?: number;
  title: string;
  description: string;
  accent: string;
  index: number;
  reducedMotion: boolean;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  dataTour?: string;
  children: React.ReactNode;
}

export function StepCard({
  id,
  step,
  title,
  description,
  accent,
  index,
  reducedMotion,
  dataTour,
  children,
}: GuidanceStepCardProps) {
  return (
    <fm.section
      id={id}
      aria-labelledby={`${id}-title`}
      data-tour={dataTour}
      initial={reducedMotion ? { opacity: 0 } : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        ...springOrInstant(reducedMotion, springs.ui),
        delay: reducedMotion ? 0 : Math.min(index, 6) * 0.04,
      }}
      style={{
        position: "relative",
        background: color.surface.raised,
        borderRadius: 12,
        padding: 22,
        marginBottom: 20,
        boxShadow: elevation.card,
        fontFamily: typography.fontFamily.body,
      }}
    >
      <span
        aria-hidden="true"
        style={{
          position: "absolute",
          left: 0,
          top: 18,
          bottom: 18,
          width: 3,
          borderRadius: 2,
          background: accent,
        }}
      />
      <StepHeading id={id} step={step} title={title} description={description} accent={accent} />
      {children}
    </fm.section>
  );
}

function StepHeading({
  id,
  step,
  title,
  description,
  accent,
}: {
  id: string;
  step?: number;
  title: string;
  description: string;
  accent: string;
}) {
  return (
    <div style={{ display: "flex", alignItems: "flex-start", gap: 12, marginBottom: 16 }}>
      {step != null ? (
        <span
          aria-hidden="true"
          style={{
            width: 28,
            height: 28,
            borderRadius: 999,
            background: accent,
            color: color.brand.onBrand,
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            fontWeight: 700,
            fontSize: 13,
            flexShrink: 0,
          }}
        >
          {step}
        </span>
      ) : null}
      <div style={{ minWidth: 0 }}>
        <h2
          id={`${id}-title`}
          style={{
            margin: 0,
            fontFamily: typography.fontFamily.heading,
            fontSize: 18,
            fontWeight: 700,
            letterSpacing: typography.letterSpacing.display,
            color: color.text.primary,
          }}
        >
          {title}
        </h2>
        <p style={{ margin: "6px 0 0", fontSize: 14, lineHeight: 1.45, color: color.text.secondary }}>
          {description}
        </p>
      </div>
    </div>
  );
}
