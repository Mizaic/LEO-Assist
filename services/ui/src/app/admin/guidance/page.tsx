"use client";

/**
 * Guidance admin page.
 *
 * Four sections guide administrators through the full workflow:
 *   1. Find and load a NICE guideline (NiceLoaderSection)
 *   1b. Loaded guidelines -- what is in the knowledge graph + Generate Rules (LoadedGuidelinesPanel)
 *   2. Check and approve AI-generated rules (RuleReviewSection)
 *   3. Compile and go live (BitmapLifecycleSection)
 *
 * All copy targets a reading age of 11.
 * Destructive actions require a ConfirmDialog (see child sections).
 * Fetch errors surface via Alert, never silently swallowed.
 */

import { useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import Divider from "@mui/material/Divider";
import NiceLoaderSection from "./NiceLoaderSection";
import LoadedGuidelinesPanel from "./LoadedGuidelinesPanel";
import RuleReviewSection from "./RuleReviewSection";
import BitmapLifecycleSection from "./BitmapLifecycleSection";

function StepBadge({ step }: { step: number }) {
  return (
    <Box
      aria-hidden="true"
      sx={{
        width: 30,
        height: 30,
        borderRadius: "50%",
        bgcolor: "primary.main",
        color: "white",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontWeight: 700,
        fontSize: "0.8rem",
        flexShrink: 0,
      }}
    >
      {step}
    </Box>
  );
}

function SectionBox({
  id,
  title,
  description,
  step,
  accent,
  children,
}: {
  id: string;
  title: string;
  description: string;
  step?: number;
  accent?: string;
  children: React.ReactNode;
}) {
  return (
    <Card
      id={id}
      component="section"
      aria-labelledby={`${id}-title`}
      variant="outlined"
      sx={{
        mb: 3,
        borderRadius: 2,
        borderLeft: "4px solid",
        borderLeftColor: accent ?? "primary.main",
        boxShadow: "0 1px 4px rgba(0,0,0,0.06)",
      }}
    >
      <CardContent>
        <Stack direction="row" spacing={1.5} alignItems="flex-start" sx={{ mb: 2 }}>
          {step != null && <StepBadge step={step} />}
          <Box sx={{ flex: 1 }}>
            <Typography
              id={`${id}-title`}
              variant="h6"
              component="h2"
              sx={{ fontWeight: 700, fontSize: "1rem", lineHeight: 1.3, mb: 0.4 }}
            >
              {title}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ fontSize: "0.8rem" }}>
              {description}
            </Typography>
          </Box>
        </Stack>
        <Divider sx={{ mb: 2 }} />
        {children}
      </CardContent>
    </Card>
  );
}

export default function GuidancePage() {
  const [loadedRefreshKey, setLoadedRefreshKey] = useState(0);
  const [ruleRefreshKey, setRuleRefreshKey] = useState(0);

  return (
    <Box sx={{ p: 3, maxWidth: 960, mx: "auto" }}>
      <Box sx={{ mb: 4 }}>
        <Typography variant="h5" component="h1" sx={{ fontWeight: 700, mb: 0.5 }}>
          Manage NICE guidelines
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Load a clinical guideline, check the rules the AI has written for you,
          then compile and switch them on. All changes are recorded for audit.
        </Typography>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ mt: 1.5 }}>
          <Button size="small" variant="outlined" href="#nice-loader">1. Load</Button>
          <Button size="small" variant="outlined" href="#rule-review">2. Review</Button>
          <Button size="small" variant="outlined" href="#bitmap-lifecycle">3. Compile</Button>
        </Stack>
      </Box>

      <SectionBox
        id="nice-loader"
        step={1}
        title="Find and load a guideline"
        description="Search by condition name or type a NICE code directly. Loading brings the guideline into the system."
        accent="#1F3A8A"
      >
        <NiceLoaderSection
          onGuidelineLoaded={() => setLoadedRefreshKey((n) => n + 1)}
        />
      </SectionBox>

      <SectionBox
        id="loaded-guidelines"
        title="What is in the knowledge graph"
        description="These are the guidelines already loaded. Check chapters and recommendations are correct, then click 'Generate rules' to ask the AI to write decision criteria for each recommendation."
        accent="#64748b"
      >
        <LoadedGuidelinesPanel
          refreshKey={loadedRefreshKey}
          onRulesGenerated={() => setRuleRefreshKey((n) => n + 1)}
        />
      </SectionBox>

      <SectionBox
        id="rule-review"
        step={2}
        title="Check and approve AI-generated rules"
        description="The AI has suggested the criteria for each recommendation. Read each one and click 'Looks right', 'Edit', or 'Reject'."
        accent="#1F3A8A"
      >
        <RuleReviewSection refreshKey={ruleRefreshKey} />
      </SectionBox>

      <SectionBox
        id="bitmap-lifecycle"
        step={3}
        title="Compile and go live"
        description="Once you are happy with the rules, compile them into the live lookup index. Only approved rules are included."
        accent="#14B8A6"
      >
        <BitmapLifecycleSection />
      </SectionBox>
    </Box>
  );
}
