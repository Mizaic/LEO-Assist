import { readFileSync } from "fs";
import path from "path";

const root = path.resolve(__dirname, "../");

function readUi(relativePath: string): string {
  return readFileSync(path.join(root, relativePath), "utf8");
}

describe("AI summarisation scenario runs", () => {
  it("redirects the AI summarisation page to Validation Lab", () => {
    const source = readUi("app/admin/ai-summarisation/page.tsx");

    expect(source).toContain("/admin/validation-lab");
    expect(source).toContain("router.replace");
    expect(source).toContain("Moved to Validation Lab");
  });

  it("uses the scenario run API and shows persisted SBAR detail", () => {
    const source = readUi("app/admin/ai-summarisation/ScenarioRunPanel.tsx");

    expect(source).toContain("listScenarioOptions");
    expect(source).toContain("startScenarioRun");
    expect(source).toContain("Previous scenario runs");
    expect(source).toContain("SbarFinalView");
    expect(source).toContain("composeSbarMarkdown");
    expect(source).toContain("normaliseBackgroundParts");
  });

  it("auto-refreshes and animates running scenario runs", () => {
    const source = readUi("app/admin/ai-summarisation/ScenarioRunPanel.tsx");

    expect(source).toContain("useAutoRefresh");
    expect(source).toContain("ACTIVE_STATUSES");
    expect(source).toContain("PULSE_SX");
    expect(source).toContain("LiveDot");
    expect(source).toContain("LinearProgress");
    expect(source).toContain("Skeleton");
    expect(source).toContain("Auto-refreshing");
  });

  it("labels pipeline stages by subgraph or action id, not durable_step", () => {
    const source = readUi("app/admin/ai-summarisation/ScenarioRunPanel.tsx");

    expect(source).toContain("stageDisplayName");
    expect(source).toContain('eventType !== "durable_step"');
    expect(source).toContain("stageDisplayName(stage)");
  });

  it("adds two validation tabs to the run detail dialog", () => {
    const source = readUi("app/admin/ai-summarisation/ScenarioRunPanel.tsx");

    expect(source).toContain("Workflow validation");
    expect(source).toContain("Consumer validation");
    expect(source).toContain("Tabs");
    expect(source).toContain("Tab");
  });

  it("shows CompletionEventPanel with raw completion event JSON", () => {
    const source = readUi("app/admin/ai-summarisation/ScenarioRunPanel.tsx");

    expect(source).toContain("CompletionEventPanel");
    expect(source).toContain("completion_event");
    expect(source).toContain("referral-assessments-output");
    expect(source).toContain("completion-event-json");
    expect(source).toContain("completion-event-toggle");
  });

  it("renders ConsumerValidationPanel with step-by-step consumer flow", () => {
    const source = readUi("app/admin/ai-summarisation/ScenarioRunPanel.tsx");

    expect(source).toContain("ConsumerValidationPanel");
    expect(source).toContain("consumer-completion-event");
    expect(source).toContain("load-widget-button");
    expect(source).toContain("Load widget");
    expect(source).toContain("widget-host");
    expect(source).toContain("leo-sbar-widget");
    expect(source).toContain("widget-event-log");
  });

  it("uses leo-sbar web component with correct attributes", () => {
    const source = readUi("app/admin/ai-summarisation/ScenarioRunPanel.tsx");

    expect(source).toContain("leo-sbar");
    expect(source).toContain("assessment-id");
    expect(source).toContain("widget-token");
    expect(source).toContain("proxy-origin");
    expect(source).toContain("@mizaic/leo-widget");
  });

  it("posts to /api/sdk/widget-token to exchange host secret for widget token", () => {
    const source = readUi("app/admin/ai-summarisation/ScenarioRunPanel.tsx");

    expect(source).toContain("/api/sdk/widget-token");
    expect(source).toContain("assessment_id");
    expect(source).toContain("widget_token");
  });

  it("widget-token route proxies sdk/auth/exchange server-to-server", () => {
    const source = readUi("app/api/sdk/widget-token/route.ts");

    expect(source).toContain("sdk/auth/exchange");
    expect(source).toContain("X-Mizaic-Host-Secret");
    expect(source).toContain("SCENARIO_SDK_HOST_SECRET");
    expect(source).toContain("SDK_HOST_SHARED_SECRET");
    expect(source).toContain("widget_token");
    expect(source).toContain("assessment_id");
  });

  it("completion event type is declared in the API types", () => {
    const source = readUi("app/admin/ai-summarisation/scenarioRunsApi.ts");

    expect(source).toContain("ReferralAssessmentCompletedEvent");
    expect(source).toContain("completion_event");
    expect(source).toContain("referral_assessment_completed");
  });
});
