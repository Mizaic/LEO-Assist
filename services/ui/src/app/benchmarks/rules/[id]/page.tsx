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
          <CircularProgress />
        </Box>
      }
    >
      <RuleContent {...props} />
    </Suspense>
  );
}
