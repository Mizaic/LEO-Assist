/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-10218528
 *   DI: DI-FAF97A8C
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-10218528")
 */
"use client";

import { useState } from "react";

import { ROLE_COPY, type Role } from "./types";
import { useRole } from "./RoleContext";

export interface RoleSwitcherProps {
  // Hook point for the app shell to warn the user about unsaved work before
  // the role switch actually commits. Returning false cancels the switch.
  onBeforeSwitch?: (next: Role) => boolean | Promise<boolean>;
  onAfterSwitch?: (next: Role) => void;
}

const buttonStyle: React.CSSProperties = {
  background: "#FFFFFF",
  color: "#0F172A",
  border: "1px solid #E2E8F0",
  borderRadius: 8,
  padding: "6px 12px",
  fontSize: 14,
  fontWeight: 600,
  cursor: "pointer",
  minHeight: 36,
  display: "inline-flex",
  alignItems: "center",
  gap: 6,
  fontFamily:
    "var(--font-dm-sans), 'DM Sans', -apple-system, system-ui, sans-serif",
};

const menuStyle: React.CSSProperties = {
  position: "absolute",
  top: "100%",
  right: 0,
  marginTop: 6,
  background: "#FFFFFF",
  borderRadius: 8,
  boxShadow:
    "0 8px 16px rgba(15, 23, 42, 0.08), 0 2px 4px rgba(15, 23, 42, 0.06)",
  padding: 4,
  minWidth: 220,
  zIndex: 1300,
};

const optionStyle: React.CSSProperties = {
  display: "block",
  width: "100%",
  textAlign: "left",
  padding: "8px 12px",
  border: "none",
  background: "transparent",
  borderRadius: 6,
  cursor: "pointer",
  fontSize: 14,
  fontFamily: "inherit",
  color: "#0F172A",
};

export function RoleSwitcher({
  onBeforeSwitch,
  onAfterSwitch,
}: RoleSwitcherProps = {}) {
  const { selectedRole, allowedRoles, switchRole } = useRole();
  const [open, setOpen] = useState<boolean>(false);

  if (allowedRoles.length <= 1) return null;

  const current = selectedRole ? ROLE_COPY[selectedRole].label : "No role";

  const handleChoose = async (next: Role) => {
    setOpen(false);
    if (next === selectedRole) return;
    if (onBeforeSwitch) {
      const allowed = await onBeforeSwitch(next);
      if (!allowed) return;
    }
    await switchRole(next);
    onAfterSwitch?.(next);
  };

  return (
    <div style={{ position: "relative" }}>
      <button
        type="button"
        aria-label="Switch role"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((o: boolean) => !o)}
        style={buttonStyle}
      >
        <span aria-hidden="true">{current}</span>
        <span aria-hidden="true" style={{ fontSize: 12, color: "#596577" }}>
          {"\u25BE"}
        </span>
      </button>
      {open ? (
        <div role="menu" aria-label="Available roles" style={menuStyle}>
          {allowedRoles.map((r) => (
            <button
              key={r}
              type="button"
              role="menuitemradio"
              aria-checked={r === selectedRole}
              onClick={() => handleChoose(r)}
              style={{
                ...optionStyle,
                background: r === selectedRole ? "#EFF6FF" : "transparent",
              }}
            >
              {ROLE_COPY[r].label}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
