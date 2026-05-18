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

import { RolePicker } from "./RolePicker";
import { useRole } from "./RoleContext";

export interface RoleGateProps {
  children: ReactNode;
  // Default true. When false the gate renders children without ever
  // presenting the picker - useful for unauthenticated routes or when the
  // role-first feature flag is off.
  enabled?: boolean;
  // Fire the one-time session fetch on mount. The app shell usually already
  // manages this via AuthProvider, but supplying it via the gate keeps
  // stand-alone usage straightforward.
  autoFetch?: boolean;
}

export function RoleGate({
  children,
  enabled = true,
  autoFetch = false,
}: RoleGateProps) {
  const { refetch, selectedRole, allowedRoles, needsSessionRoleChoice, error } =
    useRole();

  useEffect(() => {
    if (autoFetch) {
      void refetch();
    }
  }, [autoFetch, refetch]);

  if (!enabled) return <>{children}</>;

  const pickerNeeded =
    error == null &&
    allowedRoles.length > 0 &&
    (selectedRole == null || needsSessionRoleChoice);

  return (
    <>
      {children}
      {pickerNeeded ? <RolePicker /> : null}
    </>
  );
}
