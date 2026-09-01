/**
 * Facts/codes preview and classified SBAR errors for Validation Lab.
 *
 * Atlas: DI-257D6883 / DO-158BE606 / VT-825F42CC
 */
import { render, screen } from "@testing-library/react";
import { StageDetailPane } from "../app/admin/validation-lab/inspector/StageDetailPane";
import type { LabStageDetail, LabTraceSpan } from "../app/admin/validation-lab/inspectorTypes";

import { LetterMarkLegend } from "../app/admin/validation-lab/LetterMarks";
import { StageWorkPreview } from "../app/admin/validation-lab/inspector/StageWorkPreview";
import {
  extractRelationItems,
  formatEvidenceTooltip,
  plainLetterText,
  workPreviewFromStage,
} from "../app/admin/validation-lab/inspector/stageWorkItems";
import {
  diffLetterMarks,
  diffWorkItems,
  letterHighlightMarks,
  letterHighlightTerms,
} from "../app/admin/validation-lab/letterHighlight";
import {
  assertionStyle,
  markBackground,
  markContextBar,
  semanticTagStyle,
} from "../app/admin/validation-lab/letterMarkStyle";
import {
  canOpenStep,
  nextStepId,
  unlockedIndex,
} from "../app/admin/validation-lab/reviewWalk";
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

  it("copies assertion and semantic tag onto each fact", () => {
    const preview = workPreviewFromStage({
      entities: [
        {
          text: "chronic pancreatitis",
          assertion: "historical",
          semantic_tag: "disorder",
        },
      ],
    });
    expect(preview.items?.[0].assertion).toBe("historical");
    expect(preview.items?.[0].semanticTag).toBe("disorder");
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

describe("letterHighlightTerms", () => {
  it("marks every fact that can appear in the letter", () => {
    const terms = letterHighlightTerms(
      [
        { text: "suspected pancreatic cancer" },
        { text: "painless jaundice", evidence: "painless jaundice" },
        { text: "chronic pancreatitis" },
      ],
      "",
    );
    expect(terms).toEqual(
      expect.arrayContaining([
        "suspected pancreatic cancer",
        "painless jaundice",
        "chronic pancreatitis",
      ]),
    );
    expect(terms[0]).toBe("suspected pancreatic cancer");
  });

  it("keeps context and kind on each letter mark", () => {
    const marks = letterHighlightMarks([
      {
        text: "chronic pancreatitis",
        assertion: "historical",
        semanticTag: "disorder",
      },
      {
        text: "painless jaundice",
        assertion: "present",
        semanticTag: "finding",
      },
    ]);
    expect(marks).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          term: "chronic pancreatitis",
          assertion: "historical",
          semanticTag: "disorder",
        }),
        expect.objectContaining({
          term: "painless jaundice",
          assertion: "present",
          semanticTag: "finding",
        }),
      ]),
    );
  });

  it("uses one fill colour for kind and a bar colour for context", () => {
    expect(markBackground("historical", "disorder")).toBe("#F9A8D4");
    expect(markBackground("present", "finding")).toBe("#99F6E4");
    expect(markBackground("present", "")).toBe("#E2E8F0");
    expect(markContextBar("historical")).toBe("#475569");
    expect(markContextBar("present")).toBe("#CA8A04");
    expect(markContextBar("absent")).toBe("#DC2626");
    expect(markContextBar("planned")).toBe("#2563EB");
    expect(assertionStyle("present").bg).toBe("#FDE68A");
    expect(assertionStyle("planned").bg).toBe("#BFDBFE");
    expect(assertionStyle("absent").bg).toBe("#FECACA");
    expect(semanticTagStyle("procedure")?.bg).toBe("#86EFAC");
    expect(semanticTagStyle("finding")?.bg).toBe("#99F6E4");
  });
});

