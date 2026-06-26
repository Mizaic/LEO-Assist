/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-0A8B7188
 *   Also implements: DO-E647765A
 *   DI: DI-0C8FBAF7, DI-AA9F5EDA
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-0A8B7188")
 */
"use client";

/**
 * Clinical Guidelines admin page -- Wave E Phase 5 redesign.
 *
 * Visible chrome (intro + page width) is provided upstream by
 * KnowledgePageLayout when this page is mounted inside the Knowledge
 * tab system. The page itself contributes a workflow strip and four
 * design-system-styled step cards. All four child sections
 * (NiceLoaderSection, LoadedGuidelinesPanel, RuleReviewSection,
 * BitmapLifecycleSection) are preserved untouched.
 *
 * Design Controls: DI-LEO-AI-149, DO-LEO-AI-145, VT-LEO-AI-147.
 */

import { useState } from "react";
import { motion as fm } from "framer-motion";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import Divider from "@mui/material/Divider";

import { SegmentedTabs } from "@leo/design-system";

import NiceLoaderSection from "./NiceLoaderSection";
import LoadedGuidelinesPanel from "./LoadedGuidelinesPanel";
import RuleReviewSection from "./RuleReviewSection";
import BitmapLifecycleSection from "./BitmapLifecycleSection";

type StepId = "load" | "review" | "compile";

interface StepCardProps {
  id: string;
  step?: number;
  title: string;
  description: string;
  accent: string;
  index: number;
  children: React.ReactNode;
}

function StepCard({
  id,
  step,
  title,
  description,
  accent,
  index,
  children,
}: StepCardProps) {
  return (
    <fm.section
      id={id}
      aria-labelledby={`${id}-title`}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        duration: 0.24,
        ease: "easeOut",
        delay: Math.min(index, 6) * 0.05,
      }}
      style={{
        position: "relative",
        background: "#FFFFFF",
        border: "1px solid #E2E8F0",
        borderRadius: 12,
        padding: 22,
        marginBottom: 20,
      }}
    >
      <span
        aria-hidden="true"
        style={{
          position: "absolute",
          left: 0,
          top: 18,
          bottom: 18,
          width: 3,
          borderRadius: 2,
          background: accent,
        }}
      />
      <Stack
        direction="row"
        alignItems="flex-start"
        spacing={1.5}
        sx={{ mb: 2 }}
      >
        {step != null ? (
          <Box
            aria-hidden="true"
            sx={{
              width: 28,
              height: 28,
              borderRadius: "50%",
              bgcolor: accent,
              color: "#FFFFFF",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontWeight: 700,
              fontSize: "0.78rem",
              flexShrink: 0,
              mt: 0.25,
            }}
          >
            {step}
          </Box>
        ) : null}
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography
            id={`${id}-title`}
            variant="h6"
            component="h2"
            sx={{
              fontWeight: 700,
              fontSize: "1rem",
              lineHeight: 1.3,
              mb: 0.4,
            }}
          >
            {title}
          </Typography>
          <Typography
            variant="body2"
            color="text.secondary"
            sx={{ fontSize: "0.82rem", lineHeight: 1.5 }}
          >
            {description}
          </Typography>
        </Box>
      </Stack>
      <Divider sx={{ mb: 2 }} />
      {children}
    </fm.section>
  );
}

const STEP_TABS: ReadonlyArray<{ id: StepId; label: string; href: string }> = [
  { id: "load", label: "1. Load", href: "#nice-loader" },
  { id: "review", label: "2. Review", href: "#rule-review" },
  { id: "compile", label: "3. Compile", href: "#bitmap-lifecycle" },
];

export default function GuidancePage() {
  const [loadedRefreshKey, setLoadedRefreshKey] = useState(0);
  const [ruleRefreshKey, setRuleRefreshKey] = useState(0);
  const [activeStep, setActiveStep] = useState<StepId>("load");

  const handleJump = (id: string) => {
    setActiveStep(id as StepId);
    const target = STEP_TABS.find((t) => t.id === id);
    if (!target) return;
    const el = document.querySelector(target.href);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  };

  return (
    <Box>
      <Box
        data-testid="guidance-jump-strip"
        sx={{
          position: "sticky",
          top: 0,
          zIndex: 5,
          mb: 2,
          py: 1,
          bgcolor: "rgba(255,255,255,0.92)",
          backdropFilter: "blur(8px)",
          borderBottom: "1px solid",
          borderColor: "divider",
        }}
      >
        <SegmentedTabs
          tabs={STEP_TABS.map((t) => ({ id: t.id, label: t.label }))}
          value={activeStep}
          onChange={handleJump}
          aria-label="Jump to guidance workflow step"
        />
      </Box>

      <StepCard
        id="nice-loader"
        index={0}
        step={1}
        title="Find and load a guideline"
        description="Search by condition name or type a NICE code directly. Loading brings the guideline into the system."
        accent="#1F3A8A"
      >
        <NiceLoaderSection
          onGuidelineLoaded={() => setLoadedRefreshKey((n) => n + 1)}
        />
      </StepCard>

      <StepCard
        id="loaded-guidelines"
        index={1}
        title="What is in the knowledge graph"
        description="These are the guidelines already loaded. Check chapters and recommendations are correct, then click 'Generate rules' to ask the AI to write decision criteria for each recommendation."
        accent="#64748B"
      >
        <LoadedGuidelinesPanel
          refreshKey={loadedRefreshKey}
          onRulesGenerated={() => setRuleRefreshKey((n) => n + 1)}
        />
      </StepCard>

      <StepCard
        id="rule-review"
        index={2}
        step={2}
        title="Check and approve AI-generated rules"
        description="The AI has suggested the criteria for each recommendation. Read each one and click 'Looks right', 'Edit', or 'Reject'."
        accent="#1F3A8A"
      >
        <RuleReviewSection refreshKey={ruleRefreshKey} />
      </StepCard>

      <StepCard
        id="bitmap-lifecycle"
        index={3}
        step={3}
        title="Compile and go live"
        description="Once you are happy with the rules, compile them into the live lookup index. Only approved rules are included."
        accent="#14B8A6"
      >
        <BitmapLifecycleSection />
      </StepCard>
    </Box>
  );
}
