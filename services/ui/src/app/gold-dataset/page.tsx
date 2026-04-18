"use client";

import { Suspense } from "react";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import GoldDatasetPanel from "@/components/gold-dataset/GoldDatasetPanel";

export default function GoldDatasetPage() {
  return (
    <Suspense
      fallback={
        <Box sx={{ display: "flex", justifyContent: "center", p: 6 }}>
          <CircularProgress aria-label="Loading" />
        </Box>
      }
    >
      <GoldDatasetPanel />
    </Suspense>
  );
}
