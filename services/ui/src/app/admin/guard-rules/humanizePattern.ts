/** Turn a regex fragment into a short label for the card list. */
export function humanizePattern(pattern: string): string {
  let text = pattern;
  text = text.replace(/\\s\*/g, " ");
  text = text.replace(/\\s\+/g, " ");
  text = text.replace(/\\s/g, " ");
  text = text.replace(/\\b/g, "");
  text = text.replace(/\[\s\\s-\]\*/g, "-");
  text = text.replace(/\(\?:/g, "(");
  text = text.replace(/\\-/g, "-");
  text = text.replace(/\\d/g, "n");
  text = text.replace(/[\\^$?]/g, "");
  text = text.replace(/\s+/g, " ").trim();
  if (!text) return pattern;
  if (text.length > 72) return text.slice(0, 69) + "...";
  return text;
}
