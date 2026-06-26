/**
 * VT -- Multi-phase AI Draft Assistant (static-source layer)
 *
 * Atlas trace:
 *   DO: DO-3775670C
 *   DI: DI-64CA7740
 *
 * Covers:
 *   - auditDraftChatAdapter.ts: new phase/answers/approvedTiles fields
 *   - auditMockData.ts: generateMockData returns correctly shaped data
 *   - AuditDraftAssistant.tsx: phase state machine and sub-component refs
 *   - AuditDraftSubComponents.tsx: DiscoveryCard, PlanCard, BuildReport exports
 *   - AuditTemplateRenderer.tsx: PresentationMode and mock data integration
 *   - MetricTile.tsx: mockData prop and storytelling headline
 *   - TileConfigPanel.tsx: Story tab present
 *   - audit_template Pydantic model: TileStoryConfig fields
 */

import fs from "fs";
import path from "path";

const ROOT = path.resolve(__dirname, "../../../..");
const read = (rel: string) => fs.readFileSync(path.join(ROOT, rel), "utf8");

const ADAPTER = "services/ui/src/lib/auditDraftChatAdapter.ts";
const MOCK_DATA = "services/ui/src/lib/auditMockData.ts";
const ASSISTANT = "services/ui/src/components/audit-template-builder/AuditDraftAssistant.tsx";
const SUBCOMPS = "services/ui/src/components/audit-template-builder/AuditDraftSubComponents.tsx";
const RENDERER = "services/ui/src/components/audit-template-renderer/AuditTemplateRenderer.tsx";
const METRIC_TILE = "services/ui/src/components/audit-template-renderer/MetricTile.tsx";
const PRESENTATION = "services/ui/src/components/audit-template-renderer/PresentationMode.tsx";
const CONFIG_PANEL = "services/ui/src/components/audit-template-builder/TileConfigPanel.tsx";
const API_TS = "services/ui/src/lib/auditTemplateApi.ts";

// ---------------------------------------------------------------------------
// auditDraftChatAdapter -- new types and phase routing
// ---------------------------------------------------------------------------

describe("auditDraftChatAdapter -- multi-phase types", () => {
  let src: string;
  beforeAll(() => { src = read(ADAPTER); });

  test("exports DiscoveryQuestion interface", () => {
    expect(src).toContain("DiscoveryQuestion");
    expect(src).toContain("options: DiscoveryOption[]");
  });

  test("exports DashboardPlan interface", () => {
    expect(src).toContain("DashboardPlan");
    expect(src).toContain("rationale: string");
    expect(src).toContain("tiles: PlannedTile[]");
    expect(src).toContain("warnings: string[]");
  });

  test("exports PlannedTile with reason field", () => {
    expect(src).toContain("PlannedTile");
    expect(src).toContain("reason: string");
  });

  test("exports BuildSummary", () => {
    expect(src).toContain("BuildSummary");
    expect(src).toContain("added: number");
    expect(src).toContain("skipped: SkippedTile[]");
  });

  test("SendMessageOptions has phase field", () => {
    expect(src).toContain("phase: AssistantPhaseRequest");
  });

  test("SendMessageOptions has answers field", () => {
    expect(src).toContain("answers?: Record<string, string>");
  });

  test("SendMessageOptions has approvedTiles field", () => {
    expect(src).toContain("approvedTiles?: PlannedTile[]");
  });

  test("request body includes phase and answers", () => {
    expect(src).toContain("phase,");
    expect(src).toContain("answers,");
    expect(src).toContain("approved_tiles:");
  });

  test("handles questions-available SSE event", () => {
    expect(src).toContain("questions-available");
    expect(src).toContain("onQuestions?.(");
  });

  test("handles plan-available SSE event", () => {
    expect(src).toContain("plan-available");
    expect(src).toContain("onPlan?.(");
  });

  test("handles tile-added SSE event", () => {
    expect(src).toContain("tile-added");
    expect(src).toContain("onTileAdded?.(");
  });

  test("handles build-complete SSE event", () => {
    expect(src).toContain("build-complete");
    expect(src).toContain("onBuildComplete?.(");
  });
});

// ---------------------------------------------------------------------------
// auditMockData -- generateMockData function
// ---------------------------------------------------------------------------

