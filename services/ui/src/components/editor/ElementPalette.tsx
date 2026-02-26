'use client';

import { useCallback } from 'react';
import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import BarChartOutlined from '@mui/icons-material/BarChartOutlined';
import TextFieldsOutlined from '@mui/icons-material/TextFieldsOutlined';
import ImageOutlined from '@mui/icons-material/ImageOutlined';
import TableChartOutlined from '@mui/icons-material/TableChartOutlined';
import InsertChartOutlined from '@mui/icons-material/InsertChartOutlined';
import { useDraggable } from '@dnd-kit/core';
import { ElementType } from '@/lib/types/layout';

interface PaletteItemConfig {
  type: ElementType;
  label: string;
  icon: React.ReactNode;
  description: string;
}

const PALETTE_ITEMS: PaletteItemConfig[] = [
  {
    type: 'measure',
    label: 'Measure',
    icon: <BarChartOutlined />,
    description: 'Add a measure display',
  },
  {
    type: 'interpretation',
    label: 'Interpretation',
    icon: <TextFieldsOutlined />,
    description: 'Add an AI interpretation box',
  },
  {
    type: 'executiveSummary',
    label: 'Executive Summary',
    icon: <TextFieldsOutlined />,
    description: 'Summarise all interpretations',
  },
  {
    type: 'heading1',
    label: 'Heading 1',
    icon: <TextFieldsOutlined />,
    description: 'Add a large heading',
  },
  {
    type: 'heading2',
    label: 'Heading 2',
    icon: <TextFieldsOutlined />,
    description: 'Add a medium heading',
  },
  {
    type: 'heading3',
    label: 'Heading 3',
    icon: <TextFieldsOutlined />,
    description: 'Add a small heading',
  },
  {
    type: 'subtitle',
    label: 'Subtitle',
    icon: <TextFieldsOutlined />,
    description: 'Add a subtitle',
  },
  {
    type: 'bulletList',
    label: 'Bullets',
    icon: <TextFieldsOutlined />,
    description: 'Add a bullet list',
  },
  {
    type: 'checklist',
    label: 'Checklist',
    icon: <TextFieldsOutlined />,
    description: 'Add a checklist',
  },
  {
    type: 'divider',
    label: 'Divider',
    icon: <TextFieldsOutlined />,
    description: 'Add a section divider',
  },
  {
    type: 'cover',
    label: 'Cover',
    icon: <ImageOutlined />,
    description: 'Add a cover block',
  },
  {
    type: 'text',
    label: 'Text',
    icon: <TextFieldsOutlined />,
    description: 'Add a text block',
  },
  {
    type: 'image',
    label: 'Image',
    icon: <ImageOutlined />,
    description: 'Add an image',
  },
  {
    type: 'table',
    label: 'Table',
    icon: <TableChartOutlined />,
    description: 'Add a data table',
  },
  {
    type: 'chart',
    label: 'Chart',
    icon: <InsertChartOutlined />,
    description: 'Add a chart',
  },
  {
    type: 'kpiCard',
    label: 'KPI Card',
    icon: <BarChartOutlined />,
    description: 'Add a KPI summary card',
  },
  {
    type: 'heroStats',
    label: 'Hero Stats',
    icon: <TextFieldsOutlined />,
    description: 'Add a hero stats banner',
  },
  {
    type: 'comparisonBars',
    label: 'Comparison Bars',
    icon: <InsertChartOutlined />,
    description: 'Add comparison metrics',
  },
  {
    type: 'populationPyramid',
    label: 'Population Pyramid',
    icon: <InsertChartOutlined />,
    description: 'Add a population pyramid chart',
  },
  {
    type: 'tableOfContents',
    label: 'Table of Contents',
    icon: <TextFieldsOutlined />,
    description: 'Auto-generated TOC with anchor links',
  },
  {
    type: 'pathwayGantt',
    label: 'Pathway Gantt',
    icon: <InsertChartOutlined />,
    description: 'Timeline showing patient pathway milestones',
  },
  {
    type: 'complianceHeatmap',
    label: 'Compliance Heatmap',
    icon: <InsertChartOutlined />,
    description: 'NHS target compliance by cancer type / time period',
  },
  {
    type: 'cssMatchProgression',
    label: 'CSS Match Progression',
    icon: <InsertChartOutlined />,
    description: 'NG12 guideline match progression per patient',
  },
];

interface DraggablePaletteItemProps {
  item: PaletteItemConfig;
}

function DraggablePaletteItem({ item }: DraggablePaletteItemProps) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: `palette-${item.type}`,
    data: {
      fromPalette: true,
      elementType: item.type,
    },
  });

  return (
    <Tooltip title={item.description}>
      <Card
        ref={setNodeRef}
        data-testid={`palette-item-${item.type}`}
        {...listeners}
        {...attributes}
        sx={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          p: '12px 8px',
          cursor: 'grab',
          transition: 'all 0.1s ease',
          opacity: isDragging ? 0.5 : 1,
          '&:hover': {
            bgcolor: 'action.hover',
            transform: 'scale(1.02)',
          },
          '&:active': {
            cursor: 'grabbing',
          },
        }}
      >
        <Box sx={{ fontSize: '24px', mb: 0.5, color: 'primary.main' }}>
          {item.icon}
        </Box>
        <Typography sx={{ fontSize: '0.625rem', color: 'text.secondary', textAlign: 'center' }}>
          {item.label}
        </Typography>
      </Card>
    </Tooltip>
  );
}

export function ElementPalette() {
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', p: 1.5, gap: 1 }} data-testid="element-palette">
      <Box sx={{ mb: 1 }}>
        <Typography
          data-testid="element-palette-title"
          sx={{ fontSize: '0.75rem', fontWeight: 600, color: 'text.secondary', textTransform: 'uppercase' }}
        >
          Elements
        </Typography>
      </Box>

      <Typography sx={{ fontSize: '0.625rem', fontWeight: 600, color: 'text.disabled', mb: 1 }}>
        Drag to canvas
      </Typography>

      <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 1 }}>
        {PALETTE_ITEMS.map((item) => (
          <DraggablePaletteItem key={item.type} item={item} />
        ))}
      </Box>

      <Box sx={{ height: '1px', bgcolor: 'grey.300', my: 1.5 }} />

      <Typography sx={{ fontSize: '0.625rem', fontWeight: 600, color: 'text.disabled', mb: 1 }}>
        Tips
      </Typography>
      <Typography sx={{ fontSize: '0.625rem', color: 'text.disabled' }}>
        • Drag elements onto pages
        <br />
        • Click to select, drag to move
        <br />
        • Use handles to resize
        <br />
        • Delete key removes selected
      </Typography>
    </Box>
  );
}
