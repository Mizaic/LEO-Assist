/**
 * Typed fetch helpers for /api/admin/* endpoints.
 * All require platform admin; session cookie is sent via credentials: 'include'.
 *
 * Atlas trace:
 *   DO: DO-19BBE973
 *   DI: DI-B746E19E
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-19BBE973")
 */
import { api, apiFetch } from './client';

const ADMIN_BASE = '/api/admin';

// ------------------------------------------------------------------
// Types
// ------------------------------------------------------------------

export interface OrgSubscription {
  id: string;
  tier: string;
  credits_purchased: number;
  credits_consumed: number;
  expires_at?: string;
}

export interface Org {
  id: string;
  name: string;
  odsCode?: string;
  short_name?: string;
  entra_tenant_id?: string;
  onboarding_status?: string;
  ods_sync_status?: string;
  ods_discrepancy?: Record<string, { ods: string; leo: string }>;
  ods_sync_last_checked?: string;
  type: string; // gp | icb | alliance | pcn | service_provider | organization
  labels: string[];
  patient_count: number;
  parent_id?: string;
  parent_name?: string;
  alliance_id?: string;
  alliance_name?: string;
  pcn_id?: string;
  pcn_name?: string;
  subscription?: OrgSubscription | null;
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
  source?: 'local' | 'entra';
  entra_object_id?: string;
  entra_tenant_id?: string;
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

export interface OrgService {
  id: string;
  name?: string;
  code?: string;
}

export async function listOrgServices(orgId: string): Promise<OrgService[]> {
  return api.get<OrgService[]>(`${ADMIN_BASE}/orgs/${encodeURIComponent(orgId)}/services`);
}

export interface OrgGraphNode {
  id: string;
  name: string;
  short_name?: string;
  odsCode?: string;
  type: string;
  ods_sync_status?: string;
  ods_parent_ods_code?: string;
  ods_address?: { line1?: string; city?: string; postcode?: string };
  onboarding_status?: string;
  patient_count: number;
}

export interface OrgGraphEdge {
  source: string;
  target: string;
}

export interface OrgGraph {
  nodes: OrgGraphNode[];
  edges: OrgGraphEdge[];
}

export async function getOrgGraph(): Promise<OrgGraph> {
  return api.get<OrgGraph>(`${ADMIN_BASE}/orgs/graph`);
}

export async function createOrg(body: {
  type: 'gp' | 'icb' | 'alliance' | 'pcn';
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

export async function listOrgUsers(orgId: string): Promise<User[]> {
  return api.get<User[]>(`${ADMIN_BASE}/orgs/${encodeURIComponent(orgId)}/users`);
}

export async function addUserToOrg(orgId: string, email: string): Promise<{ email: string; org_id: string; action: string }> {
  return api.post(`${ADMIN_BASE}/orgs/${encodeURIComponent(orgId)}/users/${encodeURIComponent(email)}`, {});
}

export async function removeUserFromOrg(orgId: string, email: string): Promise<{ email: string; org_id: string; action: string }> {
  return apiFetch(`${ADMIN_BASE}/orgs/${encodeURIComponent(orgId)}/users/${encodeURIComponent(email)}`, { method: 'DELETE' });
}

export async function assignOrgRole(email: string, orgId: string, roleName: string): Promise<{ role: string; org_id?: string }> {
  return api.post(`${ADMIN_BASE}/users/${encodeURIComponent(email)}/roles`, { role_name: roleName, org_id: orgId });
}

export async function removeOrgRole(email: string, roleName: string): Promise<{ role: string }> {
  return api.delete(`${ADMIN_BASE}/users/${encodeURIComponent(email)}/roles/${encodeURIComponent(roleName)}`);
}

export async function acquireGpToPcn(gpId: string, pcnId: string): Promise<{ gp_id: string; pcn_id: string; action: string }> {
  return api.post(`${ADMIN_BASE}/orgs/${gpId}/pcn/${pcnId}`, {});
}

export async function releaseGpFromPcn(gpId: string, pcnId: string): Promise<{ gp_id: string; pcn_id: string; action: string }> {
  return apiFetch(`${ADMIN_BASE}/orgs/${gpId}/pcn/${pcnId}`, { method: 'DELETE' });
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

// ------------------------------------------------------------------
// Onboarding
// ------------------------------------------------------------------

export interface OnboardRequest {
  organisation: {
    name: string;
    type: 'gp' | 'icb' | 'alliance' | 'pcn';
    ods_code: string;
    parent_org_id?: string;
    region?: string;
    entra_tenant_id?: string;
    subscription?: {
      tier: string;
      credits?: number;
      expires_at?: string;
      purchase_ref?: string;
    };
  };
  primary_user: {
    email: string;
    given_name: string;
    family_name: string;
    job_title?: string;
    phone?: string;
  };
}

export interface OnboardResponse {
  org_id: string;
  user_email: string;
  onboarding_status: string;
  message: string;
}

export async function onboardOrg(body: OnboardRequest): Promise<OnboardResponse> {
  return apiFetch<OnboardResponse>('/api/onboard', { method: 'POST', body });
}

// ------------------------------------------------------------------
// Microsoft Entra (admin portal Graph extension)
// See DI-31F4C232, DI-5A18A227, DI-6CF7FCE0.
// ------------------------------------------------------------------

const ENTRA_BASE = '/api/admin/entra';

export interface EntraCapability {
  tenant_id?: string;
  can_list_domains: boolean;
  can_search_users: boolean;
  can_list_groups: boolean;
  can_write_groups: boolean;
  can_manage_membership: boolean;
  scopes_granted: string[];
  scopes_required: string[];
  admin_consent_url: string;
  from_cache?: boolean;
  probed_at?: number;
}

export interface EntraDomain {
  id: string;
  isDefault?: boolean;
  isVerified?: boolean;
  authenticationType?: string;
  supportedServices?: string[];
}

export interface EntraUser {
  id: string;
  displayName: string;
  mail?: string;
  userPrincipalName?: string;
}

export interface EntraGroup {
  id: string;
  displayName: string;
  description?: string;
  securityEnabled?: boolean;
  mailEnabled?: boolean;
}

export interface EntraShadowGroup {
  entra_object_id: string;
  id: string;
  name: string;
  description?: string;
  entra_tenant_id?: string;
  source: 'local' | 'entra';
}

export interface EntraBindResult {
  entra_object_id: string;
  role_name: string;
  org_id?: string;
}

export class EntraConsentRequiredError extends Error {
  consentUrl: string;
  graphErrorCode: string;
  constructor(message: string, consentUrl: string, graphErrorCode = '') {
    super(message);
    this.name = 'EntraConsentRequiredError';
    this.consentUrl = consentUrl;
    this.graphErrorCode = graphErrorCode;
  }
}

export async function getEntraCapability(): Promise<EntraCapability> {
  return api.get<EntraCapability>(`${ENTRA_BASE}/capability`);
}

export async function listEntraDomains(): Promise<{
  tenant_id: string;
  domains: EntraDomain[];
}> {
  return api.get(`${ENTRA_BASE}/domains`);
}

export async function searchEntraUsers(
  q: string,
  top = 25
): Promise<{ tenant_id: string; users: EntraUser[] }> {
  const url = `${ENTRA_BASE}/users?q=${encodeURIComponent(q)}&top=${top}`;
  return api.get(url);
}

export async function listEntraGroups(
  prefix = '',
  top = 50
): Promise<{ tenant_id: string; groups: EntraGroup[] }> {
  const params = new URLSearchParams();
  if (prefix) params.set('prefix', prefix);
  params.set('top', String(top));
  return api.get(`${ENTRA_BASE}/groups?${params.toString()}`);
}

export async function createEntraGroup(body: {
  display_name: string;
  description?: string;
  mail_nickname?: string;
  org_id?: string;
  bind_role_name?: string;
}): Promise<{
  graph: EntraGroup;
  shadow: EntraShadowGroup;
  bind: EntraBindResult | null;
}> {
  return api.post(`${ENTRA_BASE}/groups`, body);
}

export async function bindEntraGroup(
  groupObjectId: string,
  body: {
    display_name: string;
    name: string;
    role_name: string;
    description?: string;
    org_id?: string;
    confirm_display_name: string;
  }
): Promise<{ shadow: EntraShadowGroup; bind: EntraBindResult }> {
  return api.post(
    `${ENTRA_BASE}/groups/${encodeURIComponent(groupObjectId)}/bind`,
    body
  );
}

export async function addEntraGroupMember(
  groupObjectId: string,
  userObjectId: string
): Promise<{
  group_object_id: string;
  user_object_id: string;
  action: 'added';
}> {
  return api.post(
    `${ENTRA_BASE}/groups/${encodeURIComponent(groupObjectId)}/members`,
    { user_object_id: userObjectId }
  );
}

export async function removeEntraGroupMember(
  groupObjectId: string,
  userObjectId: string
): Promise<{
  group_object_id: string;
  user_object_id: string;
  action: 'removed';
}> {
  return apiFetch(
    `${ENTRA_BASE}/groups/${encodeURIComponent(groupObjectId)}/members/${encodeURIComponent(userObjectId)}`,
    { method: 'DELETE' }
  );
}
