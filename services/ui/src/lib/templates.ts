/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-CD075278
 *   DI: DI-B5EEBC4C
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-CD075278")
 */
import type { LayoutJson } from '@/lib/types/layout';
import { DEFAULT_LAYOUT } from '@/lib/types/layout';

export interface ReportTemplate {
  id: string;
  name: string;
  description: string;
  generate: () => LayoutJson;
}

const TEMPLATES: ReportTemplate[] = [];

export function getTemplates(): ReportTemplate[] {
  return TEMPLATES;
}

export function getTemplateById(id: string): ReportTemplate | null {
  return TEMPLATES.find((t) => t.id === id) ?? null;
}
