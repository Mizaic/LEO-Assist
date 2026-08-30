/**
 * Atlas trace:
 *   UN: UN-3B25A20E
 *   DI: DI-10667413
 *   DO: DO-9C9CB1D8
 */
export interface TenantCompletenessGroup {
  name: string;
  kind?: string;
  required?: boolean;
}

export interface TenantCompletenessDomain {
  domain_id: string;
  domain_name: string;
  organization_id: string;
  organization_name: string;
  completeness_groups: TenantCompletenessGroup[];
}

export async function fetchTenantCompletenessDomains(
  organizationId?: string,
): Promise<TenantCompletenessDomain[]> {
  const qs = organizationId
    ? `?organization_id=${encodeURIComponent(organizationId)}`
    : "";
  const res = await fetch(`/api/completeness-domains/${qs}`, {
    credentials: "include",
    headers: { "X-Requested-With": "XMLHttpRequest" },
  });
  if (!res.ok) {
    throw new Error("Could not load completeness domains. Please retry.");
  }
  const data = (await res.json()) as { domains?: TenantCompletenessDomain[] };
  return data.domains ?? [];
}
