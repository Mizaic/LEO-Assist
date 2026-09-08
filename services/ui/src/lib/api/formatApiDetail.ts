/**
 * Turn FastAPI / Pydantic error payloads into plain English for the UI.
 *
 * Atlas trace:
 *   DO: DO-19BBE973
 *   DI: DI-B746E19E
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-19BBE973")
 */

export function formatApiDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const parts = detail
      .map((d) => {
        if (typeof d === "string") return d;
        if (d && typeof d === "object") {
          const obj = d as Record<string, unknown>;
          const loc = Array.isArray(obj.loc)
            ? (obj.loc as unknown[])
                .filter((x) => x !== "body" && x !== "updates")
                .join(".")
            : "";
          const msg = typeof obj.msg === "string" ? obj.msg : "";
          if (loc && msg) return `${loc}: ${msg}`;
          if (msg) return msg;
        }
        try {
          return JSON.stringify(d);
        } catch {
          return String(d);
        }
      })
      .filter((s) => s.length > 0);
    return parts.join("; ");
  }
  if (detail && typeof detail === "object") {
    try {
      return JSON.stringify(detail);
    } catch {
      return String(detail);
    }
  }
  return "";
}