describe("auditMockData -- mock data generator", () => {
  let src: string;
  beforeAll(() => { src = read(MOCK_DATA); });

  test("exports generateMockData function", () => {
    expect(src).toContain("export function generateMockData");
  });

  test("accepts MetricCatalogueEntry parameter", () => {
    expect(src).toContain("MetricCatalogueEntry");
  });

  test("returns MetricRunResult shape", () => {
    expect(src).toContain("MetricRunResult");
    expect(src).toContain("metric_id:");
    expect(src).toContain("columns");
    expect(src).toContain("rows:");
  });

  test("has curated data for patient_count", () => {
    expect(src).toContain("patient_count");
    expect(src).toContain("count: 142");
  });

  test("has curated data for episode_count_by_condition", () => {
    expect(src).toContain("episode_count_by_condition");
    expect(src).toContain("Breast");
  });

  test("has curated data for cancer_stage_distribution", () => {
    expect(src).toContain("cancer_stage_distribution");
    expect(src).toContain("Stage 1");
  });

  test("has generic fallback for unknown metrics", () => {
    expect(src).toContain("genericMockRows");
    expect(src).toContain("output_schema");
  });
});

// ---------------------------------------------------------------------------
// AuditDraftAssistant -- phase state machine
// ---------------------------------------------------------------------------

describe("AuditDraftAssistant -- phase state machine", () => {
  let src: string;
  beforeAll(() => { src = read(ASSISTANT); });

  test("defines AssistantPhase type with all phases", () => {
    expect(src).toContain("AssistantPhase");
    expect(src).toContain('"idle"');
    expect(src).toContain('"intent"');
    expect(src).toContain('"discovering"');
    expect(src).toContain('"planning"');
    expect(src).toContain('"reviewing"');
    expect(src).toContain('"building"');
  });

  test("imports DiscoveryCard and PlanCard sub-components", () => {
    expect(src).toContain("DiscoveryCard");
    expect(src).toContain("PlanCard");
    expect(src).toContain("BuildReport");
  });

  test("input is hidden during reviewing phase", () => {
    expect(src).toContain('showInput');
    expect(src).toContain('"reviewing"');
  });

  test("suggestion chips only shown in idle phase", () => {
    expect(src).toContain("showSuggestions");
  });

  test("uses sendMessage with phase field", () => {
    expect(src).toContain("phase: \"intent\"");
    expect(src).toContain("phase: \"discover\"");
    expect(src).toContain("phase: \"build\"");
  });

  test("aborts stream on drawer close", () => {
    expect(src).toContain("abortRef.current?.abort()");
    expect(src).toContain("AbortController");
  });

  test("onAddTile accepts storyHeadline and highlightKey", () => {
    expect(src).toContain("storyHeadline");
    expect(src).toContain("highlightKey");
  });
});

// ---------------------------------------------------------------------------
// AuditDraftSubComponents -- DiscoveryCard, PlanCard, BuildReport
// ---------------------------------------------------------------------------

describe("AuditDraftSubComponents -- exported sub-components", () => {
  let src: string;
  beforeAll(() => { src = read(SUBCOMPS); });

  test("exports DiscoveryCard", () => {
    expect(src).toContain("export function DiscoveryCard");
  });

  test("DiscoveryCard renders ToggleButtonGroup", () => {
    expect(src).toContain("ToggleButtonGroup");
    expect(src).toContain("ToggleButton");
  });

  test("DiscoveryCard shows recommended star", () => {
    expect(src).toContain("recommended");
    expect(src).toContain("StarIcon");
  });

  test("DiscoveryCard has Continue button", () => {
    expect(src).toContain("Continue");
  });

  test("exports PlanCard", () => {
    expect(src).toContain("export function PlanCard");
  });

  test("PlanCard has Approve button", () => {
    expect(src).toContain("Approve");
  });

  test("PlanCard has Request changes button", () => {
    expect(src).toContain("Request changes");
  });

  test("exports BuildReport", () => {
    expect(src).toContain("export function BuildReport");
  });

  test("BuildReport shows added count", () => {
    expect(src).toContain("summary.added");
    expect(src).toContain("tiles added");
  });
});

// ---------------------------------------------------------------------------
// AuditTemplateRenderer -- mock data and presentation mode
// ---------------------------------------------------------------------------

describe("AuditTemplateRenderer -- mock data and presentation mode", () => {
  let src: string;
  beforeAll(() => { src = read(RENDERER); });

  test("accepts useMockData prop", () => {
    expect(src).toContain("useMockData");
  });

  test("accepts catalogue prop", () => {
    expect(src).toContain("catalogue");
  });

  test("imports generateMockData", () => {
    expect(src).toContain("generateMockData");
    expect(src).toContain("auditMockData");
  });

  test("passes mockData to MetricTile", () => {
    expect(src).toContain("mockData={mockDataMap.get(tile.metric_id)}");
  });

  test("shows MockBadge when useMockData is true", () => {
    expect(src).toContain("MockBadge");
    expect(src).toContain("Mock data");
  });

  test("renders PresentationMode on state toggle", () => {
    expect(src).toContain("PresentationMode");
    expect(src).toContain("presentationOpen");
  });

  test("Present button triggers presentation mode", () => {
    expect(src).toContain("setPresentationOpen(true)");
    expect(src).toContain("Present");
    expect(src).toContain("SlideshowOutlinedIcon");
  });
});

