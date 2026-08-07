/**
 * Plain-English pipeline stage messages for Validation Lab live log.
 *
 * Atlas trace:
 *   DO: DO-158BE606
 *   DI: DI-2289D095
 */

const LOW_CONF_RE =
  /^terminology_low_confidence:\s*(\d+)\s+entity\/entities below score threshold ([0-9.]+)\s*--\s*([\s\S]+)$/;
const TERM_SCORE_RE = /"([^"]+)"\s*\(score\s*([0-9.]+)\)/g;
const NOT_CODEABLE_RE =
  /^coding_verifier:\s*(\d+)\s+(entity|entities)\s+classified not_codeable$/;

export function plainEnglishPipelineMessage(text: string): string {
  const raw = String(text || "").trim();
  if (!raw) return "";

  if (raw.startsWith("terminology_low_confidence:")) {
    const match = LOW_CONF_RE.exec(raw);
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
          .map(({ term, scorePct }) =>
            scorePct <= 0
              ? `"${term}" (no SNOMED match found)`
              : `"${term}" (${scorePct}% match)`,
          )
          .join(", ");
        const noun = count === 1 ? "term" : "terms";
        return (
          `Could not map ${count} clinical ${noun} to SNOMED codes with enough ` +
          `confidence (need at least ${thresholdPct}%): ${joined}. ` +
          "Those terms were left uncoded."
        );
      }
    }
    return (
      "One or more clinical terms could not be mapped to SNOMED codes with " +
      "enough confidence. Those terms were left uncoded."
    );
  }

  if (raw.startsWith("coding_verifier:") && raw.includes("not_codeable")) {
    const match = NOT_CODEABLE_RE.exec(raw);
    if (match) {
      const count = Number(match[1]);
      const noun = count === 1 ? "term" : "terms";
      return (
        `${count} extracted ${noun} were not coded because they are ` +
        "descriptors or overlap another finding."
      );
    }
    return (
      "Some extracted terms were not coded because they are descriptors " +
      "or overlap another finding."
    );
  }

  if (raw.startsWith("terminology:")) {
    const detail = raw.slice("terminology:".length).trim();
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

  if (raw.startsWith("coding_verifier:") && raw.includes("gate_failed")) {
    return (
      "The coding checker could not verify one or more SNOMED matches. " +
      "Human review is required."
    );
  }

  if (raw.startsWith("stage_poisoned")) {
    return "This step failed too many times and was stopped.";
  }

  return raw;
}

/** @deprecated use plainEnglishPipelineMessage */
export function plainEnglishPipelineError(error: string): string {
  return plainEnglishPipelineMessage(error);
}

export function summarizeStageMessages(messages: string[]): string {
  const cleaned = messages.map((e) => String(e || "").trim()).filter(Boolean);
  if (!cleaned.length) return "";
  return cleaned.map(plainEnglishPipelineMessage).join(" ");
}

export function summarizeStageErrors(errors: string[]): string {
  return summarizeStageMessages(errors);
}

export function stageLabelFromStepId(stepId: string): string {
  const raw = String(stepId || "").trim();
  if (!raw) return "pipeline step";
  const tail = raw.includes("-") ? raw.split("-").pop() || raw : raw;
  return tail.replace(/_/g, " ");
}
