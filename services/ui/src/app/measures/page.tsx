"use client";

import { Suspense } from "react";
import CircularProgress from "@mui/material/CircularProgress";
import Box from "@mui/material/Box";
import { MeasureList } from "@/components/measures/MeasureList";

export default function MeasuresPage() {
  return (
    <Suspense fallback={<Box sx={{ display: "flex", justifyContent: "center", p: 6 }}><CircularProgress aria-label="Loading" /></Box>}>
      <MeasureList />
    </Suspense>
  );
}