describe("diffLetterMarks", () => {
  it("marks a context change and an uncoded phrase", () => {
    const previous = letterHighlightMarks([
      { text: "chronic pancreatitis", assertion: "present", semanticTag: "disorder" },
      { text: "painless jaundice", assertion: "present", semanticTag: "finding" },
    ]);
    const current = letterHighlightMarks([
      {
        text: "chronic pancreatitis",
        assertion: "historical",
        semanticTag: "disorder",
      },
      { text: "painless jaundice", assertion: "present", semanticTag: "finding" },
    ]);
    const diff = diffLetterMarks(previous, current, true);
    expect(diff.find((row) => row.term === "chronic pancreatitis")?.change).toBe(
      "context",
    );
    expect(diff.find((row) => row.term === "painless jaundice")?.change).toBe(
      "uncoded",
    );
  });
});

describe("reviewWalk", () => {
  const spans = [
    { step_id: "act-ref-extract" },
    { step_id: "act-ref-post-process" },
    { step_id: "act-ref-terminology" },
  ];

  it("locks later steps until the current one is reviewed", () => {
    expect(unlockedIndex(spans, [])).toBe(0);
    expect(canOpenStep(spans, "act-ref-extract", [])).toBe(true);
    expect(canOpenStep(spans, "act-ref-terminology", [])).toBe(false);
    expect(canOpenStep(spans, "act-ref-post-process", ["act-ref-extract"])).toBe(
      true,
    );
    expect(nextStepId(spans, "act-ref-extract")).toBe("act-ref-post-process");
  });
});

describe("formatEvidenceTooltip", () => {
  it("uses labelled lines and strips markdown marks", () => {
    const text = formatEvidenceTooltip({
      text: "change in bowel habit",
      code: "88111009",
      evidence: "change in bowel habit",
      evidenceSentence:
        "Patient reports a **10-week history** of progressive change.",
    });
    expect(text).toContain("change in bowel habit");
    expect(text).toContain("Code 88111009");
    expect(text).toContain("From the letter:");
    expect(text).not.toContain("**");
    expect(text).not.toContain("evidence_sentence:");
    expect(plainLetterText("**loose stools**")).toBe("loose stools");
  });

  it("includes measurement and reference range lines for observables", () => {
    const text = formatEvidenceTooltip({
      text: "HbA1c",
      semanticTag: "observable_entity",
      value: "7.2",
      unit: "%",
      referenceRange: "4.0 - 6.0",
    });
    expect(text).toContain("Measurement: 7.2 %");
    expect(text).toContain("Reference range: 4.0 - 6.0");
  });

  it("omits measurement lines when value and unit are absent", () => {
    const text = formatEvidenceTooltip({ text: "HbA1c" });
    expect(text).not.toContain("Measurement:");
    expect(text).not.toContain("Reference range:");
  });
});

