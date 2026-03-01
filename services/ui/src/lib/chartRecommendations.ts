/**
 * Chart recommendations based on measure data shape and benchmark presence.
 * Suggests chart types and axis mappings for measure elements.
 */

export type DataShape = 'single' | 'grouped' | 'series' | 'table';

export interface ChartRecommendation {
  displayMode: string;
  label: string;
  reason: string;
  axisMapping?: {
    xAxisKey?: string;
    yAxisKey?: string;
    seriesKey?: string;
    benchmarkAs?: 'line' | 'secondSeries' | 'column';
  };
}

/**
 * Recommend a chart type based on data shape and whether benchmarks are available.
 */
export function recommendChart(
  dataShape: DataShape,
  hasBenchmark: boolean
): ChartRecommendation {
  if (hasBenchmark) {
    switch (dataShape) {
      case 'single':
        return {
          displayMode: 'bullet',
          label: 'Bullet/Target Band',
          reason: 'Single value with benchmark – ideal for target comparison',
          axisMapping: { benchmarkAs: 'line' },
        };
      case 'grouped':
        return {
          displayMode: 'bar',
          label: 'Bar Chart',
          reason: 'Grouped data with benchmark – bars with reference line',
          axisMapping: {
            xAxisKey: 'name',
            yAxisKey: 'value',
            benchmarkAs: 'line',
          },
        };
      case 'series':
        return {
          displayMode: 'line',
          label: 'Line Chart',
          reason: 'Time series with benchmark – line with reference',
          axisMapping: {
            xAxisKey: 'name',
            yAxisKey: 'value',
            benchmarkAs: 'line',
          },
        };
      case 'table':
        return {
          displayMode: 'table',
          label: 'Table',
          reason: 'Table with benchmark column for detailed comparison',
          axisMapping: { benchmarkAs: 'column' },
        };
      default:
        return {
          displayMode: 'bar',
          label: 'Bar Chart',
          reason: 'Default recommendation with benchmark',
          axisMapping: { xAxisKey: 'name', yAxisKey: 'value', benchmarkAs: 'line' },
        };
    }
  }

  switch (dataShape) {
    case 'single':
      return {
        displayMode: 'value',
        label: 'Value',
        reason: 'Single value – display as number',
      };
    case 'grouped':
      return {
        displayMode: 'bar',
        label: 'Bar Chart',
        reason: 'Grouped data – bars by category',
        axisMapping: { xAxisKey: 'name', yAxisKey: 'value' },
      };
    case 'series':
      return {
        displayMode: 'line',
        label: 'Line Chart',
        reason: 'Time or ordered series – line chart',
        axisMapping: { xAxisKey: 'name', yAxisKey: 'value' },
      };
    case 'table':
      return {
        displayMode: 'table',
        label: 'Table',
        reason: 'Multiple columns – table view',
      };
    default:
      return {
        displayMode: 'bar',
        label: 'Bar Chart',
        reason: 'Default recommendation',
        axisMapping: { xAxisKey: 'name', yAxisKey: 'value' },
      };
  }
}

/**
 * Infer data shape from measure report rows.
 */
export function inferDataShape(rows: Array<Record<string, string | number>>): DataShape {
  if (!rows || rows.length === 0) return 'single';
  if (rows.length === 1) {
    const keys = Object.keys(rows[0]).filter((k) => typeof rows[0][k] === 'number');
    return keys.length <= 1 ? 'single' : 'table';
  }
  const keys = Object.keys(rows[0] || {});
  const hasName = keys.includes('name');
  const hasValue = keys.includes('value');
  if (hasName && hasValue && keys.length <= 3) return 'grouped';
  if (keys.some((k) => ['date', 'period', 'month', 'year'].includes(k.toLowerCase()))) return 'series';
  return 'table';
}

/**
 * Infer data shape from axis options (categoryKeys, valueKeys).
 */
export function inferDataShapeFromAxis(categoryKeys: string[], valueKeys: string[]): DataShape {
  if (valueKeys.length === 0) return 'single';
  if (categoryKeys.length === 0 && valueKeys.length === 1) return 'single';
  if (categoryKeys.includes('name') && valueKeys.includes('value')) return 'grouped';
  if (categoryKeys.some((k) => ['date', 'period', 'month', 'year'].includes(k.toLowerCase()))) return 'series';
  if (categoryKeys.length > 0 || valueKeys.length > 1) return 'grouped';
  return 'table';
}
