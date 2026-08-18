/**
 * Step-specific Validation Lab evidence and review walk unlock.
 *
 * Atlas: DI-257D6883 / DI-C953EF73 / DO-158BE606 / DO-4FD76836
 *        VT-825F42CC / VT-F0A6B9F4
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { PipelineWizard } from "../app/admin/validation-lab/inspector/PipelineWizard";
import { StageDetailPane } from "../app/admin/validation-lab/inspector/StageDetailPane";
import { stageStory } from "../app/admin/validation-lab/inspector/stageEvidence";
import { plainStageCopy } from "../app/admin/validation-lab/plainStageCopy";
import {
  canOpenStep,
  walkComplete,
} from "../app/admin/validation-lab/reviewWalk";

describe("stageStory", () => {
  it("states cleaning label changes in English", () => {
    const story = stageStory(
      "act-ref-post-process",
      {
        entities: [
          { text: "GORD", assertion: "absent" },
          { text: "obesity", assertion: "present" },
        ],
      },
      {
        entities: [
          { text: "GORD", assertion: "present" },
          { text: "obesity", assertion: "present" },
        ],
      },
    );
    expect(story.kind).toBe("label_changes");
    expect(story.lines.join(" ")).toMatch(/GORD: was Present, now treated as Not present/);
    expect(story.lines.join(" ")).not.toMatch(/obesity/);
  });

  it("says LEO did not join any facts when linking has no relations", () => {
    const story = stageStory("act-ref-relation-link", {
      entities: [{ text: "jaundice" }, { text: "weight loss" }],
    });
    expect(story.kind).toBe("links");
    expect(story.empty).toMatch(/did not join any facts/i);
    expect(story.items || []).toHaveLength(0);
  });

  it("lists relation lines when linking found joins", () => {
    const story = stageStory("act-ref-relation-link", {
      entities: [
        {
          text: "weight loss",
          __relations: [
            { type: "associated_finding", target_text: "pancreatic cancer" },
          ],
        },
      ],
    });
    expect(story.items?.[0].relationTarget).toBe("pancreatic cancer");
  });

  it("says the checker did not change anything when llm_check_changes is empty", () => {
    const story = stageStory("act-ref-extraction-check", {
      entities: [{ text: "jaundice", assertion: "present" }],
      llm_check_changes: [],
    });
    expect(story.empty).toMatch(/did not change anything/i);
  });

  it("keeps the phrase before the code on coding steps", () => {
    const story = stageStory("act-ref-terminology", {
      entities: [
        {
          text: "standard proton pump inhibitor therapy",
          coding: { snomed_concept_id: "394872000" },
        },
      ],
    });
    expect(story.kind).toBe("codes");
    expect(story.items?.[0].text).toBe("standard proton pump inhibitor therapy");
    expect(story.items?.[0].code).toBe("394872000");
  });

  it("lists only inferred body sites", () => {
    const story = stageStory("act-ref-snomed-enrich", {
      entities: [
        { text: "jaundice" },
        { text: "Liver structure", inferred: true },
      ],
    });
    expect(story.kind).toBe("body_sites");
    expect(story.items?.map((item) => item.text)).toEqual(["Liver structure"]);
  });

  it("reports how many coded facts were saved", () => {
    const story = stageStory("act-ref-persist-facts", { documents_written: 7 });
    expect(story.headline).toBe("Saved 7 coded facts");
  });

  it("shows the referral reason text", () => {
    const story = stageStory("act-ref-referral-reason", {
      referral_reason: "Suspected pancreatic cancer with weight loss.",
    });
    expect(story.lines[0]).toMatch(/Suspected pancreatic cancer/);
  });

  it("lists matched guideline rules by name", () => {
    const story = stageStory("act-ref-compliance", {
      matched_rules: [{ name: "NICE NG12 weight loss", rule_id: "ng12-wl" }],
    });
    expect(story.lines.join(" ")).toMatch(/NICE NG12 weight loss/);
  });

  it("lists gap descriptions", () => {
    const story = stageStory("act-ref-completeness", {
      quality_issues: [
        { description: "Required referral information is missing" },
      ],
    });
    expect(story.lines[0]).toMatch(/Required referral information is missing/);
  });

  it("shows full SBAR sections", () => {
    const longSit =
      "This patient was referred because of persistent dyspepsia and a possible abdominal mass that has not settled on treatment.";
    const story = stageStory("act-ref-sbar", {
      sbar_report: {
        situation: longSit,
        background: "Prior GORD.",
        assessment: "Needs urgent imaging.",
        recommendation: "Two-week wait.",
      },
    });
    expect(story.lines.find((line) => line.startsWith("Situation:"))).toContain(
      longSit,
    );
    expect(story.lines.some((line) => line.startsWith("Background:"))).toBe(true);
  });
});

describe("plainStageCopy -- judge step", () => {
  it("names the after-coding judge Checking links after coding", () => {
    expect(plainStageCopy("act-ref-snomed-relation-judge").name).toBe(
      "Checking links after coding",
    );
    expect(plainStageCopy("act-ref-snomed-relation-judge").question).not.toBe(
      "Does this step look right?",
    );
  });
});

describe("reviewWalk -- Yes or a saved finding unlocks", () => {
  const spans = [
    { step_id: "act-ref-extract" },
    { step_id: "act-ref-post-process" },
    { step_id: "act-ref-sbar" },
  ];

  it("unlocks the next step after the current step is in reviewed", () => {
    expect(canOpenStep(spans, "act-ref-post-process", [])).toBe(false);
    expect(
      canOpenStep(spans, "act-ref-post-process", ["act-ref-extract"]),
    ).toBe(true);
  });

  it("marks the walk complete when every step is reviewed", () => {
    expect(walkComplete(spans, ["act-ref-extract"])).toBe(false);
    expect(
      walkComplete(spans, [
        "act-ref-extract",
        "act-ref-post-process",
        "act-ref-sbar",
      ]),
    ).toBe(true);
  });
});

describe("StageDetailPane -- extra detail and last-step finish", () => {
  it("hides worker hash and raw step id until Show extra detail", async () => {
    const user = userEvent.setup();
    render(
      <StageDetailPane
        span={{
          step_id: "act-ref-post-process",
          status: "completed",
          worker_id: "worker-hash-9f3a",
        }}
        detailReady={true}
        stageDetail={{
          step_id: "act-ref-post-process",
          status: "completed",
          output: { entities: [{ text: "jaundice" }] },
        }}
        stageLoading={false}
        onFixInGuards={() => {}}
        onNext={() => {}}
      />,
    );
    expect(screen.queryByText(/act-ref-/)).toBeNull();
    expect(screen.queryByText("worker-hash-9f3a")).toBeNull();
    await user.click(screen.getByRole("button", { name: /show extra detail/i }));
    expect(screen.getByText("worker-hash-9f3a")).toBeInTheDocument();
  });

  it("shows review finished copy on the last reviewed step", () => {
    render(
      <StageDetailPane
        span={{ step_id: "act-ref-sbar", status: "completed" }}
        detailReady={true}
        stageDetail={{
          step_id: "act-ref-sbar",
          status: "completed",
          output: {
            sbar_report: {
              situation: "Sit.",
              background: "Bg.",
              assessment: "As.",
              recommendation: "Rec.",
            },
          },
        }}
        stageLoading={false}
        onFixInGuards={() => {}}
        onNext={() => {}}
        walkFinished={true}
        reviewed={true}
        isLastStep={true}
      />,
    );
    expect(screen.getByTestId("validation-lab-review-finished")).toHaveTextContent(
      "Review finished. You can save this as gold.",
    );
  });

  it("shows Next step after the current step is reviewed and is not last", () => {
    render(
      <StageDetailPane
        span={{ step_id: "act-ref-extract", status: "completed" }}
        detailReady={true}
        stageDetail={null}
        stageLoading={false}
        onFixInGuards={() => {}}
        onNext={() => {}}
        reviewed={true}
        isLastStep={false}
      />,
    );
    expect(
      screen.getByRole("button", { name: /next step/i }),
    ).toBeInTheDocument();
  });
});

describe("PipelineWizard -- saved finding unlocks later stages", () => {
  it("unlocks the next rail row after findingSavedAt ticks", () => {
    const spans = [
      { step_id: "act-ref-extract", status: "completed" as const },
      { step_id: "act-ref-post-process", status: "completed" as const },
    ];
    const { rerender } = render(
      <PipelineWizard
        spans={spans}
        selectedStepId="act-ref-extract"
        onSelectStep={() => {}}
        stageDetail={null}
        stageLoading={false}
        onFixInGuards={() => {}}
        findingSavedAt={0}
      />,
    );
    expect(document.querySelectorAll('[data-locked="true"]')).toHaveLength(1);
    rerender(
      <PipelineWizard
        spans={spans}
        selectedStepId="act-ref-extract"
        onSelectStep={() => {}}
        stageDetail={null}
        stageLoading={false}
        onFixInGuards={() => {}}
        findingSavedAt={1}
      />,
    );
    expect(document.querySelectorAll('[data-locked="true"]')).toHaveLength(0);
  });
});
