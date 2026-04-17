// Flesch-Kincaid Grade Level calculator. Identical formula to
// services/ui/src/lib/readability.ts, relocated here so copy checks can run
// without importing from the consuming app. See DI-LEO-AI-128 and
// DI-LEO-AI-132.

function countSyllables(word: string): number {
  const cleaned = word.toLowerCase().replace(/[^a-z]/g, "");
  if (!cleaned) return 0;
  if (cleaned.length <= 3) return 1;
  const stripped = cleaned
    .replace(/(?:[^laeiouy]es|ed|[^laeiouy]e)$/, "")
    .replace(/^y/, "");
  const groups = stripped.match(/[aeiouy]{1,2}/g);
  return groups ? groups.length : 1;
}

export interface ReadabilityResult {
  sentences: number;
  words: number;
  syllables: number;
  grade: number;
}

export function fleschKincaidGrade(text: string): ReadabilityResult {
  const cleaned = text.replace(/\s+/g, " ").trim();
  if (!cleaned) return { sentences: 0, words: 0, syllables: 0, grade: 0 };
  const sentences = cleaned.split(/[.!?]+/).filter(Boolean).length || 1;
  const wordList = cleaned.split(/\s+/).filter(Boolean);
  const words = wordList.length || 1;
  const syllables = wordList.reduce((s, w) => s + countSyllables(w), 0) || 1;
  const grade =
    0.39 * (words / sentences) + 11.8 * (syllables / words) - 15.59;
  return {
    sentences,
    words,
    syllables,
    grade: Number(grade.toFixed(2)),
  };
}
