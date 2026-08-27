/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-9A5C65AF
 *   Also implements: DO-DA9FD5E8
 *   DI: DI-5E7E8CEF, DI-6424B6FC, DI-BE09736F
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-9A5C65AF")
 */
"use client";

import { useCallback, useEffect, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import dynamic from "next/dynamic";
import { AnimatePresence, motion } from "framer-motion";
import {
  KnowledgePageLayout,
  isRole,
  springOrInstant,
  springs,
  useMotion,
  type KnowledgeLayoutWidth,
  type Role,
} from "@leo/design-system";
import { color } from "@leo/design-system/tokens";

import { KNOWLEDGE_TAB_COPY, type KnowledgeTabKey } from "@/lib/knowledgeCopy";
import { useAuth } from "@/lib/authContext";
import { KnowledgeSidebar } from "@/components/ui/KnowledgeSidebar";
import { KnowledgeCommandPalette } from "@/components/ui/KnowledgeCommandPalette";

// Per DI-LEO-AI-144: wide layout for data-heavy tabs.
const TAB_WIDTH: Record<KnowledgeTabKey, KnowledgeLayoutWidth> = {
  "training-data": "wide",
  "surface-forms": "wide",
  "context-rules": "wide",
  "guard-rules": "wide",
  "ai-instructions": "wide",
  "clinical-guidelines": "wide",
  pathways: "wide",
  "form-templates": "wide",
  domains: "wide",
  terminology: "wide",
  "results-labs": "wide",
  "validation-lab": "wide",
};

const GoldDatasetPage = dynamic(() => import("@/app/admin/gold-dataset/page"), { ssr: false });
const SurfaceFormsPage = dynamic(() => import("@/app/admin/surface-forms/page"), { ssr: false });
const ContextRulesPage = dynamic(() => import("@/app/admin/context-rules/page"), { ssr: false });
const GuardRulesPage = dynamic(() => import("@/app/admin/guard-rules/page"), { ssr: false });
const PromptsPage = dynamic(() => import("@/app/admin/prompts/page"), { ssr: false });
const GuidancePage = dynamic(() => import("@/app/admin/guidance/page"), { ssr: false });
const PathwaysPage = dynamic(() => import("@/app/admin/pathways/page"), { ssr: false });
const FormSchemasPage = dynamic(
  () => import("@/app/admin/form-schemas/page"),
  { ssr: false },
);
const DomainsPage = dynamic(() => import("@/app/admin/domains/page"), { ssr: false });
const TerminologyPage = dynamic(() => import("@/app/admin/terminology/page"), { ssr: false });
const LabResultsPage = dynamic(() => import("@/app/admin/lab-results/page"), { ssr: false });
const ValidationLabPage = dynamic(
  () => import("@/app/admin/validation-lab/page"),
  { ssr: false },
);

const TAB_PANELS: Record<KnowledgeTabKey, React.ComponentType> = {
  "training-data": GoldDatasetPage,
  "surface-forms": SurfaceFormsPage,
  "context-rules": ContextRulesPage,
  "guard-rules": GuardRulesPage,
  "ai-instructions": PromptsPage,
  "clinical-guidelines": GuidancePage,
  pathways: PathwaysPage,
  "form-templates": FormSchemasPage,
  domains: DomainsPage,
  terminology: TerminologyPage,
  "results-labs": LabResultsPage,
  "validation-lab": ValidationLabPage,
};

// Canonical tab order -- keys are part of URL contract and must stay stable.
export const TABS: Array<{ key: KnowledgeTabKey; label: string }> = [
  { key: "training-data", label: "Training Data" },
  { key: "surface-forms", label: "Phrase mappings" },
  { key: "context-rules", label: "Context Rules" },
  { key: "guard-rules", label: "Pipeline Guards" },
  { key: "ai-instructions", label: "AI Instructions" },
  { key: "clinical-guidelines", label: "Clinical Guidelines" },
  { key: "pathways", label: "Pathways" },
  { key: "form-templates", label: "Form templates" },
  { key: "domains", label: "Domains" },
  { key: "terminology", label: "Terminology" },
  { key: "results-labs", label: "Results/Labs" },
  { key: "validation-lab", label: "Validation Lab" },
];

function resolveRole(selectedRole: string | null): Role | null {
  return selectedRole && isRole(selectedRole) ? selectedRole : null;
}

export default function KnowledgePage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const auth = useAuth();
  const { reducedMotion } = useMotion();
  const [paletteOpen, setPaletteOpen] = useState(false);

  const rawTab = searchParams.get("tab") ?? "training-data";
  const tabParam = rawTab as KnowledgeTabKey;
  const validKeys = TABS.map((t) => t.key);
  const activeKey: KnowledgeTabKey = validKeys.includes(tabParam)
    ? tabParam
    : "training-data";
  const ActiveBody = TAB_PANELS[activeKey];
  const role = resolveRole(auth.session?.selectedRole ?? null);

  const handleTabChange = useCallback(
    (key: KnowledgeTabKey) => {
      router.replace(`/admin/knowledge?tab=${key}`);
    },
    [router],
  );

  // Retired Test Patients tab -> Validation Lab (single unified flow).
  useEffect(() => {
    if (rawTab !== "test-patients") return;
    const params = new URLSearchParams(searchParams.toString());
    params.set("tab", "validation-lab");
    params.delete("view");
    router.replace(`/admin/knowledge?${params.toString()}`);
  }, [rawTab, router, searchParams]);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setPaletteOpen(true);
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);

  return (
    <div
      style={{
        display: "flex",
        minHeight: "100vh",
        background: color.surface.canvas,
      }}
    >
      <KnowledgeSidebar
        activeKey={activeKey}
        onTabChange={handleTabChange}
        onSearchClick={() => setPaletteOpen(true)}
      />

      <div style={{ flex: 1, minWidth: 0, overflowY: "auto" }}>
        <AnimatePresence mode="wait">
          <motion.div
            key={activeKey}
            initial={reducedMotion ? { opacity: 0 } : { opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={reducedMotion ? { opacity: 0 } : { opacity: 0, y: -8 }}
            transition={springOrInstant(reducedMotion, springs.ui)}
          >
            <KnowledgePageLayout
              screenId={`knowledge-${activeKey}`}
              intro={KNOWLEDGE_TAB_COPY[activeKey]}
              role={role}
              width={TAB_WIDTH[activeKey]}
            >
              <ActiveBody />
            </KnowledgePageLayout>
          </motion.div>
        </AnimatePresence>
      </div>

      <KnowledgeCommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        onNavigate={(tab) => {
          handleTabChange(tab);
          setPaletteOpen(false);
        }}
      />
    </div>
  );
}
