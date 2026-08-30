/**
 * Widget embedding-host register helpers.
 *
 * Atlas trace:
 *   DO: DO-6F6771E5
 *   DI: DI-14809BB8
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-6F6771E5")
 */
import { api } from "./client";

export const ARTEFACT_KEYS = [
  "saas_embedding_agreement",
  "dpa",
  "dcb0129_reference",
  "ifu_acknowledged",
] as const;

export type ArtefactKey = (typeof ARTEFACT_KEYS)[number];

export interface SdkHostRecord {
  host_id: string;
  name: string;
  contact: string;
  artefacts: Record<string, string | null>;
  acknowledged_ifu_version: string | null;
  is_production_ready: boolean;
}

const JSON_HEADERS = {
  Accept: "application/json",
  "Content-Type": "application/json",
};

export async function listSdkHosts(): Promise<SdkHostRecord[]> {
  return api.get<SdkHostRecord[]>("/api/sdk/governance/register", {
    headers: JSON_HEADERS,
  });
}

export async function registerSdkHost(body: {
  host_id: string;
  name: string;
  contact: string;
}): Promise<SdkHostRecord> {
  return api.post<SdkHostRecord>("/api/sdk/governance/hosts", body, {
    headers: JSON_HEADERS,
  });
}

export async function recordSdkHostArtefact(
  hostId: string,
  artefact: ArtefactKey,
  evidenceUri: string,
): Promise<SdkHostRecord> {
  const path = `/api/sdk/governance/hosts/${encodeURIComponent(hostId)}/artefacts`;
  return api.post<SdkHostRecord>(
    path,
    { artefact, evidence_uri: evidenceUri },
    { headers: JSON_HEADERS },
  );
}

export async function acknowledgeSdkHostIfu(
  hostId: string,
  version: string,
): Promise<SdkHostRecord> {
  const path = `/api/sdk/governance/hosts/${encodeURIComponent(hostId)}/ifu`;
  return api.post<SdkHostRecord>(path, { version }, { headers: JSON_HEADERS });
}
