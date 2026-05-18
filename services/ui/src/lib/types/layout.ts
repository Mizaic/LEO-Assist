/**
 * Layout JSON types for the Report Builder.
 *
 * Element types are defined in elementTypes.ts and re-exported here
 * so existing imports from '@/lib/types/layout' continue to work.
 *
 * Atlas trace:
 *   DO: DO-CD075278
 *   DI: DI-B5EEBC4C
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-CD075278")
 */
export * from './elementTypes';

import type { ElementType, LayoutElement, CohortFilters } from './elementTypes';

export type PageOrientation = 'portrait' | 'landscape';
export type PageSize = 'A4' | 'Letter' | 'Legal';
export type Units = 'mm' | 'in' | 'px';
export type ReportScope = 'patient' | 'organization';

export interface LayoutPage {
  id: string;
  orientation: PageOrientation;
  elements: LayoutElement[];
  backgroundColor?: string;
  marginTop?: number;
  marginRight?: number;
  marginBottom?: number;
  marginLeft?: number;
  hideHeader?: boolean;
  hideFooter?: boolean;
  hideCover?: boolean;
}

export interface LayoutJson {
  pages: LayoutPage[];
  pageSize: PageSize;
  units: Units;
  version: string;
  reportScope?: ReportScope;
  runtimeParams?: {
    organizationId?: string;
    organizationIds?: string[];
    subjectRef?: string;
    cohortFilters?: CohortFilters;
    refreshToken?: number;
  };
}

export const PAGE_DIMENSIONS: Record<
  PageSize,
  { width: number; height: number }
> = {
  A4: { width: 210, height: 297 },
  Letter: { width: 215.9, height: 279.4 },
  Legal: { width: 215.9, height: 355.6 },
};

export const DEFAULT_LAYOUT: LayoutJson = {
  pages: [
    {
      id: 'page-1',
      orientation: 'portrait',
      elements: [],
    },
  ],
  pageSize: 'A4',
  units: 'mm',
  version: '1.0',
  reportScope: 'organization',
  runtimeParams: {},
};

export function getPageDimensions(
  pageSize: PageSize,
  orientation: PageOrientation
): { width: number; height: number } {
  const dims = PAGE_DIMENSIONS[pageSize];
  if (orientation === 'landscape') {
    return { width: dims.height, height: dims.width };
  }
  return dims;
}

export function generateElementId(type: ElementType): string {
  return `${type}-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
}

export function generatePageId(): string {
  return `page-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
}
