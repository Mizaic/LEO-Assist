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

import { useCallback, useEffect, useState } from "react";
import { AnimatePresence, motion as fm } from "framer-motion";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Collapse from "@mui/material/Collapse";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import ExpandMoreRoundedIcon from "@mui/icons-material/ExpandMoreRounded";
import ReplayRoundedIcon from "@mui/icons-material/ReplayRounded";

import { SegmentedTabs, StatHero, useMotion, type StatTile } from "@leo/design-system";

import CoachTour from "@/components/ui/CoachTour";

import NiceLoaderSection from "./NiceLoaderSection";
import LoadedGuidelinesPanel from "./LoadedGuidelinesPanel";
import RuleReviewSection from "./RuleReviewSection";
import BitmapLifecycleSection from "./BitmapLifecycleSection";
import GuidelineBuilderSplash, {
  GUIDANCE_SPLASH_SESSION_KEY,
} from "./GuidelineBuilderSplash";
import LocalGuidelineImportDialog from "./LocalGuidelineImportDialog";
import { PAGE_TOUR_STEPS } from "./guidanceTourSteps";
import { popSpring, staggerDelay } from "./motionPresets";

type StepId = "load" | "inspect" | "review" | "compile";

interface StepCardProps {
  id: string;
  step?: number;
  title: string;
  description: string;
  accent: string;
  index: number;
  reducedMotion: boolean;
  /** Controlled open state; defaults closed when omitted. */
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** IFU CoachTour / Playwright screenshot anchor id. */
  dataTour?: string;
  children: React.ReactNode;
}

function StepCard({
  id,
  step,
  title,
  description,
  accent,
  index,
  reducedMotion,
  open,
  onOpenChange,
  dataTour,
  children,
}: StepCardProps) {
  return (
    <fm.section
      id={id}
      aria-labelledby={`${id}-title`}
      data-tour={dataTour}
      initial={reducedMotion ? { opacity: 0 } : { opacity: 0, y: 26, scale: 0.96 }}
      animate={reducedMotion ? { opacity: 1 } : { opacity: 1, y: 0, scale: 1 }}
      transition={popSpring(reducedMotion, staggerDelay(index, 0.08, 6))}
      style={{ position: "relative", background: "#FFFFFF", border: "1px solid #E2E8F0", borderRadius: 12, padding: 22, marginBottom: 20 }}
    >
          <span aria-hidden="true" style={{ position: "absolute", left: 0, top: 18, bottom: 18, width: 3, borderRadius: 2, background: accent, }} />
      <Stack
        component="button"
        type="button"
        direction="row"
        alignItems="flex-start"
        spacing={1.5}
        onClick={() => onOpenChange(!open)}
        aria-expanded={open}
        aria-controls={`${id}-body`}
        sx={{
          mb: open ? 2 : 0,
          width: "100%",
          p: 0,
          border: "none",
          bgcolor: "transparent",
          textAlign: "left",
          cursor: "pointer",
          "&:focus-visible": {
            outline: "2px solid",
            outlineColor: "primary.main",
            outlineOffset: 2,
            borderRadius: 1,
          },
        }}
      >
        {step != null ? (
          <Box aria-hidden="true" sx={{ width: 28, height: 28, borderRadius: "50%", bgcolor: accent, color: "#FFFFFF", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 700, fontSize: "0.78rem", flexShrink: 0, mt: 0.25 }}>
            {step}
          </Box>
        ) : null}
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography id={`${id}-title`} variant="h6" component="h2" sx={{ fontWeight: 700, fontSize: "1rem", lineHeight: 1.3, mb: 0.4 }}>
            {title}
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ fontSize: "0.82rem", lineHeight: 1.5 }}>
            {description}
          </Typography>
        </Box>
        <IconButton
          size="small"
          tabIndex={-1}
          aria-hidden
          sx={{
            mt: 0.25,
            transform: open ? "rotate(180deg)" : "rotate(0deg)",
            transition: "transform 160ms ease",
          }}
        >
          <ExpandMoreRoundedIcon fontSize="small" />
        </IconButton>
      </Stack>
      <Collapse in={open} timeout={reducedMotion ? 0 : "auto"}>
        <Box id={`${id}-body`}>
          <Divider sx={{ mb: 2 }} />
          {children}
        </Box>
      </Collapse>
    </fm.section>
  );
}

const STEP_SECTION_IDS: Record<StepId, string> = {
  load: "nice-loader",
  inspect: "loaded-guidelines",
  review: "rule-review",
  compile: "bitmap-lifecycle",
};

