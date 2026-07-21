/**
 * Pads the episode-linked window by ~10% of the patient's full
 * history span on each side so the default brush opens with a bit
 * of "before / after" context visible. Clamped to the patient range.
 *
 * Extracted from EncounterTextTab.tsx to keep that file under the
 * 500 LOC ceiling enforced by VT-LEO-AI-173 (TC-011).
 *
 * Atlas trace:
 *   DO: DO-5312F884
 *   DI: DI-AA1F5F5B
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-5312F884")
 */
export function padRange(
  fromMs: number,
  toMs: number,
  fullMinMs: number,
  fullMaxMs: number
): { fromMs: number; toMs: number } | null {
  if (
    !Number.isFinite(fromMs) ||
    !Number.isFinite(toMs) ||
    !Number.isFinite(fullMinMs) ||
    !Number.isFinite(fullMaxMs)
  ) {
    return null;
  }
  const span = Math.max(0, fullMaxMs - fullMinMs);
  const pad = span > 0 ? span * 0.1 : 0;
  return {
    fromMs: Math.max(fullMinMs, fromMs - pad),
    toMs: Math.min(fullMaxMs, toMs + pad),
  };
}
