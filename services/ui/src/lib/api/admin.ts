/**
 * Typed fetch helpers for /api/admin/* endpoints.
 * All require platform admin; session cookie is sent via credentials: 'include'.
 */

import { api, apiFetch } from './client';

const ADMIN_BASE = '/api/admin';

// ------------------------------------------------------------------
// Types
// ------------------------------------------------------------------

export interface Org {
  id: string;
  name: string;
  odsCode?: string;
  short_name?: string;
  type: string; // gp | icb | alliance | organization
  labels: string[];
  patient_count: number;
  parent_id?: string;
  parent_name?: string;
  alliance_id?: string;
  alliance_name?: string;
}

export interface User {
  id?: string;
  email: string;
  name: string;
  is_platform_admin: boolean;
  org_ids: string[];
  org_names: string[];
  roles: Array<{ role: string; org_id?: string }>;
  last_seen_at?: string;
  invited_at?: string;
  active_sessions_count: number;
}

export interface Group {
  id: string;
  name: string;
  description?: string;
  org_id?: string;
  org_name?: string;
  member_count: number;
  created_at?: string;
}

export interface Role {
  name: string;
  permissions: string[];
  description?: string;
}

export interface Session {
  session_id: string;
  email: string;
  ttl_seconds: number;
}

export interface AuthConfig {
  session_ttl_hours: number;
  idle_timeout_minutes: number;
  cookie_secure: boolean;
  require_mfa: boolean;
}

// ------------------------------------------------------------------
// Orgs
// ------------------------------------------------------------------

export async function listOrgs(): Promise<Org[]> {
  return api.get<Org[]>(`${ADMIN_BASE}/orgs`);
}

export async function createOrg(body: {
  type: 'gp' | 'icb' | 'alliance';
  name: string;
  ods_code?: string;
  short_name?: string;
  parent_id?: string;
  alliance_id?: string;
}): Promise<{ id: string }> {
  return api.post<{ id: string }>(`${ADMIN_BASE}/orgs`, body);
}

export async function patchOrg(
  id: string,
  body: { name?: string; ods_code?: string; short_name?: string }
): Promise<{ id: string }> {
  return apiFetch<{ id: string }>(`${ADMIN_BASE}/orgs/${id}`, {
    method: 'PATCH',
    body,
  });
}

export async function deleteOrg(id: string): Promise<{ deleted: string }> {
  return api.delete<{ deleted: string }>(`${ADMIN_BASE}/orgs/${id}`);
}

export async function linkOrg(
  orgId: string,
  body: { link_type: string; parent_id: string }
): Promise<{ id: string }> {
  return api.post<{ id: string }>(`${ADMIN_BASE}/orgs/${orgId}/link`, body);
}

// ------------------------------------------------------------------
// Users
// ------------------------------------------------------------------

export async function listUsers(): Promise<User[]> {
  return api.get<User[]>(`${ADMIN_BASE}/users`);
}

export async function createUser(body: {
  email: string;
  name: string;
  is_platform_admin?: boolean;
  org_ids?: string[];
}): Promise<{ email: string }> {
  return api.post<{ email: string }>(`${ADMIN_BASE}/users`, body);
}

export async function patchUser(
  email: string,
  body: { name?: string; is_platform_admin?: boolean; org_ids?: string[] }
): Promise<{ email: string }> {
  return apiFetch<{ email: string }>(`${ADMIN_BASE}/users/${encodeURIComponent(email)}`, {
    method: 'PATCH',
    body,
  });
}

export async function deleteUser(email: string): Promise<{ email: string }> {
  return api.delete<{ email: string }>(`${ADMIN_BASE}/users/${encodeURIComponent(email)}`);
}

export async function forceLogoutUser(
  email: string
): Promise<{ email: string; sessions_deleted: number }> {
  return api.post<{ email: string; sessions_deleted: number }>(
    `${ADMIN_BASE}/users/${encodeURIComponent(email)}/logout`,
    {}
  );
}

