/**
 * VT-CE7006EE -- Ask LEO on a paused extraction fact.
 *
 * Atlas: DI-4A012A59 / DO-E7824FED
 */
import {
  applyAskLeoPatch,
  tagFromLeoCandidate,
} from "../components/operations/askLeoFactPatch";
import type { AskLeoSmartResult } from "../lib/types";

function result(partial: Partial<AskLeoSmartResult>): AskLeoSmartResult {
  return {
    matched_candidate: null,
    reason: "",
    is_ambiguous: false,
    alternative_query_used: null,
    assertion_warning: null,
    assertion: "present",
    ...partial,
  };
}

describe("Ask LEO on a draft fact", () => {
  test("maps a SNOMED tag onto the review tag list", () => {
    expect(tagFromLeoCandidate("clinical finding")).toBe("finding");
    expect(tagFromLeoCandidate("body structure")).toBe("body_structure");
    expect(tagFromLeoCandidate("observable entity")).toBe("observable");
    expect(tagFromLeoCandidate("disorder")).toBe("disorder");
  });

  test("accepting a match sets the tag and assertion", () => {
    const patch = applyAskLeoPatch(
      result({
        matched_candidate: {
          snomed_concept_id: "271939006",
          term: "Vaginal discharge",
          semantic_tag: "finding",
        },
        assertion: "present",
        reason: "The letter names vaginal discharge as a current symptom.",
      }),
    );
    expect(patch).toEqual({
      semantic_tag: "finding",
      assertion: "present",
    });
  });

  test("a not-codeable warning does not change the fact", () => {
    expect(
      applyAskLeoPatch(
        result({
          assertion_warning: "This is a form label, not a patient finding.",
          reason: "Do not code this phrase.",
        }),
      ),
    ).toBeNull();
  });

  test("an ambiguous result does not change the fact", () => {
    expect(
      applyAskLeoPatch(
        result({
          is_ambiguous: true,
          reason: "More than one code fits.",
        }),
      ),
    ).toBeNull();
  });
});
