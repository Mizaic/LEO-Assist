"use client";

import { Suspense } from "react";
import CircularProgress from "@mui/material/CircularProgress";
import Box from "@mui/material/Box";
import { BenchmarkSetList } from "@/components/benchmarks/BenchmarkSetList";

export default function BenchmarksPage() {
  return (
    <Suspense
      fallback={
        <Box sx={{ display: "flex", justifyContent: "center", p: 6 }}>
          <CircularProgress aria-label="Loading" />
        </Box>
      }
    >
      <BenchmarkSetList />
    </Suspense>
  );
}