describe("LetterMarkLegend", () => {
  it("shows a worked example with colour for kind and a bar for context", () => {
    render(
      <LetterMarkLegend
        marks={[
          {
            term: "jaundice",
            assertion: "present",
            semanticTag: "finding",
          },
          {
            term: "pancreatitis",
            assertion: "historical",
            semanticTag: "disorder",
          },
        ]}
      />,
    );
    expect(screen.getByText("How to read a highlight")).toBeInTheDocument();
    expect(screen.getByText("jaundice")).toBeInTheDocument();
    expect(screen.getByText("When it applies -- the bar")).toBeInTheDocument();
    expect(screen.getByText("What it is -- the colour")).toBeInTheDocument();
    expect(
      screen.getByText("Example: the colour means finding. The bar means present."),
    ).toBeInTheDocument();
  });

  it("always shows the same hardcoded when and what colours", () => {
    render(
      <LetterMarkLegend
        marks={[
          {
            term: "jaundice",
            assertion: "present",
            semanticTag: "finding",
          },
        ]}
      />,
    );
    expect(screen.getByText("Present")).toBeInTheDocument();
    expect(screen.getByText("History")).toBeInTheDocument();
    expect(screen.getByText("Family")).toBeInTheDocument();
    expect(screen.getByText("Not present")).toBeInTheDocument();
    expect(screen.getByText("Planned")).toBeInTheDocument();
    expect(screen.getByText("Finding")).toBeInTheDocument();
    expect(screen.getByText("Disorder")).toBeInTheDocument();
    expect(screen.getByText("Situation")).toBeInTheDocument();
    expect(screen.getByText("Procedure")).toBeInTheDocument();
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
    expect(plainStageCopy("act-ref-snomed-enrich").name).toBe(
      "Adding body sites from codes",
    );
    expect(plainStageCopy("act-ref-coding-verify").name).toBe("Checking the codes");
    expect(plainStageCopy("act-ref-snomed-relation-judge").name).toBe(
      "Checking links after coding",
    );
  });

  it("uses Yes=good phrasing for all stages (no inverted questions)", () => {
    const steps = [
      "act-ref-extract",
      "act-ref-post-process",
      "act-ref-extraction-check",
      "act-ref-terminology",
      "act-ref-coding-verify",
      "act-ref-persist",
      "act-ref-sbar",
    ];
    for (const step of steps) {
      const { question } = plainStageCopy(step);
      expect(question).not.toMatch(/did.*drop/i);
      expect(question).not.toMatch(/did.*reject/i);
    }
  });

  it("explains context changes in the post-process plain copy", () => {
    const copy = plainStageCopy("act-ref-post-process");
    expect(copy.plain).toMatch(/amber/i);
    expect(copy.plain).toMatch(/label.*changed|changed.*label/i);
  });
});

describe("extractRelationItems", () => {
  it("returns one item per relation with relationType and relationTarget", () => {
    const entities = [
      {
        text: "weight loss",
        label: "finding",
        __relations: [
          { type: "associated_finding", target_text: "suspected pancreatic cancer", confidence: 0.9 },
        ],
      },
    ];
    const items = extractRelationItems(entities);
    expect(items).toHaveLength(1);
    expect(items[0].text).toBe("weight loss");
    expect(items[0].relationType).toBe("linked to");
    expect(items[0].relationTarget).toBe("suspected pancreatic cancer");
    expect(items[0].kind).toBe("relation");
  });

  it("returns an empty list when no entities have __relations", () => {
    expect(extractRelationItems([{ text: "jaundice", label: "finding" }])).toHaveLength(0);
  });

  it("maps finding_site to 'at site' label", () => {
    const entities = [
      {
        text: "pain",
        label: "finding",
        __relations: [{ type: "finding_site", target_text: "epigastrium" }],
      },
    ];
    const items = extractRelationItems(entities);
    expect(items[0].relationType).toBe("at site");
  });
});

describe("inferred SNOMED body sites", () => {
  it("marks inferred entities as kind inferred", () => {
    const preview = workPreviewFromStage({
      entities: [
        {
          text: "Liver structure",
          label: "body_structure",
          concept_id: "10200004",
          inferred: true,
        },
      ],
    });
    expect(preview.items?.[0].kind).toBe("inferred");
  });

  it("keeps inferred chips beside relation links", () => {
    const preview = workPreviewFromStage({
      entities: [
        {
          text: "jaundice",
          label: "finding",
          __relations: [{ type: "finding_site", target_text: "Liver structure" }],
        },
        {
          text: "Liver structure",
          label: "body_structure",
          inferred: true,
        },
      ],
    });
    expect(preview.items?.some((item) => item.kind === "inferred")).toBe(true);
    expect(preview.items?.some((item) => item.kind === "relation")).toBe(true);
  });

  it("renders inferred chips with a dashed border", () => {
    render(
      <StageWorkPreview
        loading={false}
        preview={{
          headline: "Found 1 fact",
          items: [{ kind: "inferred", text: "Liver structure" }],
        }}
      />,
    );
    expect(screen.getByText("Liver structure")).toBeInTheDocument();
  });
});

