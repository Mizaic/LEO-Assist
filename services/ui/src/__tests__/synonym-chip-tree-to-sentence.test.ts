/**
 * treeToSentence rendering of the synonym set + exclusions
 * (UN-LEO-AI-093 / DI-LEO-AI-511).
 *
 * Verifies the human-readable summary renders multi-seed chips in
 * plain English, names exclusions either by resolved term or by
 * "code <id>" when the resolver has no answer, and stays compatible
 * with legacy single-seed chips. Author copy follows
 * `health-literacy.mdc` (reading age 9-11).
 */

import { treeToSentence } from "@/app/admin/guidance/EditRuleDialog/treeToSentence";
import type { EditableLogicNode } from "@/app/admin/guidance/EditRuleDialog/types";

const conceptNode = (
  primaryId: string,
  primaryTerm: string,
  extra?: Partial<EditableLogicNode["criterion"]>,
): EditableLogicNode => ({
  node_id: "n1",
  kind: "CONCEPT",
  criterion: {
    snomed_concept_id: primaryId,
    preferred_term: primaryTerm,
    semantic_tag: "finding",
    ...extra,
  },
});

const wrapAnd = (child: EditableLogicNode): EditableLogicNode => ({
  node_id: "root",
  kind: "AND",
  children: [child],
});

describe("treeToSentence -- synonym set rendering", () => {
  test("legacy single-seed chip reads as before", () => {
    const root = wrapAnd(conceptNode("1", "Smoker"));
    const out = treeToSentence(root);
    expect(out.lead.toLowerCase()).toContain("smoker");
    expect(out.lead.toLowerCase()).not.toContain("kind of:");
  });

  test("two seeds with descendants render as 'or any kind of: ...'", () => {
    const root = wrapAnd(
      conceptNode("1", "Smoker", {
        primary_concept_id: "1",
        seeds: [
          {
            snomed_concept_id: "1",
            preferred_term: "Smoker",
            include_descendants: true,
          },
          {
            snomed_concept_id: "2",
            preferred_term: "Cigarette smoker",
            include_descendants: true,
          },
        ],
      }),
    );
    const text = treeToSentence(root).lead.toLowerCase();
    expect(text).toContain("smoker");
    expect(text).toContain("cigarette smoker");
    expect(text).toContain("or any kind of:");
  });

  test("multiple seeds with descendants OFF render as 'one of: ...'", () => {
    const root = wrapAnd(
      conceptNode("1", "Smoker", {
        primary_concept_id: "1",
        seeds: [
          {
            snomed_concept_id: "1",
            preferred_term: "Smoker",
            include_descendants: false,
          },
          {
            snomed_concept_id: "2",
            preferred_term: "Cigarette smoker",
            include_descendants: false,
          },
        ],
      }),
    );
    const text = treeToSentence(root).lead.toLowerCase();
    expect(text).toContain("one of:");
  });

  test("excluded ids render as 'except <term>' when resolver knows the term", () => {
    const root = wrapAnd(
      conceptNode("1", "Smoker", {
        primary_concept_id: "1",
        seeds: [
          {
            snomed_concept_id: "1",
            preferred_term: "Smoker",
            include_descendants: true,
          },
        ],
        excluded_concept_ids: ["999"],
      }),
    );
    const resolve = (id: string) => (id === "999" ? "trial of smoking" : undefined);
    const text = treeToSentence(root, resolve).lead.toLowerCase();
    expect(text).toContain("except trial of smoking");
  });

  test("excluded ids fall back to 'code <id>' when resolver returns nothing", () => {
    const root = wrapAnd(
      conceptNode("1", "Smoker", {
        primary_concept_id: "1",
        seeds: [
          {
            snomed_concept_id: "1",
            preferred_term: "Smoker",
            include_descendants: true,
          },
        ],
        excluded_concept_ids: ["999"],
      }),
    );
    const text = treeToSentence(root).lead.toLowerCase();
    expect(text).toContain("except code 999");
  });
});
