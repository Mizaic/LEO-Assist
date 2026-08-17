/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-8972ED05
 *   DI: DI-F0846E55
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-8972ED05")
 */
"use client";

import type { ReactNode } from "react";
import { MotionProvider, RoleGate, RoleProvider, isRole, type Role, type RoleState } from "@leo/design-system";

import { useAuth } from "@/lib/authContext";

function toRoleState(
  selectedRole: string | null,
  allowedRoles: string[],
  needsSessionRoleChoice: boolean,
): RoleState {
  const allowed = allowedRoles.filter(isRole) as Role[];
  const selected = isRole(selectedRole) ? (selectedRole as Role) : null;
  return { selectedRole: selected, allowedRoles: allowed, needsSessionRoleChoice };
}

export default function RoleShellProvider({
  children,
}: {
  children: ReactNode;
}) {
  const { session, status, refetch: refetchAuth } = useAuth();
  const initial = toRoleState(
    session?.selectedRole ?? null,
    session?.allowedRoles ?? [],
    session?.needsRoleChoice ?? false,
  );
  const gateEnabled = status === "authenticated";
  const roleProviderKey = [
    session?.user?.email ?? "",
    String(session?.needsRoleChoice ?? false),
    (session?.allowedRoles ?? []).slice().sort().join(","),
  ].join("|");

  return (
    <MotionProvider>
      <RoleProvider
        key={roleProviderKey}
        initialState={initial}
        onSessionRoleSynced={refetchAuth}
      >
        <RoleGate enabled={gateEnabled} autoFetch={gateEnabled}>
          {children}
        </RoleGate>
      </RoleProvider>
    </MotionProvider>
  );
}
