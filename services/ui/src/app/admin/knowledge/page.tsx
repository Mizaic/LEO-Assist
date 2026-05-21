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

import { useCallback } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import Box from "@mui/material/Box";
import Tabs from "@mui/material/Tabs";
import Tab from "@mui/material/Tab";
import Typography from "@mui/material/Typography";
import dynamic from "next/dynamic";
import {
  KnowledgePageLayout,
  isRole,
  type KnowledgeLayoutWidth,
  type Role,
} from "@leo/design-system";

import { KNOWLEDGE_TAB_COPY, type KnowledgeTabKey } from "@/lib/knowledgeCopy";
import { useAuth } from "@/lib/authContext";

// Per DI-LEO-AI-144: data-heavy tabs get the wide (1600px) column so
// reviewers have horizontal room for long clinical sentences, entity
// chip rows, and grid columns. Intro-heavy tabs stay at the reading
// default (1280px).
const TAB_WIDTH: Record<KnowledgeTabKey, KnowledgeLayoutWidth> = {
  "training-data": "wide",
  "surface-forms": "wide",
  "context-rules": "wide",
  "ai-instructions": "wide",
  "clinical-guidelines": "wide",
  pathways: "wide",
  domains: "wide",
  terminology: "wide",
  "ai-summarisation": "wide",
  "test-patients": "wide",
  "extraction-scenarios": "wide",
  "coding-validation": "wide",
};

const GoldDatasetPage = dynamic(() => import("@/app/admin/gold-dataset/page"), { ssr: false });
const SurfaceFormsPage = dynamic(() => import("@/app/admin/surface-forms/page"), { ssr: false });
const ContextRulesPage = dynamic(() => import("@/app/admin/context-rules/page"), { ssr: false });
const PromptsPage = dynamic(() => import("@/app/admin/prompts/page"), { ssr: false });
const GuidancePage = dynamic(() => import("@/app/admin/guidance/page"), { ssr: false });
const PathwaysPage = dynamic(() => import("@/app/admin/pathways/page"), { ssr: false });
const DomainsPage = dynamic(() => import("@/app/admin/domains/page"), { ssr: false });
const TerminologyPage = dynamic(() => import("@/app/admin/terminology/page"), { ssr: false });
const AiSummarisationPage = dynamic(
  () => import("@/app/admin/ai-summarisation/page"),
  { ssr: false },
);
const TestPatientsPage = dynamic(
  () => import("@/app/admin/knowledge/test-patients/page"),
  { ssr: false },
);
const ExtractionScenariosPage = dynamic(
  () => import("@/app/admin/extraction-scenarios/page"),
  { ssr: false },
);
const CodingValidationPage = dynamic(
  () => import("@/app/admin/coding-validation/page"),
  { ssr: false },
);

// Canonical tab order per DI-LEO-AI-135. First five are the legacy
// Knowledge tabs (reference data curated by staff + QA); last three are
// the legacy Clinical tabs merged in by Phase 2 of the role-first
// redesign. The keys are part of the URL contract and must stay stable.
export const TABS: Array<{ key: KnowledgeTabKey; label: string }> = [
  { key: "training-data", label: "Training Data" },
  { key: "surface-forms", label: "Surface Forms" },
  { key: "context-rules", label: "Context Rules" },
  { key: "ai-instructions", label: "AI Instructions" },
  { key: "clinical-guidelines", label: "Clinical Guidelines" },
  { key: "pathways", label: "Pathways" },
  { key: "domains", label: "Domains" },
  { key: "terminology", label: "Terminology" },
  { key: "ai-summarisation", label: "AI Summarisation" },
  { key: "test-patients", label: "Test Patients" },
  { key: "extraction-scenarios", label: "Extraction Scenarios" },
  { key: "coding-validation", label: "Coding Validation" },
];

const TAB_PANELS: Record<KnowledgeTabKey, React.ComponentType> = {
  "training-data": GoldDatasetPage,
  "surface-forms": SurfaceFormsPage,
  "context-rules": ContextRulesPage,
  "ai-instructions": PromptsPage,
  "clinical-guidelines": GuidancePage,
  pathways: PathwaysPage,
  domains: DomainsPage,
  terminology: TerminologyPage,
  "ai-summarisation": AiSummarisationPage,
  "test-patients": TestPatientsPage,
  "extraction-scenarios": ExtractionScenariosPage,
  "coding-validation": CodingValidationPage,
};

function resolveRole(selectedRole: string | null): Role | null {
  return selectedRole && isRole(selectedRole) ? selectedRole : null;
}

export default function KnowledgePage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const auth = useAuth();
  const tabParam = (searchParams.get("tab") ?? "training-data") as KnowledgeTabKey;
  const activeIdx = Math.max(0, TABS.findIndex((t) => t.key === tabParam));
  const activeKey = TABS[activeIdx].key;
  const ActiveBody = TAB_PANELS[activeKey];
  const role = resolveRole(auth.session?.selectedRole ?? null);

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

      <KnowledgePageLayout
        screenId={`knowledge-${activeKey}`}
        intro={KNOWLEDGE_TAB_COPY[activeKey]}
        role={role}
        width={TAB_WIDTH[activeKey]}
      >
        <ActiveBody />
      </KnowledgePageLayout>
    </Box>
  );
}
