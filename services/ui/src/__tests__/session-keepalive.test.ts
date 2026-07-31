/**
 * VT-AA19233B -- session idle slide / UI keepalive chrome.
 *
 * Static-source verification:
 *   - useSessionKeepalive interval helpers clamp half-idle window
 *   - AuthProvider wires keepalive when authenticated
 *
 * Design Controls: DI-8A96990F, DO-F7C82FB5, VT-AA19233B.
 */

import * as fs from "fs";
import * as path from "path";

import { keepaliveIntervalMs } from "@/lib/useSessionKeepalive";

const UI_ROOT = path.resolve(__dirname, "../..");

function readFile(relPath: string): string {
  return fs.readFileSync(path.join(UI_ROOT, relPath), "utf8");
}

describe("VT-AA19233B - session keepalive chrome", () => {
  test("TC-001: half idle window clamped between 1 and 10 minutes", () => {
    expect(keepaliveIntervalMs(30)).toBe(10 * 60_000);
    expect(keepaliveIntervalMs(4)).toBe(2 * 60_000);
    expect(keepaliveIntervalMs(1)).toBe(60_000);
    expect(keepaliveIntervalMs(0)).toBe(5 * 60_000);
  });

  test("TC-002: AuthProvider wires useSessionKeepalive when authenticated", () => {
    const src = readFile("src/lib/authContext.tsx");
    expect(src).toMatch(/useSessionKeepalive/);
    expect(src).toMatch(/status\s*===\s*["']authenticated["']/);
    expect(src).toMatch(/idleTimeoutMinutes/);
  });

  test("TC-003: keepalive fetches /auth/session with credentials", () => {
    const src = readFile("src/lib/useSessionKeepalive.ts");
    expect(src).toMatch(/\/auth\/session/);
    expect(src).toMatch(/credentials:\s*["']include["']/);
    expect(src).toMatch(/visibilityState/);
  });
});
