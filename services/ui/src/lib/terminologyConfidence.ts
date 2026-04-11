export type TerminologyConfidenceBand = "low" | "medium" | "high" | "unknown";

const MEDIUM_THRESHOLD = 0.7;
const HIGH_THRESHOLD = 0.95;

export function getTerminologyConfidenceBand(
  score: number | null | undefined,
): TerminologyConfidenceBand {
  if (score == null || Number.isNaN(score)) {
    return "unknown";
  }
  if (score >= HIGH_THRESHOLD) {
    return "high";
  }
  if (score >= MEDIUM_THRESHOLD) {
    return "medium";
  }
  return "low";
}

export function getTerminologyConfidenceLabel(
  score: number | null | undefined,
): string {
  const band = getTerminologyConfidenceBand(score);
  if (band === "high") return "High";
  if (band === "medium") return "Medium";
  if (band === "low") return "Low";
  return "Unknown";
}

export function getTerminologyConfidenceExplanation(
  score: number | null | undefined,
): string {
  const band = getTerminologyConfidenceBand(score);
  if (band === "high") return "High confidence. This code is likely right.";
  if (band === "medium") return "Medium confidence. Please check this code.";
  if (band === "low") return "Low confidence. Check this code carefully.";
  return "Confidence is not available. Please check this code.";
}
