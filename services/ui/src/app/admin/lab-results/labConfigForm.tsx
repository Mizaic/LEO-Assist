/**
 * Shared add-form chrome for lab config tabs.
 *
 * Atlas trace:
 *   DI: DI-3F771AFB
 */
"use client";

import type { CSSProperties, ReactNode } from "react";
import { color, typography } from "@leo/design-system/tokens";

export const formCardStyle: CSSProperties = {
  margin: 0,
  padding: 16,
  border: "1px solid " + color.text.secondary,
  borderRadius: 12,
  background: color.surface.raised,
  minWidth: 0,
};

export const formGridStyle: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1fr)",
  gap: 12,
  minWidth: 0,
};

export function FormSection({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <div style={{ minWidth: 0 }}>
      <p style={sectionTitleStyle()}>{title}</p>
      <div style={formGridStyle}>{children}</div>
    </div>
  );
}

export function ConfirmRows({ rows }: { rows: { label: string; value: string }[] }) {
  return (
    <div data-testid="lab-add-confirm" style={confirmStyle()}>
      {rows.map((row) => (
        <div key={row.label} style={{ marginBottom: 10 }}>
          <div style={sectionTitleStyle()}>{row.label}</div>
          <div style={{ marginTop: 2, color: color.text.primary }}>{row.value}</div>
        </div>
      ))}
    </div>
  );
}

export function spanTwo(): CSSProperties {
  return { gridColumn: "1 / -1", minWidth: 0 };
}

function sectionTitleStyle(): CSSProperties {
  return {
    margin: "0 0 8px",
    fontSize: 12,
    fontWeight: 700,
    letterSpacing: typography.letterSpacing.caption,
    textTransform: "uppercase",
    color: color.text.caption,
    fontFamily: typography.fontFamily.body,
  };
}

function confirmStyle(): CSSProperties {
  return {
    marginTop: 14,
    padding: "12px 14px",
    borderRadius: 12,
    border: "1px solid " + color.brand.primary,
    background: color.surface.alt,
    fontFamily: typography.fontFamily.body,
  };
}
