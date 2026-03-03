'use client';

import { useMemo, useState } from 'react';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import Button from '@mui/material/Button';
import CircularProgress from '@mui/material/CircularProgress';
import TextFieldsOutlined from '@mui/icons-material/TextFieldsOutlined';
import { ExecutiveSummaryElement as ExecutiveSummaryElementType } from '@/lib/types/layout';
import { executiveSummary } from '@/lib/api/agent';
import { getMeasureReport, extractAgentSummaryEntries } from '@/lib/api/measureReports';
import { useEditorStore } from '@/stores/editorStore';

const containerSx = {
  width: '100%',
  height: '100%',
  display: 'flex',
  flexDirection: 'column',
  bgcolor: 'background.paper',
  border: 1,
  borderColor: 'divider',
  borderRadius: 0.5,
  overflow: 'hidden',
} as const;

interface ExecutiveSummaryElementProps {
  element: ExecutiveSummaryElementType;
  pageId: string;
  readOnly?: boolean;
}

export function ExecutiveSummaryElement({ element, pageId, readOnly = false }: ExecutiveSummaryElementProps) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { report, updateElement } = useEditorStore();

  const title = element.title?.trim() || 'Executive Summary';
  const excluded = useMemo(() => new Set(element.excludedMeasureIds || []), [element.excludedMeasureIds]);

  const renderInline = (input: string) => {
    const parts = input.split(/(\*\*[^*]+\*\*)/g).filter(Boolean);
    return parts.map((part, index) => {
      if (part.startsWith('**') && part.endsWith('**')) {
        const text = part.slice(2, -2);
        return (
          <Typography key={`bold-${index}`} component="span" sx={{ fontWeight: 600 }}>
            {text}
          </Typography>
        );
      }
      return (
        <Typography key={`text-${index}`} component="span">
          {part}
        </Typography>
      );
    });
  };

  const renderSummary = (summary: string) => {
    const lines = summary.split('\n').map((line) => line.trim());
    return lines.map((line, index) => {
      if (!line) {
        return <div key={`spacer-${index}`} style={{ height: 8 }} />;
      }
      if (line.startsWith('### ')) {
        return (
          <Typography
            key={`h3-${index}`}
            sx={{ fontSize: '0.875rem', fontWeight: 600, color: 'text.primary' }}
          >
            {renderInline(line.slice(4))}
          </Typography>
        );
      }
      if (line.startsWith('## ')) {
        return (
          <Typography
            key={`h2-${index}`}
            sx={{ fontSize: '0.875rem', fontWeight: 600, color: 'text.primary' }}
          >
            {renderInline(line.slice(3))}
          </Typography>
        );
      }
      if (line.startsWith('# ')) {
        return (
          <Typography
            key={`h1-${index}`}
            sx={{ fontSize: '0.875rem', fontWeight: 600, color: 'text.primary' }}
          >
            {renderInline(line.slice(2))}
          </Typography>
        );
      }
      if (line.startsWith('- ') || line.startsWith('• ')) {
        return (
          <Typography
            key={`bullet-${index}`}
            sx={{ fontSize: '0.75rem', color: 'text.primary' }}
          >
            • {renderInline(line.replace(/^[-•]\s+/, ''))}
          </Typography>
        );
      }
      return (
        <Typography
          key={`p-${index}`}
          sx={{ fontSize: '0.75rem', color: 'text.primary', whiteSpace: 'pre-wrap' }}
        >
          {renderInline(line)}
        </Typography>
      );
    });
  };

  const handleRun = async () => {
    if (readOnly) return;
    if (!report?.id) {
      setError('Save the report before running the summary.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const latestReport = await getMeasureReport(report.id);
      const entries = extractAgentSummaryEntries(latestReport)
        .filter((entry) => entry.measure_id)
        .filter((entry) => !excluded.has(entry.measure_id || ''));

      if (entries.length === 0) {
        setError('No interpretations available to summarise.');
        setBusy(false);
        return;
      }

      const response = await executiveSummary({
        report_id: report.id,
        mode: element.mode || 'default',
        model_size: element.modelSize || 'small',
        excluded_measure_ids: element.excludedMeasureIds || [],
        summaries: entries.map((entry) => entry.summary),
      });

      updateElement(pageId, element.id, {
        preview: { summary: response.summary },
        lastRunAt: response.generated_at,
      });
    } catch (err) {
      console.error('Failed to run executive summary:', err);
      setError('Failed to run executive summary.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Box sx={containerSx}>
      <Box
        sx={{
          padding: '8px',
          bgcolor: 'grey.200',
          borderBottom: 1,
          borderColor: 'divider',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '8px',
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: '6px', minWidth: 0 }}>
          <TextFieldsOutlined />
          <Typography
            sx={{
              fontSize: '0.75rem',
              fontWeight: 600,
              color: 'text.primary',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {title}
          </Typography>
        </Box>
        <Button size="small" onClick={handleRun} disabled={busy || readOnly}>
          {busy ? <CircularProgress aria-label="Loading" size={16} /> : 'Run'}
        </Button>
      </Box>
      <Box
        sx={{
          flex: 1,
          padding: '8px',
          overflow: 'auto',
          display: 'flex',
          flexDirection: 'column',
          gap: '6px',
        }}
      >
        {!element.preview?.summary && !error && (
          <Box
            sx={{
              color: 'text.disabled',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              textAlign: 'center',
              gap: '8px',
              height: '100%',
            }}
          >
            <TextFieldsOutlined sx={{ fontSize: '28px' }} />
            <Typography>Run executive summary to preview output.</Typography>
          </Box>
        )}
        {element.preview?.summary && renderSummary(element.preview.summary)}
        {error && (
          <Typography sx={{ color: 'error.main', fontSize: '0.625rem' }}>
            {error}
          </Typography>
        )}
      </Box>
    </Box>
  );
}
