import React from "react";
import { render, screen } from "@testing-library/react";
import fs from "fs";
import path from "path";
import CodingReviewCasesModal from "../components/operations/CodingReviewCasesModal";
import { CODING_REVIEW_INTRO } from "../components/operations/codingReviewCopy";
import { fleschKincaidGrade } from "../lib/readability";
import { lookupTerm } from "../lib/glossary";

jest.mock("../components/TermSearch", () => ({
  __esModule: true,
  default: () => <div data-testid="term-search-mock" />,
}));

const MODULE_DIR = path.resolve(
  __dirname,
  "..",
  "components",
  "operations",
);

const SPLIT_MODULES = [
  "CodingReviewCasesModal.tsx",
  "CodingReviewCasesModalTitle.tsx",
  "CaseCard.tsx",
  "CaseCardLeoResult.tsx",
  "CaseCardSuppressForm.tsx",
  "EncounterContextPanel.tsx",
  "codingReviewUtils.ts",
  "codingReviewCopy.ts",
];

const LOC_LIMIT = 500;

describe("VT-118-TC-001 All split modules are <=500 LOC", () => {
  it.each(SPLIT_MODULES)(
    "%s has at most 500 lines",
    (filename) => {
      const full = path.join(MODULE_DIR, filename);
      expect(fs.existsSync(full)).toBe(true);
      const lines = fs.readFileSync(full, "utf8").split(/\r?\n/).length;
      expect(lines).toBeLessThanOrEqual(LOC_LIMIT);
    },
  );
});

describe("VT-118-TC-002 PageIntro copy passes FK grade <=9", () => {
  it.each(Object.entries(CODING_REVIEW_INTRO))(
    "%s copy reads at grade <=9",
    (_key, value) => {
      expect(fleschKincaidGrade(value)).toBeLessThanOrEqual(9);
    },
  );
});

describe("VT-118-TC-003 Glossary has plain-language entries for core terms", () => {
  const TERM_IDS = [
    "assertion",
    "semantic-tag",
    "suppress",
    "declined",
    "absent",
    "planned",
    "hypothetical",
  ];

  it.each(TERM_IDS)("%s resolves and reads at grade <=9", (termId) => {
    const entry = lookupTerm(termId);
    expect(entry).toBeDefined();
    expect(entry!.plainLanguage.length).toBeGreaterThan(0);
    expect(fleschKincaidGrade(entry!.plainLanguage)).toBeLessThanOrEqual(9);
  });
});

describe("VT-118-TC-004 CodingReviewCasesModal preserves its Props signature", () => {
  it("renders empty state with the PageIntro when initialCases is empty", () => {
    render(
      <CodingReviewCasesModal
        item={{
          id: "test-id",
          kind: "coding",
          entityText: "cough",
          entityLabel: "finding",
          count: 0,
          confidence: null,
          uncoded: false,
          question: "",
          explanation: "",
          assertion: "present",
          sampleEncounterText: "patient with cough",
        }}
        open={true}
        onClose={() => {}}
        onAllResolved={() => {}}
        initialCases={[]}
      />,
    );
    expect(
      screen.getByText(/coding review queue/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/All cases resolved/i)).toBeInTheDocument();
  });
});
