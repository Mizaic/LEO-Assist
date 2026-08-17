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

import { AnimatePresence } from "framer-motion";
import AddIcon from "@mui/icons-material/Add";
import ReplayRoundedIcon from "@mui/icons-material/ReplayRounded";
import {
  SegmentedTabs,
  SpringSwap,
  StatHero,
  StickyChrome,
  ToolbarActions,
  type ToolbarAction,
} from "@leo/design-system";
import { color, typography } from "@leo/design-system/tokens";

import CoachTour from "@/components/ui/CoachTour";

import NiceLoaderSection from "./NiceLoaderSection";
import LoadedGuidelinesPanel from "./LoadedGuidelinesPanel";
import RuleReviewSection from "./RuleReviewSection";
import BitmapLifecycleSection from "./BitmapLifecycleSection";
import GuidelineBuilderSplash from "./GuidelineBuilderSplash";
import LocalGuidelineImportDialog from "./LocalGuidelineImportDialog";
import { PAGE_TOUR_STEPS } from "./guidanceTourSteps";
import { StepCard } from "./GuidanceStepCard";
import {
  STEP_TABS,
  useGuidancePage,
  type StepId,
} from "./useGuidancePage";

export default function GuidancePage() {
  const page = useGuidancePage();
  return (
    <div data-testid="clinical-guidelines-workspace">
      <AnimatePresence>
        {page.showSplash ? (
          <GuidelineBuilderSplash key="guidance-splash" onDismiss={page.dismissSplash} />
        ) : null}
      </AnimatePresence>
      <StatHero stats={page.statTiles} />
      <GuidanceChrome page={page} />
      <CoachTour
        tourId="guidance-page"
        steps={PAGE_TOUR_STEPS}
        active={page.tourActive}
        onFinish={page.finishPageTour}
        prepareStep={page.preparePageTourStep}
      />
      <LocalGuidelineImportDialog
        open={page.showLocalImport}
        onClose={() => page.setShowLocalImport(false)}
        onImported={() => {
          page.setLoadedRefreshKey((n) => n + 1);
          page.setActiveStep("inspect");
        }}
      />
      <SpringSwap swapKey={page.activeStep}>
        <GuidanceStepBody page={page} />
      </SpringSwap>
    </div>
  );
}

function GuidanceChrome({ page }: { page: ReturnType<typeof useGuidancePage> }) {
  const actions: ToolbarAction[] = [
    {
      id: "import-local",
      label: "Import local guideline",
      icon: <AddIcon fontSize="small" />,
      variant: "primary",
      onClick: () => page.setShowLocalImport(true),
    },
  ];
  return (
    <StickyChrome testId="guidance-jump-strip">
      <div data-tour="cg-01-jump" style={{ position: "sticky" }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
          <ToolbarActions actions={actions} />
          <TourButtons onStart={() => page.setTourActive(true)} />
        </div>
        <div style={{ marginTop: 12 }}>
          <p
            style={{
              margin: "0 0 6px",
              fontSize: 12,
              fontWeight: 700,
              letterSpacing: typography.letterSpacing.caption,
              color: color.text.secondary,
              fontFamily: typography.fontFamily.body,
            }}
          >
            Choose a step
          </p>
          <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            <SegmentedTabs
              tabs={STEP_TABS.map((t) => ({ id: t.id, label: t.label }))}
              value={page.activeStep}
              onChange={page.handleJump}
              aria-label="Jump to guidance workflow step"
            />
            <NextStepButton step={page.activeStep} onJump={page.handleJump} />
          </div>
        </div>
        <p style={{ margin: "10px 0 0", fontSize: 13, color: color.text.secondary, fontFamily: typography.fontFamily.body }}>
          {stepHint(page.activeStep)}
        </p>
      </div>
    </StickyChrome>
  );
}

function TourButtons({ onStart }: { onStart: () => void }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
      <button
        type="button"
        onClick={onStart}
        aria-label="Take the guideline tab tour"
        data-testid="guidance-tour-trigger"
        style={{
          border: 0,
          background: "transparent",
          cursor: "pointer",
          color: color.brand.primary,
          fontWeight: 600,
          fontFamily: typography.fontFamily.body,
        }}
      >
        Guide me
      </button>
      <button
        type="button"
        onClick={onStart}
        aria-label="Replay the guideline tab tour"
        data-testid="coach-tour-replay"
        style={{ border: 0, background: "transparent", cursor: "pointer", color: color.text.secondary }}
      >
        <ReplayRoundedIcon fontSize="small" />
      </button>
    </div>
  );
}

