/**
 * Atlas trace:
 *   DO: DO-BCA9B190
 *   DI: DI-C5A523A7
 */
"use client";

import type { CSSProperties, ReactNode } from "react";
import { motion as fm } from "framer-motion";

import { springOrInstant, springs, tapScale, useMotion } from "../motion";
import { color } from "../tokens/color";
import { elevation, radius } from "../tokens/spacing";
import { typography } from "../tokens/typography";

export interface PageHeroCta {
  label: string;
  onClick: () => void;
  icon?: ReactNode;
  disabled?: boolean;
}

export interface PageHeroProps {
  icon: ReactNode;
  title: string;
  subtitle?: string;
  cta?: PageHeroCta;
  accent?: string;
  "data-testid"?: string;
}

/**
 * PageHero -- persistent page-level header with icon circle, title,
 * optional subtitle, and optional primary CTA. Does not dismiss (unlike
 * IntroCard). Used at the top of Knowledge admin tab bodies to give
 * every section a clear visual identity.
 *
 * Design Controls: DI-C5A523A7, DO-BCA9B190.
 */

function IconCircle({
  icon,
  accent,
}: {
  icon: ReactNode;
  accent: string;
}) {
  return (
    <span
      aria-hidden="true"
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        width: 48,
        height: 48,
        borderRadius: radius.md,
        background: accent + "1a",
        color: accent,
        flexShrink: 0,
        fontSize: 24,
      }}
    >
      {icon}
    </span>
  );
}

function CtaButton({
  cta,
  accent,
}: {
  cta: PageHeroCta;
  accent: string;
}) {
  const { reducedMotion } = useMotion();
  const disabled = Boolean(cta.disabled);
  return (
    <fm.button
      type="button"
      onClick={cta.onClick}
      disabled={disabled}
      whileTap={disabled ? undefined : tapScale(reducedMotion)}
      transition={springOrInstant(reducedMotion, springs.press)}
      style={ctaStyle(accent, disabled)}
    >
      {cta.icon ? (
        <span style={{ fontSize: 16, display: "inline-flex" }}>{cta.icon}</span>
      ) : null}
      {cta.label}
    </fm.button>
  );
}

function ctaStyle(accent: string, disabled: boolean): CSSProperties {
  if (disabled) {
    return {
      display: "inline-flex",
      alignItems: "center",
      gap: 6,
      appearance: "none",
      border: "1px solid " + color.text.secondary,
      borderRadius: radius.md,
      background: color.surface.divider,
      color: color.text.secondary,
      fontFamily: typography.fontFamily.body,
      fontSize: 14,
      fontWeight: 600,
      padding: "8px 16px",
      cursor: "not-allowed",
      flexShrink: 0,
      whiteSpace: "nowrap",
    };
  }
  return {
    display: "inline-flex",
    alignItems: "center",
    gap: 6,
    appearance: "none",
    border: "none",
    borderRadius: radius.md,
    background: accent,
    color: color.brand.onBrand,
    fontFamily: typography.fontFamily.body,
    fontSize: 14,
    fontWeight: 600,
    padding: "8px 16px",
    cursor: "pointer",
    flexShrink: 0,
    whiteSpace: "nowrap",
  };
}

export function PageHero({
  icon,
  title,
  subtitle,
  cta,
  accent = color.brand.primary,
  "data-testid": testId = "page-hero",
}: PageHeroProps) {
  return (
    <div
      data-testid={testId}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 16,
        background: color.surface.raised,
        border: "1px solid " + color.surface.divider,
        borderLeft: "3px solid " + accent,
        borderRadius: radius.md,
        boxShadow: elevation.card,
        padding: "16px 20px",
        marginBottom: 12,
        fontFamily: typography.fontFamily.body,
      }}
    >
      <IconCircle icon={icon} accent={accent} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            fontFamily: typography.fontFamily.heading,
            fontSize: 18,
            fontWeight: 700,
            letterSpacing: typography.letterSpacing.display,
            color: color.text.primary,
            lineHeight: 1.25,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {title}
        </div>
        {subtitle ? (
          <div
            style={{
              marginTop: 3,
              fontSize: 13,
              color: color.text.secondary,
              lineHeight: 1.45,
            }}
          >
            {subtitle}
          </div>
        ) : null}
      </div>
      {cta ? <CtaButton cta={cta} accent={accent} /> : null}
    </div>
  );
}
