/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2C03CA0E
 *   DI: DI-3F771AFB
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C03CA0E")
 */
"use client";

import { useState } from "react";
import dynamic from "next/dynamic";
import Box from "@mui/material/Box";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";

const SbarPlayground = dynamic(() => import("./SbarPlayground"), {
  ssr: false,
});
const ScenarioRunPanel = dynamic(() => import("./ScenarioRunPanel"), {
  ssr: false,
});

export default function AiSummarisationPage() {
  const [tab, setTab] = useState<"playground" | "scenarios">("playground");
  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <Tabs
        value={tab}
        onChange={(_, value) => setTab(value)}
        aria-label="AI summarisation views"
      >
        <Tab value="playground" label="Manual SBAR playground" />
        <Tab value="scenarios" label="Scenario runs" />
      </Tabs>
      {tab === "playground" ? <SbarPlayground /> : <ScenarioRunPanel />}
    </Box>
  );
}
