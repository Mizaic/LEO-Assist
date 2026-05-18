/**
 * VT-4081E44C - Widget rejects bad-aud and over-TTL widget tokens.
 *
 * Atlas trace:
 *   DO: DO-5C88CA8F
 *   DI: DI-A1206416 AC1: "Widget rejects any token without aud=widget
 *       or with a TTL beyond 15 minutes."
 *
 * Drives WidgetTokenHolder against four representative payloads and
 * asserts no localStorage / sessionStorage / cookie writes occur
 * during parse().
 */

import {
  LEO_WIDGET_AUDIENCE,
  LEO_WIDGET_MAX_TTL_SECONDS,
  WidgetTokenError,
  WidgetTokenHolder,
} from "../auth/widget_token";

const FIXED_NOW_MS = 1_700_000_000_000;
const NOW_S = Math.floor(FIXED_NOW_MS / 1000);

function _b64url(value: string): string {
  return Buffer.from(value, "utf-8")
    .toString("base64")
    .replace(/=+$/, "")
    .replace(/\+/g, "-")
    .replace(/\//g, "_");
}

function _makeJwt(claims: Record<string, unknown>): string {
  const header = _b64url(JSON.stringify({ alg: "HS256", typ: "JWT" }));
  const body = _b64url(JSON.stringify(claims));
  return `${header}.${body}.signature-not-checked-by-widget`;
}

function _validClaims(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    aud: LEO_WIDGET_AUDIENCE,
    iss: "leo-core-api",
    sub: "host-user-001",
    tenant_id: "tenant-A",
    assessment_id: "ASSESS-1",
    user_role: "clinician",
    scope: "sbar.read:assessment:ASSESS-1",
    iat: NOW_S,
    exp: NOW_S + LEO_WIDGET_MAX_TTL_SECONDS,
    jti: "abc123",
    ...overrides,
  };
}

describe("WidgetTokenHolder.parse - DI-A1206416 AC1", () => {
  let holder: WidgetTokenHolder;

  beforeEach(() => {
    holder = new WidgetTokenHolder(() => FIXED_NOW_MS);
  });

  test("AC1.a accepts a valid leo-widget token within the 15-minute ceiling", () => {
    const claims = holder.parse(_makeJwt(_validClaims()));
    expect(claims.aud).toBe(LEO_WIDGET_AUDIENCE);
    expect(claims.assessment_id).toBe("ASSESS-1");
    expect(claims.tenant_id).toBe("tenant-A");
    expect(holder.token).not.toBeNull();
  });

  test("AC1.b rejects a token whose aud is not 'leo-widget'", () => {
    const token = _makeJwt(_validClaims({ aud: "leo-api" }));
    expect(() => holder.parse(token)).toThrow(WidgetTokenError);
    expect(() => holder.parse(token)).toThrow(/aud='leo-api'/);
    expect(holder.token).toBeNull();
  });

  test("AC1.c rejects a token whose remaining TTL exceeds 900 seconds", () => {
    const token = _makeJwt(_validClaims({ exp: NOW_S + 1800 }));
    expect(() => holder.parse(token)).toThrow(WidgetTokenError);
    expect(() => holder.parse(token)).toThrow(/exceeds the 900s ceiling/);
    expect(holder.token).toBeNull();
  });

  test("AC1.d rejects a token that is already expired", () => {
    const token = _makeJwt(_validClaims({ exp: NOW_S - 10 }));
    expect(() => holder.parse(token)).toThrow(WidgetTokenError);
    expect(() => holder.parse(token)).toThrow(/already expired/);
    expect(holder.token).toBeNull();
  });

  test("AC1.e never writes to localStorage / sessionStorage / cookie", () => {
    const localSetSpy = jest.spyOn(window.localStorage.__proto__, "setItem");
    const sessionSetSpy = jest.spyOn(window.sessionStorage.__proto__, "setItem");
    const cookieSetSpy = jest.fn();
    Object.defineProperty(document, "cookie", {
      configurable: true,
      get: () => "",
      set: cookieSetSpy,
    });

    holder.parse(_makeJwt(_validClaims()));

    expect(localSetSpy).not.toHaveBeenCalled();
    expect(sessionSetSpy).not.toHaveBeenCalled();
    expect(cookieSetSpy).not.toHaveBeenCalled();

    localSetSpy.mockRestore();
    sessionSetSpy.mockRestore();
  });
});
