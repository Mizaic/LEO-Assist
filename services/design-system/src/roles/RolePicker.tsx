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

import { CANONICAL_ROLES, ROLE_COPY, type OrgOption, type Role, type RoleCategory } from "./types";
import { useRole } from "./RoleContext";

export interface RolePickerProps {
  pinned?: boolean;
  onConfirm?: (role: Role) => void;
  userName?: string;
  organizations?: OrgOption[];
  selectedOrgId?: string;
  onOrgSelect?: (orgId: string) => void;
  /** Platform admins see all roles and can impersonate any of them. */
  isPlatformAdmin?: boolean;
}

// -- Styles -----------------------------------------------------------------

const S = {
  page: {
    position: "fixed" as const,
    inset: 0,
    background: "#F8FAFC",
    overflowY: "auto" as const,
    zIndex: 1400,
    fontFamily: "var(--font-dm-sans), 'DM Sans', -apple-system, system-ui, sans-serif",
    color: "#0F172A",
  },
  inner: {
    maxWidth: 760,
    margin: "0 auto",
    padding: "40px 24px 80px",
  },
  avatar: {
    width: 56,
    height: 56,
    borderRadius: "50%",
    background: "#1D4ED8",
    color: "#fff",
    display: "flex" as const,
    alignItems: "center" as const,
    justifyContent: "center" as const,
    fontWeight: 700,
    fontSize: 22,
    margin: "0 auto 12px",
  },
  welcome: { textAlign: "center" as const, marginBottom: 24 },
  welcomeTitle: { fontSize: 22, fontWeight: 700, margin: "0 0 4px" },
  welcomeSub: { fontSize: 14, color: "#64748B", margin: 0 },
  steps: {
    display: "flex" as const,
    alignItems: "center" as const,
    justifyContent: "center" as const,
    gap: 8,
    marginBottom: 24,
  },
  orgBanner: {
    display: "flex" as const,
    alignItems: "center" as const,
    gap: 12,
    background: "#EFF6FF",
    border: "1px solid #BFDBFE",
    borderRadius: 10,
    padding: "12px 16px",
    marginBottom: 24,
  },
  orgBannerText: { flex: 1, minWidth: 0 },
  orgLabel: { fontSize: 11, color: "#64748B", textTransform: "uppercase" as const, fontWeight: 600, letterSpacing: "0.05em", margin: 0 },
  orgName: { fontSize: 15, fontWeight: 700, margin: "2px 0 0", whiteSpace: "nowrap" as const, overflow: "hidden" as const, textOverflow: "ellipsis" as const },
  stepHeading: { fontSize: 20, fontWeight: 700, margin: "0 0 4px" },
  stepSub: { fontSize: 14, color: "#64748B", margin: "0 0 16px" },
  search: {
    width: "100%",
    boxSizing: "border-box" as const,
    padding: "10px 16px 10px 40px",
    border: "1px solid #E2E8F0",
    borderRadius: 8,
    fontSize: 14,
    background: "#fff",
    outline: "none" as const,
    marginBottom: 24,
  },
  searchWrap: { position: "relative" as const, marginBottom: 24 },
  searchIcon: { position: "absolute" as const, left: 14, top: "50%", transform: "translateY(-50%)", color: "#94A3B8", fontSize: 16, pointerEvents: "none" as const },
  category: { marginBottom: 28 },
  catHeader: { display: "flex" as const, alignItems: "center" as const, gap: 10, borderBottom: "2px solid #1D4ED8", paddingBottom: 8, marginBottom: 14 },
  catTitle: { fontSize: 15, fontWeight: 700, color: "#1D4ED8", margin: 0 },
  catBadge: {
    background: "#DBEAFE",
    color: "#1D4ED8",
    borderRadius: 20,
    padding: "2px 8px",
    fontSize: 12,
    fontWeight: 600,
  },
  grid: {
    display: "grid" as const,
    gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))",
    gap: 12,
  },
  card: (selected: boolean): React.CSSProperties => ({
    position: "relative",
    background: selected ? "#EFF6FF" : "#fff",
    border: `1px solid ${selected ? "#1D4ED8" : "#E2E8F0"}`,
    borderRadius: 10,
    padding: "14px 14px 12px",
    cursor: "pointer",
    textAlign: "left",
    fontFamily: "inherit",
    width: "100%",
    transition: "border-color 0.1s, background 0.1s",
  }),
  cardIcon: { fontSize: 28, marginBottom: 6, display: "block" as const },
  cardLabel: { fontWeight: 600, fontSize: 14, margin: "0 0 4px", display: "block" as const },
  cardDesc: { fontSize: 12, color: "#64748B", margin: 0, lineHeight: 1.4 },
  star: (fav: boolean): React.CSSProperties => ({
    position: "absolute",
    top: 8,
    right: 8,
    cursor: "pointer",
    fontSize: 16,
    color: fav ? "#F59E0B" : "#CBD5E1",
    padding: 2,
    lineHeight: 1,
    userSelect: "none",
  }),
  footer: { marginTop: 32, display: "flex" as const, justifyContent: "flex-end" as const },
  primaryBtn: (disabled: boolean): React.CSSProperties => ({
    background: "#1D4ED8",
    color: "#fff",
    border: "none",
    borderRadius: 8,
    padding: "10px 28px",
    fontWeight: 600,
    fontSize: 15,
    cursor: disabled ? "not-allowed" : "pointer",
    opacity: disabled ? 0.55 : 1,
    minHeight: 44,
    fontFamily: "inherit",
  }),
  outlineBtn: {
    background: "#fff",
    color: "#334155",
    border: "1px solid #E2E8F0",
    borderRadius: 8,
    padding: "10px 20px",
    fontWeight: 600,
    fontSize: 14,
    cursor: "pointer",
    minHeight: 44,
    fontFamily: "inherit",
  } as React.CSSProperties,
  changeBtn: {
    background: "#fff",
    color: "#1D4ED8",
    border: "1px solid #BFDBFE",
    borderRadius: 8,
    padding: "6px 14px",
    fontSize: 13,
    fontWeight: 600,
    cursor: "pointer",
    whiteSpace: "nowrap" as const,
    fontFamily: "inherit",
  },
};

