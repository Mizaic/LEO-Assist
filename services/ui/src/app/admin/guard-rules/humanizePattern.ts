/** Turn a regex fragment into a short label for the card list.
 *
 * Atlas trace:
 *   DO: DO-7E9AD55B
 *   DI: DI-DA60AC55
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-7E9AD55B")
 */
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
