/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-CD075278
 *   DI: DI-B5EEBC4C
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-CD075278")
 */
"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useAuth } from "@/lib/authContext";
import type { OrgInfo } from "@/lib/authContext";

interface OrgContextValue {
  /** Currently selected organization (null if none / loading) */
  currentOrg: OrgInfo | null;
  /** All organizations the user can access */
  organizations: OrgInfo[];
  /** True if user is a platform admin (can see all orgs) */
  isPlatformAdmin: boolean;
  /** Switch to a different organization */
  switchOrg: (orgId: string) => void;
  /** "All Organizations" mode (platform admins only, orgId = undefined) */
  viewAll: boolean;
  setViewAll: (val: boolean) => void;
}

const OrgContext = createContext<OrgContextValue | null>(null);

const STORAGE_KEY = "leo_selected_org";

export function OrgProvider({ children }: { children: ReactNode }) {
  const { session } = useAuth();
  const organizations: OrgInfo[] = session?.organizations ?? [];
  const isPlatformAdmin: boolean = session?.isPlatformAdmin ?? false;

  const [selectedOrgId, setSelectedOrgId] = useState<string | null>(null);
  const [viewAll, setViewAll] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "__all__") {
      setViewAll(true);
      setSelectedOrgId(null);
    } else if (stored) {
      setSelectedOrgId(stored);
    }
  }, []);

  useEffect(() => {
    if (organizations.length > 0 && !selectedOrgId && !viewAll) {
      const stored = localStorage.getItem(STORAGE_KEY);
      const match = stored
        ? organizations.find((o) => o.id === stored)
        : null;
      if (match) {
        setSelectedOrgId(match.id);
      } else if (!isPlatformAdmin) {
        setSelectedOrgId(organizations[0].id);
        localStorage.setItem(STORAGE_KEY, organizations[0].id);
      } else {
        setViewAll(true);
        localStorage.setItem(STORAGE_KEY, "__all__");
      }
    }
  }, [organizations, selectedOrgId, viewAll, isPlatformAdmin]);

  // Platform admin with no org rows in session still needs "All organisations" mode;
  // the org picker is shown (AppShell) but the previous effect never ran when length is 0.
  useEffect(() => {
    if (!isPlatformAdmin || organizations.length > 0) return;
    setViewAll(true);
    setSelectedOrgId(null);
    localStorage.setItem(STORAGE_KEY, "__all__");
  }, [isPlatformAdmin, organizations.length]);

  useEffect(() => {
    if (isPlatformAdmin || !viewAll || organizations.length === 0) return;
    const stored = localStorage.getItem(STORAGE_KEY);
    const match = stored
      ? organizations.find((o) => o.id === stored)
      : null;
    const nextOrgId = match?.id ?? organizations[0].id;
    setViewAll(false);
    setSelectedOrgId(nextOrgId);
    localStorage.setItem(STORAGE_KEY, nextOrgId);
  }, [isPlatformAdmin, organizations, viewAll]);

  const switchOrg = useCallback(
    (orgId: string) => {
      if (orgId === "__all__") {
        setViewAll(true);
        setSelectedOrgId(null);
        localStorage.setItem(STORAGE_KEY, "__all__");
      } else {
        setViewAll(false);
        setSelectedOrgId(orgId);
        localStorage.setItem(STORAGE_KEY, orgId);
      }
    },
    [],
  );

  const currentOrg = useMemo(
    () => organizations.find((o) => o.id === selectedOrgId) ?? null,
    [organizations, selectedOrgId],
  );

  const value: OrgContextValue = {
    currentOrg,
    organizations,
    isPlatformAdmin,
    switchOrg,
    viewAll,
    setViewAll,
  };

  return <OrgContext.Provider value={value}>{children}</OrgContext.Provider>;
}

export function useOrg() {
  const ctx = useContext(OrgContext);
  if (!ctx) {
    throw new Error("useOrg must be used within OrgProvider");
  }
  return ctx;
}

/**
 * Returns the orgId to pass to API calls.
 * - If viewAll is true (platform admin), returns undefined (no filter).
 * - Otherwise returns the selected org's id.
 */
export function useOrgId(): string | undefined {
  const { currentOrg, viewAll } = useOrg();
  if (viewAll) return undefined;
  return currentOrg?.id;
}
