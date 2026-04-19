/**
 * VT-LEO-AI-511 -- TC-009 reading-age sweep on EditRuleDialog/copy.ts.
 *
 * UN-LEO-AI-094 sets the user audience at UK reading age 7-11. The
 * Flesch-Kincaid grade level is the standard metric: grade 6 maps to
 * a UK reading age of approximately 11. We compute the metric inline
 * (no extra dependency) so that any future copy edits cannot regress
 * the reading age below the design-input acceptance criterion.
 */

import {
  ADD_BAR_LABELS,
  ALL_READY_LABEL,
  STEP_HELPERS,
  STEP_SHORT_TITLES,
  STEP_STATE_LABELS,
  STEP_TITLES,
} from "../app/admin/guidance/EditRuleDialog/copy";

function countSyllables(word: string): number {
  const w = word.toLowerCase().replace(/[^a-z]/g, "");
  if (!w) return 0;
  if (w.length <= 3) return 1;
  // Strip silent trailing 'e' and adjectival '-ed' / '-es'.
  const stripped = w.replace(/(?:[^laeiouy]es|ed|[^laeiouy]e)$/, "");
  const groups = stripped.match(/[aeiouy]+/g);
  return Math.max(groups ? groups.length : 1, 1);
}

function fleschKincaidGrade(corpus: string): number {
  const sentences = corpus
    .split(/[.!?]+/)
    .map((s) => s.trim())
    .filter(Boolean);
  const words = corpus
    .split(/\s+/)
    .map((w) => w.replace(/[^a-zA-Z']/g, ""))
    .filter(Boolean);
  const syllables = words.reduce((acc, w) => acc + countSyllables(w), 0);

  if (sentences.length === 0 || words.length === 0) return 0;
  // Flesch-Kincaid grade = 0.39 * (W/S) + 11.8 * (Sy/W) - 15.59
  return (
    0.39 * (words.length / sentences.length) +
    11.8 * (syllables / words.length) -
    15.59
  );
}

describe("EditRuleDialog copy reading age -- VT-511-TC-009", () => {
  it("Flesch-Kincaid grade <= 6 across every chrome string in copy.ts", () => {
    const corpus = [
      ...Object.values(STEP_TITLES),
      ...Object.values(STEP_SHORT_TITLES),
      ...Object.values(STEP_HELPERS),
      ...Object.values(STEP_STATE_LABELS),
      ALL_READY_LABEL,
      ...Object.values(ADD_BAR_LABELS),
    ].join(". ");

    const grade = fleschKincaidGrade(corpus);
    expect(grade).toBeLessThanOrEqual(6);
  });

  it("each step helper sentence is short (<= 25 words)", () => {
    for (const helper of Object.values(STEP_HELPERS)) {
      // Helpers may have one or two short sentences; assert each one
      // separately so a single long sentence cannot slip through.
      const sentences = helper.split(/[.!?]+/).map((s) => s.trim()).filter(Boolean);
      for (const sentence of sentences) {
        const wordCount = sentence.split(/\s+/).filter(Boolean).length;
        expect(wordCount).toBeLessThanOrEqual(25);
      }
    }
  });
});
