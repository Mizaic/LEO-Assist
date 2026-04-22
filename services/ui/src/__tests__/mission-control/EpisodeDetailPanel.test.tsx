/**
 * Live-render VT for EpisodeDetailPanel.
 *
 * Atlas trace:
 *   DI: DI-CC0BD732
 *   DI: DI-885930F8
 *   DI: DI-E8FE404D
 *
 * Verifies the actual rendered behaviour:
 *   - Episode header chips reflect the model values.
 *   - Coherence + coding QA flags trigger the per-flag-reason
 *     resolve callbacks.
 *   - Empty canonical-code and empty-SBAR states surface their
 *     respective alerts and primary actions.
 */

import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import EpisodeDetailPanel, {
  type EpisodeDetail,
} from "@/components/mission-control/EpisodeDetailPanel";

jest.mock("@/components/markdown-editor/MarkdownEditor", () => ({
  __esModule: true,
  default: ({ initialContent }: { initialContent: string }) => (
    <div data-testid="md-stub">{initialContent}</div>
  ),
}));

const BASE_EPISODE: EpisodeDetail = {
  episodeId: "ep-breast-1",
  patientId: "P1",
  suspectedSite: "breast",
  status: "open",
  encounterIds: ["e-1", "e-2", "e-3"],
  canonicalCode: {
    conceptId: "254837009",
    displayName: "Malignant tumor of breast",
    intent: "confirmed",
    confidence: 0.95,
  },
  sbarMarkdown: "# SBAR\n\n## Situation\nRight breast lesion.\n",
  coherenceFlags: [],
  codingQaFlags: [],
};

describe("EpisodeDetailPanel live render", () => {
  test("renders episode header chips with model values", () => {
    render(<EpisodeDetailPanel episode={BASE_EPISODE} />);
    expect(screen.getByTestId("episode-detail-site-chip")).toHaveTextContent(
      "Site: breast",
    );
    expect(screen.getByTestId("episode-detail-status-chip")).toHaveTextContent(
      "Status: open",
    );
    expect(
      screen.getByTestId("episode-detail-encounter-count"),
    ).toHaveTextContent("3 encounters");
  });

  test("canonical code card shows display name, intent and confidence", () => {
    render(<EpisodeDetailPanel episode={BASE_EPISODE} />);
    expect(screen.getByTestId("canonical-code-display")).toHaveTextContent(
      "Malignant tumor of breast (254837009)",
    );
    expect(screen.getByTestId("canonical-code-intent")).toHaveTextContent(
      "confirmed",
    );
    expect(screen.getByTestId("canonical-code-confidence")).toHaveTextContent(
      "confidence 95%",
    );
  });

  test("accept and override callbacks fire when buttons clicked", () => {
    const onAccept = jest.fn();
    const onOverride = jest.fn();
    render(
      <EpisodeDetailPanel
        episode={BASE_EPISODE}
        onAcceptCode={onAccept}
        onOverrideCode={onOverride}
      />,
    );
    fireEvent.click(screen.getByTestId("canonical-code-accept"));
    fireEvent.click(screen.getByTestId("canonical-code-override"));
    expect(onAccept).toHaveBeenCalledTimes(1);
    expect(onOverride).toHaveBeenCalledTimes(1);
  });

  test("missing canonical code shows the empty alert", () => {
    render(
      <EpisodeDetailPanel
        episode={{ ...BASE_EPISODE, canonicalCode: null }}
      />,
    );
    expect(screen.getByTestId("canonical-code-empty")).toBeInTheDocument();
  });

  test("coherence flag click invokes onResolveCoherenceFlag with the code", () => {
    const onResolve = jest.fn();
    render(
      <EpisodeDetailPanel
        episode={{
          ...BASE_EPISODE,
          coherenceFlags: [
            {
              code: "narrative_contradiction",
              severity: "high",
              summary: "Assessment denies cancer but recommendation escalates.",
            },
          ],
        }}
        onResolveCoherenceFlag={onResolve}
      />,
    );
    fireEvent.click(
      screen.getByTestId("coherence-flag-narrative_contradiction-resolve"),
    );
    expect(onResolve).toHaveBeenCalledWith("narrative_contradiction");
  });

  test("coding QA flag click invokes onResolveCodingQaFlag with the flag id", () => {
    const onResolve = jest.fn();
    render(
      <EpisodeDetailPanel
        episode={{
          ...BASE_EPISODE,
          codingQaFlags: [
            {
              flagId: "qa-1",
              code: "site_mismatch",
              severity: "medium",
              summary: "Encounter coded as lung but episode is breast.",
              encounterIds: ["e-99"],
            },
          ],
        }}
        onResolveCodingQaFlag={onResolve}
      />,
    );
    fireEvent.click(screen.getByTestId("coding-qa-flag-qa-1-resolve"));
    expect(onResolve).toHaveBeenCalledWith("qa-1");
  });

  test("empty SBAR shows generate prompt and triggers callback", () => {
    const onRegenerate = jest.fn();
    render(
      <EpisodeDetailPanel
        episode={{ ...BASE_EPISODE, sbarMarkdown: "" }}
        onRegenerateSbar={onRegenerate}
      />,
    );
    expect(screen.getByTestId("episode-sbar-empty")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("episode-sbar-generate"));
    expect(onRegenerate).toHaveBeenCalledTimes(1);
  });

  test("scope chip names the episode id explicitly", () => {
    render(<EpisodeDetailPanel episode={BASE_EPISODE} />);
    expect(screen.getByTestId("episode-sbar-scope-chip")).toHaveTextContent(
      "Scope: episode ep-breast-1",
    );
  });
});
