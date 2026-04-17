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
  const { refetch, selectedRole, allowedRoles, error } = useRole();

  useEffect(() => {
    if (autoFetch) {
      void refetch();
    }
  }, [autoFetch, refetch]);

  if (!enabled) return <>{children}</>;

  const pickerNeeded =
    error == null && selectedRole == null && allowedRoles.length > 0;

  return (
    <>
      {children}
      {pickerNeeded ? <RolePicker /> : null}
    </>
  );
}
