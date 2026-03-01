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
