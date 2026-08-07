/**
 * Plain-English pipeline stage errors for Validation Lab live log.
 *
 * Atlas trace:
 *   DO: DO-158BE606
 *   DI: DI-2289D095
 */

const LOW_CONF_RE =
  /^terminology_low_confidence:\s*(\d+)\s+entity\/entities below score threshold ([0-9.]+)\s*--\s*(.+)$/s;
const TERM_SCORE_RE = /"([^"]+)"\s*\(score\s*([0-9.]+)\)/g;

export function plainEnglishPipelineError(error: string): string {
  const text = String(error || "").trim();
  if (!text) return "";

  if (text.startsWith("terminology_low_confidence:")) {
    const match = LOW_CONF_RE.exec(text);
    if (match) {
      const count = Number(match[1]);
      const thresholdPct = Math.round(Number(match[2]) * 100);
      const termsBlob = match[3];
      const terms: Array<{ term: string; scorePct: number }> = [];
      for (const hit of termsBlob.matchAll(TERM_SCORE_RE)) {
        terms.push({
          term: hit[1],
          scorePct: Math.round(Number(hit[2]) * 100),
        });
      }
      if (terms.length) {
        const joined = terms
          .map(({ term, scorePct }) => `"${term}" (${scorePct}% match)`)
          .join(", ");
        const noun = count === 1 ? "term" : "terms";
        return (
          `Could not map ${count} clinical ${noun} to SNOMED codes with enough ` +
          `confidence (need at least ${thresholdPct}%): ${joined}. ` +
          "The run stopped so unsafe codes are not applied automatically."
        );
      }
    }
    return (
      "One or more clinical terms could not be mapped to SNOMED codes with " +
      "enough confidence. The run stopped so unsafe codes are not applied " +
      "automatically."
    );
  }

  if (text.startsWith("terminology:")) {
    const detail = text.slice("terminology:".length).trim();
    const lower = detail.toLowerCase();
    if (lower.includes("connection") || lower.includes("refused")) {
      return (
        "The terminology service could not be reached. " +
        "Check that the terminology API is running."
      );
    }
    if (detail) return `Terminology lookup failed: ${detail}.`;
    return "Terminology lookup failed.";
  }

  if (text.startsWith("stage_poisoned")) {
    return "This step failed too many times and was stopped.";
  }

  return text;
}

export function summarizeStageErrors(errors: string[]): string {
  const cleaned = errors.map((e) => String(e || "").trim()).filter(Boolean);
  if (!cleaned.length) return "";
  return cleaned.map(plainEnglishPipelineError).join(" ");
}

export function stageLabelFromStepId(stepId: string): string {
  const raw = String(stepId || "").trim();
  if (!raw) return "pipeline step";
  const tail = raw.includes("-") ? raw.split("-").pop() || raw : raw;
  return tail.replace(/_/g, " ");
}
