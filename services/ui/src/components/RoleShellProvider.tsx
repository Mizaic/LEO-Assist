/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-8972ED05
 *   DI: DI-F0846E55
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-8972ED05")
 */
"use client";

import {
  MotionProvider,
  RoleGate,
  RoleProvider,
  isRole,
  type Role,
  type RoleState,
} from "@leo/design-system";

import { useAuth } from "@/lib/authContext";

// DI-LEO-AI-140: the role-first shell is the shipped experience. The
// `NEXT_PUBLIC_ROLE_FIRST` rollout flag was removed in Phase 6, so the
// gate opens as soon as the user is authenticated.
function toRoleState(
  selectedRole: string | null,
  allowedRoles: string[],
): RoleState {
  const allowed = allowedRoles.filter(isRole) as Role[];
  const selected = isRole(selectedRole) ? (selectedRole as Role) : null;
  return { selectedRole: selected, allowedRoles: allowed };
}

export default function RoleShellProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const { session, status } = useAuth();
  const initial = toRoleState(
    session?.selectedRole ?? null,
    session?.allowedRoles ?? [],
  );
  const gateEnabled = status === "authenticated";
  return (
    <MotionProvider>
      <RoleProvider initialState={initial}>
        <RoleGate enabled={gateEnabled}>{children}</RoleGate>
      </RoleProvider>
    </MotionProvider>
  );
}