// -- Helpers ----------------------------------------------------------------

function orgLabel(org: OrgOption): string {
  const parts = [org.odsCode, org.name].filter(Boolean);
  if (org.shortName) parts.push(`(${org.shortName})`);
  return parts.join(" ");
}

function StepPill({ n, label, active, done }: { n: number; label: string; active: boolean; done: boolean }) {
  const bg = done ? "#22C55E" : active ? "#1D4ED8" : "#E2E8F0";
  const fg = done || active ? "#fff" : "#94A3B8";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <span style={{ width: 24, height: 24, borderRadius: "50%", background: bg, color: fg, display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 12, fontWeight: 700 }}>
        {done ? "✓" : n}
      </span>
      <span style={{ fontSize: 13, fontWeight: 600, color: active ? "#0F172A" : "#94A3B8" }}>{label}</span>
    </div>
  );
}

function StepDivider() {
  return <span style={{ color: "#CBD5E1", fontSize: 18 }}>→</span>;
}

function useFavourites() {
  const [favs, setFavs] = useState<Set<string>>(() => {
    try {
      const raw = typeof window !== "undefined" ? localStorage.getItem("leo_role_favs") : null;
      return new Set(raw ? JSON.parse(raw) : []);
    } catch {
      return new Set();
    }
  });

  const toggle = (role: string) => {
    setFavs((prev) => {
      const next = new Set(prev);
      next.has(role) ? next.delete(role) : next.add(role);
      try { localStorage.setItem("leo_role_favs", JSON.stringify([...next])); } catch { /* noop */ }
      return next;
    });
  };

  return { favs, toggle };
}

function groupByCategory(roles: Role[]): Array<{ category: RoleCategory; roles: Role[] }> {
  const order: RoleCategory[] = ["Clinical Roles", "Administration & Management", "System & Onboarding", "Other"];
  const map = new Map<RoleCategory, Role[]>();
  for (const r of roles) {
    const cat = ROLE_COPY[r].category;
    if (!map.has(cat)) map.set(cat, []);
    map.get(cat)!.push(r);
  }
  return order.filter((c) => map.has(c)).map((category) => ({ category, roles: map.get(category)! }));
}

// -- OrgStep ----------------------------------------------------------------

const ORG_ICON = (
  <svg width="36" height="36" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <rect x="3" y="7" width="18" height="13" rx="2" stroke="#1D4ED8" strokeWidth="1.5" fill="#EFF6FF"/>
    <path d="M8 20V13h8v7" stroke="#1D4ED8" strokeWidth="1.5" strokeLinejoin="round"/>
    <path d="M3 9l9-6 9 6" stroke="#1D4ED8" strokeWidth="1.5" strokeLinejoin="round"/>
  </svg>
);

