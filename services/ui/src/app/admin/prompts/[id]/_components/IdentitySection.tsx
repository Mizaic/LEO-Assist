/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2C03CA0E
 *   DI: DI-3F771AFB
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C03CA0E")
 */
"use client";

/**
 * Name + description + verification toggle for the AI Instructions editor.
 * Extracted from prompts/[id]/page.tsx (Phase 4b decomposition).
 */

import type { CSSProperties } from "react";
import Tooltip from "@mui/material/Tooltip";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import { color, elevation, radius, typography } from "@leo/design-system/tokens";

interface IdentitySectionProps {
  name: string;
  description: string;
  verification: boolean;
  onNameChange: (next: string) => void;
  onDescriptionChange: (next: string) => void;
  onVerificationChange: (next: boolean) => void;
}

export function IdentitySection({
  name,
  description,
  verification,
  onNameChange,
  onDescriptionChange,
  onVerificationChange,
}: IdentitySectionProps) {
  return (
    <div style={cardStyle()} data-testid="prompt-identity">
      <Field
        id="prompt-name"
        label="Name"
        value={name}
        onChange={onNameChange}
        placeholder="e.g. Standard clinical coder, Referral letter extractor"
      />
      <Field
        id="prompt-purpose"
        label="What is this for?"
        value={description}
        onChange={onDescriptionChange}
        placeholder="A plain English summary of what these instructions do -- shown on the cards page."
        multiline
      />
      <VerificationToggle
        checked={verification}
        onChange={onVerificationChange}
      />
    </div>
  );
}

function Field({
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

function VerificationToggle({
  checked,
  onChange,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
}) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label="Double-check results"
        onClick={() => onChange(!checked)}
        style={switchStyle(checked)}
      >
        <span style={switchThumb(checked)} />
      </button>
      <span style={{ fontSize: 14, color: color.text.primary, fontFamily: typography.fontFamily.body }}>
        Double-check results
      </span>
      <Tooltip title="When on, a second AI check runs after the first to confirm accuracy before saving.">
        <InfoOutlinedIcon sx={{ fontSize: 15, color: color.text.caption }} />
      </Tooltip>
      {checked ? (
        <span style={onChip()}>
          <CheckCircleOutlineIcon sx={{ fontSize: 13 }} />
          On
        </span>
      ) : null}
    </div>
  );
}

function cardStyle(): CSSProperties {
  return {
    display: "grid",
    gap: 14,
    padding: 20,
    marginBottom: 12,
    background: color.surface.raised,
    borderRadius: radius.md,
    boxShadow: elevation.card,
    border: "1px solid " + color.surface.divider,
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

function switchStyle(on: boolean): CSSProperties {
  return {
    width: 40,
    height: 22,
    border: 0,
    borderRadius: 999,
    padding: 2,
    background: on ? color.status.success : color.surface.divider,
    cursor: "pointer",
    position: "relative",
  };
}

function switchThumb(on: boolean): CSSProperties {
  return {
    display: "block",
    width: 18,
    height: 18,
    borderRadius: 999,
    background: color.surface.raised,
    transform: on ? "translateX(18px)" : "translateX(0)",
  };
}

function onChip(): CSSProperties {
  return {
    display: "inline-flex",
    alignItems: "center",
    gap: 4,
    fontSize: 11,
    fontWeight: 600,
    color: color.status.success,
    background: "rgba(4, 120, 87, 0.12)",
    borderRadius: 999,
    padding: "2px 8px",
  };
}
