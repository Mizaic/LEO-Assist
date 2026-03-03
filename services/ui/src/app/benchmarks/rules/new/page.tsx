"use client";

import { Suspense } from "react";
import CircularProgress from "@mui/material/CircularProgress";
import Box from "@mui/material/Box";
import { BenchmarkRuleEditor } from "@/components/benchmarks/BenchmarkRuleEditor";

export default function NewBenchmarkRulePage() {
  return (
    <Suspense
      fallback={
        <Box sx={{ display: "flex", justifyContent: "center", p: 6 }}>
          <CircularProgress aria-label="Loading" />
        </Box>
      }
    >
      <BenchmarkRuleEditor />
    </Suspense>
  );
}