export async function listUserRoles(
  email: string
): Promise<Array<{ role: string; org_id?: string }>> {
  return api.get<Array<{ role: string; org_id?: string }>>(
    `${ADMIN_BASE}/users/${encodeURIComponent(email)}/roles`
  );
}

export async function assignUserRole(
  email: string,
  body: { role_name: string; org_id?: string }
): Promise<{ role: string; org_id?: string }> {
  return api.post<{ role: string; org_id?: string }>(
    `${ADMIN_BASE}/users/${encodeURIComponent(email)}/roles`,
    body
  );
}

export async function removeUserRole(
  email: string,
  roleName: string
): Promise<{ role: string }> {
  return api.delete<{ role: string }>(
    `${ADMIN_BASE}/users/${encodeURIComponent(email)}/roles/${encodeURIComponent(roleName)}`
  );
}

// ------------------------------------------------------------------
// Sessions
// ------------------------------------------------------------------

export async function listSessions(): Promise<Session[]> {
  return api.get<Session[]>(`${ADMIN_BASE}/sessions`);
}

export async function deleteSession(sessionId: string): Promise<{ session_id: string }> {
  return api.delete<{ session_id: string }>(
    `${ADMIN_BASE}/sessions/${encodeURIComponent(sessionId)}`
  );
}

export async function deleteAllSessions(): Promise<{ sessions_deleted: number }> {
  return api.delete<{ sessions_deleted: number }>(`${ADMIN_BASE}/sessions`);
}

// ------------------------------------------------------------------
// Groups
// ------------------------------------------------------------------

export async function listGroups(): Promise<Group[]> {
  return api.get<Group[]>(`${ADMIN_BASE}/groups`);
}

export async function createGroup(body: {
  name: string;
  description?: string;
  org_id?: string;
}): Promise<{ id: string }> {
  return api.post<{ id: string }>(`${ADMIN_BASE}/groups`, body);
}

export async function patchGroup(
  id: string,
  body: { name?: string; description?: string }
): Promise<{ id: string }> {
  return apiFetch<{ id: string }>(`${ADMIN_BASE}/groups/${id}`, {
    method: 'PATCH',
    body,
  });
}

export async function deleteGroup(id: string): Promise<{ id: string }> {
  return api.delete<{ id: string }>(`${ADMIN_BASE}/groups/${id}`);
}

export async function listGroupMembers(
  groupId: string
): Promise<Array<{ email: string; name?: string }>> {
  return api.get<Array<{ email: string; name?: string }>>(
    `${ADMIN_BASE}/groups/${groupId}/members`
  );
}

export async function addGroupMember(
  groupId: string,
  body: { email: string }
): Promise<{ email: string }> {
  return api.post<{ email: string }>(`${ADMIN_BASE}/groups/${groupId}/members`, body);
}

export async function removeGroupMember(
  groupId: string,
  email: string
): Promise<{ email: string }> {
  return api.delete<{ email: string }>(
    `${ADMIN_BASE}/groups/${groupId}/members/${encodeURIComponent(email)}`
  );
}

// ------------------------------------------------------------------
// Auth config
// ------------------------------------------------------------------

export async function getAuthConfig(): Promise<AuthConfig> {
  return api.get<AuthConfig>(`${ADMIN_BASE}/auth-config`);
}

export async function patchAuthConfig(body: {
  session_ttl_hours?: number;
  idle_timeout_minutes?: number;
  cookie_secure?: boolean;
  require_mfa?: boolean;
}): Promise<{ session_ttl_hours: number; idle_timeout_minutes: number }> {
  return apiFetch<{ session_ttl_hours: number; idle_timeout_minutes: number }>(
    `${ADMIN_BASE}/auth-config`,
    { method: 'PATCH', body }
  );
}

// ------------------------------------------------------------------
// Roles
// ------------------------------------------------------------------

export async function listRoles(): Promise<Role[]> {
  return api.get<Role[]>(`${ADMIN_BASE}/roles`);
}
