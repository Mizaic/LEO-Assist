/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-19BBE973
 *   DI: DI-B746E19E
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-19BBE973")
 */
import { api } from './client';
import type { Library, Bundle } from '@/lib/types/fhir';

const ENDPOINT = '/fhir/Library';

export interface LibrarySearchParams {
  name?: string;
  status?: string;
  _count?: number;
  _offset?: number;
}

export async function getLibraries(
  params?: LibrarySearchParams
): Promise<Bundle<Library>> {
  const searchParams = new URLSearchParams();
  if (params?.name) searchParams.set('name', params.name);
  if (params?.status) searchParams.set('status', params.status);
  if (params?._count) searchParams.set('_count', params._count.toString());
  if (params?._offset) searchParams.set('_offset', params._offset.toString());

  const query = searchParams.toString();
  const url = query ? `${ENDPOINT}?${query}` : ENDPOINT;
  return api.get<Bundle<Library>>(url);
}

export async function getLibrary(id: string): Promise<Library> {
  return api.get<Library>(`${ENDPOINT}/${id}`);
}