describe("workPreviewFromStage -- relation-link output", () => {
  it("uses relation items and headline 'Found N links' when __relations are present", () => {
    const preview = workPreviewFromStage({
      entities: [
        {
          text: "weight loss",
          label: "finding",
          __relations: [
            { type: "associated_finding", target_text: "pancreatic cancer" },
          ],
        },
      ],
    });
    expect(preview.headline).toBe("Found 1 link");
    expect(preview.items?.[0].kind).toBe("relation");
    expect(preview.items?.[0].relationType).toBe("linked to");
  });
});

describe("StageWorkPreview -- relation chip rendering", () => {
  it("shows head -- relationType -- target in the chip label", () => {
    render(
      <StageWorkPreview
        preview={{
          headline: "Found 1 link",
          items: [
            {
              kind: "relation",
              text: "weight loss",
              relationType: "linked to",
              relationTarget: "pancreatic cancer",
            },
          ],
        }}
        loading={false}
      />,
    );
    expect(screen.getByTestId("validation-lab-stage-work")).toHaveTextContent(
      "weight loss -- linked to -- pancreatic cancer",
    );
  });
});

describe("workPreviewFromStage -- observable value/unit", () => {
  it("carries value, unit, and referenceRange onto the work item", () => {
    const preview = workPreviewFromStage({
      entities: [
        {
          text: "HbA1c",
          semantic_tag: "observable_entity",
          value: "7.2",
          unit: "%",
          reference_range: "4.0 - 6.0",
        },
      ],
    });
    expect(preview.items?.[0].value).toBe("7.2");
    expect(preview.items?.[0].unit).toBe("%");
    expect(preview.items?.[0].referenceRange).toBe("4.0 - 6.0");
    expect(preview.items?.[0].kind).toBe("observable");
  });

  it("falls back to numeric_value when value is absent", () => {
    const preview = workPreviewFromStage({
      entities: [
        {
          text: "Ferritin",
          semantic_tag: "observable_entity",
          numeric_value: "15",
          unit: "ng/mL",
        },
      ],
    });
    expect(preview.items?.[0].value).toBe("15");
    expect(preview.items?.[0].unit).toBe("ng/mL");
  });
});

describe("StageWorkPreview -- observable chip label", () => {
  it("shows measurement inline when value and unit are present", () => {
    render(
      <StageWorkPreview
        preview={{
          headline: "Found 1 fact",
          items: [
            {
              kind: "observable",
              text: "HbA1c",
              semanticTag: "observable_entity",
              value: "7.2",
              unit: "%",
            },
          ],
        }}
        loading={false}
      />,
    );
    expect(screen.getByTestId("validation-lab-stage-work")).toHaveTextContent(
      "HbA1c -- 7.2 %",
    );
  });

  it("falls back to code label when no measurement is present", () => {
    render(
      <StageWorkPreview
        preview={{
          headline: "Found 1 fact",
          items: [{ kind: "code", text: "HbA1c", code: "43396009" }],
        }}
        loading={false}
      />,
    );
    expect(screen.getByTestId("validation-lab-stage-work")).toHaveTextContent(
      "HbA1c -- 43396009",
    );
  });

  it("keeps the code visible when a coded fact also has a measurement", () => {
    render(
      <StageWorkPreview
        preview={{
          headline: "Coded 1 of 1 facts",
          items: [
            {
              kind: "code",
              text: "BMI",
              code: "60621009",
              semanticTag: "observable_entity",
              value: "20.2",
              unit: "Kg/m2",
            },
          ],
        }}
        loading={false}
      />,
    );
    expect(screen.getByTestId("validation-lab-stage-work")).toHaveTextContent(
      "BMI -- 60621009",
    );
  });
});

