/**
 * Element type definitions for the report layout system.
 */

export type ElementType =
  | 'measure'
  | 'interpretation'
  | 'executiveSummary'
  | 'text'
  | 'heading1'
  | 'heading2'
  | 'heading3'
  | 'subtitle'
  | 'bulletList'
  | 'checklist'
  | 'divider'
  | 'cover'
  | 'image'
  | 'table'
  | 'chart'
  | 'kpiCard'
  | 'heroStats'
  | 'comparisonBars'
  | 'populationPyramid'
  | 'tableOfContents'
  | 'pathwayGantt'
  | 'complianceHeatmap'
  | 'safetyNetMatchProgression';

export type ChartType =
  | 'bar'
  | 'horizontalBar'
  | 'pie'
  | 'line'
  | 'area'
  | 'radar'
  | 'radialBar'
  | 'scatter'
  | 'composed'
  | 'sankey'
  | 'boxPlot'
  | 'funnel'
  | 'heatmap'
  | 'bullet';

export type MeasureDisplayType = 'value' | ChartType | 'table' | 'populationPyramid';
export type TextAlign = 'left' | 'center' | 'right';
export type ObjectFit = 'contain' | 'cover' | 'fill' | 'none';

export interface CohortFilters {
  ce_agent_confidence?: number | null;
  ce_condition_type?: string[];
  ce_status?: string[];
  ce_status_exclude?: string[];
  ce_created_at_start?: string;
  ce_created_at_end?: string;
  ce_first_encounter_date_start?: string;
  ce_first_encounter_date_end?: string;
  ce_last_encounter_date_start?: string;
  ce_last_encounter_date_end?: string;
  ce_referral_date_start?: string;
  ce_referral_date_end?: string;
  ce_diagnosis_date_start?: string;
  ce_diagnosis_date_end?: string;
  ce_treatment_start_date_start?: string;
  ce_treatment_start_date_end?: string;
}

export interface ElementStyle {
  fontSize?: number;
  fontWeight?: 'normal' | 'bold';
  color?: string;
  backgroundColor?: string;
  borderColor?: string;
  borderWidth?: number;
  borderRadius?: number;
  align?: TextAlign;
  padding?: number;
}

export interface BaseElement {
  id: string;
  type: ElementType;
  x: number;
  y: number;
  w: number;
  h: number;
  style?: ElementStyle;
  locked?: boolean;
  zIndex?: number;
}

export interface MeasureElement extends BaseElement {
  type: 'measure';
  measureId: string;
  title?: string;
  displayMode?: MeasureDisplayType;
  showTitle?: boolean;
  showScore?: boolean;
  chartType?: ChartType;
  dataBindings?: {
    xAxisKey?: string;
    yAxisKey?: string;
    seriesKey?: string;
    fieldGroup?: 'all' | 'pct' | 'count';
  };
  cohortFilters?: CohortFilters;
}

export type InterpretationContentFormat = 'summary' | 'bullets' | 'full';

export interface InterpretationElement extends BaseElement {
  type: 'interpretation';
  title?: string;
  linkedElementIds?: string[];
  modelSize?: 'small' | 'big';
  contentFormat?: InterpretationContentFormat;
  lastRunAt?: string;
  preview?: {
    summary?: string;
    insights?: Array<string | Record<string, unknown>>;
    quality_checks?: Array<string | Record<string, unknown>>;
    recommended_measures?: Array<string | Record<string, unknown>>;
    follow_up_questions?: Array<string | Record<string, unknown>>;
    caveats?: Array<string | Record<string, unknown>>;
  };
}

export interface ExecutiveSummaryElement extends BaseElement {
  type: 'executiveSummary';
  title?: string;
  mode?: 'default' | 'tight';
  modelSize?: 'small' | 'big';
  excludedMeasureIds?: string[];
  lastRunAt?: string;
  preview?: {
    summary?: string;
  };
}

export interface TextElement extends BaseElement {
  type: 'text';
  text: string;
  placeholder?: string;
}

export interface HeadingElement extends BaseElement {
  type: 'heading1' | 'heading2' | 'heading3' | 'subtitle';
  text: string;
}

export interface BulletListElement extends BaseElement {
  type: 'bulletList';
  items: string[];
}

export interface ChecklistItem {
  id: string;
  text: string;
  checked: boolean;
}

export interface ChecklistElement extends BaseElement {
  type: 'checklist';
  items: ChecklistItem[];
}

export interface DividerElement extends BaseElement {
  type: 'divider';
  thickness?: number;
  color?: string;
}

export interface CoverElement extends BaseElement {
  type: 'cover';
  title: string;
  subtitle?: string;
  date?: string;
  backgroundColor?: string;
  backgroundImageUrl?: string;
  logoUrl?: string;
  panelBackgroundColor?: string;
  panelBorderColor?: string;
}

