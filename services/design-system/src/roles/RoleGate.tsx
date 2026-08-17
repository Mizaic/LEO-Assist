/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-124AC2C4
 *   DI: DI-613A48DA
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-124AC2C4")
 */
"use client";

import { useEffect, type ReactNode } from "react";

import { type RolePickerProps } from "./RolePicker";
import { useRole } from "./RoleContext";

export interface RoleGateProps
  extends Pick<
    RolePickerProps,
    "userName" | "organizations" | "selectedOrgId" | "onOrgSelect" | "isPlatformAdmin"
  > {
  children: ReactNode;
  enabled?: boolean;
  autoFetch?: boolean;
}

export function RoleGate({
  children,
  enabled = true,
  autoFetch = false,
}: RoleGateProps) {
  const { refetch, selectedRole, allowedRoles, needsSessionRoleChoice, error, switchRole } =
    useRole();

  useEffect(() => {
    if (autoFetch) {
      void refetch();
    }
  }, [autoFetch, refetch]);

  useEffect(() => {
    if (!enabled || error != null) return;
    if (allowedRoles.length === 0) return;
    if (selectedRole != null && !needsSessionRoleChoice) return;
    const next = selectedRole ?? allowedRoles[0];
    if (!next) return;
    void switchRole(next);
  }, [
    allowedRoles,
    enabled,
    error,
    needsSessionRoleChoice,
    selectedRole,
    switchRole,
  ]);

  return <>{children}</>;
}