describe("diffWorkItems", () => {
  it("marks new facts that appear only in current", () => {
    const prev = [{ kind: "fact", text: "jaundice" }];
    const curr = [{ kind: "fact", text: "jaundice" }, { kind: "fact", text: "weight loss" }];
    const diff = diffWorkItems(prev, curr);
    expect(diff.find((i) => i.text === "jaundice")?.change).toBe("stable");
    expect(diff.find((i) => i.text === "weight loss")?.change).toBe("new");
  });

  it("marks dropped facts that appeared in previous but not current", () => {
    const prev = [{ kind: "fact", text: "jaundice" }, { kind: "fact", text: "nausea" }];
    const curr = [{ kind: "fact", text: "jaundice" }];
    const diff = diffWorkItems(prev, curr);
    expect(diff.find((i) => i.text === "nausea")?.change).toBe("dropped");
  });

  it("marks context change when assertion differs", () => {
    const prev = [{ kind: "fact", text: "pancreatitis", assertion: "present" }];
    const curr = [{ kind: "fact", text: "pancreatitis", assertion: "historical" }];
    const diff = diffWorkItems(prev, curr);
    expect(diff.find((i) => i.text === "pancreatitis")?.change).toBe("context");
  });

  it("marks uncoded only in coding steps", () => {
    const prev = [{ kind: "fact", text: "jaundice" }];
    const curr = [{ kind: "fact", text: "jaundice" }];
    const diffCoding = diffWorkItems(prev, curr, true);
    const diffNotCoding = diffWorkItems(prev, curr, false);
    expect(diffCoding.find((i) => i.text === "jaundice")?.change).toBe("uncoded");
    expect(diffNotCoding.find((i) => i.text === "jaundice")?.change).toBe("stable");
  });

  it("marks measured when value or unit changes for the same observable", () => {
    const prev = [{ kind: "observable", text: "HbA1c", value: "7.2", unit: "%" }];
    const curr = [{ kind: "observable", text: "HbA1c", value: "7.5", unit: "%" }];
    const diff = diffWorkItems(prev, curr);
    expect(diff.find((i) => i.text === "HbA1c")?.change).toBe("measured");
  });

  it("marks measured when a value is newly added (no value before)", () => {
    const prev = [{ kind: "observable", text: "HbA1c" }];
    const curr = [{ kind: "observable", text: "HbA1c", value: "7.2", unit: "%" }];
    const diff = diffWorkItems(prev, curr);
    expect(diff.find((i) => i.text === "HbA1c")?.change).toBe("measured");
  });

  it("does not mark measured when both items have no measurement", () => {
    const prev = [{ kind: "observable", text: "HbA1c" }];
    const curr = [{ kind: "observable", text: "HbA1c" }];
    const diff = diffWorkItems(prev, curr);
    expect(diff.find((i) => i.text === "HbA1c")?.change).toBe("stable");
  });
});

describe("StageWorkPreview -- diff chip styling", () => {
  it("sets data-change on each chip", () => {
    render(
      <StageWorkPreview
        preview={{
          headline: "Found 2 facts",
          items: [
            { kind: "fact", text: "jaundice", change: "stable" },
            { kind: "fact", text: "weight loss", change: "new" },
          ],
        }}
        loading={false}
      />,
    );
    const chips = document.querySelectorAll("[data-change]");
    const changes = Array.from(chips).map((c) => c.getAttribute("data-change"));
    expect(changes).toContain("stable");
    expect(changes).toContain("new");
  });

  it("shows the diff badge when there are new or dropped items", () => {
    render(
      <StageWorkPreview
        preview={{
          headline: "Found 2 facts",
          items: [
            { kind: "fact", text: "jaundice", change: "new" },
            { kind: "fact", text: "nausea", change: "dropped" },
          ],
        }}
        loading={false}
      />,
    );
    expect(screen.getByTestId("validation-lab-diff-badge")).toBeInTheDocument();
    expect(screen.getByTestId("validation-lab-diff-badge")).toHaveTextContent("+1 new");
    expect(screen.getByTestId("validation-lab-diff-badge")).toHaveTextContent("-1 dropped");
  });

  it("hides the diff badge when all items are stable", () => {
    render(
      <StageWorkPreview
        preview={{
          headline: "Found 1 fact",
          items: [{ kind: "fact", text: "jaundice", change: "stable" }],
        }}
        loading={false}
      />,
    );
    expect(screen.queryByTestId("validation-lab-diff-badge")).toBeNull();
  });
});

