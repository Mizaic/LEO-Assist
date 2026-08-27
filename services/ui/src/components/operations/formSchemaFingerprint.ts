/**
 * Compute a stable form fingerprint from sample referral text.
 *
 * Uses the same server-side hash as the extraction pipeline.
 * Atlas trace: DI-5C9CA57B
 */

export async function computeFormFingerprint(text: string): Promise<string> {
  const res = await fetch("/api/form-schemas/fingerprint", {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      "X-Requested-With": "XMLHttpRequest",
    },
    body: JSON.stringify({ text }),
  });
  if (!res.ok) {
    const detail = await readErrorDetail(res);
    throw new Error(detail || "Could not compute the form fingerprint. Try again.");
  }
  const data = (await res.json()) as { fingerprint?: string };
  const fingerprint = String(data.fingerprint ?? "").trim();
  if (!fingerprint) {
    throw new Error("We could not compute a fingerprint for this text.");
  }
  return fingerprint;
}

async function readErrorDetail(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: string };
    if (typeof body.detail === "string" && body.detail.trim()) {
      return body.detail;
    }
  } catch {
    /* ignore */
  }
  return "";
}
