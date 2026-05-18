/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2E8544FD
 *   DI: DI-C65FD45B
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2E8544FD")
 */
"use client";

import { use, Suspense } from "react";
import CircularProgress from "@mui/material/CircularProgress";
import Box from "@mui/material/Box";
import { BenchmarkRuleEditor } from "@/components/benchmarks/BenchmarkRuleEditor";

interface PageProps {
  params: Promise<{ id: string }>;
}

function RuleContent({ params }: PageProps) {
  const { id } = use(params);
  return <BenchmarkRuleEditor ruleId={id} />;
}

export default function BenchmarkRulePage(props: PageProps) {
  return (
    <Suspense
      fallback={
        <Box sx={{ display: "flex", justifyContent: "center", p: 6 }}>
          <CircularProgress aria-label="Loading" />
        </Box>
      }
    >
      <RuleContent {...props} />
    </Suspense>
  );
}
