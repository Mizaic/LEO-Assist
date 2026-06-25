/**
 * Atlas trace:
 *   DO: DO-BCA9B190
 *   DI: DI-C5A523A7
 */
"use client";

import type { ReactNode } from "react";

import { color } from "../tokens/color";
import { radius } from "../tokens/spacing";
import { typography } from "../tokens/typography";

export interface EmptyStateCta {
  label: string;
  onClick: () => void;
  icon?: ReactNode;
}

export interface EmptyStateProps {
  icon: ReactNode;
  title: string;
  body?: string;
  cta?: EmptyStateCta;
  "data-testid"?: string;
}

/**
 * EmptyState -- illustrated empty state with a large icon circle,
 * h6 title, body copy, and optional primary CTA. Replaces plain
 * Typography empty states and dashed-border Paper boxes throughout
 * the Knowledge admin UI.
 *
 * Design Controls: DI-C5A523A7, DO-BCA9B190.
 */

function EmptyIconCircle({ icon }: { icon: ReactNode }) {
  return (
    <span
      aria-hidden="true"
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        width: 72,
        height: 72,
        borderRadius: "50%",
        background: color.surface.divider + "33",
        color: color.text.disabled,
        fontSize: 36,
        marginBottom: 16,
        flexShrink: 0,
      }}
    >
      {icon}
    </span>
  );
}

function EmptyCtaButton({ cta }: { cta: EmptyStateCta }) {
  return (
    <button
      type="button"
      onClick={cta.onClick}
      style={{
        marginTop: 16,
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        appearance: "none",
        border: "1px solid " + color.brand.primary,
        borderRadius: radius.md,
        background: color.brand.primary,
        color: "#FFFFFF",
        fontFamily: typography.fontFamily.body,
        fontSize: 14,
        fontWeight: 600,
        padding: "8px 20px",
        cursor: "pointer",
        transition: "opacity 120ms ease-out",
      }}
    >
      {cta.icon ? (
        <span style={{ fontSize: 16, display: "inline-flex" }}>{cta.icon}</span>
      ) : null}
      {cta.label}
    </button>
  );
}

export function EmptyState({
  icon,
  title,
  body,
  cta,
  "data-testid": testId = "empty-state",
}: EmptyStateProps) {
  return (
    <div
      data-testid={testId}
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        textAlign: "center",
        padding: "48px 32px",
        border: "1px dashed " + color.surface.divider,
        borderRadius: radius.md,
        background: color.surface.alt,
        fontFamily: typography.fontFamily.body,
      }}
    >
      <EmptyIconCircle icon={icon} />

      <div
        style={{
          fontSize: 16,
          fontWeight: 600,
          color: color.text.primary,
          lineHeight: 1.3,
        }}
      >
        {title}
      </div>

      {body ? (
        <div
          style={{
            marginTop: 8,
            fontSize: 14,
            color: color.text.secondary,
            lineHeight: 1.5,
            maxWidth: 380,
          }}
        >
          {body}
        </div>
      ) : null}

      {cta ? <EmptyCtaButton cta={cta} /> : null}
    </div>
  );
}
