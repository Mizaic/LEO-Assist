import { api } from './client';
import type { Organization, Bundle } from '@/lib/types/fhir';

const ENDPOINT = '/fhir/Organization';

export interface OrganizationSearchParams {
  name?: string;
  _count?: number;
  _offset?: number;
}

export async function getOrganizations(
  params?: OrganizationSearchParams
): Promise<Bundle<Organization>> {
  const searchParams = new URLSearchParams();
  if (params?.name) searchParams.set('name', params.name);
  if (params?._count) searchParams.set('_count', params._count.toString());
  if (params?._offset) searchParams.set('_offset', params._offset.toString());

  const query = searchParams.toString();
  const url = query ? `${ENDPOINT}?${query}` : ENDPOINT;
  return api.get<Bundle<Organization>>(url);
}
