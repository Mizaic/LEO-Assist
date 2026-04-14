"use client";

import { useCallback, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import Box from "@mui/material/Box";
import Tabs from "@mui/material/Tabs";
import Tab from "@mui/material/Tab";
import Typography from "@mui/material/Typography";
import dynamic from "next/dynamic";

const GoldDatasetPage = dynamic(() => import("@/app/admin/gold-dataset/page"), { ssr: false });
const SurfaceFormsPage = dynamic(() => import("@/app/admin/surface-forms/page"), { ssr: false });
const ContextRulesPage = dynamic(() => import("@/app/admin/context-rules/page"), { ssr: false });
const PromptsPage = dynamic(() => import("@/app/admin/prompts/page"), { ssr: false });
const GuidancePage = dynamic(() => import("@/app/admin/guidance/page"), { ssr: false });

const TABS = [
  { key: "training-data", label: "Training Data" },
  { key: "surface-forms", label: "Surface Forms" },
  { key: "context-rules", label: "Context Rules" },
  { key: "ai-instructions", label: "AI Instructions" },
  { key: "clinical-guidelines", label: "Clinical Guidelines" },
];

export default function KnowledgePage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const tabParam = searchParams.get("tab") ?? "training-data";
  const activeIdx = Math.max(0, TABS.findIndex((t) => t.key === tabParam));

  const handleTabChange = useCallback(
    (_: React.SyntheticEvent, newIdx: number) => {
      router.replace(`/admin/knowledge?tab=${TABS[newIdx].key}`);
    },
    [router]
  );

  return (
    <Box sx={{ minHeight: "100vh" }}>
      <Box sx={{ px: 3, pt: 3, pb: 0, borderBottom: "1px solid", borderColor: "divider", bgcolor: "background.paper" }}>
        <Typography variant="h5" sx={{ fontWeight: 700, mb: 1.5 }}>
          Knowledge
        </Typography>
        <Tabs value={activeIdx} onChange={handleTabChange} variant="scrollable" scrollButtons="auto">
          {TABS.map((t) => (
            <Tab key={t.key} label={t.label} sx={{ textTransform: "none", fontSize: "0.875rem" }} />
          ))}
        </Tabs>
      </Box>

      <Box>
        {activeIdx === 0 && <GoldDatasetPage />}
        {activeIdx === 1 && <SurfaceFormsPage />}
        {activeIdx === 2 && <ContextRulesPage />}
        {activeIdx === 3 && <PromptsPage />}
        {activeIdx === 4 && <GuidancePage />}
      </Box>
    </Box>
  );
}
