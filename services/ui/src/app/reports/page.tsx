"use client";

import { Suspense } from "react";
import CircularProgress from "@mui/material/CircularProgress";
import Box from "@mui/material/Box";
import { ReportList } from "@/components/reports/ReportList";

export default function ReportsPage() {
  return (
    <Suspense fallback={<Box sx={{ display: "flex", justifyContent: "center", p: 6 }}><CircularProgress /></Box>}>
      <ReportList />
    </Suspense>
  );
}
