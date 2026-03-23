"use client";

/**
 * Guidance admin page.
 *
 * Four sections guide administrators through the full workflow:
 *   1. Find and load a NICE guideline (NiceLoaderSection)
 *   1b. Loaded guidelines — what is in the knowledge graph + Generate Rules (LoadedGuidelinesPanel)
 *   2. Check and approve AI-generated rules (RuleReviewSection)
 *   3. Compile and go live (BitmapLifecycleSection)
 *
 * All copy targets a reading age of 11.
 * Destructive actions require a ConfirmDialog (see child sections).
 * Fetch errors surface via Alert, never silently swallowed.
 */

import { useState } from "react";
import Box from "@mui/material/Box";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Typography from "@mui/material/Typography";
import Divider from "@mui/material/Divider";
import NiceLoaderSection from "./NiceLoaderSection";
import LoadedGuidelinesPanel from "./LoadedGuidelinesPanel";
import RuleReviewSection from "./RuleReviewSection";
import BitmapLifecycleSection from "./BitmapLifecycleSection";

function SectionBox({
  id,
  title,
  description,
  children,
}: {
  id: string;
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <Card id={id} component="section" aria-labelledby={`${id}-title`} sx={{ mb: 3 }}>
      <CardContent>
        <Typography
          id={`${id}-title`}
          variant="h6"
          component="h2"
          sx={{ fontWeight: 700, fontSize: "1rem", mb: 0.5 }}
        >
          {title}
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2, fontSize: "0.8rem" }}>
          {description}
        </Typography>
        <Divider sx={{ mb: 2 }} />
        {children}
      </CardContent>
    </Card>
  );
}

export default function GuidancePage() {
  // Incremented to trigger a refresh of the loaded-guidelines panel
  const [loadedRefreshKey, setLoadedRefreshKey] = useState(0);
  // Incremented to trigger a refresh of the rule-review section
  const [ruleRefreshKey, setRuleRefreshKey] = useState(0);

  return (
    <Box sx={{ p: 3, maxWidth: 900, mx: "auto" }}>
      <Typography variant="h5" component="h1" sx={{ fontWeight: 700, mb: 0.5 }}>
        Manage NICE guidelines
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        Load a clinical guideline, check the rules the AI has written for you,
        then compile and switch them on. All changes are recorded for audit.
      </Typography>

      <SectionBox
        id="nice-loader"
        title="Step 1 -- Find and load a guideline"
        description="Search by condition name or type a NICE code directly. Loading brings the guideline into the system."
      >
        <NiceLoaderSection
          onGuidelineLoaded={() => setLoadedRefreshKey((n) => n + 1)}
        />
      </SectionBox>

      <SectionBox
        id="loaded-guidelines"
        title="What is in the knowledge graph"
        description="These are the guidelines already loaded. Check chapters and recommendations are correct, then click 'Generate rules' to ask the AI to write decision criteria for each recommendation."
      >
        <LoadedGuidelinesPanel
          refreshKey={loadedRefreshKey}
          onRulesGenerated={() => setRuleRefreshKey((n) => n + 1)}
        />
      </SectionBox>

      <SectionBox
        id="rule-review"
        title="Step 2 -- Check and approve AI-generated rules"
        description="The AI has suggested the criteria for each recommendation. Read each one and click 'Looks right', 'Edit', or 'Reject'."
      >
        <RuleReviewSection refreshKey={ruleRefreshKey} />
      </SectionBox>

      <SectionBox
        id="bitmap-lifecycle"
        title="Step 3 -- Compile and go live"
        description="Once you are happy with the rules, compile them into the live lookup index. Only approved rules are included."
      >
        <BitmapLifecycleSection />
      </SectionBox>
    </Box>
  );
}
