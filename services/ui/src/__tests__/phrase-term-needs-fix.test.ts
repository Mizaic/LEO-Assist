/**
 * VT-76C15B0E -- code-only preferred terms need confirm.
 *
 * Atlas trace:
 *   DI: DI-6BD7B681
 */
import {
  draftNeedsTermFix,
  termNeedsFix,
} from "../app/settings/surface-forms/termNeedsFix";

describe("termNeedsFix", () => {
  it("flags a missing preferred term", () => {
    expect(termNeedsFix("", "1018251000000107")).toBe(true);
  });

  it("flags a code used as the preferred term", () => {
    expect(termNeedsFix("1018251000000107", "1018251000000107")).toBe(true);
    expect(termNeedsFix("60621009", "60621009")).toBe(true);
  });

  it("accepts an official preferred term", () => {
    expect(
      termNeedsFix(
        "Serum alanine aminotransferase level (observable entity)",
        "1018251000000107",
      ),
    ).toBe(false);
  });

  it("does not flag a draft with no clinical code", () => {
    expect(termNeedsFix("", "")).toBe(false);
  });
});

describe("draftNeedsTermFix", () => {
  it("only flags map drafts that lack a preferred term", () => {
    expect(
      draftNeedsTermFix({
        draft_action: "map",
        draft_concept_id: "1018251000000107",
        draft_concept_term: "1018251000000107",
      }),
    ).toBe(true);
    expect(
      draftNeedsTermFix({
        draft_action: "exclude",
        draft_concept_id: "1018251000000107",
      }),
    ).toBe(false);
  });
});
