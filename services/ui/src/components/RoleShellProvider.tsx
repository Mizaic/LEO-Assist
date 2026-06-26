/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-8972ED05
 *   DI: DI-F0846E55
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-8972ED05")
 */
"use client";

import { useState } from "react";
import {
  MotionProvider,
  RoleGate,
  RoleProvider,
  isRole,
  type OrgOption,
  type Role,
  type RoleState,
} from "@leo/design-system";

import { useAuth } from "@/lib/authContext";

// Key must match the one in OrgContext so the picker's selection persists.
const ORG_STORAGE_KEY = "leo_selected_org";

// DI-LEO-AI-140: the role-first shell is the shipped experience. The
// `NEXT_PUBLIC_ROLE_FIRST` rollout flag was removed in Phase 6, so the
// gate opens as soon as the user is authenticated.
function toRoleState(
  selectedRole: string | null,
  allowedRoles: string[],
  needsSessionRoleChoice: boolean,
): RoleState {
  const allowed = allowedRoles.filter(isRole) as Role[];
  const selected = isRole(selectedRole) ? (selectedRole as Role) : null;
  return { selectedRole: selected, allowedRoles: allowed, needsSessionRoleChoice };
}

function toOrgOptions(
  orgs: Array<{ id: string; name: string; odsCode?: string; shortName?: string; scopeType?: string }> | undefined,
): OrgOption[] {
  return (orgs ?? []).map((o) => ({
    id: o.id,
    name: o.name,
    odsCode: o.odsCode,
    shortName: o.shortName,
    scopeType: o.scopeType,
  }));
}

function resolveInitialOrgId(
  orgs: OrgOption[],
): string {
  try {
    const stored = typeof window !== "undefined" ? localStorage.getItem(ORG_STORAGE_KEY) : null;
    if (stored && stored !== "__all__" && orgs.find((o) => o.id === stored)) return stored;
  } catch { /* noop */ }
  return orgs[0]?.id ?? "";
}

export default function RoleShellProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const { session, status, refetch: refetchAuth } = useAuth();
  const orgOptions = toOrgOptions(session?.organizations);
  const [selectedOrgId, setSelectedOrgId] = useState<string>(
    () => resolveInitialOrgId(orgOptions),
  );

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

  const userName = session?.user?.name ?? session?.user?.email ?? undefined;
  const isPlatformAdmin = session?.isPlatformAdmin ?? false;

  const handleOrgSelect = (id: string) => {
    setSelectedOrgId(id);
    try { localStorage.setItem(ORG_STORAGE_KEY, id); } catch { /* noop */ }
  };

  return (
    <MotionProvider>
      <RoleProvider
        key={roleProviderKey}
        initialState={initial}
        onSessionRoleSynced={refetchAuth}
      >
        <RoleGate
          enabled={gateEnabled}
          autoFetch={gateEnabled}
          userName={userName}
          organizations={orgOptions}
          selectedOrgId={selectedOrgId}
          onOrgSelect={handleOrgSelect}
          isPlatformAdmin={isPlatformAdmin}
        >
          {children}
        </RoleGate>
      </RoleProvider>
    </MotionProvider>
  );
}
