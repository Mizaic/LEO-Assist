/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-10218528
 *   DI: DI-FAF97A8C
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-10218528")
 */
"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { isRole, type Role } from "./types";

export interface RoleState {
  selectedRole: Role | null;
  allowedRoles: Role[];
}

export interface RoleContextValue extends RoleState {
  switchRole: (next: Role) => Promise<void>;
  refetch: () => Promise<void>;
  // Error state is exposed so the shell can show a warning and fall back
  // to the legacy nav if the role API is unreachable. See R-LEO-AI-089.
  error: string | null;
  loading: boolean;
}

const defaultValue: RoleContextValue = {
  selectedRole: null,
  allowedRoles: [],
  switchRole: async () => undefined,
  refetch: async () => undefined,
  error: null,
  loading: false,
};

export const RoleContext = createContext<RoleContextValue>(defaultValue);

export interface RoleProviderProps {
  children: ReactNode;
  initialState?: RoleState;
  // Injected to make the provider trivially testable without stubbing fetch.
  // Default implementation calls /auth/session and /auth/session/role.
  api?: RoleApi;
}

export interface RoleApi {
  getRoleState: () => Promise<RoleState>;
  setSelectedRole: (role: Role) => Promise<RoleState>;
}

export const defaultRoleApi: RoleApi = {
  async getRoleState() {
    const res = await fetch("/auth/session", { credentials: "include" });
    if (!res.ok) throw new Error(`session ${res.status}`);
    const data = await res.json();
    const allowed = Array.isArray(data?.allowed_roles)
      ? (data.allowed_roles as unknown[]).filter(isRole)
      : [];
    const selected = isRole(data?.selected_role) ? data.selected_role : null;
    return { selectedRole: selected, allowedRoles: allowed };
  },
  async setSelectedRole(role: Role) {
    const res = await fetch("/auth/session/role", {
      method: "PATCH",
      credentials: "include",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ role }),
    });
    if (!res.ok) throw new Error(`patch ${res.status}`);
    const data = await res.json();
    const allowed = Array.isArray(data?.allowed_roles)
      ? (data.allowed_roles as unknown[]).filter(isRole)
      : [];
    const selected = isRole(data?.selected_role) ? data.selected_role : role;
    return { selectedRole: selected, allowedRoles: allowed };
  },
};

export function RoleProvider({
  children,
  initialState,
  api = defaultRoleApi,
}: RoleProviderProps) {
  const [state, setState] = useState<RoleState>(
    initialState ?? { selectedRole: null, allowedRoles: [] },
  );
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(false);

  const refetch = useCallback(async () => {
    setLoading(true);
    try {
      const next = await api.getRoleState();
      setState(next);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "role_fetch_failed");
    } finally {
      setLoading(false);
    }
  }, [api]);

  const switchRole = useCallback(
    async (next: Role) => {
      if (!state.allowedRoles.includes(next)) {
        setError("role_not_allowed");
        return;
      }
      setLoading(true);
      try {
        const updated = await api.setSelectedRole(next);
        setState(updated);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : "role_switch_failed");
      } finally {
        setLoading(false);
      }
    },
    [api, state.allowedRoles],
  );

  const value = useMemo<RoleContextValue>(
    () => ({
      selectedRole: state.selectedRole,
      allowedRoles: state.allowedRoles,
      switchRole,
      refetch,
      error,
      loading,
    }),
    [state.selectedRole, state.allowedRoles, switchRole, refetch, error, loading],
  );

  return (
    <RoleContext.Provider value={value}>{children}</RoleContext.Provider>
  );
}

export function useRole(): RoleContextValue {
  return useContext(RoleContext);
}
