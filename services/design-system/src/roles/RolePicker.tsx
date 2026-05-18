/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-10218528
 *   DI: DI-FAF97A8C
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-10218528")
 */
"use client";

import { useEffect, useRef, useState } from "react";

import { ROLE_COPY, type Role } from "./types";
import { useRole } from "./RoleContext";

export interface RolePickerProps {
  // When true the picker never auto-dismisses (useful for testing). In
  // production the picker closes as soon as the user confirms a role.
  pinned?: boolean;
  onConfirm?: (role: Role) => void;
}

// Lightweight, dependency-free dialog so the picker can live in the shared
// package without pulling MUI. Styled with inline CSS tokens so it looks
// consistent regardless of the consuming app's theme.
const overlayStyle: React.CSSProperties = {
  position: "fixed",
  inset: 0,
  background: "rgba(15, 23, 42, 0.45)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  zIndex: 1400,
};

const dialogStyle: React.CSSProperties = {
  background: "#FFFFFF",
  borderRadius: 12,
  padding: 24,
  width: "min(480px, 92vw)",
  boxShadow: "0 24px 48px rgba(15, 23, 42, 0.18)",
  fontFamily:
    "var(--font-dm-sans), 'DM Sans', -apple-system, system-ui, sans-serif",
  color: "#0F172A",
};

const optionStyle: React.CSSProperties = {
  display: "block",
  width: "100%",
  textAlign: "left",
  padding: 12,
  borderRadius: 8,
  border: "1px solid #E2E8F0",
  background: "#FFFFFF",
  marginBottom: 8,
  cursor: "pointer",
  fontFamily: "inherit",
  fontSize: 16,
};

const primaryButton: React.CSSProperties = {
  background: "#1D4ED8",
  color: "#FFFFFF",
  border: "none",
  borderRadius: 8,
  padding: "10px 20px",
  fontWeight: 600,
  fontSize: 16,
  cursor: "pointer",
  minHeight: 44,
};

export function RolePicker({ pinned = false, onConfirm }: RolePickerProps) {
  const { selectedRole, allowedRoles, needsSessionRoleChoice, switchRole, loading } =
    useRole();
  const [choice, setChoice] = useState<Role | null>(() => {
    if (selectedRole != null && allowedRoles.includes(selectedRole)) {
      return selectedRole;
    }
    return null;
  });
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Focus the first option on mount so keyboard users land inside the dialog.
    const first = dialogRef.current?.querySelector<HTMLButtonElement>(
      "button[data-role-option]",
    );
    first?.focus();
  }, []);

  useEffect(() => {
    if (!needsSessionRoleChoice) return;
    if (choice != null) return;
    if (selectedRole != null && allowedRoles.includes(selectedRole)) {
      setChoice(selectedRole);
    }
  }, [needsSessionRoleChoice, selectedRole, allowedRoles, choice]);

  const shouldRender =
    pinned || selectedRole == null || needsSessionRoleChoice;
  if (!shouldRender) return null;
  if (allowedRoles.length === 0) return null;

  const confirm = async () => {
    if (!choice) return;
    await switchRole(choice);
    onConfirm?.(choice);
  };

  return (
    <div style={overlayStyle} data-testid="role-picker-overlay">
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="role-picker-title"
        aria-describedby="role-picker-desc"
        style={dialogStyle}
      >
        <h2
          id="role-picker-title"
          style={{ fontSize: 24, margin: 0, marginBottom: 8 }}
        >
          Pick your role
        </h2>
        <p
          id="role-picker-desc"
          style={{ fontSize: 16, margin: 0, marginBottom: 16, color: "#596577" }}
        >
          We use your role to show you the right home screen. You can change
          this later from the top right.
        </p>
        <div role="radiogroup" aria-label="Role">
          {allowedRoles.map((r) => {
            const copy = ROLE_COPY[r];
            const selected = choice === r;
            return (
              <button
                key={r}
                type="button"
                data-role-option={r}
                role="radio"
                aria-checked={selected}
                onClick={() => setChoice(r)}
                style={{
                  ...optionStyle,
                  borderColor: selected ? "#1D4ED8" : "#E2E8F0",
                  background: selected ? "#EFF6FF" : "#FFFFFF",
                }}
              >
                <span style={{ display: "block", fontWeight: 600 }}>
                  {copy.label}
                </span>
                <span style={{ display: "block", color: "#596577", marginTop: 4 }}>
                  {copy.description}
                </span>
              </button>
            );
          })}
        </div>
        <div
          style={{
            marginTop: 16,
            display: "flex",
            justifyContent: "flex-end",
            gap: 8,
          }}
        >
          <button
            type="button"
            onClick={confirm}
            disabled={!choice || loading}
            style={{
              ...primaryButton,
              opacity: !choice || loading ? 0.6 : 1,
              cursor: !choice || loading ? "not-allowed" : "pointer",
            }}
          >
            Continue
          </button>
        </div>
      </div>
    </div>
  );
}
