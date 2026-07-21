/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2C03CA0E
 *   DI: DI-3F771AFB
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C03CA0E")
 */
async function parseApiError(res: Response): Promise<string> {
  const text = await res.text();
  if (text.trimStart().startsWith("<!")) {
    return `Unable to load coding validation data (${res.status}). Please retry.`;
  }
  try {
    const payload = JSON.parse(text) as { detail?: string | { msg?: string }[] };
    if (typeof payload.detail === "string" && payload.detail.trim()) {
      return payload.detail;
    }
  } catch {
    // Fall through to raw text handling.
  }
  return text || `Request failed (${res.status})`;
}

export async function getCodingValidation() {
  const res = await fetch("/api/coding-validation", {
    headers: { "X-Requested-With": "XMLHttpRequest" },
  });
  if (!res.ok) throw new Error(await parseApiError(res));
  return res.json();
}

export async function updateGroundTruth(caseId: string, surfaceForm: string, action: string) {
  const res = await fetch("/api/coding-validation/update", {
    method: "POST",
    headers: {
      "X-Requested-With": "XMLHttpRequest",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ case_id: caseId, surface_form: surfaceForm, action }),
  });
  if (!res.ok) throw new Error(await parseApiError(res));
  return res.json();
}
