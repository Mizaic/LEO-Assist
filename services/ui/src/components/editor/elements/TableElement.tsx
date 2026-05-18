/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-30A82196
 *   DI: DI-85B110A5
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-30A82196")
 */
'use client';

import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import TableChartOutlined from '@mui/icons-material/TableChartOutlined';
import { TableElement as TableElementType, TableColumn } from '@/lib/types/layout';
import { useEffect, useState } from 'react';
import { evaluateMeasure } from '@/lib/api';
import { ApiError } from '@/lib/api/client';
import { useEditorStore } from '@/stores/editorStore';
import { useOrgId } from '@/context/OrgContext';
import { extractMeasureReportSeries, MeasureSeriesPoint } from '@/lib/measureData';

const containerSx = {
  width: '100%',
  height: '100%',
  overflow: 'auto',
  bgcolor: 'background.paper',
  border: 1,
  borderColor: 'divider',
  borderRadius: 0.5,
} as const;

const placeholderSx = {
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  justifyContent: 'center',
  color: 'text.disabled',
  gap: '8px',
  padding: '24px',
  textAlign: 'center',
  height: '100%',
} as const;

const thStyle: React.CSSProperties = {
  padding: '8px',
  textAlign: 'left',
  backgroundColor: '#EEEEEE',
  borderBottom: '1px solid rgba(0, 0, 0, 0.12)',
  fontWeight: 600,
  color: 'rgba(0, 0, 0, 0.87)',
};

const tdStyle: React.CSSProperties = {
  padding: '8px',
  borderBottom: '1px solid #E0E0E0',
  color: 'rgba(0, 0, 0, 0.87)',
};

interface TableElementProps {
  element: TableElementType;
}

export function TableElement({ element }: TableElementProps) {
  const report = useEditorStore((state) => state.report);
  const reportScope = useEditorStore((state) => state.layout.reportScope);
  const runtimeParams = useEditorStore((state) => state.layout.runtimeParams);
  const globalOrgId = useOrgId();
  const orgIdsKey = (runtimeParams?.organizationIds || []).join('|');
  const cohortFiltersKey = JSON.stringify(runtimeParams?.cohortFilters || {});
  const [boundSeries, setBoundSeries] = useState<MeasureSeriesPoint[] | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!element.dataSource) return;
    const orgId =
      reportScope === 'organization'
        ? (runtimeParams?.organizationId || globalOrgId)
        : undefined;
    if (reportScope === 'organization' && !orgId) {
      setBoundSeries([]);
      setErrorMessage('Select an organization in the toolbar (or header) to evaluate this measure.');
      return;
    }
    const measureId = element.dataSource.replace('Measure/', '');
    const periodStart = report?.period?.start || new Date().toISOString().split('T')[0];
    const periodEnd = report?.period?.end || new Date().toISOString().split('T')[0];
    const subject =
      reportScope === 'patient' ? runtimeParams?.subjectRef : undefined;
    const orgIds =
      reportScope === 'organization' ? runtimeParams?.organizationIds : undefined;
    evaluateMeasure(measureId, {
      periodStart,
      periodEnd,
      subject,
      orgId,
      orgIds,
      cohortFilters: runtimeParams?.cohortFilters,
    }).then(result => {
      const series = extractMeasureReportSeries(result as any);
      setBoundSeries(series);
      setErrorMessage(null);
    }).catch(error => {
      const msg = error instanceof ApiError ? error.message : (error instanceof Error ? error.message : 'Failed to evaluate table data');
      setErrorMessage(msg);
      setBoundSeries([]);
    });
  }, [
    element.dataSource,
    report?.period?.start,
    report?.period?.end,
    reportScope,
    runtimeParams?.subjectRef,
    runtimeParams?.organizationId,
    globalOrgId,
    orgIdsKey,
    cohortFiltersKey,
    runtimeParams?.refreshToken,
  ]);

  const boundColumns = [
    { id: 'label', header: 'Label', align: 'left' as const },
    { id: 'value', header: 'Value', align: 'right' as const },
  ];
  const boundRows = (boundSeries || []).map((row) => ({
    label: row.name,
    value: row.value,
  }));

  if (errorMessage) {
    return (
      <Box sx={containerSx}>
        <Box sx={placeholderSx}>
          <TableChartOutlined sx={{ fontSize: '32px' }} />
          <Typography sx={{ fontSize: '0.625rem' }}>{errorMessage}</Typography>
        </Box>
      </Box>
    );
  }

  if (!element.dataSource && (!element.columns || element.columns.length === 0)) {
    return (
      <Box sx={containerSx}>
        <Box sx={placeholderSx}>
          <TableChartOutlined sx={{ fontSize: '32px' }} />
          <Typography sx={{ fontSize: '0.625rem' }}>
            No table structure.
            <br />
            Configure in properties.
          </Typography>
        </Box>
      </Box>
    );
  }

  const columnsToUse: TableColumn[] = element.dataSource ? boundColumns : element.columns;
  const rowsToUse: Record<string, string | number>[] = element.dataSource ? boundRows : element.rows;
  const hasRows = rowsToUse && rowsToUse.length > 0;

  return (
    <Box sx={containerSx}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.75rem' }}>
        {element.showHeader !== false && (
          <thead>
            <tr>
              {columnsToUse.map((col) => (
                <th
                  key={col.id}
                  style={{
                    ...thStyle,
                    width: col.width ? `${col.width}px` : undefined,
                    textAlign: col.align || 'left',
                  }}
                >
                  {col.header}
                </th>
              ))}
            </tr>
          </thead>
        )}
        <tbody>
          {hasRows ? (
            rowsToUse.map((row, rowIndex) => (
              <tr
                key={rowIndex}
                style={
                  element.striped && rowIndex % 2 === 1
                    ? { backgroundColor: '#F5F5F5' }
                    : undefined
                }
              >
                {columnsToUse.map((col) => (
                  <td
                    key={col.id}
                    style={{ ...tdStyle, textAlign: col.align || 'left' }}
                  >
                    {row[col.id] ?? '-'}
                  </td>
                ))}
              </tr>
            ))
          ) : (
            <tr>
              <td
                colSpan={columnsToUse.length}
                style={{ ...tdStyle, textAlign: 'center', color: 'rgba(0, 0, 0, 0.38)' }}
              >
                {element.dataSource ? 'No data available' : 'No data'}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </Box>
  );
}
