/**
 * Atlas trace:
 *   DO: DO-CFA1ED55
 *   DI: DI-340279C1
 */
import type { CSSProperties } from "react";
import { color, radius, typography } from "@leo/design-system/tokens";

export function Field({
  id,
  label,
  value,
  onChange,
  placeholder,
  multiline,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (next: string) => void;
  placeholder: string;
  multiline?: boolean;
}) {
  const shared = fieldStyle();
  return (
    <label htmlFor={id} style={{ display: "grid", gap: 6 }}>
      <span style={labelStyle()}>{label}</span>
      {multiline ? (
        <textarea
          id={id}
          rows={2}
          value={value}
          placeholder={placeholder}
          onChange={(e) => onChange(e.target.value)}
          style={{ ...shared, minHeight: 64, resize: "vertical" }}
        />
      ) : (
        <input
          id={id}
          value={value}
          placeholder={placeholder}
          onChange={(e) => onChange(e.target.value)}
          style={shared}
        />
      )}
    </label>
  );
}

export function titleStyle(): CSSProperties {
  return {
    margin: 0,
    fontFamily: typography.fontFamily.heading,
    fontSize: 20,
    fontWeight: 700,
    letterSpacing: typography.letterSpacing.display,
    color: color.text.primary,
  };
}

export function ghostBtn(): CSSProperties {
  return {
    border: "1px solid " + color.text.secondary,
    background: color.surface.raised,
    borderRadius: radius.sm,
    padding: "8px 14px",
    fontWeight: 600,
    cursor: "pointer",
    fontFamily: typography.fontFamily.body,
  };
}

export function primaryBtn(disabled: boolean): CSSProperties {
  if (disabled) {
    return {
      border: "1px solid " + color.text.secondary,
      background: color.surface.divider,
      color: color.text.secondary,
      borderRadius: radius.sm,
      padding: "8px 14px",
      fontWeight: 600,
      cursor: "not-allowed",
      fontFamily: typography.fontFamily.body,
    };
  }
  return {
    border: 0,
    background: color.brand.primary,
    color: color.brand.onBrand,
    borderRadius: radius.sm,
    padding: "8px 14px",
    fontWeight: 600,
    cursor: "pointer",
    fontFamily: typography.fontFamily.body,
  };
}

function labelStyle(): CSSProperties {
  return {
    fontSize: 12,
    fontWeight: 700,
    letterSpacing: typography.letterSpacing.caption,
    color: color.text.secondary,
    fontFamily: typography.fontFamily.body,
  };
}

function fieldStyle(): CSSProperties {
  return {
    width: "100%",
    boxSizing: "border-box",
    border: "1px solid " + color.text.secondary,
    borderRadius: radius.sm,
    padding: "10px 12px",
    background: color.surface.raised,
    color: color.text.primary,
    fontSize: 14,
    fontFamily: typography.fontFamily.body,
  };
}
