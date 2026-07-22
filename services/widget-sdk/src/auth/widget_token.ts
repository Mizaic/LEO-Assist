/**
 * Widget token holder.
 *
 * Atlas trace:
 *   DO: DO-5C88CA8F
 *   DI: DI-A1206416
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-5C88CA8F")
 *
 * Holds a short-lived widget JWT in memory for the lifetime of the
 * embedded widget. Strict policy:
 *
 *   - Token MUST have aud = "leo-widget"
 *   - Remaining TTL (exp - now) MUST be <= 900 seconds
 *   - The holder MUST NOT touch localStorage, sessionStorage,
 *     IndexedDB or document.cookie.
 *
 * The widget is NOT authoritative over the token: it cannot verify
 * the signature (that requires the server's secret). It only
 * checks the claims it can read (aud, exp, assessment_id) so that
 * a misconfigured host product is caught at the boundary instead of
 * making a useless request to the proxy.
 */

export const LEO_WIDGET_AUDIENCE = "leo-widget";
export const LEO_WIDGET_MAX_TTL_SECONDS = 900;

export interface WidgetClaims {
  readonly sub: string;
  readonly tenant_id: string;
  readonly assessment_id: string;
  readonly user_role: string;
  readonly scope: string;
  readonly aud: string;
  readonly iat: number;
  readonly exp: number;
  readonly jti: string;
}

export class WidgetTokenError extends Error {
  constructor(message: string) {
    super(`leo-widget: ${message}`);
    this.name = "WidgetTokenError";
  }
}

function _base64UrlDecode(segment: string): string {
  const padded = segment.replace(/-/g, "+").replace(/_/g, "/");
  const fill = padded.length % 4;
  const padding = fill === 0 ? "" : "=".repeat(4 - fill);
  if (typeof atob === "function") {
    return atob(padded + padding);
  }
  return Buffer.from(padded + padding, "base64").toString("binary");
}

function _decodePayload(token: string): Record<string, unknown> {
  const parts = token.split(".");
  const payloadSegment = parts[1];
  if (parts.length !== 3 || payloadSegment === undefined) {
    throw new WidgetTokenError(
      "widget token is not a JWT (expected three dot-separated segments)",
    );
  }
  let raw: string;
  try {
    raw = _base64UrlDecode(payloadSegment);
  } catch {
    throw new WidgetTokenError("widget token payload is not base64url");
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    throw new WidgetTokenError("widget token payload is not valid JSON");
  }
  if (typeof parsed !== "object" || parsed === null) {
    throw new WidgetTokenError("widget token payload is not an object");
  }
  return parsed as Record<string, unknown>;
}

function _requireString(payload: Record<string, unknown>, key: string): string {
  const value = payload[key];
  if (typeof value !== "string" || value.length === 0) {
    throw new WidgetTokenError(`widget token missing required claim '${key}'`);
  }
  return value;
}

function _requireNumber(payload: Record<string, unknown>, key: string): number {
  const value = payload[key];
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new WidgetTokenError(`widget token missing numeric claim '${key}'`);
  }
  return value;
}

export class WidgetTokenHolder {
  private _token: string | null = null;
  private _claims: WidgetClaims | null = null;
  private readonly _now: () => number;

  constructor(now: () => number = () => Date.now()) {
    this._now = now;
  }

  parse(token: string): WidgetClaims {
    const payload = _decodePayload(token);
    const aud = payload["aud"];
    const audValue = Array.isArray(aud) ? aud[0] : aud;
    if (audValue !== LEO_WIDGET_AUDIENCE) {
      throw new WidgetTokenError(
        `refusing token with aud='${String(audValue)}', expected '${LEO_WIDGET_AUDIENCE}'`,
      );
    }
    const iat = _requireNumber(payload, "iat");
    const exp = _requireNumber(payload, "exp");
    const remaining = exp - Math.floor(this._now() / 1000);
    if (remaining > LEO_WIDGET_MAX_TTL_SECONDS) {
      throw new WidgetTokenError(
        `refusing token whose remaining TTL (${remaining}s) exceeds the 900s ceiling`,
      );
    }
    if (remaining <= 0) {
      throw new WidgetTokenError("widget token is already expired");
    }
    const claims: WidgetClaims = {
      sub: _requireString(payload, "sub"),
      tenant_id: _requireString(payload, "tenant_id"),
      assessment_id: _requireString(payload, "assessment_id"),
      user_role: _requireString(payload, "user_role"),
      scope: _requireString(payload, "scope"),
      aud: LEO_WIDGET_AUDIENCE,
      iat,
      exp,
      jti: _requireString(payload, "jti"),
    };
    this._token = token;
    this._claims = claims;
    return claims;
  }

  get token(): string | null {
    return this._token;
  }

  get claims(): WidgetClaims | null {
    return this._claims;
  }

  clear(): void {
    this._token = null;
    this._claims = null;
  }
}
