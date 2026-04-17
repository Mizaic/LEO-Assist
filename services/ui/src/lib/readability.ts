/**
 * Flesch-Kincaid Grade Level calculator.
 *
 * Grade = 0.39 * (words/sentences) + 11.8 * (syllables/words) - 15.59
 *
 * Used by the CI readability gate for glossary plainLanguage strings
 * (DI-LEO-AI-121, VT-LEO-AI-116) and for regression checks on PageIntro
 * default copy.
 */

export function countSentences(text: string): number {
  const trimmed = text.trim();
  if (!trimmed) return 0;
  const matches = trimmed.match(/[^.!?]+[.!?]+/g);
  if (matches && matches.length > 0) return matches.length;
  return 1;
}

export function countWords(text: string): number {
  const trimmed = text.trim();
  if (!trimmed) return 0;
  return trimmed.split(/\s+/).filter(Boolean).length;
}

const VOWEL_GROUP = /[aeiouy]+/g;

export function countSyllablesInWord(word: string): number {
  const cleaned = word.toLowerCase().replace(/[^a-z]/g, "");
  if (!cleaned) return 0;
  if (cleaned.length <= 3) return 1;
  const trimmed = cleaned
    .replace(/(?:[^laeiouy]es|ed|[^laeiouy]e)$/, "")
    .replace(/^y/, "");
  const groups = trimmed.match(VOWEL_GROUP);
  return groups ? groups.length : 1;
}

export function countSyllables(text: string): number {
  return text
    .split(/\s+/)
    .filter(Boolean)
    .reduce((sum, word) => sum + countSyllablesInWord(word), 0);
}

export function fleschKincaidGrade(text: string): number {
  const sentences = countSentences(text);
  const words = countWords(text);
  if (!sentences || !words) return 0;
  const syllables = countSyllables(text);
  return 0.39 * (words / sentences) + 11.8 * (syllables / words) - 15.59;
}