const BASE_SPAN: LabTraceSpan = {
  step_id: "act-ref-extract",
  status: "running",
};

const POST_PROCESS_DETAIL: LabStageDetail = {
  step_id: "act-ref-post-process",
  status: "completed",
  input: { entities: [{ text: "jaundice", assertion: "present", semantic_tag: "finding" }] },
  output: {
    entities: [
      { text: "jaundice", assertion: "present", semantic_tag: "finding" },
      { text: "weight loss", assertion: "present", semantic_tag: "finding" },
    ],
  },
};

describe("StageDetailPane -- stage diff chips", () => {
  it("marks a newly added fact as new when diffing input to output", () => {
    render(
      <StageDetailPane
        span={{ step_id: "act-ref-post-process", status: "completed" }}
        detailReady={true}
        stageDetail={POST_PROCESS_DETAIL}
        stageLoading={false}
        onFixInGuards={() => {}}
        onNext={() => {}}
      />,
    );
    const newChip = document.querySelector("[data-change='new']");
    expect(newChip).toBeTruthy();
    expect(newChip?.textContent).toContain("weight loss");
  });

  it("hides unchanged facts on the cleaning step", () => {
    render(
      <StageDetailPane
        span={{ step_id: "act-ref-post-process", status: "completed" }}
        detailReady={true}
        stageDetail={POST_PROCESS_DETAIL}
        stageLoading={false}
        onFixInGuards={() => {}}
        onNext={() => {}}
      />,
    );
    expect(document.querySelector("[data-change='stable']")).toBeNull();
    expect(screen.queryByText("jaundice")).toBeNull();
  });

  it("shows retest diff when previousPreview is provided", () => {
    render(
      <StageDetailPane
        span={{ step_id: "act-ref-post-process", status: "completed" }}
        detailReady={true}
        stageDetail={POST_PROCESS_DETAIL}
        stageLoading={false}
        onFixInGuards={() => {}}
        onNext={() => {}}
        previousPreview={{ headline: "Found 1 fact", items: [{ kind: "fact", text: "jaundice" }] }}
      />,
    );
    expect(document.querySelector("[data-change='new']")?.textContent).toContain("weight loss");
  });
});

describe("StageDetailPane -- Yes/No question gate", () => {
  it("hides Yes and No buttons while the stage is still running", () => {
    render(
      <StageDetailPane
        span={{ ...BASE_SPAN, status: "running" }}
        detailReady={false}
        stageDetail={null}
        stageLoading={false}
        onFixInGuards={() => {}}
        onNext={() => {}}
        onMarkWrong={() => {}}
      />,
    );
    expect(screen.queryByRole("button", { name: /yes/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /no/i })).toBeNull();
  });

  it("shows Yes and No buttons only after the stage completes", () => {
    render(
      <StageDetailPane
        span={{ ...BASE_SPAN, status: "completed" }}
        detailReady={true}
        stageDetail={null}
        stageLoading={false}
        onFixInGuards={() => {}}
        onNext={() => {}}
        onMarkWrong={() => {}}
      />,
    );
    expect(
      screen.getByRole("button", { name: /yes.*right/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /no.*mark/i }),
    ).toBeInTheDocument();
  });

  it("hides Yes and No buttons when the stage failed", () => {
    render(
      <StageDetailPane
        span={{ ...BASE_SPAN, status: "failed", error_summary: "timeout" }}
        detailReady={true}
        stageDetail={null}
        stageLoading={false}
        onFixInGuards={() => {}}
        onNext={() => {}}
        onMarkWrong={() => {}}
      />,
    );
    expect(screen.queryByRole("button", { name: /yes/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /no/i })).toBeNull();
  });
});
