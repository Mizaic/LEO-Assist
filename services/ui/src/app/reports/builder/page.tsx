"use client";

import { Suspense } from "react";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import ReportBuilder from "@/components/reports/ReportBuilder";

export default function ReportBuilderPage() {
  return (
    <Suspense
      fallback={
        <Box sx={{ display: "flex", justifyContent: "center", py: 10 }}>
          <CircularProgress />
        </Box>
      }
    >
      <ReportBuilder />
    </Suspense>
  );
}