export interface ImageElement extends BaseElement {
  type: 'image';
  src: string;
  alt?: string;
  objectFit?: ObjectFit;
}

export interface TableColumn {
  id: string;
  header: string;
  width?: number;
  align?: TextAlign;
}

export interface TableElement extends BaseElement {
  type: 'table';
  columns: TableColumn[];
  rows: Record<string, string | number>[];
  showHeader?: boolean;
  striped?: boolean;
  dataSource?: string;
}

export interface ChartSeries {
  dataKey: string;
  name?: string;
  color?: string;
  type?: 'line' | 'bar' | 'area';
}

export interface ShadedArea {
  start: string;
  end: string;
  label?: string;
  color?: string;
}

export interface HighlightedPoint {
  key: string;
  label?: string;
  color?: string;
}

export interface SankeyNode {
  id?: string;
  name: string;
  category?: string;
  count?: number;
}

export interface SankeyLink {
  source: string | number;
  target: string | number;
  value: number;
}

export interface SankeyData {
  nodes: SankeyNode[];
  links: SankeyLink[];
}

export interface ChartElement extends BaseElement {
  type: 'chart';
  chartType: ChartType;
  dataSource?: string;
  xAxisKey?: string;
  yAxisKey?: string;
  seriesKey?: string;
  fieldGroup?: 'all' | 'pct' | 'count';
  targetKey?: string;
  rangeKeys?: string[];
  data?: Array<Record<string, unknown>>;
  multiSeries?: ChartSeries[];
  composedSeries?: ChartSeries[];
  shadedAreas?: ShadedArea[];
  highlightedPoints?: HighlightedPoint[];
  sankey?: SankeyData;
  colors?: string[];
  showLegend?: boolean;
  showGrid?: boolean;
}

export interface KpiCardElement extends BaseElement {
  type: 'kpiCard';
  title: string;
  value: number;
  unit?: string;
  target?: number;
  metTarget?: boolean;
  comparison?: number;
  comparisonLabel?: string;
  trend?: 'up' | 'down';
}

export interface HeroStat {
  label: string;
  value: number;
  unit?: string;
}

export interface HeroStatsElement extends BaseElement {
  type: 'heroStats';
  title: string;
  stats: HeroStat[];
}

export interface ComparisonMetric {
  metric: string;
  current: number;
  target: number;
  benchmark?: number;
  unit?: string;
  /** For composite metrics (e.g. sex distribution): display "51% / 49%" per scope instead of bars. */
  scopeDisplayValues?: Record<string, string>;
}

export interface ComparisonBarsElement extends BaseElement {
  type: 'comparisonBars';
  title: string;
  metrics: ComparisonMetric[];
  source?: string;
}

export interface PopulationPyramidDatum {
  ageBand: string;
  male?: number;
  female?: number;
  gender?: 'male' | 'female';
  count?: number;
}

export interface PopulationPyramidElement extends BaseElement {
  type: 'populationPyramid';
  title?: string;
  data: PopulationPyramidDatum[];
  colors?: { male: string; female: string };
}

export interface TableOfContentsElement extends BaseElement {
  type: 'tableOfContents';
  title?: string;
  showPageNumbers?: boolean;
}

export interface PathwayGanttMilestone {
  type: string;
  date?: string;
  dayOffset: number;
  confidence?: number;
}

export interface PathwayGanttTarget {
  name: string;
  days: number;
  breached: boolean;
}

export interface PathwayGanttElement extends BaseElement {
  type: 'pathwayGantt';
  title?: string;
  milestones: PathwayGanttMilestone[];
  nhsTargets: PathwayGanttTarget[];
}

export interface ComplianceHeatmapRow {
  label: string;
  values: number[];
}

export interface ComplianceHeatmapElement extends BaseElement {
  type: 'complianceHeatmap';
  title?: string;
  rows: ComplianceHeatmapRow[];
  columns: string[];
}

export interface CSSRuleProgression {
  ruleId: string;
  ruleName: string;
  matched: number;
  total: number;
  status: string;
}

export interface CSSSummary {
  alertsCreated: number;
  alertsActioned: number;
  alertsCovered: number;
  alertsMissed: number;
}

export interface SafetyNetMatchProgressionElement extends BaseElement {
  type: 'safetyNetMatchProgression';
  title?: string;
  rules: CSSRuleProgression[];
  summary?: CSSSummary;
}

/** Union type for all layout elements. */
export type LayoutElement =
  | MeasureElement
  | InterpretationElement
  | ExecutiveSummaryElement
  | TextElement
  | HeadingElement
  | BulletListElement
  | ChecklistElement
  | DividerElement
  | CoverElement
  | ImageElement
  | TableElement
  | ChartElement
  | KpiCardElement
  | HeroStatsElement
  | ComparisonBarsElement
  | PopulationPyramidElement
  | TableOfContentsElement
  | PathwayGanttElement
  | ComplianceHeatmapElement
  | SafetyNetMatchProgressionElement;
