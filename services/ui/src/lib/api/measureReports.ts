/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-19BBE973
 *   DI: DI-B746E19E
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-19BBE973")
 */
import { api } from './client';
import type { MeasureReport, Bundle, Extension } from '@/lib/types/fhir';
import type { LayoutJson } from '@/lib/types/layout';

const ENDPOINT = '/fhir/MeasureReport';
const LAYOUT_EXTENSION_URL =
  'http://example.org/fhir/StructureDefinition/report-layout';
const AGENT_SUMMARY_EXTENSION_URL =
  'http://example.org/fhir/StructureDefinition/agent-summary';

const utf8Encoder = new TextEncoder();
const utf8Decoder = new TextDecoder();

function encodeBase64Utf8(value: string): string {
  const bytes = utf8Encoder.encode(value);
  let binary = '';
  bytes.forEach((byte) => { binary += String.fromCharCode(byte); });
  return btoa(binary);
}

function decodeBase64Utf8(value: string): string {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  return utf8Decoder.decode(bytes);
}

export interface MeasureReportSearchParams {
  subject?: string;
  measure?: string;
  status?: string;
  date?: string;
  _count?: number;
  _offset?: number;
}

export async function getMeasureReports(
  params?: MeasureReportSearchParams
): Promise<Bundle<MeasureReport>> {
  const searchParams = new URLSearchParams();
  if (params?.subject) searchParams.set('subject', params.subject);
  if (params?.measure) searchParams.set('measure', params.measure);
  if (params?.status) searchParams.set('status', params.status);
  if (params?.date) searchParams.set('date', params.date);
  if (params?._count) searchParams.set('_count', params._count.toString());
  if (params?._offset) searchParams.set('_offset', params._offset.toString());

  const query = searchParams.toString();
  const url = query ? `${ENDPOINT}?${query}` : ENDPOINT;
  return api.get<Bundle<MeasureReport>>(url);
}

export async function getMeasureReport(id: string): Promise<MeasureReport> {
  return api.get<MeasureReport>(`${ENDPOINT}/${id}`);
}

export async function createMeasureReport(
  report: Omit<MeasureReport, 'id'>
): Promise<MeasureReport> {
  return api.post<MeasureReport>(ENDPOINT, report);
}

export async function updateMeasureReport(
  id: string,
  report: MeasureReport
): Promise<MeasureReport> {
  return api.put<MeasureReport>(`${ENDPOINT}/${id}`, report);
}

export async function deleteMeasureReport(id: string): Promise<void> {
  return api.delete<void>(`${ENDPOINT}/${id}`);
}

export function extractLayoutFromReport(
  report: MeasureReport
): LayoutJson | null {
  const ext = report.extension?.find((e) => e.url === LAYOUT_EXTENSION_URL);
  if (!ext?.valueAttachment?.data) return null;
  try {
    return JSON.parse(decodeBase64Utf8(ext.valueAttachment.data)) as LayoutJson;
  } catch {
    return null;
  }
}

export function encodeLayoutForReport(layout: LayoutJson): Extension {
  return {
    url: LAYOUT_EXTENSION_URL,
    valueAttachment: {
      contentType: 'application/json',
      data: encodeBase64Utf8(JSON.stringify(layout)),
    },
  };
}

export interface AgentSummaryEntry {
  measure_id?: string | null;
  summary: Record<string, unknown>;
  summary_type?: string;
}

export function extractAgentSummaryEntries(report: MeasureReport): AgentSummaryEntry[] {
  const extension = report.extension?.find((ext) => ext.url === AGENT_SUMMARY_EXTENSION_URL);
  if (!extension?.valueAttachment?.data) return [];
  try {
    const decoded = decodeBase64Utf8(extension.valueAttachment.data);
    const payload = JSON.parse(decoded) as { entries?: AgentSummaryEntry[] };
    if (Array.isArray(payload.entries)) return payload.entries;
    if (payload && typeof payload === 'object') return [{ summary: payload } as AgentSummaryEntry];
  } catch {
    // ignore decode failures
  }
  return [];
}

export async function saveMeasureReportWithLayout(
  report: MeasureReport,
  layout: LayoutJson
): Promise<MeasureReport> {
  const layoutExtension = encodeLayoutForReport(layout);
  const extensions = (report.extension || []).filter(
    (ext) => ext.url !== LAYOUT_EXTENSION_URL
  );
  extensions.push(layoutExtension);

  const updatedReport: MeasureReport = { ...report, extension: extensions };
  if (report.id) {
    return updateMeasureReport(report.id, updatedReport);
  }
  return createMeasureReport(updatedReport);
}
