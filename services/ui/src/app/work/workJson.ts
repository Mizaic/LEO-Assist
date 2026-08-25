/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-E7824FED
 *   DI: DI-4A012A59
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-E7824FED")
 */

export async function workJson<T>(
  url: string,
  init?: RequestInit,
): Promise<T> {
  const res = await fetch(url, {
    credentials: "include",
    ...init,
    headers: {
      "X-Requested-With": "XMLHttpRequest",
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    throw new Error("Request failed (" + res.status + ")");
  }
  return (await res.json()) as T;
}