function OrgStep({ orgs, selectedId, onSelect }: { orgs: OrgOption[]; selectedId: string; onSelect: (id: string) => void }) {
  return (
    <div>
      <p style={S.stepSub}>Select the organisation you want to work with. This determines which team and resources you&apos;ll have access to.</p>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: 12 }}>
        {orgs.map((o) => {
          const selected = o.id === selectedId;
          return (
            <button key={o.id} type="button" onClick={() => onSelect(o.id)}
              style={{
                ...S.card(selected),
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                gap: 8,
                padding: "24px 16px 20px",
                textAlign: "center",
                minHeight: 120,
              }}>
              <span style={{ color: selected ? "#1D4ED8" : "#94A3B8" }}>{ORG_ICON}</span>
              <span style={{ ...S.cardLabel, textAlign: "center" }}>{o.name}</span>
              {o.odsCode && (
                <span style={{ ...S.cardDesc, textAlign: "center" }}>
                  {o.odsCode}{o.shortName ? ` (${o.shortName})` : ""}
                </span>
              )}
              <span style={{ fontSize: 11, color: selected ? "#1D4ED8" : "#94A3B8", fontWeight: 500, marginTop: 2 }}>
                {selected ? "Selected" : "Click to select"}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

// -- RoleStep ---------------------------------------------------------------

function RoleStep({ allowedRoles, choice, onChoice, query, onQuery, favs, onToggleFav }:
  { allowedRoles: Role[]; choice: Role | null; onChoice: (r: Role) => void; query: string; onQuery: (q: string) => void; favs: Set<string>; onToggleFav: (r: string) => void }) {
  const allowedSet = new Set<string>(allowedRoles);
  const allRoles = CANONICAL_ROLES as unknown as Role[];

  const filtered = allRoles.filter((r) => {
    if (!query) return true;
    const q = query.toLowerCase();
    const copy = ROLE_COPY[r];
    return copy.label.toLowerCase().includes(q) || copy.description.toLowerCase().includes(q) || copy.category.toLowerCase().includes(q);
  });

  const groups = groupByCategory(filtered);
  const availableCount = filtered.filter((r) => allowedSet.has(r)).length;

  return (
    <div>
      <p style={S.stepSub}>
        Click the role that best describes what you will be doing. You will proceed automatically once you click.
        {allowedSet.size < CANONICAL_ROLES.length && (
          <span style={{ color: "#94A3B8" }}> Grayed-out roles are not assigned to your account.</span>
        )}
      </p>
      <div style={S.searchWrap}>
        <span style={S.searchIcon}>🔍</span>
        <input
          type="search"
          placeholder="Search roles by name, category, or description..."
          value={query}
          onChange={(e) => onQuery(e.target.value)}
          style={S.search}
          aria-label="Search roles"
        />
      </div>
      {availableCount === 0 && query && (
        <p style={{ color: "#94A3B8", textAlign: "center", padding: "32px 0" }}>No available roles match your search.</p>
      )}
      {groups.map(({ category, roles: grpRoles }) => {
        const available = grpRoles.filter((r) => allowedSet.has(r));
        return (
          <div key={category} style={S.category}>
            <div style={S.catHeader}>
              <h3 style={S.catTitle}>{category}</h3>
              <span style={S.catBadge}>{available.length} {available.length === 1 ? "role" : "roles"}</span>
            </div>
            <div style={S.grid}>
              {grpRoles.map((r) => {
                const copy = ROLE_COPY[r];
                const selected = choice === r;
                const available = allowedSet.has(r);
                return (
                  <button key={r} type="button" data-role-option={r} role="radio" aria-checked={selected}
                    disabled={!available}
                    onClick={() => available && onChoice(r)}
                    style={{
                      ...S.card(selected),
                      opacity: available ? 1 : 0.38,
                      cursor: available ? "pointer" : "not-allowed",
                      filter: available ? undefined : "grayscale(0.4)",
                    }}>
                    <span role="img" aria-label={favs.has(r) ? "Remove from favourites" : "Add to favourites"}
                      onClick={(e) => { e.stopPropagation(); if (available) onToggleFav(r); }} style={S.star(favs.has(r))}>
                      {favs.has(r) ? "★" : "☆"}
                    </span>
                    <span style={S.cardIcon}>{copy.icon}</span>
                    <span style={S.cardLabel}>{copy.label}</span>
                    <span style={S.cardDesc}>{copy.description}</span>
                    {!available && (
                      <span style={{ fontSize: 10, color: "#94A3B8", marginTop: 4, display: "block", fontWeight: 500 }}>
                        Not assigned
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// -- Main component ---------------------------------------------------------

export function RolePicker({ pinned = false, onConfirm, userName, organizations = [], selectedOrgId, onOrgSelect, isPlatformAdmin = false }: RolePickerProps) {
  const { selectedRole, allowedRoles, needsSessionRoleChoice, switchRole, loading } = useRole();
  // Platform admins skip the org step -- they work across all orgs.
  const multiOrg = !isPlatformAdmin && organizations.length > 1;
  const [step, setStep] = useState<1 | 2>(multiOrg ? 1 : 2);
  const [currentOrgId, setCurrentOrgId] = useState<string>(
    selectedOrgId ?? organizations[0]?.id ?? "",
  );
  const [choice, setChoice] = useState<Role | null>(() => (selectedRole != null && allowedRoles.includes(selectedRole) ? selectedRole : null));
  const [query, setQuery] = useState("");
  const { favs, toggle: toggleFav } = useFavourites();
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (selectedOrgId) setCurrentOrgId(selectedOrgId);
  }, [selectedOrgId]);

  useEffect(() => {
    containerRef.current?.focus();
  }, []);

  useEffect(() => {
    if (!needsSessionRoleChoice || choice != null) return;
    if (selectedRole != null && allowedRoles.includes(selectedRole)) setChoice(selectedRole);
  }, [needsSessionRoleChoice, selectedRole, allowedRoles, choice]);

  const shouldRender = pinned || selectedRole == null || needsSessionRoleChoice;
  if (!shouldRender || allowedRoles.length === 0) return null;

  const currentOrg = organizations.find((o) => o.id === currentOrgId) ?? organizations[0];

  const handleOrgSelect = (id: string) => {
    setCurrentOrgId(id);
    onOrgSelect?.(id);
  };

  const handleRoleChoice = async (r: Role) => {
    setChoice(r);
    await switchRole(r);
    onConfirm?.(r);
  };

  const displayName = userName ?? "there";

  return (
    <div style={S.page} data-testid="role-picker-overlay" ref={containerRef} tabIndex={-1}>
      <div style={S.inner}>
        <div style={S.avatar}>LEO</div>
        <div style={S.welcome}>
          <h1 style={S.welcomeTitle}>Welcome, {displayName}!</h1>
          <p style={S.welcomeSub}>Let&apos;s get you started in just {multiOrg ? "2" : "1"} click{multiOrg ? "s" : ""}.</p>
          {isPlatformAdmin && (
            <p style={{
              marginTop: 6,
              padding: "6px 12px",
              borderRadius: 6,
              background: "#FEF9C3",
              color: "#713F12",
              fontSize: 13,
              fontWeight: 500,
              display: "inline-block",
            }}>
              Platform admin -- you can try any role. Changes are real.
            </p>
          )}
        </div>

        <div style={S.steps}>
          {multiOrg && (
            <>
              <StepPill n={1} label="Choose Organisation" active={step === 1} done={step === 2} />
              <StepDivider />
            </>
          )}
          <StepPill n={multiOrg ? 2 : 1} label="Choose Your Role" active={step === 2} done={false} />
        </div>

        {currentOrg && step === 2 && (
          <div style={S.orgBanner}>
            <span style={{ fontSize: 24 }}>🏥</span>
            <div style={S.orgBannerText}>
              <p style={S.orgLabel}>Selected Organisation</p>
              <p style={S.orgName}>{orgLabel(currentOrg)}</p>
            </div>
            {multiOrg && (
              <button type="button" onClick={() => setStep(1)} style={S.changeBtn}>
                ← Change
              </button>
            )}
          </div>
        )}

        {step === 1 ? (
          <>
            <h2 style={S.stepHeading}>Step 1: Choose Your Organisation</h2>
            <OrgStep orgs={organizations} selectedId={currentOrgId} onSelect={handleOrgSelect} />
            <div style={S.footer}>
              <button type="button" onClick={() => setStep(2)} disabled={!currentOrgId} style={S.primaryBtn(!currentOrgId)}>
                Next
              </button>
            </div>
          </>
        ) : (
          <div role="radiogroup" aria-label="Choose your role">
            <h2 style={S.stepHeading}>Step {multiOrg ? "2" : "1"}: Choose Your Role</h2>
            <RoleStep allowedRoles={allowedRoles} choice={choice} onChoice={handleRoleChoice} query={query} onQuery={setQuery} favs={favs} onToggleFav={toggleFav} />
            {loading && (
              <p style={{ textAlign: "center", color: "#94A3B8", marginTop: 16 }}>Setting your role...</p>
            )}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 24, paddingTop: 16, borderTop: "1px solid #E2E8F0" }}>
              {multiOrg ? (
                <button type="button" onClick={() => setStep(1)} style={S.outlineBtn}>
                  ← Back to Organisations
                </button>
              ) : <span />}
              <span style={{ fontSize: 13, color: "#94A3B8" }}>→ Click any role to continue</span>
            </div>
          </div>
        )}
      </div>
      <p style={{ textAlign: "center", fontSize: 13, color: "#94A3B8", marginTop: 24 }}>
        {"\uD83D\uDCA1"} <strong>Need help?</strong> If you&apos;re not sure which organisation or role to choose, contact your administrator or team lead for guidance.
      </p>
    </div>
  );
}
