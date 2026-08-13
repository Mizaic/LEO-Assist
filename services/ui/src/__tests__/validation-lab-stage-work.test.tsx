/**
 * Facts/codes preview and classified SBAR errors for Validation Lab.
 *
 * Atlas: DI-257D6883 / DO-158BE606 / VT-825F42CC
 */
import { render, screen } from "@testing-library/react";

import { StageWorkPreview } from "../app/admin/validation-lab/inspector/StageWorkPreview";
import { workPreviewFromStage } from "../app/admin/validation-lab/inspector/stageWorkItems";
import { parseSbarStageError } from "../app/admin/validation-lab/pipelineStageErrors";
import { watchStepId } from "../app/admin/validation-lab/inspector/pipelineWizardChrome";
import { plainStageCopy } from "../app/admin/validation-lab/plainStageCopy";

describe("workPreviewFromStage", () => {
  it("lists extracted facts", () => {
    const preview = workPreviewFromStage({
      entities: [{ text: "dysphagia" }, { text: "weight loss" }],
    });
    expect(preview.headline).toContain("2 facts");
    expect(preview.items?.map((item) => item.text)).toEqual([
      "dysphagia",
      "weight loss",
    ]);
  });

  it("says found 0 facts when entities is an empty list", () => {
    const preview = workPreviewFromStage({ entities: [] });
    expect(preview.headline).toBe("Found 0 facts");
    expect(preview.items).toEqual([]);
  });

  it("lists SNOMED codes nested under coding", () => {
    const preview = workPreviewFromStage({
      entities: [
        {
          text: "dysphagia",
          coding: { snomed_concept_id: "40739000" },
        },
      ],
    });
    expect(preview.items?.[0].code).toBe("40739000");
  });
});

describe("StageWorkPreview", () => {
  it("renders fact chips", () => {
    render(
      <StageWorkPreview
        preview={{
          headline: "Found 1 fact",
          items: [{ kind: "fact", text: "dysphagia" }],
        }}
        loading={false}
      />,
    );
    expect(screen.getByTestId("validation-lab-stage-work")).toHaveTextContent(
      "dysphagia",
    );
  });
});

describe("parseSbarStageError", () => {
  it("strips the situation prefix and keeps the classified code", () => {
    const parsed = parseSbarStageError(
      "situation:timeout:The AI service took too long to write the Situation section. Try running it again in a moment.",
    );
    expect(parsed?.code).toBe("timeout");
    expect(parsed?.message).toContain("too long");
    expect(parsed?.message).not.toMatch(/^situation:/);
  });

  it("still reads legacy situation:message strings", () => {
    const parsed = parseSbarStageError(
      "situation:Something went wrong while writing the Situation section. Try running it again. If it keeps happening, tell the team.",
    );
    expect(parsed?.stage).toBe("situation");
    expect(parsed?.message).toContain("Situation section");
  });
});

describe("watchStepId", () => {
  it("follows the latest running stage", () => {
    expect(
      watchStepId([
        { step_id: "act-ref-extract", status: "completed" },
        { step_id: "act-ref-sbar", status: "running" },
      ]),
    ).toBe("act-ref-sbar");
  });
});

describe("plainStageCopy", () => {
  it("gives coding-verify a different name from terminology", () => {
    expect(plainStageCopy("act-ref-terminology").name).toBe("Adding medical codes");
    expect(plainStageCopy("act-ref-coding-verify").name).toBe("Checking the codes");
  });
});
