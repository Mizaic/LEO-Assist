/**
 * Atlas trace:
 *   DO: DO-0A8B7188
 *   DI: DI-0C8FBAF7
 */
"use client";

import { useCallback, useEffect, useState } from "react";
import { useMotion, type StatTile } from "@leo/design-system";

import { pageTourJumpForStep, type TourStep } from "./guidanceTourSteps";
import { GUIDANCE_SPLASH_SESSION_KEY } from "./GuidelineBuilderSplash";

export type StepId = "load" | "inspect" | "review" | "compile";

export const STEP_SECTION_IDS: Record<StepId, string> = {
  load: "nice-loader",
  inspect: "loaded-guidelines",
  review: "rule-review",
  compile: "bitmap-lifecycle",
};

export const STEP_TABS: ReadonlyArray<{ id: StepId; label: string; href: string }> = [
  { id: "load", label: "1. Load", href: "#nice-loader" },
  { id: "inspect", label: "2. Inspect", href: "#loaded-guidelines" },
  { id: "review", label: "3. Review", href: "#rule-review" },
  { id: "compile", label: "4. Compile", href: "#bitmap-lifecycle" },
];

interface PageStats {
  guidelinesLoaded: number;
  rulesPending: number;
  rulesApproved: number;
  activeBitmapVersion: string;
}

const EMPTY_STATS: PageStats = {
  guidelinesLoaded: 0,
  rulesPending: 0,
  rulesApproved: 0,
  activeBitmapVersion: "--",
};

export function useGuidancePage() {
  const [loadedRefreshKey, setLoadedRefreshKey] = useState(0);
  const [ruleRefreshKey, setRuleRefreshKey] = useState(0);
  const [bitmapRefreshKey, setBitmapRefreshKey] = useState(0);
  const [activeStep, setActiveStep] = useState<StepId>("load");
  const [stats, setStats] = useState<PageStats>(EMPTY_STATS);
  const [showSplash, setShowSplash] = useState(false);
  const [showLocalImport, setShowLocalImport] = useState(false);
  const [tourActive, setTourActive] = useState(false);
  const { reducedMotion } = useMotion();

  useEffect(() => {
    fetchPageStats().then(setStats).catch(() => {
      /* keep last good stats */
    });
  }, [loadedRefreshKey, ruleRefreshKey, bitmapRefreshKey]);

  useEffect(() => {
    try {
      if (!sessionStorage.getItem(GUIDANCE_SPLASH_SESSION_KEY)) {
        setShowSplash(true);
      }
    } catch {
      /* private browsing -- skip splash */
    }
  }, []);

  const dismissSplash = useCallback(() => {
    try {
      sessionStorage.setItem(GUIDANCE_SPLASH_SESSION_KEY, "1");
    } catch {
      /* best-effort */
    }
    setShowSplash(false);
  }, []);

  const handleJump = useCallback((id: string) => {
    setActiveStep(id as StepId);
  }, []);
  const preparePageTourStep = usePrepareTour(handleJump);

  return {
    loadedRefreshKey,
    ruleRefreshKey,
    bitmapRefreshKey,
    setLoadedRefreshKey,
    setRuleRefreshKey,
    setBitmapRefreshKey,
    activeStep,
    setActiveStep,
    handleJump,
    statTiles: toStatTiles(stats),
    showSplash,
    dismissSplash,
    showLocalImport,
    setShowLocalImport,
    tourActive,
    setTourActive,
    reducedMotion,
    preparePageTourStep,
    finishPageTour: () => setTourActive(false),
  };
}

function usePrepareTour(handleJump: (id: string) => void) {
  return useCallback(async (step: TourStep) => {
    const jump = pageTourJumpForStep(step.id);
    if (jump) handleJump(jump);
    await delay(120);
    if (jump === "review") {
      const closed = document.querySelector(
        '[data-testid="rule-pool-pending"] button[aria-expanded="false"]',
      );
      if (closed instanceof HTMLElement) closed.click();
      await delay(80);
    }
    if (step.id === "cg-05-card") {
      if (!document.querySelector('[data-tour="cg-05-card"]')) return false;
    }
    return true;
  }, [handleJump]);
}

function toStatTiles(stats: PageStats): StatTile[] {
  return [
    { id: "loaded", label: "Guidelines loaded", value: stats.guidelinesLoaded },
    {
      id: "pending",
      label: "Rules pending",
      value: stats.rulesPending,
      tone: stats.rulesPending > 0 ? "warning" : "neutral",
      hint: stats.rulesPending > 0 ? "Waiting for a person to check" : undefined,
    },
    { id: "approved", label: "Rules approved", value: stats.rulesApproved },
    {
      id: "bitmap",
      label: "Active bitmap version",
      value: stats.activeBitmapVersion,
      hint: "The live lookup index",
    },
  ];
}

async function fetchPageStats(): Promise<PageStats> {
  const [loadedResp, bitmapResp] = await Promise.allSettled([
    fetch("/api/nice/loaded"),
    fetch(
      "/api/terminology/guidelines/bitmap/status?scope_type=global&scope_id=default",
    ),
  ]);
  const loaded = await readLoaded(loadedResp);
  return { ...loaded, activeBitmapVersion: await readBitmapVersion(bitmapResp) };
}

async function readLoaded(
  loadedResp: PromiseSettledResult<Response>,
): Promise<Pick<PageStats, "guidelinesLoaded" | "rulesPending" | "rulesApproved">> {
  if (loadedResp.status !== "fulfilled" || !loadedResp.value.ok) {
    return { guidelinesLoaded: 0, rulesPending: 0, rulesApproved: 0 };
  }
  const data = (await loadedResp.value.json()) as Array<{
    rules_pending?: number;
    rules_approved?: number;
  }>;
  return {
    guidelinesLoaded: data.length,
    rulesPending: data.reduce((sum, row) => sum + (row.rules_pending ?? 0), 0),
    rulesApproved: data.reduce((sum, row) => sum + (row.rules_approved ?? 0), 0),
  };
}

async function readBitmapVersion(
  bitmapResp: PromiseSettledResult<Response>,
): Promise<string> {
  if (bitmapResp.status !== "fulfilled" || !bitmapResp.value.ok) return "--";
  const bm = (await bitmapResp.value.json()) as { active_version?: string | null };
  return bm.active_version || "--";
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}