// ---------------------------------------------------------------------------
// MetricTile -- mockData prop and storytelling
// ---------------------------------------------------------------------------

describe("MetricTile -- mockData prop and storytelling", () => {
  let src: string;
  beforeAll(() => { src = read(METRIC_TILE); });

  test("accepts mockData optional prop", () => {
    expect(src).toContain("mockData?: MetricRunResult");
  });

  test("skips API fetch when mockData is provided", () => {
    expect(src).toContain("if (mockData)");
    expect(src).toContain("setResult(mockData");
  });

  test("renders headline overlay when story.headline set", () => {
    expect(src).toContain("story?.headline");
    expect(src).toContain("DataPOV");
  });

  test("applies highlight emphasis to bar chart", () => {
    expect(src).toContain("highlight_key");
    expect(src).toContain("HIGHLIGHT");
    expect(src).toContain("MUTED");
  });

  test("renders threshold ReferenceLine", () => {
    expect(src).toContain("ReferenceLine");
    expect(src).toContain("thresholdLines");
    expect(src).toContain("threshold");
  });

  test("renders callout Label", () => {
    expect(src).toContain("calloutLabel");
    expect(src).toContain("callout");
  });
});

// ---------------------------------------------------------------------------
// PresentationMode -- full-screen slide deck
// ---------------------------------------------------------------------------

describe("PresentationMode -- slide deck component", () => {
  let src: string;
  beforeAll(() => { src = read(PRESENTATION); });

  test("builds slide deck from template sections", () => {
    expect(src).toContain("buildSlides");
    expect(src).toContain("section-title");
  });

  test("keyboard navigation handlers", () => {
    expect(src).toContain("ArrowRight");
    expect(src).toContain("ArrowLeft");
    expect(src).toContain("Escape");
  });

  test("progress indicator present", () => {
    expect(src).toContain("ProgressBar");
    expect(src).toContain("total");
  });

  test("animate_in CSS transition", () => {
    expect(src).toContain("animate_in");
    expect(src).toContain("transition");
  });

  test("section title card component", () => {
    expect(src).toContain("SectionTitleCard");
  });
});

// ---------------------------------------------------------------------------
// TileConfigPanel -- Story tab
// ---------------------------------------------------------------------------

describe("TileConfigPanel -- Story tab", () => {
  let src: string;
  beforeAll(() => { src = read(CONFIG_PANEL); });

  test("has Story tab label", () => {
    expect(src).toContain('"Story"');
  });

  test("has Settings tab label", () => {
    expect(src).toContain('"Settings"');
  });

  test("StoryTab has headline input", () => {
    expect(src).toContain("Data headline");
    expect(src).toContain("headline");
  });

  test("StoryTab has highlight_key input", () => {
    expect(src).toContain("Highlight category");
    expect(src).toContain("highlight_key");
  });

  test("StoryTab has benchmark/threshold annotations", () => {
    expect(src).toContain("Benchmark lines");
    expect(src).toContain("threshold");
  });

  test("StoryTab has callout annotations", () => {
    expect(src).toContain("Callout annotations");
    expect(src).toContain("callout");
  });

  test("StoryTab has animate-in toggle", () => {
    expect(src).toContain("animate_in");
    expect(src).toContain("presentation mode");
  });
});

// ---------------------------------------------------------------------------
// auditTemplateApi -- TileStoryConfig types
// ---------------------------------------------------------------------------

describe("auditTemplateApi -- TileStoryConfig types", () => {
  let src: string;
  beforeAll(() => { src = read(API_TS); });

  test("exports TileAnnotation interface", () => {
    expect(src).toContain("TileAnnotation");
    expect(src).toContain('"callout" | "threshold"');
  });

  test("exports TileStoryConfig interface", () => {
    expect(src).toContain("TileStoryConfig");
    expect(src).toContain("headline?: string");
    expect(src).toContain("highlight_key?: string");
    expect(src).toContain("annotations?: TileAnnotation[]");
    expect(src).toContain("animate_in?: boolean");
  });

  test("AuditTile has optional story field", () => {
    expect(src).toContain("story?: TileStoryConfig");
  });
});
