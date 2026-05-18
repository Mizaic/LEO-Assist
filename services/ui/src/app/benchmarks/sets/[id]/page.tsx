/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2E8544FD
 *   DI: DI-C65FD45B
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2E8544FD")
 */
'use client';

import { use } from 'react';
import { Suspense } from 'react';
import Box from '@mui/material/Box';
import CircularProgress from '@mui/material/CircularProgress';
import { BenchmarkSetDetail } from '@/components/benchmarks/BenchmarkSetDetail';

interface Params {
  id: string;
}

export default function BenchmarkSetDetailPage({ params }: { params: Promise<Params> }) {
  const { id } = use(params);
  return (
    <Suspense
      fallback={
        <Box sx={{ display: 'flex', justifyContent: 'center', p: 6 }}>
          <CircularProgress aria-label="Loading" />
        </Box>
      }
    >
      <BenchmarkSetDetail setId={id} />
    </Suspense>
  );
}