function stepHint(step: StepId): string {
  if (step === "load") return "Step 1 of 4. Find a guideline and load it.";
  if (step === "inspect") return "Step 2 of 4. Check what loaded, then generate rules.";
  if (step === "review") return "Step 3 of 4. Read each rule and decide.";
  return "Step 4 of 4. Compile so patients see the approved rules.";
}

function nextStep(step: StepId): { id: StepId; label: string } | null {
  if (step === "load") return { id: "inspect", label: "Next: Inspect" };
  if (step === "inspect") return { id: "review", label: "Next: Review" };
  if (step === "review") return { id: "compile", label: "Next: Compile" };
  return null;
}

function NextStepButton({
  step,
  onJump,
}: {
  step: StepId;
  onJump: (id: string) => void;
}) {
  const next = nextStep(step);
  if (!next) return null;
  return (
    <button
      type="button"
      onClick={() => onJump(next.id)}
      data-testid="guidance-next-step"
      style={{
        border: 0,
        borderRadius: 10,
        padding: "8px 14px",
        background: color.brand.primary,
        color: color.brand.onBrand,
        fontWeight: 600,
        fontFamily: typography.fontFamily.body,
        cursor: "pointer",
      }}
    >
      {next.label}
    </button>
  );
}

function GuidanceStepBody({ page }: { page: ReturnType<typeof useGuidancePage> }) {
  if (page.activeStep === "load") return <LoadStep page={page} />;
  if (page.activeStep === "inspect") return <InspectStep page={page} />;
  if (page.activeStep === "review") return <ReviewStep page={page} />;
  return <CompileStep page={page} />;
}

function LoadStep({ page }: { page: ReturnType<typeof useGuidancePage> }) {
  return (
    <StepCard
      id="nice-loader"
      index={0}
      step={1}
      title="Find and load a guideline"
      description="Search by condition name or type a NICE code. Loading brings the guideline into LEO."
      accent={color.brand.primary}
      reducedMotion={page.reducedMotion}
      open
      onOpenChange={() => undefined}
      dataTour="cg-02-load"
    >
      <NiceLoaderSection onGuidelineLoaded={() => page.setLoadedRefreshKey((n) => n + 1)} />
    </StepCard>
  );
}

function InspectStep({ page }: { page: ReturnType<typeof useGuidancePage> }) {
  return (
    <StepCard
      id="loaded-guidelines"
      index={1}
      step={2}
      title="What is in the knowledge graph"
      description="These are the guidelines already loaded. Check chapters, then generate rules."
      accent={color.text.secondary}
      reducedMotion={page.reducedMotion}
      open
      onOpenChange={() => undefined}
      dataTour="cg-03-inspect"
    >
      <LoadedGuidelinesPanel
        refreshKey={page.loadedRefreshKey}
        onRulesGenerated={() => page.setRuleRefreshKey((n) => n + 1)}
      />
    </StepCard>
  );
}

function ReviewStep({ page }: { page: ReturnType<typeof useGuidancePage> }) {
  return (
    <StepCard
      id="rule-review"
      index={2}
      step={3}
      title="Check and approve AI-generated rules"
      description="Read each suggested rule. Click Looks right, Edit, or Reject."
      accent={color.brand.primary}
      reducedMotion={page.reducedMotion}
      open
      onOpenChange={() => undefined}
    >
      <RuleReviewSection refreshKey={page.ruleRefreshKey} />
    </StepCard>
  );
}

function CompileStep({ page }: { page: ReturnType<typeof useGuidancePage> }) {
  return (
    <StepCard
      id="bitmap-lifecycle"
      index={3}
      step={4}
      title="Compile and go live"
      description="Compile approved rules into the live lookup index. Save is not live until you do this."
      accent={color.status.success}
      reducedMotion={page.reducedMotion}
      open
      onOpenChange={() => undefined}
      dataTour="cg-06-compile"
    >
      <BitmapLifecycleSection onVersionActivated={() => page.setBitmapRefreshKey((n) => n + 1)} />
    </StepCard>
  );
}
