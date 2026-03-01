"use client";

import { Suspense } from "react";
import CircularProgress from "@mui/material/CircularProgress";
import Box from "@mui/material/Box";
import { BenchmarkUploadWizard } from "@/components/benchmarks/BenchmarkUploadWizard";

export default function BenchmarkUploadPage() {
  return (
    <Suspense
      fallback={
        <Box sx={{ display: "flex", justifyContent: "center", p: 6 }}>
          <CircularProgress />
        </Box>
      }
    >
      <BenchmarkUploadWizard />
    </Suspense>
  );
}
