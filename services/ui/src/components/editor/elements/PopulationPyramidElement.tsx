/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-30A82196
 *   DI: DI-85B110A5
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-30A82196")
 */
'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
} from 'recharts';
import { PopulationPyramidElement as PopulationPyramidElementType } from '@/lib/types/layout';

interface PopulationPyramidElementProps {
  element: PopulationPyramidElementType;
}

export function PopulationPyramidElement({ element }: PopulationPyramidElementProps) {
  const colors = element.colors || { male: '#0d46d6', female: '#F97316' };
  const chartRef = useRef<HTMLDivElement>(null);
  const [containerSize, setContainerSize] = useState({ width: 0, height: 0 });

  const pyramidData = useMemo(() => {
    if (!element.data || element.data.length === 0) return [];

    let normalized: Array<{ gender: string; ageBand: string; count: number }> = [];
    const first = element.data[0];
    if (first && typeof first === 'object' && 'male' in first && 'female' in first) {
      element.data.forEach((item) => {
        if (!item.ageBand) return;
        const male = typeof item.male === 'number' ? Math.abs(item.male) : 0;
        const female = typeof item.female === 'number' ? item.female : 0;
        normalized.push({ gender: 'male', ageBand: item.ageBand, count: male });
        normalized.push({ gender: 'female', ageBand: item.ageBand, count: female });
      });
    } else {
      normalized = element.data
        .filter((item) => item.gender && item.ageBand && typeof item.count === 'number')
        .map((item) => ({
          gender: item.gender as string,
          ageBand: item.ageBand,
          count: item.count || 0,
        }));
    }

    const ageBands = [...new Set(normalized.map((item) => item.ageBand))].sort((a, b) => {
      const aStart = parseInt(a.split('-')[0], 10);
      const bStart = parseInt(b.split('-')[0], 10);
      return bStart - aStart;
    });

    return ageBands.map((band) => {
      const maleCount =
        normalized.find((item) => item.gender.toLowerCase() === 'male' && item.ageBand === band)
          ?.count || 0;
      const femaleCount =
        normalized.find((item) => item.gender.toLowerCase() === 'female' && item.ageBand === band)
          ?.count || 0;
      return {
        ageBand: band,
        male: -maleCount,
        maleActual: maleCount,
        female: femaleCount,
      };
    });
  }, [element.data]);

  useEffect(() => {
    const node = chartRef.current;
    if (!node) return;
    const updateSize = () => {
      const rect = node.getBoundingClientRect();
      setContainerSize({ width: rect.width, height: rect.height });
    };
    updateSize();
    const observer = new ResizeObserver(() => updateSize());
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  return (
    <Box
      sx={{
        width: '100%',
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        gap: '8px',
        bgcolor: 'background.paper',
        border: 1,
        borderColor: 'divider',
        borderRadius: 0.5,
        padding: '12px',
        boxSizing: 'border-box',
      }}
    >
      {element.title && (
        <Typography sx={{ fontSize: '0.75rem', fontWeight: 600 }}>
          {element.title}
        </Typography>
      )}
      {pyramidData.length === 0 ? (
        <Box
          sx={{
            flex: 1,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'text.disabled',
          }}
        >
          <Typography>No population data available.</Typography>
        </Box>
      ) : (
        <Box sx={{ flex: 1, minHeight: '200px', minWidth: 0 }} ref={chartRef}>
          {containerSize.width > 1 && containerSize.height > 1 ? (
            <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0}>
              <AreaChart
                data={pyramidData}
                layout="vertical"
                margin={{ top: 10, right: 10, left: 20, bottom: 10 }}
              >
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis
                  type="number"
                  tickFormatter={(value) => Math.abs(value).toString()}
                  padding={{ left: 5, right: 5 }}
                />
                <YAxis dataKey="ageBand" type="category" width={60} tickMargin={5} />
                <Tooltip
                  formatter={(value, name) => [
                    Math.abs(Number(value ?? 0)),
                    name === 'male' ? 'Male' : 'Female',
                  ]}
                />
                <Legend verticalAlign="bottom" height={24} />
                <ReferenceLine x={0} stroke="#000" />
                <Area
                  type="monotone"
                  dataKey="male"
                  name="Male"
                  stroke={colors.male}
                  fill={colors.male}
                  fillOpacity={0.6}
                  isAnimationActive={false}
                  stackId="1"
                />
                <Area
                  type="monotone"
                  dataKey="female"
                  name="Female"
                  stroke={colors.female}
                  fill={colors.female}
                  fillOpacity={0.6}
                  isAnimationActive={false}
                  stackId="2"
                />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <Box
              sx={{
                flex: 1,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'text.disabled',
              }}
            >
              <Typography>Chart area is too small.</Typography>
            </Box>
          )}
        </Box>
      )}
    </Box>
  );
}