const STEP_TABS: ReadonlyArray<{ id: StepId; label: string; href: string }> = [
  { id: "load", label: "1. Load", href: "#nice-loader" },
  { id: "inspect", label: "Inspect", href: "#loaded-guidelines" },
  { id: "review", label: "2. Review", href: "#rule-review" },
  { id: "compile", label: "3. Compile", href: "#bitmap-lifecycle" },
];

interface PageStats {
  guidelinesLoaded: number;
  rulesPending: number;
  rulesApproved: number;
  activeBitmapVersion: string;
}

async function fetchPageStats(): Promise<PageStats> {
  const [loadedResp, bitmapResp] = await Promise.allSettled([
    fetch("/api/nice/loaded"),
    fetch("/api/terminology/guidelines/bitmap/status?scope_type=global&scope_id=default"),
  ]);

  let guidelinesLoaded = 0;
  let rulesPending = 0;
  let rulesApproved = 0;
  let activeBitmapVersion = "--";

  if (loadedResp.status === "fulfilled" && loadedResp.value.ok) {
    const data = (await loadedResp.value.json()) as Array<{ rules_pending?: number; rules_approved?: number }>;
    guidelinesLoaded = data.length;
    rulesPending = data.reduce((s, g) => s + (g.rules_pending ?? 0), 0);
    rulesApproved = data.reduce((s, g) => s + (g.rules_approved ?? 0), 0);
  }
  if (bitmapResp.status === "fulfilled" && bitmapResp.value.ok) {
    const bm = (await bitmapResp.value.json()) as { active_version?: string | null };
    if (bm.active_version) activeBitmapVersion = bm.active_version;
  }
  return { guidelinesLoaded, rulesPending, rulesApproved, activeBitmapVersion };
}

