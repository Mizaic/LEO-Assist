/**
 * Static-source verification tests for the 2026-04-20 security remediation.
 *
 * Covers:
 *   - Phase 2 / H11: auth callback open-redirect / XSS guard
 *   - Phase 3 / M1:  mail iframe sanitisation + sandbox tightening
 *
 * Atlas trace: VTs under DI-PLATFORM-SECURITY-BASELINE-2026-04.
 */

import fs from "fs";
import path from "path";

const ROOT = path.resolve(__dirname, "../../../..");

function readSource(rel: string): string {
  return fs.readFileSync(path.join(ROOT, rel), "utf-8");
}

// ---------------------------------------------------------------------------
// Phase 2 / H11 -- auth callback redirect hardening
// ---------------------------------------------------------------------------

describe("phase2-h11: auth callback redirect hardening", () => {
  const source = readSource("services/ui/src/app/auth/callback/route.ts");

  it("defines a _safeStatePath helper", () => {
    expect(source).toContain("function _safeStatePath(");
  });

  it("defines a _safeDestination helper", () => {
    expect(source).toContain("function _safeDestination(");
  });

  it("rejects absolute URLs in state", () => {
    // Look for the absolute-URL detection regex in source.
    expect(source).toMatch(/\^\[a-z\]\[a-z0-9\+\.-\]\*:/);
  });

  it("rejects protocol-relative URLs", () => {
    expect(source).toMatch(/startsWith\("\/\/"\)/);
    expect(source).toMatch(/startsWith\("\\\\\\\\"\)/);
  });

  it("validates upstream Location header against the UI origin", () => {
    expect(source).toContain("url.origin === origin");
  });

  it("falls back to /care/dashboard for unsafe state values", () => {
    expect(source).toContain('"/care/dashboard"');
  });

  it("limits dev-only relaxed origin check to non-production", () => {
    expect(source).toContain('process.env.NODE_ENV !== "production"');
  });
});

// ---------------------------------------------------------------------------
// Phase 3 / M1 -- mail iframe sanitisation + sandbox
// ---------------------------------------------------------------------------

describe("phase3-m1: mail iframe sanitisation", () => {
  const source = readSource("services/ui/src/app/mail/page.tsx");

  it("imports DOMPurify", () => {
    expect(source).toContain('import DOMPurify from "dompurify"');
  });

  it("sanitises body_html before rendering in the iframe", () => {
    expect(source).toContain("DOMPurify.sanitize(selected.body_html");
  });

  it("passes only sanitised HTML into the iframe via srcDoc", () => {
    expect(source).toContain("srcDoc={safeHtml}");
    expect(source).not.toMatch(/srcDoc=\{[^}]*body_html/);
    expect(source).not.toContain("doc.write");
  });

  it("strips dangerous tags via the FORBID_TAGS option", () => {
    expect(source).toContain("FORBID_TAGS");
    expect(source).toMatch(/script[\s\S]*iframe[\s\S]*form/);
  });

  it("uses an empty sandbox attribute (no allow-* flags)", () => {
    expect(source).toContain('sandbox=""');
    expect(source).not.toContain('sandbox="allow-same-origin"');
  });

  it("sets referrerPolicy=no-referrer on the iframe", () => {
    expect(source).toContain('referrerPolicy="no-referrer"');
  });
});

// ---------------------------------------------------------------------------
// Sanity check: dompurify is in the package.json
// ---------------------------------------------------------------------------

describe("dompurify dependency", () => {
  it("is listed in services/ui/package.json", () => {
    const pkg = JSON.parse(readSource("services/ui/package.json"));
    expect(pkg.dependencies).toHaveProperty("dompurify");
  });
});