export default function GuidancePage() {
  const [loadedRefreshKey, setLoadedRefreshKey] = useState(0);
  const [ruleRefreshKey, setRuleRefreshKey] = useState(0);
  const [bitmapRefreshKey, setBitmapRefreshKey] = useState(0);
  const [activeStep, setActiveStep] = useState<StepId>("load");
  const [openSections, setOpenSections] = useState<Record<string, boolean>>({});
  const [stats, setStats] = useState<PageStats>({ guidelinesLoaded: 0, rulesPending: 0, rulesApproved: 0, activeBitmapVersion: "--" });
  const [showSplash, setShowSplash] = useState(false);
  const [showLocalImport, setShowLocalImport] = useState(false);
  const [tourActive, setTourActive] = useState(false);
  const { reducedMotion } = useMotion();

  const isSectionOpen = useCallback(
    (sectionId: string) => openSections[sectionId] === true,
    [openSections],
  );

  const setSectionOpen = useCallback((sectionId: string, open: boolean) => {
    setOpenSections((prev) => ({ ...prev, [sectionId]: open }));
  }, []);

  useEffect(() => {
    fetchPageStats().then(setStats).catch(() => {});
  }, [loadedRefreshKey, ruleRefreshKey, bitmapRefreshKey]);

  useEffect(() => {
    try {
      if (!sessionStorage.getItem(GUIDANCE_SPLASH_SESSION_KEY)) {
        setShowSplash(true);
      }
    } catch {
      // sessionStorage unavailable (e.g. private browsing) -- skip splash.
    }
  }, []);

  const dismissSplash = useCallback(() => {
    try {
      sessionStorage.setItem(GUIDANCE_SPLASH_SESSION_KEY, "1");
    } catch {
      // Best-effort only; not seeing the splash again is not safety-relevant.
    }
    setShowSplash(false);
  }, []);

  const statTiles: StatTile[] = [
    { id: "loaded", label: "Guidelines loaded", value: stats.guidelinesLoaded },
    { id: "pending", label: "Rules pending", value: stats.rulesPending },
    { id: "approved", label: "Rules approved", value: stats.rulesApproved },
    { id: "bitmap", label: "Active bitmap version", value: stats.activeBitmapVersion },
  ];

  const handleJump = (id: string) => {
    const stepId = id as StepId;
    setActiveStep(stepId);
    const sectionId = STEP_SECTION_IDS[stepId];
    if (sectionId) setSectionOpen(sectionId, true);
    const target = STEP_TABS.find((t) => t.id === id);
    if (!target) return;
    window.setTimeout(() => {
      const el = document.querySelector(target.href);
      if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 50);
  };

  return (
    <Box>
      <AnimatePresence>
        {showSplash && <GuidelineBuilderSplash key="guidance-splash" onDismiss={dismissSplash} />}
      </AnimatePresence>

      {/* -- Summary hero ------------------------------------------------- */}
      <Box sx={{ mb: 2 }}>
        <StatHero stats={statTiles} />
        <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 1 }} flexWrap="wrap">
          <Tooltip title="Paste a local guideline into the knowledge graph so you can make rules from it.">
            <span>
              <Button variant="contained" onClick={() => setShowLocalImport(true)}>
                Import local guideline
              </Button>
            </span>
          </Tooltip>
          <Button
            variant="text"
            size="small"
            onClick={() => setTourActive(true)}
            aria-label="Take the guideline tab tour"
            data-testid="guidance-tour-trigger"
          >
            Guide me
          </Button>
          <Tooltip title="Replay the guideline tab tour from the start.">
            <IconButton
              size="small"
              onClick={() => setTourActive(true)}
              aria-label="Replay the guideline tab tour"
              data-testid="coach-tour-replay"
            >
              <ReplayRoundedIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        </Stack>
      </Box>
      <CoachTour
        tourId="guidance-page"
        steps={PAGE_TOUR_STEPS}
        active={tourActive}
        onFinish={() => setTourActive(false)}
      />
      <LocalGuidelineImportDialog
        open={showLocalImport}
        onClose={() => setShowLocalImport(false)}
        onImported={() => {
          setLoadedRefreshKey((n) => n + 1);
          setActiveStep("inspect");
          setSectionOpen("loaded-guidelines", true);
          window.setTimeout(() => {
            document
              .querySelector("#loaded-guidelines")
              ?.scrollIntoView({ behavior: "smooth", block: "start" });
          }, 100);
        }}
      />

      {/* -- Jump strip --------------------------------------------------- */}
      <Box
        data-testid="guidance-jump-strip"
        data-tour="cg-01-jump"
        sx={{ position: "sticky", top: 0, zIndex: 5, mb: 2, py: 1, bgcolor: "rgba(255,255,255,0.92)", backdropFilter: "blur(8px)", borderBottom: "1px solid", borderColor: "divider" }}
      >
        <SegmentedTabs
          tabs={STEP_TABS.map((t) => ({ id: t.id, label: t.label }))}
          value={activeStep}
          onChange={handleJump}
          aria-label="Jump to guidance workflow step"
        />
      </Box>

      {/* -- Step 1: Load ------------------------------------------------- */}
      <StepCard
        id="nice-loader"
        index={0}
        step={1}
        title="Find and load a guideline"
        description="Search by condition name or type a NICE code directly. Loading brings the guideline into the system."
        accent="#1F3A8A"
        reducedMotion={reducedMotion}
        open={isSectionOpen("nice-loader")}
        onOpenChange={(open) => setSectionOpen("nice-loader", open)}
        dataTour="cg-02-load"
      >
        <NiceLoaderSection onGuidelineLoaded={() => setLoadedRefreshKey((n) => n + 1)} />
      </StepCard>

      {/* -- Inspect: What is in the graph -------------------------------- */}
      <StepCard
        id="loaded-guidelines"
        index={1}
        title="What is in the knowledge graph"
        description="These are the guidelines already loaded. Check chapters and recommendations are correct, then click 'Generate rules' to ask the AI to write decision criteria for each recommendation."
        accent="#64748B"
        reducedMotion={reducedMotion}
        open={isSectionOpen("loaded-guidelines")}
        onOpenChange={(open) => setSectionOpen("loaded-guidelines", open)}
        dataTour="cg-03-inspect"
      >
        <LoadedGuidelinesPanel refreshKey={loadedRefreshKey} onRulesGenerated={() => setRuleRefreshKey((n) => n + 1)} />
      </StepCard>

      {/* -- Step 2: Review ----------------------------------------------- */}
      <StepCard
        id="rule-review"
        index={2}
        step={2}
        title="Check and approve AI-generated rules"
        description="The AI has suggested the criteria for each recommendation. Read each one and click 'Looks right', 'Edit', or 'Reject'."
        accent="#1F3A8A"
        reducedMotion={reducedMotion}
        open={isSectionOpen("rule-review")}
        onOpenChange={(open) => setSectionOpen("rule-review", open)}
        dataTour="cg-04-review-pool"
      >
        <RuleReviewSection refreshKey={ruleRefreshKey} />
      </StepCard>

      {/* -- Step 3: Compile ---------------------------------------------- */}
      <StepCard
        id="bitmap-lifecycle"
        index={3}
        step={3}
        title="Compile and go live"
        description="Once you are happy with the rules, compile them into the live lookup index. Only approved rules are included."
        accent="#14B8A6"
        reducedMotion={reducedMotion}
        open={isSectionOpen("bitmap-lifecycle")}
        onOpenChange={(open) => setSectionOpen("bitmap-lifecycle", open)}
        dataTour="cg-06-compile"
      >
        <BitmapLifecycleSection onVersionActivated={() => setBitmapRefreshKey((n) => n + 1)} />
      </StepCard>
    </Box>
  );
}
